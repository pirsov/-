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
from . import state_hub
from .prompts import (
    AGENT_MODELS,
    ESCALATION,
    FALLBACK_ANY,
    OPENROUTER_CFG,
    SPACEBUNNY_CFG,
    WEEK_MODE,
    build_prompt,
    format_validator_checklist,
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
# Keep in sync with forge.task_parser._TASK_ID (P20.18, F1a, A1, …).
# Dotted P/W ids MUST come first: closing </DONE> is optional in the DONE matcher,
# so a leading [ABHZGFPRT] alt would otherwise capture only "P20" from "P20.20".
_DONE_ID = r"((?:[PW]\d+(?:\.\d+)*(?:\.[a-z])?)|(?:[ABHZGFRT]\d+[a-z]?))"


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
                        print(f"   rmtree failed {path}: {e} - skip write")
                        continue
                # A15: SEARCH/REPLACE patches when baseline exists
                from . import patch_apply

                existing = full.read_text(encoding="utf-8") if full.is_file() else None
                body, how = patch_apply.materialize_file_content(existing, op.content)
                full.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
                print(f"   wrote {path}" + (" (patch)" if how == "patch" else ""))
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


def mark_tz_failed_repair(root: Path, task_id: str, note: str) -> None:
    """Park a failed week task as [-] so find_pending_tasks skips it and the loop continues."""
    tz_path = root / "PROJECT_TZ.md"
    lines = tz_path.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    for line in lines:
        if re.match(rf"^- \[ \] {re.escape(task_id)} ", line):
            out.append(re.sub(r"^- \[ \]", "- [-]", line))
            out.append(f"  - FAILED_REPAIR {now_human()} | {note}")
        else:
            out.append(line)
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


EXPECTED_GAME_FILES = (
    "src/shared/Gameplay/Remotes.luau",
    "src/server/InitRemotes.server.luau",
    "src/shared/Content/LevelConfig.luau",
    "src/server/Level/Generator.server.luau",
    "src/server/Gameplay/Checkpoints.server.luau",
    "src/server/Gameplay/Coins.server.luau",
    "src/server/Gameplay/Void.server.luau",
    "src/server/Gameplay/Puzzles.server.luau",
    "src/server/Data/PlayerData.server.luau",
    "src/client/HUD.client.luau",
    "src/client/Effects.client.luau",
)


def quality_score(root: Path) -> Tuple[int, List[str]]:
    """0-100 score used as phase gate."""
    ok, errs = validate_project_integrity(root)
    score = 100
    notes: List[str] = []
    if not ok:
        score -= min(80, 15 * len(errs))
        notes.extend(errs[:10])
    for rel in EXPECTED_GAME_FILES:
        if not (root / rel).is_file():
            score -= 5
            notes.append(f"missing {rel}")
    for rel in ("docs/GDD.md", "docs/QA_REPORT.md"):
        if not (root / rel).exists():
            score -= 3
            notes.append(f"missing {rel}")
    return max(0, score), notes


def write_eval_report(root: Path) -> Path:
    """Post-run assessment → docs/AGENT_RUN_REPORT.md"""
    from .task_parser import find_pending_tasks

    lines: List[str] = []
    lines.append(f"# Agent run report")
    lines.append(f"")
    lines.append(f"- When: {now_human()}")
    lines.append(f"- Backend: `{llm.backend_name()}`")
    lines.append(f"- Root: `{root}`")
    lines.append("")

    tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8") if (root / "PROJECT_TZ.md").is_file() else ""
    pending = find_pending_tasks(tz) if tz else []
    done_n = len(re.findall(r"^- \[x\]", tz, re.M))
    open_n = len(re.findall(r"^- \[ \]", tz, re.M))
    lines.append("## TZ progress")
    lines.append(f"- Done checkboxes: **{done_n}**")
    lines.append(f"- Open checkboxes: **{open_n}**")
    if pending:
        lines.append(f"- Next pending: `{pending[0].task_id}` @{pending[0].owner}")
    else:
        lines.append("- Next pending: _(none)_")
    lines.append("")

    score, notes = quality_score(root)
    ok, errs = validate_project_integrity(root)
    lines.append("## Scores")
    lines.append(f"- Quality score: **{score}/100**")
    lines.append(f"- Integrity: **{'OK' if ok else 'FAIL'}** ({len(errs)} issues)")
    lines.append("")

    lines.append("## Expected game files")
    lines.append("| File | Present | Validator |")
    lines.append("|------|---------|-----------|")
    for rel in EXPECTED_GAME_FILES:
        p = root / rel
        if not p.is_file():
            lines.append(f"| `{rel}` | NO | — |")
            continue
        vok, verrs = validate_file(p)
        mark = "PASS" if vok else "FAIL: " + "; ".join(verrs[:2])
        lines.append(f"| `{rel}` | YES | {mark} |")
    lines.append("")

    if notes:
        lines.append("## Score notes")
        for n in notes[:20]:
            lines.append(f"- {n}")
        lines.append("")
    if errs:
        lines.append("## Integrity errors")
        for e in errs[:20]:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("## Verdict")
    if score >= 80 and ok and not pending:
        lines.append("**Ship-ready for Studio smoke** — run H* gates if any left, then playtest.")
    elif score >= 60 and ok:
        lines.append("**Playable skeleton** — finish pending TZ / human gates; re-run `--eval`.")
    else:
        lines.append("**Not ready** — fix FAIL files via new TZ tasks or `--week` repair; re-run `--eval`.")
    lines.append("")

    out = root / "docs" / "AGENT_RUN_REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


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
    is_7b = False
    # Attempt 2+: prefer repair model (7b) — surgical patch, less VRAM than second 14b pass
    if escalate and attempt >= 2:
        from .prompts import load_model_config

        repair = dict(load_model_config().get("repair") or {})
        if repair.get("model"):
            preferred = str(repair["model"])
            is_7b = True
            base["ctx"] = int(repair.get("ctx") or base.get("ctx") or 2048)
            base["predict"] = int(repair.get("predict") or 512)
            print(f"   repair model: {preferred} ctx={base['ctx']} predict={base['predict']}")
        else:
            idx = min(attempt - 1, len(ESCALATION) - 1)
            preferred = ESCALATION[idx]
            base["predict"] = max(int(base.get("predict", 1024)), 1024)

    # Cap predict on local Ollama so 6GB cards don't blow KV during long FILE writes
    week_cap = int(WEEK_MODE.get("max_predict_code") or 0)
    if week_cap and owner in {
        "gameplay_programmer",
        "client_programmer",
        "refactorer",
        "integrator",
        "tech_architect",
    }:
        base["predict"] = min(int(base.get("predict", 1024)), week_cap)

    # A15/A17: hard Ollama output + ctx ceilings (diff/repair tighter; num_ctx=2048)
    try:
        from . import llm_backends

        diff_mode = escalate and attempt >= 2
        base["predict"] = llm_backends.cap_num_predict(
            int(base.get("predict") or llm_backends.DEFAULT_NUM_PREDICT),
            diff_mode=diff_mode,
        )
        base["ctx"] = llm_backends.cap_num_ctx(int(base.get("ctx") or llm_backends.LOCAL_NUM_CTX))
        base["diff_mode"] = diff_mode
        base["is_7b"] = is_7b or ("7b" in str(preferred).lower())
        base["prompt_budget_tokens"] = llm_backends.effective_prompt_token_budget(
            is_7b=bool(base["is_7b"]),
            num_ctx=int(base["ctx"]),
            num_predict=int(base["predict"]),
            diff_mode=diff_mode,
        )
    except Exception:
        base["ctx"] = min(int(base.get("ctx") or 2048), 2048)
        base["is_7b"] = is_7b
        base["prompt_budget_tokens"] = 1000 if is_7b else 2000

    installed = installed_models()
    resolved = llm.resolve_model(preferred, installed, allow_any=FALLBACK_ANY)
    if resolved:
        if resolved != preferred:
            print(f"   model remap: {preferred} -> {resolved}")
        base["model"] = resolved
        if "is_7b" not in base:
            base["is_7b"] = "7b" in str(resolved).lower()
    else:
        base["model"] = preferred
    return base


def doctor(root: Path) -> int:
    print("Quality Forge doctor")
    print(f"  root: {root}")
    llm.reset_runtime_backend()
    be, reason = llm.resolve_runtime_backend()
    print(f"  preferred backend_name(): {llm.backend_name()}")
    print(f"  runtime backend: {be}")
    print(f"  resolve reason: {reason}")
    if be == "stub":
        print("  STUB mode: week will skip generation and leave tasks [ ] (never closed)")
        print("  FIX optional: start ollama serve, OR set SPACE_BUNNY_API_KEY / OPENROUTER_API_KEY")
        print("  Ready (degraded). Run: python run.py --week  # will stub-skip")
        return 0
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
        print("  probing API...")
        ok, msg = llm.auth_probe()
        print(f"  probe: {'OK' if ok else 'FAIL'}")
        if not ok:
            print(msg)
            return 1
        print("  Ready. Run: python run.py --week")
        return 0

    from . import ollama_client as _ollama

    ok_ping = _ollama.ping()
    print(f"  ollama reachable: {ok_ping}")
    if not ok_ping:
        print("  (unexpected) runtime said ollama but ping failed - cascade should have stubbed")
        return 1
    installed = installed_models(force=True)
    print(f"  installed models ({len(installed)}):")
    for n in installed:
        print(f"    - {n}")
    if not installed:
        print("  FIX: ollama pull qwen2.5-coder:14b-4k  OR  use Space Bunny")
        return 1
    print("  role -> resolved model:")
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
            diff_mode=bool(cfg.get("diff_mode") or attempt >= 2),
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
            print("   dry-run: would ask [y/n] - treating as n")
            confirmed = False
        elif not sys.stdin.isatty():
            print("   stdin is not a TTY - cannot ask y/n. Re-run in a terminal, or:")
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
            print(f"   marked {task.task_id} done - continuing")
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

        # A6.1 stub: never generate, never mark TZ/plugin closed
        be, be_reason = llm.resolve_runtime_backend()
        if be == "stub" and task.task_id not in self.mock_responses and not self.dry_run:
            print(f"[STUB] Dry run: skipping code generation ({task.task_id})")
            print(f"   reason: {be_reason}")
            state_hub.record_task_status(
                self.root,
                task.task_id,
                status="failed",
                note=f"stub skip — {be_reason}",
                backend="stub",
            )
            add_tz_note(
                self.root,
                task.task_id,
                "STUB",
                "skipped generation; left [ ] — not closed",
            )
            write_heartbeat(
                self.root,
                {"status": "stub_skip", "task": task.task_id, "backend": "stub", "closed": False},
            )
            return StepResult(
                ok=False,
                task_id=task.task_id,
                reason="stub",
                note="stub skip — not closed",
            )

        max_attempts = 3
        validator_feedback = None
        repair_draft: Optional[str] = None  # last rejected model body — fix in place, don't restart
        last_validator_fails: List[str] = []
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
                is_7b=bool(cfg.get("is_7b")),
                prompt_budget_tokens=cfg.get("prompt_budget_tokens"),
                num_ctx=cfg.get("ctx"),
                num_predict=cfg.get("predict"),
            )
            # A17: second-chance hard-fit if somehow still over (never send truncating prompts)
            try:
                from . import llm_backends

                budget = int(
                    cfg.get("prompt_budget_tokens")
                    or llm_backends.effective_prompt_token_budget(
                        is_7b=bool(cfg.get("is_7b")),
                        num_ctx=int(cfg.get("ctx") or llm_backends.LOCAL_NUM_CTX),
                        num_predict=int(cfg.get("predict") or llm_backends.DEFAULT_NUM_PREDICT),
                        diff_mode=bool(cfg.get("diff_mode")),
                    )
                )
                tok = llm_backends.estimate_tokens(prompt)
                if tok > budget:
                    prompt, meta = llm_backends.fit_prompt(prompt, budget)
                    print(
                        f"   HARD_FIT prompt {meta.get('tokens_before')}->{meta.get('tokens_after')} "
                        f"tok (budget={budget}, dropped={meta.get('dropped_sections')})"
                    )
                else:
                    print(f"   prompt_tokens~{tok} / budget={budget} (num_ctx={cfg.get('ctx')})")
                llm_backends.assert_prompt_fits(prompt, budget)
            except ValueError as e:
                print(f"   HARD_FIT refuse: {e}")
                raise
            (logs / f"{stamp}-{task.task_id}-prompt.txt").write_text(prompt, encoding="utf-8")

            temp = 0.1 if attempt == 1 else 0.0
            try:
                out = self._call_model(task, prompt, cfg, attempt, temp)
            except llm.StubModeError as e:
                print(f"[STUB] Dry run: skipping code generation ({task.task_id})")
                print(f"   {e}")
                state_hub.record_task_status(
                    self.root,
                    task.task_id,
                    status="failed",
                    note=str(e),
                    backend="stub",
                )
                add_tz_note(self.root, task.task_id, "STUB", "skipped; left [ ] — not closed")
                write_heartbeat(self.root, {"status": "stub_skip", "task": task.task_id, "closed": False})
                return StepResult(ok=False, task_id=task.task_id, reason="stub", note="stub skip — not closed")
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
                last_validator_fails = list(err_msgs)
                # A18.1: skeleton routing bugs (wrong archetype / ModuleScript return on
                # *.server.luau) cannot be fixed by 7B — park failed_repair immediately.
                try:
                    from . import skeletons_hub as _skel

                    routing_fail = False
                    for rel in written:
                        if _skel.is_skeleton_routing_failure(Path(rel), err_msgs):
                            routing_fail = True
                            break
                    if routing_fail and WEEK_MODE.get("disable_micro_split", True):
                        note = (
                            "skeleton routing mismatch — not sent to 7B repair; "
                            "marked failed_repair"
                        )
                        mark_tz_failed_repair(self.root, task.task_id, note)
                        state_hub.record_failed_repair(
                            self.root,
                            task.task_id,
                            note=note,
                            target_path=task.target_path or "",
                            validator_fails=last_validator_fails,
                        )
                        print(
                            "   SKELETON ROUTING FAIL - skip 7B repair -> failed_repair"
                        )
                        for i, msg in enumerate(err_msgs, 1):
                            print(f"      {i}. {msg}")
                        write_heartbeat(
                            self.root,
                            {
                                "status": "failed_repair",
                                "task": task.task_id,
                                "continue": True,
                                "skeleton_routing": True,
                            },
                        )
                        return StepResult(
                            ok=False,
                            task_id=task.task_id,
                            reason="failed_repair",
                            note="skeleton routing → failed_repair",
                        )
                except Exception as e:
                    print(f"   warn: skeleton routing check skipped: {e}")
                validator_feedback = (
                    "REPAIR your previous draft (do not start over).\n"
                    + format_validator_checklist(err_msgs)
                    + "\nKeep the rest of the file identical."
                    "\nFILE path must be the real target path, never relative/path.ext."
                    "\n*.server.luau must NOT use top-level return. Use GetService(\"Players\")."
                    '\nCheckpoints: include Humanoid.Died / LoadCharacter and '
                    'FindFirstChild("Checkpoint"..idx) when those bullets appear above.'
                )
                print("   VALIDATOR REJECTED - next attempt is repair-only")
                print("   repair checklist:")
                for i, msg in enumerate(err_msgs, 1):
                    print(f"      {i}. {msg}")
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
            # Week mode: park as failed_repair and continue queue (do not stop 24h/--week).
            if WEEK_MODE.get("disable_micro_split", True):
                note = (
                    "model output not applied; seed kept; marked failed_repair — continue next task"
                )
                mark_tz_failed_repair(self.root, task.task_id, note)
                state_hub.record_failed_repair(
                    self.root,
                    task.task_id,
                    note=note,
                    target_path=task.target_path or "",
                    validator_fails=last_validator_fails,
                )
                print(f"   KEPT seed -> failed_repair (continuing): {', '.join(checked)}")
                write_heartbeat(
                    self.root,
                    {"status": "failed_repair", "task": task.task_id, "continue": True},
                )
                return StepResult(
                    ok=False,
                    task_id=task.task_id,
                    reason="failed_repair",
                    note="kept seed → failed_repair",
                )
            # Non-week: leave pending for manual re-run
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

        # Week mode: never micro-split; park failed_repair and CONTINUE to next queue task
        if WEEK_MODE.get("disable_micro_split", True):
            note = (
                "week mode: failed after retries — open_questions+failed_repair; continue next task"
            )
            mark_tz_failed_repair(self.root, task.task_id, note)
            state_hub.record_failed_repair(
                self.root,
                task.task_id,
                note=note,
                target_path=task.target_path or "",
                validator_fails=last_validator_fails,
            )
            print("   FAILED (week mode) - marked failed_repair; continuing to next task")
            write_heartbeat(
                self.root,
                {
                    "status": "failed_repair",
                    "task": task.task_id,
                    "continue": True,
                    "validator_fails": last_validator_fails[:12],
                },
            )
            return StepResult(
                ok=False,
                task_id=task.task_id,
                reason="failed_repair",
                note="failed_repair continue",
            )

        add_tz_note(self.root, task.task_id, "FAILED", "see logs — fix prompt or model")
        write_heartbeat(self.root, {"status": "failed", "task": task.task_id})
        return StepResult(ok=False, task_id=task.task_id, reason="failed")


def _active_project_id(root: Path) -> str:
    active = root / ".forge" / "active_project.json"
    if active.is_file():
        try:
            data = json.loads(active.read_text(encoding="utf-8"))
            pid = str((data or {}).get("id") or "").strip()
            if pid:
                return pid
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    return "game1"


def summarize_done_tasks(tz_text: str) -> str:
    """Compact summary of checkbox lines for Live Ops DeepSeek prompt."""
    lines: List[str] = []
    for line in (tz_text or "").splitlines():
        if re.match(r"^\s*- \[[ xX-]\] ", line):
            lines.append(line.strip())
    # Prefer done/failed first, then pending (usually empty when Live Ops fires)
    done = [ln for ln in lines if re.match(r"^- \[[xX-]\] ", ln)]
    pending = [ln for ln in lines if ln.startswith("- [ ] ")]
    parts = done[-40:] + pending[:20]
    return "\n".join(parts) if parts else "(no checkbox tasks yet)"


def live_ops_goal(root: Path, project_id: str) -> str:
    """Best-effort goal text for Live Ops generation."""
    meta_p = root / "projects" / project_id / "meta.json"
    if meta_p.is_file():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            for key in ("skills_auto_goal", "title", "notes", "name"):
                val = str((meta or {}).get(key) or "").strip()
                if val:
                    return val[:900]
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    tz_p = root / "PROJECT_TZ.md"
    if tz_p.is_file():
        for line in tz_p.read_text(encoding="utf-8").splitlines()[:8]:
            if line.lower().startswith("# goal:"):
                return line.split(":", 1)[-1].strip()[:900]
            if line.startswith("# LAST_UPDATE:"):
                return line.replace("# LAST_UPDATE:", "", 1).strip()[:900]
    return f"Polish and extend playable Roblox project {project_id}"


def list_existing_luau(root: Path) -> List[str]:
    src = root / "src"
    if not src.is_dir():
        return []
    return [str(p.relative_to(root)).replace("\\", "/") for p in sorted(src.rglob("*.luau"))]


def append_tz_tasks_before_human(root: Path, task_lines: List[str]) -> int:
    """Insert new AGENT checkbox lines before ## HUMAN (or append to AGENT)."""
    tz_path = root / "PROJECT_TZ.md"
    if not tz_path.is_file():
        return 0
    text = tz_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # Existing ids — skip accidental duplicates on append
    existing_ids = {
        m.group(1)
        for m in re.finditer(
            r"(?m)^\s*- \[[ xX-]\] ((?:[PW]\d+(?:\.\d+)*(?:\.[a-z])?)|(?:[ABHZGFRT]\d+[a-z]?))\b",
            text,
        )
    }
    existing_descs = {
        re.sub(r"\s+", " ", m.group(1).strip().lower())[:120]
        for m in re.finditer(
            r"(?m)^\s*- \[[ xX-]\] [A-Za-z0-9.]+\s*\|\s*(.+?)\s*\|\s*@",
            text,
        )
    }
    fresh: List[str] = []
    for raw in task_lines:
        line = raw.strip()
        if not line.startswith("- [ ] "):
            continue
        m = re.match(r"^- \[ \] ([A-Za-z0-9.]+)\s*\|\s*(.+?)\s*\|\s*@", line)
        if not m:
            continue
        tid, desc = m.group(1), re.sub(r"\s+", " ", m.group(2).strip().lower())[:120]
        if tid in existing_ids or desc in existing_descs:
            continue
        fresh.append(line)
        existing_ids.add(tid)
        existing_descs.add(desc)
    if not fresh:
        return 0

    insert_at: Optional[int] = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+HUMAN\b", ln, re.I):
            insert_at = i
            break
    block = fresh[:]
    if insert_at is None:
        # ensure AGENT section exists
        agent_at = None
        for i, ln in enumerate(lines):
            if re.match(r"^##\s+AGENT\b", ln, re.I):
                agent_at = i
                break
        if agent_at is None:
            lines.extend(["", "## AGENT", *block])
        else:
            lines.extend(["", *block])
    else:
        # blank line before HUMAN if needed
        prefix = lines[:insert_at]
        while prefix and prefix[-1].strip() == "":
            prefix.pop()
        lines = prefix + ["", *block, ""] + lines[insert_at:]

    tz_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return len(fresh)


def try_live_ops_more_tasks(root: Path) -> int:
    """Generate and append more TZ tasks. Returns count appended (0 = empty/dup)."""
    from . import deepseek

    project_id = _active_project_id(root)
    tz_text = (
        (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
        if (root / "PROJECT_TZ.md").is_file()
        else ""
    )
    goal = live_ops_goal(root, project_id)
    files = list_existing_luau(root)
    summary = summarize_done_tasks(tz_text)
    new_lines = deepseek.generate_more_tasks(
        project_id,
        goal,
        files,
        summary,
    )
    if not new_lines:
        return 0
    return append_tz_tasks_before_human(root, new_lines)


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
    gate_strict: bool = False,
    week: bool = False,
) -> int:
    orch = Orchestrator(
        root,
        dry_run=dry_run,
        mock_responses=mock_responses,
        hitl_auto=hitl_auto,
    )
    completed = 0
    live_ops_fail_streak = 0
    for i in range(max_steps):
        result = orch.invoke_step()
        if not result.ok:
            # Week fail after 3 retries: park failed_repair and keep the 24h/--week cycle going
            if result.reason == "failed_repair":
                print("   failed_repair - skipping to next queue task (week/24h continues)")
                if sleep_s > 0 and i + 1 < max_steps:
                    time.sleep(sleep_s)
                continue
            # A20.0 Live Ops: empty queue in --week/24h -> invent more tasks via DeepSeek
            if result.reason == "no_tasks" and week and not dry_run:
                try:
                    n_new = try_live_ops_more_tasks(root)
                except Exception as e:
                    n_new = 0
                    print(f"[Live Ops] generate failed: {type(e).__name__}: {e}")
                if n_new > 0:
                    live_ops_fail_streak = 0
                    print(
                        f"[Live Ops] Tasks exhausted. Generated {n_new} new tasks. Continuing."
                    )
                    write_heartbeat(
                        root,
                        {"status": "live_ops", "generated": n_new, "project": _active_project_id(root)},
                    )
                    if sleep_s > 0 and i + 1 < max_steps:
                        time.sleep(sleep_s)
                    continue
                live_ops_fail_streak += 1
                if live_ops_fail_streak >= 3:
                    print("[Live Ops] DeepSeek could not invent new tasks. Stopping.")
                    write_heartbeat(root, {"status": "live_ops_stop", "streak": live_ops_fail_streak})
                    break
                print(
                    f"[Live Ops] empty/duplicate batch ({live_ops_fail_streak}/3). Retrying..."
                )
                if sleep_s > 0 and i + 1 < max_steps:
                    time.sleep(sleep_s)
                continue
            if result.reason in {"no_tasks", "human", "failed", "auth", "retry", "stub"}:
                if result.reason == "retry":
                    print("   Stopping so you can fix model/parser and re-run --week (task left pending).")
                if result.reason == "stub":
                    print("   Stub backend - task left pending (not closed). Continuing only if more steps+backends.")
                break
            break
        completed += 1
        if validate_every > 0 and completed % validate_every == 0:
            # A6.2: every N successful steps, bump pulse + compact state contracts
            try:
                state_hub.maybe_compact_after_week_gate(root, completed, every_n=validate_every)
            except Exception as e:
                print(f"   [compact] warn: {e}")

            ok, errs = validate_project_integrity(root)
            print(f"   [gate] validate after {completed} steps: {'OK' if ok else 'INVALID'}")
            if not ok:
                for e in errs[:8]:
                    print(f"      FAIL: {e}")
                write_heartbeat(root, {"status": "gate_failed", "errors": errs[:8]})
                if gate_strict:
                    print("   Stopping week loop - fix sources or git checkout seeds, then re-run.")
                    break
                # Default week: keep going so later F*/R* tasks can rewrite failing files
                print("   Gate soft-fail - continuing week (later TZ tasks should repair). Use --gate-strict to stop.")
            score, _ = quality_score(root)
            print(f"   [gate] quality_score={score}")
        if sleep_s > 0 and i + 1 < max_steps:
            time.sleep(sleep_s)
    return completed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Quality Forge - long-horizon game orchestrator")
    parser.add_argument("--loop", action="store_true", help="Process many tasks in one run")
    parser.add_argument("--week", action="store_true", help="Week mode: loop + sleep + validate gates + no micro-split")
    parser.add_argument(
        "--gate-strict",
        action="store_true",
        help="Stop --week on integrity gate fail (default: soft-fail and continue so later tasks can repair)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Max steps (default 1; 500 with --week or --loop)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=None,
        help="Seconds between steps (week default 30; pass 0 for no delay)",
    )
    parser.add_argument("--root", type=str, default=str(ROOT_DEFAULT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score", action="store_true", help="Print quality score and exit")
    parser.add_argument("--validate", action="store_true", help="Validate all src files and exit")
    parser.add_argument("--eval", action="store_true", help="Write docs/AGENT_RUN_REPORT.md assessment and exit")
    parser.add_argument("--doctor", action="store_true", help="Check Ollama + model tags, then exit")
    parser.add_argument(
        "--compact-state",
        action="store_true",
        help="Compact state.json contract snapshots into contracts/ and exit",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help=(
            "Clear task queue, reset pulse/UI cycles (unstick Smoke 48/48), "
            "write empty TZ; scope with --project <id> (e.g. game2)"
        ),
    )
    parser.add_argument(
        "--clear-queue",
        action="store_true",
        help=(
            "Clear pending tasks in state.json (task_queue + partial) only - "
            "keeps pulse/done/TZ; use before a new game/donate run when stuck on old checkpoints"
        ),
    )
    parser.add_argument(
        "--feedback",
        choices=["y", "n", "yes", "no"],
        default=None,
        help="A6.3 HITL verdict for --plugin (y=closed_verified+golden, n=broken_by_user+rule)",
    )
    parser.add_argument("--plugin", type=str, default=None, help="Plugin id for --feedback (e.g. game1.hud)")
    parser.add_argument("--note", type=str, default="", help="Human comment for --feedback / --answer other")
    parser.add_argument("--rules-list", action="store_true", help="List knowledge_base.json rules and exit")
    parser.add_argument(
        "--rules-activate",
        type=str,
        default=None,
        help="Activate draft rule id after dry-run (e.g. R001)",
    )
    parser.add_argument(
        "--rules-force",
        action="store_true",
        help="With --rules-activate: skip dry-run (human override)",
    )
    parser.add_argument(
        "--ask-pack",
        action="store_true",
        help="A7.1: print DeepSeek HITL pack (A/B/C/Other) and save pending_hitl_pack",
    )
    parser.add_argument(
        "--answer",
        type=str,
        default=None,
        help="A7.1: answer pending pack e.g. Q1=B or Q1=other (use --note for Other text)",
    )
    parser.add_argument(
        "--plan-next",
        action="store_true",
        help="A7.1: planner plan_next (ask_hitl | verify_plugin | idle)",
    )
    parser.add_argument(
        "--gate-plan",
        type=str,
        default=None,
        help="A7.1: JSON plan string or @file.json - hallucination gate (blocks unknown exports)",
    )
    parser.add_argument(
        "--archetypes-list",
        action="store_true",
        help="A7.2: list plugin skeleton archetypes from skeletons/registry.json",
    )
    parser.add_argument(
        "--scan-assets",
        action="store_true",
        help="A11.0: scan assets/models/ -> assets/catalog/assets.json and print ids",
    )
    parser.add_argument(
        "--scan-place-fruits",
        action="store_true",
        help="Scan working_game.rbxl Fruits_Inventory -> place_meshes.json + INVENTORY.md",
    )
    parser.add_argument(
        "--audit-legacy",
        type=str,
        default=None,
        metavar="PATH",
        help="A12.0: static audit of a legacy Luau tree -> docs/LEGACY_*.md + draft KB rules",
    )
    parser.add_argument(
        "--audit-no-kb-merge",
        action="store_true",
        help="With --audit-legacy: write draft_rules.json but do not merge into knowledge_base.json",
    )
    parser.add_argument(
        "--bundle-savings",
        action="store_true",
        help="A13.0: measure fat vs economy bundle_for_14b size (%% saved)",
    )
    parser.add_argument("--ui", action="store_true", help="Open control UI (projects/skills/DeepSeek/smoke)")
    parser.add_argument("--ui-port", type=int, default=8787, help="UI port (default 8787)")
    parser.add_argument(
        "--checklist",
        action="store_true",
        help="A16.0: print launch checklist (Ollama/skeletons/assets/rules) and exit",
    )
    parser.add_argument("--project", type=str, default=None, help="Activate projects/<id> into live src+TZ")
    parser.add_argument("--skills-list", action="store_true", help="List raw/compact skills and exit")
    parser.add_argument("--skills-compress", type=str, default=None, help="Compress raw skill id into compact/")
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

    if args.compact_state:
        report = state_hub.compact_state(root, force=True)
        print(f"compact_state: {json.dumps(report, ensure_ascii=False)}")
        return 0

    if args.reset_state:
        report = state_hub.reset_state(root, project_id=args.project)
        print(f"reset_state: {json.dumps(report, ensure_ascii=False)}")
        if args.project:
            print(f"  project={args.project} -> empty TZ + activated; other projects untouched")
        else:
            print("  workspace runtime cleared (pass --project <id> to scaffold a new game)")
        return 0

    if args.clear_queue:
        report = state_hub.clear_queue(root)
        print(f"clear_queue: {json.dumps(report, ensure_ascii=False)}")
        print("  task_queue/partial cleared - pulse/done/TZ kept; ready for new game or --week")
        return 0

    if args.rules_list:
        from . import feedback as feedback_hub

        for r in feedback_hub.list_rules(root):
            print(f"  {r.get('id')}  status={r.get('status')}  plugin={r.get('plugin')}  {str(r.get('human_comment') or '')[:80]}")
        return 0

    if args.rules_activate:
        from . import feedback as feedback_hub

        report = feedback_hub.activate_rule(
            root, args.rules_activate, force=bool(getattr(args, "rules_force", False))
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1

    if args.feedback is not None:
        from . import feedback as feedback_hub
        from . import planner as planner_hub

        if not args.plugin:
            print("ERROR: --feedback requires --plugin <id>")
            return 1
        report = planner_hub.submit_plugin_verdict(root, args.plugin, args.feedback, note=args.note or "")
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.archetypes_list:
        from . import skeletons_hub

        print(skeletons_hub.catalog_for_prompt(root))
        for a in skeletons_hub.list_archetypes(root):
            print(f"  {a['id']} latest={a['latest']} versions={a['versions']}")
        return 0

    if args.scan_place_fruits:
        from . import asset_hub
        from . import rbxl_inventory

        try:
            report = rbxl_inventory.write_place_meshes(root)
        except RuntimeError as exc:
            text = str(exc)
            if "zstandard" in text.lower():
                # Soft-fail: existing catalog is usable; re-scan still needs zstandard.
                print(text, file=sys.stderr)
                n = rbxl_inventory.existing_place_meshes_fruit_count(root)
                if n > 0:
                    print(
                        f"[soft-fail] kept existing place_meshes.json ({n} fruits). "
                        "Run: python -u run.py --scan-assets",
                        file=sys.stderr,
                    )
                return 1
            raise
        inv_md = root / "artifacts" / "reference_place" / "INVENTORY.md"
        inv_md.parent.mkdir(parents=True, exist_ok=True)
        inv_md.write_text(
            rbxl_inventory.inventory_markdown(report["scan"]), encoding="utf-8"
        )
        cat_path = asset_hub.write_catalog(root)
        cat = asset_hub.load_catalog(root)
        print(asset_hub.catalog_for_prompt(root))
        print(
            f"wrote {report['path']} fruits={report['count']}; "
            f"{inv_md.as_posix()}; catalog {cat_path} count={cat.get('count')}"
        )
        for a in cat.get("assets") or []:
            print(f"  {a.get('id')}  source={a.get('source') or 'file'}  {a.get('rel')}")
        return 0

    if args.scan_assets:
        from . import asset_hub

        path = asset_hub.write_catalog(root)
        cat = asset_hub.load_catalog(root)
        print(asset_hub.catalog_for_prompt(root))
        print(f"wrote {path} count={cat.get('count')}")
        for a in cat.get("assets") or []:
            print(f"  {a.get('id')}  {a.get('rel')}  {a.get('bytes')}b")
        return 0

    if args.bundle_savings:
        from . import llm_backends
        from . import skills_hub

        skill_ids = [c["id"] for c in skills_hub.list_compact(root)[:3]]
        tz_snip = ""
        tz_p = root / "PROJECT_TZ.md"
        if tz_p.is_file():
            tz_snip = tz_p.read_text(encoding="utf-8")[:1200]
        report = skills_hub.bundle_savings_report(
            root,
            skill_ids or None,
            archetype="client_ui",
            skeleton_version="v1",
            skeleton_budget=500,
            focus_text=tz_snip or "get_player_coins SetAttribute Coins DataStore pcall",
        )
        # A15 cycle token estimate (prompt in + predict out)
        lean_chars = int(report.get("chars_after") or 0)
        predict = llm_backends.DEFAULT_NUM_PREDICT
        predict_diff = llm_backends.DIFF_NUM_PREDICT
        report["a15_cycle_estimate"] = {
            "bundle_chars": lean_chars,
            "approx_input_tokens": lean_chars // 4,
            "num_predict_code": predict,
            "num_predict_diff": predict_diff,
            "approx_output_tokens_code": predict,
            "approx_output_tokens_diff": predict_diff,
            "approx_cycle_tokens_code": lean_chars // 4 + predict,
            "approx_cycle_tokens_diff": lean_chars // 4 + predict_diff,
            "note": "Rough Latin~4chars/token; patches cut output ~50-80% vs full file",
        }
        out = root / "artifacts" / "a15_context_opt" / "bundle_savings.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"bundle-savings: {report.get('percent_saved')}% smaller -> {out}")
        cyc = report["a15_cycle_estimate"]
        print(
            f"a15 cycle~ {cyc['approx_cycle_tokens_code']} tok (code) / "
            f"{cyc['approx_cycle_tokens_diff']} tok (diff) "
            f"[predict {predict}/{predict_diff}]"
        )
        return 0

    if args.audit_legacy is not None:
        from . import legacy_auditor

        project = Path(args.audit_legacy).expanduser().resolve()
        if not project.exists():
            print(f"ERROR: legacy path not found: {project}")
            return 1
        report = legacy_auditor.audit_legacy(
            project,
            forge_root=root,
            merge_kb=not args.audit_no_kb_merge,
        )
        print(
            f"audit-legacy: modules={report.get('modules')} functions={report.get('functions')} "
            f"pitfalls={report.get('pitfalls')} draft_rules={report.get('draft_rules')} "
            f"kb_added={(report.get('kb_merge') or {}).get('added')}"
        )
        print(f"  architecture -> {report.get('architecture')}")
        print(f"  pitfalls     -> {report.get('pitfalls_md')}")
        print(f"  draft rules  -> {report.get('draft_rules_json')}")
        for p in (report.get("_pitfalls") or [])[:12]:
            print(f"  [{p.get('severity')}] {p.get('id')} {p.get('file')}:{p.get('line')} - {p.get('title')}")
        if (report.get("pitfalls") or 0) > 12:
            print(f"  ... +{report['pitfalls'] - 12} more (see LEGACY_PITFALLS.md)")
        return 0

    if args.ask_pack or args.plan_next:
        from . import planner as planner_hub

        result = planner_hub.plan_next(root)
        if result.get("action") == "ask_hitl" and result.get("pack"):
            print(planner_hub.format_hitl_pack_cli(result["pack"]))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.answer is not None:
        from . import planner as planner_hub

        # Parse Q1=B or Q1=other
        answers: Dict[str, str] = {}
        other_notes: Dict[str, str] = {}
        for part in str(args.answer).split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            qid, val = part.split("=", 1)
            qid, val = qid.strip(), val.strip()
            answers[qid] = val
            if val.lower() in {"other", "другое", "o"} and args.note:
                other_notes[qid] = args.note
        report = planner_hub.record_hitl_answers(root, answers, other_notes=other_notes)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if report.get("followups"):
            from . import planner as ph

            for pack in report["followups"]:
                print(ph.format_hitl_pack_cli(pack))
        return 0 if report.get("ok") else 1

    if args.gate_plan is not None:
        from . import planner as planner_hub

        raw = args.gate_plan
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        try:
            plan_obj = json.loads(raw)
        except json.JSONDecodeError:
            plan_obj = {"description": raw, "proposed_calls": []}
        report = planner_hub.gate_and_plan(root, plan_obj if isinstance(plan_obj, dict) else {"description": str(plan_obj)})
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report.get("action") == "enqueue" else 1

    if args.checklist:
        from . import launch_checklist

        report = launch_checklist.print_checklist(root)
        return 0 if report.get("ready_for_ui") else 1

    if args.ui:
        from .ui_server import serve

        serve(port=int(args.ui_port))
        return 0

    if args.project:
        from . import projects_hub

        projects_hub.activate_project(root, args.project)
        print(f"Activated project {args.project} -> live src + PROJECT_TZ.md")
        return 0

    if args.skills_list:
        from . import skills_hub

        print("COMPACT:")
        for c in skills_hub.list_compact(root):
            print(f"  {c['id']}  chars={c['chars']} promoted={c['promoted']}")
        print("RAW (top 30):")
        for r in skills_hub.list_raw(root)[:30]:
            print(f"  {r['id']}  bytes={r['chars']}")
        print(f"raw total: {len(skills_hub.list_raw(root))}")
        return 0

    if args.skills_compress:
        from . import skills_hub

        text, dest = skills_hub.compress_raw_to_compact(args.skills_compress, root)
        print(f"Wrote {dest} ({len(text)} chars)")
        return 0

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

    if args.eval:
        path = write_eval_report(root)
        print(f"Wrote {path}")
        print(path.read_text(encoding="utf-8"))
        score, _ = quality_score(root)
        return 0 if score >= 60 else 1

    week = bool(args.week)
    if week:
        # A20.1: high default when --max omitted (UI/24h must not inherit a tiny budget).
        max_steps = args.max if args.max is not None else 500
        # None -> 30s pacing; explicit --sleep 0 must stay 0 (do not coerce to 30)
        sleep_s = 30.0 if args.sleep is None else float(args.sleep)
        validate_every = int(WEEK_MODE.get("validate_every_n_steps") or 5)
        print("Quality Forge WEEK MODE | greenfield | no micro-split | 14b+7b-repair")
        # A19.0: print current Quality Score to console before week work
        week_score, week_notes = quality_score(root)
        print(f"Quality score: {week_score}/100")
        for n in week_notes[:8]:
            print(f"  - {n}")
    else:
        max_steps = args.max if args.max is not None else (500 if args.loop else 1)
        sleep_s = 0.0 if args.sleep is None else float(args.sleep)
        validate_every = 0

    llm.reset_runtime_backend()
    be, reason = llm.resolve_runtime_backend()
    print(
        f"Quality Forge | backend={be} | root={root} | max_steps={max_steps} | "
        f"sleep={sleep_s}s | gate_every={validate_every}"
    )
    print(f"  resolve: {reason}")
    if not args.dry_run:
        # A6.1: never hard-exit on Ollama down — stub/cloud continue the pipeline
        if be == "stub":
            print("[STUB] No live LLM - tasks will be skipped and left pending (never closed)")
        elif not llm.ping():
            print(f"WARN: backend '{be}' ping unexpected fail - continuing with resolve cascade")
            llm.reset_runtime_backend()
            be, reason = llm.resolve_runtime_backend()
            print(f"  re-resolve: {be} ({reason})")
        installed = installed_models(force=True) if be != "stub" else ["stub"]
        print(f"Models: {', '.join(installed) if installed else '(none)'}")

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
        gate_strict=bool(getattr(args, "gate_strict", False)),
        week=week,
    )
    print(f"Completed {completed} step(s).")
    score, notes = quality_score(root)
    print(f"Final quality score: {score}/100")
    if week:
        print("HITL: when asked, type y after Studio smoke (or n to stop).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
