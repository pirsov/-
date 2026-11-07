"""
Quality Forge orchestrator.

Mechanic: long-horizon multi-pass game creation with:
  - APPEND that actually appends (never silent overwrite)
  - DONE requires validated FILE when task targets a path
  - snapshots + rollback on validator failure
  - validator feedback injected into retries
  - model escalation after repeated failures
  - auto-decomposition of failed tasks into micro-steps
  - integrity gate between phases
  - unattended loop with heartbeat (week-long runs)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import llm
from .prompts import (
    AGENT_MODELS,
    ESCALATION,
    FALLBACK_ANY,
    OPENROUTER_CFG,
    SPACEBUNNY_CFG,
    WEEK_MODE,
    build_prompt,
)
from .task_parser import Task, WriteMode, find_pending_tasks, parse_task_line
from .validator import validate_file, validate_project_integrity


ROOT_DEFAULT = Path(__file__).resolve().parent.parent
_INSTALLED_CACHE: Optional[List[str]] = None


@dataclass
class FileOp:
    path: str
    content: str
    mode: WriteMode


@dataclass
class StepResult:
    ok: bool
    task_id: str
    note: str = ""
    reason: str = ""
    files: List[str] = field(default_factory=list)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def now_human() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_dirs(root: Path) -> None:
    (root / "logs").mkdir(exist_ok=True)
    (root / ".forge" / "snapshots").mkdir(parents=True, exist_ok=True)
    (root / ".forge" / "state").mkdir(parents=True, exist_ok=True)


def snapshot_file(root: Path, rel: str) -> Optional[Path]:
    src = root / rel
    if not src.is_file():
        return None
    dest = root / ".forge" / "snapshots" / rel.replace("/", "__")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def restore_snapshot(root: Path, rel: str) -> bool:
    snap = root / ".forge" / "snapshots" / rel.replace("/", "__")
    dest = root / rel
    if snap.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snap, dest)
        return True
    # No prior version — remove the failed write so keep/seed can recover
    if dest.is_file():
        try:
            dest.unlink()
            print(f"   removed failed write (no snapshot): {rel}")
        except OSError as e:
            print(f"   could not remove failed write {rel}: {e}")
    return False


# Literal placeholders models copy from the prompt template
_BAD_PATHS = {
    "relative/path.ext",
    "path.ext",
    "relative/path",
    "...",
    "your/path.ext",
    "file.ext",
}


def is_placeholder_path(path: str) -> bool:
    p = path.replace("\\", "/").strip().lower()
    if p in _BAD_PATHS:
        return True
    if p.endswith("/path.ext") or p == "path.ext":
        return True
    if set(p) <= {".", "/", "\\", " "}:
        return True
    return False


KNOWN_SEEDS = {
    "src/server/Gameplay/Coins.server.luau": "src/server/Gameplay/Coins.server.luau",
    "src/shared/Gameplay/Remotes.luau": "src/shared/Gameplay/Remotes.luau",
    "src/shared/Content/LevelConfig.luau": "src/shared/Content/LevelConfig.luau",
    "src/server/Level/Generator.server.luau": "src/server/Level/Generator.server.luau",
    "src/server/Gameplay/Void.server.luau": "src/server/Gameplay/Void.server.luau",
    "src/server/Gameplay/Puzzles.server.luau": "src/server/Gameplay/Puzzles.server.luau",
    "src/server/Gameplay/Checkpoints.server.luau": "src/server/Gameplay/Checkpoints.server.luau",
    "src/client/HUD.client.luau": "src/client/HUD.client.luau",
    "src/client/Effects.client.luau": "src/client/Effects.client.luau",
    "src/server/Data/PlayerData.server.luau": "src/server/Data/PlayerData.server.luau",
    "docs/QA_REPORT.md": "docs/QA_REPORT.seed.md",
}


def parse_agent_output(text: str, expected_id: str) -> Tuple[Optional[str], str, List[FileOp], Optional[str]]:
    """Returns (done_id, note, files, blocked_id)."""
    blocked = re.search(r"<BLOCKED>\s*([PW]\d+(?:\.\d+)*)\s*</BLOCKED>", text)
    if blocked:
        return None, "", [], blocked.group(1)

    done = re.search(r"<(?:DONE|SUCCESS)>\s*([PW]\d+(?:\.\d+)*)\s*</(?:DONE|SUCCESS)>", text)
    if not done:
        return None, "", [], None
    done_id = done.group(1)
    note_m = re.search(r"<NOTE>([\s\S]*?)</NOTE>", text)
    note = note_m.group(1).strip() if note_m else ""
    files: List[FileOp] = []
    for m in re.finditer(r'<FILE\s+path="([^"]+)">\r?\n?([\s\S]*?)</FILE>', text):
        raw_path = m.group(1).strip()
        content = m.group(2).strip("\r\n")
        mode = WriteMode.REWRITE
        path = raw_path
        if "#" in raw_path:
            path = raw_path.split("#", 1)[0]
            mode = WriteMode.APPEND
        files.append(FileOp(path=path, content=content, mode=mode))
    return done_id, note, files, None


def apply_file_ops(root: Path, ops: List[FileOp], task: Task) -> List[str]:
    written: List[str] = []
    for op in ops:
        path = op.path.replace("\\", "/").strip()
        if is_placeholder_path(path):
            if task.target_path:
                print(f"   remap placeholder path {path!r} -> {task.target_path}")
                path = task.target_path
            else:
                print(f"   skip placeholder path: {path}")
                continue
        # Windows-illegal / junk
        if re.search(r"[<>:\"|?*]|/\.\./|\\\.\.\\", path) or path.endswith("..."):
            print(f"   skip illegal path: {path}")
            continue
        path = re.sub(r'[<>:"|?*]', "_", path)
        leaf = Path(path).name
        if path.endswith("/") or path.endswith("\\") or "." not in leaf:
            print(f"   skip directory-like path: {path}")
            continue
        # Single-target tasks: never write anywhere else
        if task.target_path and path != task.target_path.replace("\\", "/"):
            print(f"   coerce path {path} -> {task.target_path}")
            path = task.target_path.replace("\\", "/")

        mode = task.mode if task.mode != WriteMode.UNKNOWN else op.mode
        if task.section or task.mode == WriteMode.APPEND:
            mode = WriteMode.APPEND
        if task.mode in {WriteMode.REWRITE, WriteMode.CREATE}:
            mode = task.mode

        full = root / path
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"   skip mkdir failed for {path}: {e}")
            continue
        snapshot_file(root, path)

        try:
            if mode == WriteMode.APPEND and full.is_file():
                existing = full.read_text(encoding="utf-8")
                if op.content.strip() and op.content.strip() in existing:
                    print(f"   skip duplicate append {path}")
                else:
                    sep = "" if existing.endswith("\n") or not existing else "\n"
                    full.write_text(
                        existing + sep + op.content + ("\n" if not op.content.endswith("\n") else ""),
                        encoding="utf-8",
                    )
                    print(f"   appended {path}")
            else:
                if full.is_dir():
                    # Never rmtree placeholder-like or non-empty project roots
                    if is_placeholder_path(path) or path in {".", "..", "..."}:
                        print(f"   refuse to rmtree: {path}")
                        continue
                    try:
                        shutil.rmtree(full)
                    except OSError as e:
                        print(f"   rmtree failed {path}: {e} — skip write")
                        continue
                full.write_text(
                    op.content if op.content.endswith("\n") else op.content + "\n",
                    encoding="utf-8",
                )
                print(f"   wrote {path}")
            if path not in written:
                written.append(path)
        except OSError as e:
            print(f"   write failed {path}: {e}")
            continue
    return written


def mark_tz_done(root: Path, task_id: str, note: str) -> None:
    tz_path = root / "PROJECT_TZ.md"
    lines = tz_path.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(rf"^- \[ \] {re.escape(task_id)} ", line):
            out.append(re.sub(r"^- \[ \]", "- [x]", line))
            out.append(f"  - DONE {now_human()} | {note}")
            # bump LAST_UPDATE header if present
            i += 1
            continue
        out.append(line)
        i += 1
    if out and out[0].startswith("# LAST_UPDATE:"):
        out[0] = f"# LAST_UPDATE: {now_human()}"
    else:
        out.insert(0, f"# LAST_UPDATE: {now_human()}")
    tz_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def add_tz_note(root: Path, task_id: str, kind: str, text: str) -> None:
    tz_path = root / "PROJECT_TZ.md"
    lines = tz_path.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        if re.match(rf"^- \[ \] {re.escape(task_id)} ", line):
            out.append(f"  - {kind} {now_human()} | {text}")
    tz_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def insert_micro_tasks(root: Path, after_id: str, micro: List[str]) -> None:
    """Insert auto-decomposed micro-tasks after a failing task line."""
    tz_path = root / "PROJECT_TZ.md"
    lines = tz_path.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    for line in lines:
        out.append(line)
        if re.match(rf"^- \[.?\] {re.escape(after_id)} ", line):
            out.append("  - AUTO-DECOMPOSE | generated micro-tasks below")
            out.extend(micro)
    tz_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def decompose_task(task: Task) -> List[str]:
    """Heuristic split of a failed task into smaller APPEND/CREATE steps."""
    path = task.target_path or "src/unknown.luau"
    tid = task.task_id
    owner = task.owner
    if path.endswith(".luau"):
        return [
            f"- [ ] {tid}.a | Create {path} with exactly: --!strict | @{owner} | → {path}",
            f"- [ ] {tid}.b | APPEND services/imports only for: {task.description[:80]} | @{owner} | → {path}",
            f"- [ ] {tid}.c | APPEND core logic only for: {task.description[:80]} | @{owner} | → {path}",
            f"- [ ] {tid}.d | APPEND wiring/connections only; no top-level return if .server/.client | @{owner} | → {path}",
        ]
    return [
        f"- [ ] {tid}.a | Write first half of: {task.description[:100]} | @{owner} | → {path}",
        f"- [ ] {tid}.b | APPEND second half of: {task.description[:100]} | @{owner} | → {path}",
    ]


def write_heartbeat(root: Path, payload: dict) -> None:
    p = root / ".forge" / "state" / "heartbeat.json"
    payload = {**payload, "ts": datetime.now(timezone.utc).isoformat()}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def quality_score(root: Path) -> Tuple[int, List[str]]:
    """0-100 score used as phase gate."""
    ok, errs = validate_project_integrity(root)
    score = 100
    notes: List[str] = []
    if not ok:
        score -= min(80, 15 * len(errs))
        notes.extend(errs[:10])
    # reward presence of docs
    for rel in ("docs/GDD.md", "docs/ARCHITECTURE.md", "docs/QA_REPORT.md", "docs/RELEASE.md"):
        if not (root / rel).exists():
            score -= 5
            notes.append(f"missing {rel}")
    return max(0, score), notes


def installed_models(force: bool = False) -> List[str]:
    global _INSTALLED_CACHE
    if force or _INSTALLED_CACHE is None:
        _INSTALLED_CACHE = llm.list_models()
    return list(_INSTALLED_CACHE or [])


def pick_model(owner: str, attempt: int, escalate: bool) -> dict:
    be = llm.backend_name()
    if be == "spacebunny":
        cfg = SPACEBUNNY_CFG or {}
        return {
            "model": cfg.get("model") or "space-bunny-alpha",
            "ctx": int(cfg.get("ctx") or 1_000_000),
            "predict": int(cfg.get("predict") or 8192),
        }
    if be == "openrouter":
        cfg = OPENROUTER_CFG or {}
        return {
            "model": cfg.get("model") or "stealth/space-bunny-alpha",
            "ctx": int(cfg.get("ctx") or 1_000_000),
            "predict": int(cfg.get("predict") or 8192),
        }

    base = dict(AGENT_MODELS.get(owner, AGENT_MODELS["refactorer"]))
    preferred = base["model"]
    if escalate and attempt >= 2:
        idx = min(attempt - 1, len(ESCALATION) - 1)
        preferred = ESCALATION[idx]
        base["predict"] = max(base.get("predict", 2048), 4096)

    installed = installed_models()
    resolved = llm.resolve_model(preferred, installed, allow_any=FALLBACK_ANY)
    if resolved:
        if resolved != preferred:
            print(f"   model remap: {preferred} -> {resolved}")
        base["model"] = resolved
    else:
        base["model"] = preferred
    return base


def doctor(root: Path) -> int:
    print("Quality Forge doctor")
    print(f"  root: {root}")
    be = llm.backend_name()
    print(f"  backend: {be}")
    if be == "spacebunny":
        key = bool(os.environ.get("SPACE_BUNNY_API_KEY"))
        print(f"  SPACE_BUNNY_API_KEY set: {key}")
        if not key:
            print("  FIX: https://spacebunnymodel.com/get-jev  then set SPACE_BUNNY_API_KEY")
            return 1
        print("  model: space-bunny-alpha (1M ctx)")
        print("  Ready. Run: python run.py --week")
        return 0
    if be == "openrouter":
        key = bool(os.environ.get("OPENROUTER_API_KEY"))
        print(f"  OPENROUTER_API_KEY set: {key}")
        if not key:
            print("  FIX: set OPENROUTER_API_KEY for stealth/space-bunny-alpha")
            return 1
        print("  model: stealth/space-bunny-alpha")
        print("  Ready. Run: python run.py --week")
        return 0

    ok_ping = llm.ping()
    print(f"  ollama reachable: {ok_ping}")
    if not ok_ping:
        print("  FIX: start Ollama, OR set SPACE_BUNNY_API_KEY for Space Bunny backend")
        return 1
    installed = installed_models(force=True)
    print(f"  installed models ({len(installed)}):")
    for n in installed:
        print(f"    - {n}")
    if not installed:
        print("  FIX: ollama pull qwen2.5-coder:14b-4k  OR  use Space Bunny")
        return 1
    print("  role → resolved model:")
    for role, cfg in sorted(AGENT_MODELS.items()):
        pref = cfg["model"]
        got = llm.resolve_model(pref, installed, allow_any=FALLBACK_ANY)
        print(f"    @{role}: {pref} -> {got or '?'} [{'OK' if got else 'MISSING'}]")
    print("  Ready. Run: python run.py --week")
    return 0


class Orchestrator:
    def __init__(
        self,
        root: Path,
        *,
        dry_run: bool = False,
        mock_responses: Optional[Dict[str, List[str]]] = None,
    ):
        self.root = root
        self.dry_run = dry_run
        self.mock_responses = mock_responses or {}
        self._mock_idx: Dict[str, int] = {}
        ensure_dirs(root)

    def next_task(self) -> Optional[Task]:
        tz = (self.root / "PROJECT_TZ.md").read_text(encoding="utf-8")
        pending = find_pending_tasks(tz)
        return pending[0] if pending else None

    def _call_model(self, task: Task, prompt: str, cfg: dict, attempt: int, temp: float) -> str:
        key = task.task_id
        if key in self.mock_responses:
            idx = self._mock_idx.get(key, 0)
            responses = self.mock_responses[key]
            out = responses[min(idx, len(responses) - 1)]
            self._mock_idx[key] = idx + 1
            return out
        if self.dry_run:
            return ""
        return llm.generate(
            cfg["model"],
            prompt,
            num_ctx=cfg["ctx"],
            temperature=temp,
            num_predict=cfg["predict"],
        )

    def invoke_step(self) -> StepResult:
        task = self.next_task()
        if not task:
            print("=== No more actionable tasks. ===")
            score, notes = quality_score(self.root)
            write_heartbeat(self.root, {"status": "idle", "quality_score": score, "notes": notes})
            print(f"Quality score: {score}/100")
            if notes:
                for n in notes[:8]:
                    print(f"  - {n}")
            return StepResult(ok=False, task_id="", reason="no_tasks")

        if task.owner == "human":
            print(f"HITL: {task.task_id} needs human action.")
            print(f"   Edit PROJECT_TZ.md, change '- [ ] {task.task_id}' to '- [x]', then re-run.")
            write_heartbeat(self.root, {"status": "waiting_human", "task": task.task_id})
            return StepResult(ok=False, task_id=task.task_id, reason="human")

        print(f"[{task.task_id}] -> @{task.owner}  mode={task.mode.value}")
        write_heartbeat(self.root, {"status": "running", "task": task.task_id, "owner": task.owner})

        max_attempts = 3
        validator_feedback = None
        stamp = now_stamp()
        logs = self.root / "logs"

        for attempt in range(1, max_attempts + 1):
            cfg = pick_model(task.owner, attempt, escalate=True)
            print(f"   attempt {attempt}/{max_attempts} model={cfg['model']} predict={cfg['predict']}")
            prior = None
            if task.target_path and (self.root / task.target_path).is_file():
                prior = (self.root / task.target_path).read_text(encoding="utf-8")

            prompt = build_prompt(
                self.root,
                task.owner,
                task,
                attempt=attempt,
                validator_feedback=validator_feedback,
                prior_snapshot=prior,
            )
            (logs / f"{stamp}-{task.task_id}-prompt.txt").write_text(prompt, encoding="utf-8")

            temp = 0.1 if attempt == 1 else 0.0
            try:
                out = self._call_model(task, prompt, cfg, attempt, temp)
            except Exception as e:
                print(f"   API abort: {e}")
                validator_feedback = f"API error: {e}"
                continue

            (logs / f"{stamp}-{task.task_id}-attempt{attempt}-response.txt").write_text(out, encoding="utf-8")

            done_id, note, file_ops, blocked = parse_agent_output(out, task.task_id)
            if blocked:
                print("   model refused (BLOCKED) - retrying")
                validator_feedback = "Do not output BLOCKED. Produce <DONE> and <FILE> now."
                continue

            if not done_id:
                print(f"   attempt {attempt}/{max_attempts} malformed (no DONE), retrying...")
                validator_feedback = "Reply MUST start with <DONE>{id}</DONE> then <NOTE> and <FILE>."
                continue

            if done_id != task.task_id:
                print(f"   model DONE {done_id}, current is {task.task_id} - retrying")
                validator_feedback = f"Wrong task id. Use <DONE>{task.task_id}</DONE>."
                continue

            # BUG FIX: require FILE when task targets a path
            if task.requires_file and not file_ops:
                print("   REJECTED: DONE without <FILE> but task requires a file write")
                validator_feedback = (
                    f"You returned DONE without <FILE>. Task requires writing {task.target_path}. "
                    "Output the file content inside <FILE path=\"...\"> tags."
                )
                continue

            # Drop prompt-template placeholders; force task target path
            if task.target_path and file_ops:
                cleaned: List[FileOp] = []
                for op in file_ops:
                    if is_placeholder_path(op.path):
                        continue
                    op.path = task.target_path
                    cleaned.append(op)
                if not cleaned and file_ops:
                    # Model only emitted placeholders — use first content at real target
                    file_ops[0].path = task.target_path
                    cleaned = [file_ops[0]]
                file_ops = cleaned

            if task.requires_file and not file_ops:
                print("   REJECTED: only placeholder FILE paths (e.g. relative/path.ext)")
                validator_feedback = (
                    f'FILE path must be exactly "{task.target_path}", '
                    "never relative/path.ext or other placeholders."
                )
                continue

            written = apply_file_ops(self.root, file_ops, task)

            # Validate each written file
            all_valid = True
            err_msgs: List[str] = []
            for rel in written:
                ok, errs = validate_file(self.root / rel)
                if ok:
                    print(f"  VALIDATOR PASS [{Path(rel).name}]")
                else:
                    print(f"  VALIDATOR FAIL [{Path(rel).name}]: {'; '.join(errs)}")
                    all_valid = False
                    err_msgs.extend(errs)
                    restore_snapshot(self.root, rel)
                    print(f"   rolled back {rel}")

            if written and not all_valid:
                validator_feedback = (
                    "Fix these validator errors:\n- "
                    + "\n- ".join(err_msgs)
                    + "\nFILE path must be the real target path, never relative/path.ext."
                    "\n*.server.luau must NOT use top-level return. Use GetService(\"Players\")."
                )
                print("   VALIDATOR REJECTED - retrying with feedback")
                continue

            if task.requires_file and not written:
                print("   REJECTED: no files written (paths skipped)")
                validator_feedback = f'Write <FILE path="{task.target_path}"> with real code.'
                continue

            # Integrity gate for gameplay files
            if any(rel.startswith("src/") for rel in written):
                iok, ierrs = validate_project_integrity(self.root)
                if not iok:
                    # soft warn unless critical missing defs
                    critical = [e for e in ierrs if "likely APPEND overwrite" in e or "missing" in e]
                    if critical and task.mode == WriteMode.APPEND:
                        validator_feedback = (
                            "APPEND corrupted file integrity:\n- "
                            + "\n- ".join(critical)
                            + "\nReturn ONLY new lines to append; do not rewrite the whole file."
                        )
                        for rel in written:
                            restore_snapshot(self.root, rel)
                        print("   INTEGRITY REJECTED append overwrite residue - retrying")
                        continue

            mark_tz_done(self.root, task.task_id, note)
            score, _ = quality_score(self.root)
            write_heartbeat(
                self.root,
                {
                    "status": "done_step",
                    "task": task.task_id,
                    "quality_score": score,
                    "files": written,
                },
            )
            print(f"   DONE: {task.task_id} - {note} (quality={score})")
            return StepResult(ok=True, task_id=task.task_id, note=note, files=written)

        # Failed after retries
        print("   AGENT FAILED after retries.")

        # Re-apply known seed if present in git tree, then keep-check
        if task.target_path and task.target_path.replace("\\", "/") in KNOWN_SEEDS:
            rel = task.target_path.replace("\\", "/")
            seed_rel = KNOWN_SEEDS[rel]
            seed_path = self.root / seed_rel
            # For Coins/Remotes/LevelConfig the "seed" IS the canonical file in repo;
            # after bad writes we may have deleted it — restore from snapshot of seed name
            # or from packaged content if file still exists in snapshots.
            snap = self.root / ".forge" / "snapshots" / rel.replace("/", "__")
            if snap.is_file() and validate_file(snap)[0]:
                (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snap, self.root / rel)
                print(f"   restored seed snapshot for {rel}")
            elif seed_path.is_file() and validate_file(seed_path)[0]:
                if seed_path.resolve() != (self.root / rel).resolve():
                    shutil.copy2(seed_path, self.root / rel)
                print(f"   using canonical seed {rel}")

        keep_candidates = []
        if task.target_path:
            keep_candidates.append(task.target_path)
        if task.owner in {"integrator", "refactorer", "gameplay_programmer"}:
            keep_candidates.extend(
                [
                    "src/shared/Gameplay/Remotes.luau",
                    "src/server/Gameplay/Checkpoints.server.luau",
                    "src/server/Gameplay/Coins.server.luau",
                    "src/shared/Content/LevelConfig.luau",
                ]
            )
        kept_ok = True
        checked = []
        for rel in dict.fromkeys(keep_candidates):
            p = self.root / rel
            if not p.is_file():
                continue
            # Only require the task target (if any) + always-ok shared files when they're the target
            if task.target_path and rel != task.target_path.replace("\\", "/"):
                if task.owner == "gameplay_programmer":
                    continue
            ok, errs = validate_file(p)
            checked.append(rel)
            if not ok:
                kept_ok = False
                print(f"   keep-check FAIL [{rel}]: {'; '.join(errs)}")
                break
        if checked and kept_ok:
            mark_tz_done(
                self.root,
                task.task_id,
                "kept existing valid files after model failures",
            )
            print(f"   KEPT existing valid file(s): {', '.join(checked)}")
            return StepResult(ok=True, task_id=task.task_id, note="kept existing", files=checked)

        # QA docs seed
        if task.owner == "qa_engineer" and task.target_path and task.target_path.endswith("QA_REPORT.md"):
            seed = self.root / "docs" / "QA_REPORT.seed.md"
            dest = self.root / task.target_path
            if seed.is_file():
                dest.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
            mark_tz_done(self.root, task.task_id, "SEEDED QA_REPORT after model failures")
            print("   SEEDED docs/QA_REPORT.md and marked done")
            return StepResult(ok=True, task_id=task.task_id, note="seeded QA", files=[task.target_path])

        # Week mode: NEVER micro-split code — skip task with note or stop
        if WEEK_MODE.get("disable_micro_split", True):
            add_tz_note(
                self.root,
                task.task_id,
                "SKIPPED",
                "week mode: model failed; seed kept / fix prompt manually",
            )
            # Mark done so the week continues past poison tasks
            mark_tz_done(self.root, task.task_id, "SKIPPED after failures (week mode, no micro-split)")
            print("   SKIPPED task (week mode) — continuing pipeline")
            write_heartbeat(self.root, {"status": "skipped", "task": task.task_id})
            return StepResult(ok=True, task_id=task.task_id, note="skipped", reason="skipped")

        add_tz_note(self.root, task.task_id, "FAILED", "see logs — fix prompt or model")
        write_heartbeat(self.root, {"status": "failed", "task": task.task_id})
        return StepResult(ok=False, task_id=task.task_id, reason="failed")


def run_loop(
    root: Path,
    *,
    max_steps: int = 1,
    sleep_s: float = 0.0,
    dry_run: bool = False,
    mock_responses: Optional[Dict[str, List[str]]] = None,
    stop_on_human: bool = True,
    validate_every: int = 0,
) -> int:
    orch = Orchestrator(root, dry_run=dry_run, mock_responses=mock_responses)
    completed = 0
    for i in range(max_steps):
        result = orch.invoke_step()
        if not result.ok:
            if result.reason in {"no_tasks", "human", "failed"}:
                break
            break
        completed += 1
        if validate_every > 0 and completed % validate_every == 0:
            ok, errs = validate_project_integrity(root)
            print(f"   [gate] validate after {completed} steps: {'OK' if ok else 'INVALID'}")
            if not ok:
                for e in errs[:8]:
                    print(f"      FAIL: {e}")
                write_heartbeat(root, {"status": "gate_failed", "errors": errs[:8]})
                print("   Stopping week loop — fix sources or git checkout seeds, then re-run.")
                break
            score, _ = quality_score(root)
            print(f"   [gate] quality_score={score}")
        if sleep_s > 0 and i + 1 < max_steps:
            time.sleep(sleep_s)
    return completed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Quality Forge — long-horizon game orchestrator")
    parser.add_argument("--loop", action="store_true", help="Process many tasks in one run")
    parser.add_argument("--week", action="store_true", help="Week mode: loop + sleep + validate gates + no micro-split")
    parser.add_argument("--max", type=int, default=None, help="Max steps (default 1, or 500 with --loop)")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds between steps (week-long pacing)")
    parser.add_argument("--root", type=str, default=str(ROOT_DEFAULT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score", action="store_true", help="Print quality score and exit")
    parser.add_argument("--validate", action="store_true", help="Validate all src files and exit")
    parser.add_argument("--doctor", action="store_true", help="Check Ollama + model tags, then exit")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    ensure_dirs(root)

    if args.doctor:
        return doctor(root)

    if args.score:
        score, notes = quality_score(root)
        print(f"Quality score: {score}/100")
        for n in notes:
            print(f"  - {n}")
        return 0 if score >= 80 else 1

    if args.validate:
        ok, errs = validate_project_integrity(root)
        for e in errs:
            print(f"FAIL: {e}")
        print("OK" if ok else "INVALID")
        return 0 if ok else 1

    week = bool(args.week)
    if week:
        max_steps = args.max if args.max is not None else 200
        sleep_s = args.sleep if args.sleep > 0 else 30.0
        validate_every = int(WEEK_MODE.get("validate_every_n_steps") or 5)
        print("Quality Forge WEEK MODE | seed-first | no micro-split | 14b code models")
    else:
        max_steps = args.max if args.max is not None else (500 if args.loop else 1)
        sleep_s = args.sleep
        validate_every = 0

    be = llm.backend_name()
    print(
        f"Quality Forge | backend={be} | root={root} | max_steps={max_steps} | "
        f"sleep={sleep_s}s | gate_every={validate_every}"
    )
    if not args.dry_run:
        if not llm.ping():
            print(f"ERROR: backend '{be}' not ready")
            print("  Ollama: start ollama serve")
            print("  Space Bunny: set SPACE_BUNNY_API_KEY (https://spacebunnymodel.com/get-jev)")
            print("  OpenRouter: set OPENROUTER_API_KEY + FORGE_BACKEND=openrouter")
            return 1
        installed = installed_models(force=True)
        print(f"Models: {', '.join(installed) if installed else '(cloud)'}")

    completed = run_loop(
        root,
        max_steps=max_steps,
        sleep_s=sleep_s,
        dry_run=args.dry_run,
        validate_every=validate_every,
    )
    print(f"Completed {completed} step(s).")
    score, notes = quality_score(root)
    print(f"Final quality score: {score}/100")
    if week:
        print("Next: if HITL, do Studio smoke, mark @human [x] in PROJECT_TZ.md, re-run --week")
    return 0


if __name__ == "__main__":
    sys.exit(main())
