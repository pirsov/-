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


# Greenfield: no packaged game seeds. Only optional QA template for failed QA writes.
KNOWN_SEEDS = {
    "docs/QA_REPORT.md": "docs/QA_REPORT.seed.md",
}


# Sprint A1/B2/Z3/G10/F1, human H1, week W1.5, legacy P30.1 / P20.20.a
_DONE_ID = r"((?:[ABHZGF]\d+)|(?:[PW]\d+(?:\.\d+)*(?:\.[a-z])?))"


def parse_agent_output(text: str, expected_id: str) -> Tuple[Optional[str], str, List[FileOp], Optional[str]]:
    """Returns (done_id, note, files, blocked_id)."""
    blocked = re.search(rf"<BLOCKED>\s*{_DONE_ID}\s*</BLOCKED>", text, re.I)
    if blocked:
        return None, "", [], blocked.group(1)

    # Accept <DONE>A1</DONE>, <SUCCESS>…, and sloppy DONE>A3 (missing '<')
    done = re.search(
        rf"(?:<(?:DONE|SUCCESS)>|(?<![\w/])DONE>)\s*{_DONE_ID}\s*(?:</(?:DONE|SUCCESS)>)?",
        text,
        re.I,
    )
    if not done:
        # Last resort: expected id appears right after DONE somewhere
        loose = re.search(
            rf"(?:DONE|SUCCESS)\s*>?\s*{re.escape(expected_id)}\b",
            text,
            re.I,
        )
        if not loose:
            return None, "", [], None
        done_id = expected_id
    else:
        done_id = done.group(1)

    note_m = re.search(r"<NOTE>([\s\S]*?)</NOTE>", text, re.I)
    note = note_m.group(1).strip() if note_m else ""
    files: List[FileOp] = []
    for m in re.finditer(r'<FILE\s+path="([^"]+)">\r?\n?([\s\S]*?)</FILE>', text, re.I):
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
    # Attempt 2+: prefer repair model (7b) — surgical patch, less VRAM than second 14b pass
    if escalate and attempt >= 2:
        from .prompts import load_model_config

        repair = dict(load_model_config().get("repair") or {})
        if repair.get("model"):
            preferred = str(repair["model"])
            base["ctx"] = int(repair.get("ctx") or base.get("ctx") or 2048)
            base["predict"] = int(repair.get("predict") or 3072)
            print(f"   repair model: {preferred} ctx={base['ctx']} predict={base['predict']}")
        else:
            idx = min(attempt - 1, len(ESCALATION) - 1)
            preferred = ESCALATION[idx]
            base["predict"] = max(int(base.get("predict", 2048)), 3072)

    # Cap predict on local Ollama so 6GB cards don't blow KV during long FILE writes
    week_cap = int(WEEK_MODE.get("max_predict_code") or 0)
    if week_cap and owner in {
        "gameplay_programmer",
        "client_programmer",
        "refactorer",
        "integrator",
        "tech_architect",
    }:
        base["predict"] = min(int(base.get("predict", 2048)), week_cap)

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
    if be in {"spacebunny", "openrouter"}:
        env_name = "SPACE_BUNNY_API_KEY" if be == "spacebunny" else "OPENROUTER_API_KEY"
        raw = os.environ.get(env_name) or ""
        key = llm._clean_key(raw)  # noqa: SLF001 — doctor needs same cleaner
        print(f"  {env_name} set: {bool(key)}  {llm._mask_key(key) if key else ''}")  # noqa: SLF001
        if not key:
            if be == "spacebunny":
                print("  FIX: https://spacebunnymodel.com/get-jev")
            else:
                print("  FIX: https://openrouter.ai/keys  (key must start with sk-or-)")
            return 1
        print(f"  model: {'space-bunny-alpha' if be == 'spacebunny' else 'stealth/space-bunny-alpha'}")
        print("  probing API…")
        ok, msg = llm.auth_probe()
        print(f"  probe: {'OK' if ok else 'FAIL'}")
        if not ok:
            print(msg)
            return 1
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


def ask_yn(prompt: str, *, default: Optional[str] = None) -> bool:
    """Ask y/n on stdin. Returns True for y, False for n. Loops until valid."""
    hint = " [y/n]"
    if default == "y":
        hint = " [Y/n]"
    elif default == "n":
        hint = " [y/N]"
    while True:
        try:
            raw = input(f"{prompt}{hint}: ").strip().lower()
        except EOFError:
            print()
            return False
        if not raw and default in {"y", "n"}:
            raw = default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("   type y or n")


def resolve_hitl_choice(*, auto: Optional[str] = None) -> Optional[bool]:
    """None = ask interactively; True/False = forced from flag/env."""
    if auto is not None:
        a = auto.strip().lower()
        if a in {"y", "yes", "1", "true"}:
            return True
        if a in {"n", "no", "0", "false"}:
            return False
    env = (os.environ.get("FORGE_HITL_AUTO") or "").strip().lower()
    if env in {"y", "yes", "1", "true"}:
        return True
    if env in {"n", "no", "0", "false"}:
        return False
    return None


class Orchestrator:
    def __init__(
        self,
        root: Path,
        *,
        dry_run: bool = False,
        mock_responses: Optional[Dict[str, List[str]]] = None,
        hitl_auto: Optional[str] = None,
    ):
        self.root = root
        self.dry_run = dry_run
        self.mock_responses = mock_responses or {}
        self.hitl_auto = hitl_auto
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

    def _handle_hitl(self, task: Task) -> StepResult:
        title = (task.description or task.raw or task.task_id).strip()
        print()
        print("=" * 60)
        print(f"HITL: {task.task_id} needs YOU")
        print(f"   {title}")
        print("   1) Open place in Studio (Rojo sync preferred)")
        print("   2) Smoke-test what the task asks")
        print("   3) Answer below")
        print("=" * 60)
        write_heartbeat(self.root, {"status": "waiting_human", "task": task.task_id})

        forced = resolve_hitl_choice(auto=self.hitl_auto)
        if forced is True:
            print("   FORGE_HITL_AUTO/y: marking done and continuing")
            confirmed = True
        elif forced is False:
            print("   FORGE_HITL_AUTO/n: stopping")
            confirmed = False
        elif self.dry_run:
            print("   dry-run: would ask [y/n] — treating as n")
            confirmed = False
        elif not sys.stdin.isatty():
            print("   stdin is not a TTY — cannot ask y/n. Re-run in a terminal, or:")
            print("     $env:FORGE_HITL_AUTO='y'   # auto-confirm")
            print("     $env:FORGE_HITL_AUTO='n'   # stop")
            confirmed = False
        else:
            confirmed = ask_yn(
                f"Studio done for {task.task_id}? Mark [x] and continue",
                default=None,
            )

        if confirmed:
            if not self.dry_run:
                mark_tz_done(self.root, task.task_id, "human confirmed via y/n prompt")
            print(f"   marked {task.task_id} done — continuing")
            write_heartbeat(self.root, {"status": "human_done", "task": task.task_id})
            return StepResult(ok=True, task_id=task.task_id, note="human ok", reason="human_ok")

        print(f"   stopped on {task.task_id}. When ready, re-run and answer y.")
        print(f"   Or manually: change '- [ ] {task.task_id}' to '- [x]' in PROJECT_TZ.md")
        return StepResult(ok=False, task_id=task.task_id, reason="human")

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
            return self._handle_hitl(task)

        print(f"[{task.task_id}] -> @{task.owner}  mode={task.mode.value}")
        write_heartbeat(self.root, {"status": "running", "task": task.task_id, "owner": task.owner})

        max_attempts = 3
        validator_feedback = None
        repair_draft: Optional[str] = None  # last rejected model body — fix in place, don't restart
        stamp = now_stamp()
        logs = self.root / "logs"

        for attempt in range(1, max_attempts + 1):
            cfg = pick_model(task.owner, attempt, escalate=True)
            print(f"   attempt {attempt}/{max_attempts} model={cfg['model']} predict={cfg['predict']}")
            prior = None
            if task.target_path and (self.root / task.target_path).is_file():
                prior = (self.root / task.target_path).read_text(encoding="utf-8")
            if repair_draft:
                print("   repair mode: fixing previous draft (not rewriting from seed)")

            prompt = build_prompt(
                self.root,
                task.owner,
                task,
                attempt=attempt,
                validator_feedback=validator_feedback,
                prior_snapshot=prior,
                repair_draft=repair_draft,
            )
            (logs / f"{stamp}-{task.task_id}-prompt.txt").write_text(prompt, encoding="utf-8")

            temp = 0.1 if attempt == 1 else 0.0
            try:
                out = self._call_model(task, prompt, cfg, attempt, temp)
            except llm.AuthError as e:
                print(f"   AUTH FAIL (no retries): {e}")
                write_heartbeat(self.root, {"status": "auth_failed", "task": task.task_id})
                return StepResult(ok=False, task_id=task.task_id, reason="auth", note=str(e))
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
            rejected_for_repair: Optional[str] = None
            for rel in written:
                ok, errs = validate_file(self.root / rel)
                if ok:
                    print(f"  VALIDATOR PASS [{Path(rel).name}]")
                else:
                    print(f"  VALIDATOR FAIL [{Path(rel).name}]: {'; '.join(errs)}")
                    all_valid = False
                    err_msgs.extend(errs)
                    # Keep the draft for the next attempt to PATCH (user's 7b→fix loop).
                    try:
                        rejected_for_repair = (self.root / rel).read_text(encoding="utf-8")
                    except OSError:
                        rejected_for_repair = None
                    restore_snapshot(self.root, rel)
                    print(f"   rolled back disk to seed; draft kept in memory for repair")

            if written and not all_valid:
                repair_draft = rejected_for_repair or repair_draft
                validator_feedback = (
                    "REPAIR your previous draft (do not start over).\n"
                    "Fix ONLY these validator errors:\n- "
                    + "\n- ".join(err_msgs)
                    + "\nKeep the rest of the file identical."
                    "\nFILE path must be the real target path, never relative/path.ext."
                    "\n*.server.luau must NOT use top-level return. Use GetService(\"Players\")."
                )
                print("   VALIDATOR REJECTED — next attempt is repair-only")
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
            # Do NOT mark TZ done — seed keep is recovery, not task completion.
            # (Old bug: "KEPT" marked A1 done while <DONE>A1</DONE> was ignored by parser.)
            add_tz_note(
                self.root,
                task.task_id,
                "RETRY",
                "model output not applied; seed kept; leave [ ] for re-run",
            )
            print(f"   KEPT seed (task still pending): {', '.join(checked)}")
            write_heartbeat(self.root, {"status": "retry", "task": task.task_id})
            return StepResult(ok=False, task_id=task.task_id, reason="retry", note="kept seed")

        # QA docs seed
        if task.owner == "qa_engineer" and task.target_path and task.target_path.endswith("QA_REPORT.md"):
            seed = self.root / "docs" / "QA_REPORT.seed.md"
            dest = self.root / task.target_path
            if seed.is_file():
                dest.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
            mark_tz_done(self.root, task.task_id, "SEEDED QA_REPORT after model failures")
            print("   SEEDED docs/QA_REPORT.md and marked done")
            return StepResult(ok=True, task_id=task.task_id, note="seeded QA", files=[task.target_path])

        # Week mode: never micro-split; leave task pending so a forge/model fix can retry
        if WEEK_MODE.get("disable_micro_split", True):
            add_tz_note(
                self.root,
                task.task_id,
                "RETRY",
                "week mode: model failed; task left [ ] — re-run --week after fix",
            )
            print("   FAILED (week mode) — task left pending; stopping loop")
            write_heartbeat(self.root, {"status": "retry", "task": task.task_id})
            return StepResult(ok=False, task_id=task.task_id, reason="retry", note="pending retry")

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
    hitl_auto: Optional[str] = None,
) -> int:
    orch = Orchestrator(
        root,
        dry_run=dry_run,
        mock_responses=mock_responses,
        hitl_auto=hitl_auto,
    )
    completed = 0
    for i in range(max_steps):
        result = orch.invoke_step()
        if not result.ok:
            if result.reason in {"no_tasks", "human", "failed", "auth", "retry"}:
                if result.reason == "retry":
                    print("   Stopping so you can fix model/parser and re-run --week (task left pending).")
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
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-answer y on HITL prompts (same as FORGE_HITL_AUTO=y)",
    )
    parser.add_argument(
        "--hitl",
        choices=["ask", "y", "n"],
        default="ask",
        help="HITL behavior: ask (default y/n), y=auto-confirm, n=stop",
    )
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

    hitl_auto: Optional[str] = None
    if args.yes:
        hitl_auto = "y"
    elif args.hitl in {"y", "n"}:
        hitl_auto = args.hitl

    completed = run_loop(
        root,
        max_steps=max_steps,
        sleep_s=sleep_s,
        dry_run=args.dry_run,
        validate_every=validate_every,
        hitl_auto=hitl_auto,
    )
    print(f"Completed {completed} step(s).")
    score, notes = quality_score(root)
    print(f"Final quality score: {score}/100")
    if week:
        print("HITL: when asked, type y after Studio smoke (or n to stop).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
