"""Prompt builder with context budget (fixes 39KB prompt blowups)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from .task_parser import Task, WriteMode

SKIP_NAMES = {"run.ps1", "run.py", "PROJECT_TZ.md", "AGENTS.md"}
SKIP_DIRS = {"logs", ".git", "forge", "build", ".forge", "__pycache__", "tests"}

_MODELS_PATH = Path(__file__).resolve().parent / "models.json"


def load_model_config() -> dict:
    if _MODELS_PATH.is_file():
        return json.loads(_MODELS_PATH.read_text(encoding="utf-8"))
    return {"agents": {}, "escalation": [], "fallback_any": True}


_CFG = load_model_config()

# Defaults match the user's original Ollama tags (7b-2k / 14b-4k / 3b-8k), NOT bare :7b/:14b
AGENT_MODELS: Dict[str, dict] = {
    name: dict(cfg)
    for name, cfg in (_CFG.get("agents") or {}).items()
}

# Ensure every known role has an entry even if JSON is trimmed
_FALLBACK_ROLE = {"model": "qwen2.5-coder:14b-4k", "ctx": 2048, "predict": 1024}
for _role in (
    "game_designer",
    "tech_architect",
    "gameplay_programmer",
    "client_programmer",
    "qa_engineer",
    "refactorer",
    "builder",
    "systems_designer",
    "content_author",
    "integrator",
):
    AGENT_MODELS.setdefault(_role, dict(_FALLBACK_ROLE))

ESCALATION: List[str] = list(_CFG.get("escalation") or [
    "qwen2.5-coder:14b-4k",
    "qwen2.5-coder:14b-2k",
    "qwen2.5-coder:14b",
])
FALLBACK_ANY = bool(_CFG.get("fallback_any", True))
WEEK_MODE: dict = dict(_CFG.get("week_mode") or {
    "disable_micro_split": True,
    "seed_first": True,
    "validate_every_n_steps": 5,
})
SPACEBUNNY_CFG: dict = dict(_CFG.get("spacebunny") or {})
OPENROUTER_CFG: dict = dict(_CFG.get("openrouter") or {})


def extract_agent_section(agents_md: str, owner: str) -> str:
    # Roles are "### @owner" (or "## @owner"); keep universal rules above first role.
    role_start = re.search(r"(?m)^#{2,3} @\w+", agents_md)
    universal = agents_md[: role_start.start() if role_start else len(agents_md)]
    m = re.search(
        rf"(?ms)^#{{2,3}} @{re.escape(owner)}\b.*?(?=^#{{2,3}} @|\Z)",
        agents_md,
    )
    section = m.group(0) if m else ""
    return universal + "\n" + section


def relevant_paths(root: Path, task: Task, owner: str = "") -> List[Path]:
    """Prefer files related to the task.

    A34 / A27.0 Max Context:
    - gameplay_programmer & client_programmer → ONLY task.target_path + Remotes.luau
    - needs_all_src ONLY for refactorer & qa_engineer
    """
    picks: List[Path] = []
    seen: Set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve())
        if key in seen or not p.is_file():
            return
        seen.add(key)
        picks.append(p)

    remotes = root / "src/shared/Gameplay/Remotes.luau"
    src = root / "src"

    # Slim path set for code agents — keep prompts ~1500 tok.
    if owner in {"gameplay_programmer", "client_programmer"}:
        if task.target_path:
            add(root / task.target_path)
        add(remotes)
        return picks

    # Roles that MUST see the whole game tree
    needs_all_src = owner in {"qa_engineer", "refactorer"}

    if needs_all_src and src.is_dir():
        for p in sorted(src.rglob("*.luau")):
            add(p)

    if task.target_path:
        add(root / task.target_path)
        # only add siblings for non-docs targets (docs/* siblings ate the budget)
        parent = (root / task.target_path).parent
        if parent.is_dir() and parent.name != "docs":
            for child in sorted(parent.glob("*")):
                add(child)

    for rel in (
        "default.project.json",
        "src/shared/Gameplay/Remotes.luau",
        "docs/ARCHITECTURE.md",
        "docs/GDD.md",
        "docs/QA_REPORT.md",
    ):
        add(root / rel)

    if len(picks) < 4 and src.is_dir():
        for p in sorted(src.rglob("*.luau")):
            add(p)

    return picks


def tz_compact_for_task(tz: str, task: Task, *, first_n: int = 8) -> str:
    """A34/A27.0: first N TZ lines + the current open task line (deduped)."""
    lines = (tz or "").splitlines()
    head = lines[:first_n]
    current = ""
    tid = (task.task_id or "").strip()
    raw = (task.raw or "").strip()
    for line in lines:
        if tid and f" {tid} " in f" {line} " and ("- [ ]" in line or "- [-]" in line or "- [x]" in line):
            current = line
            break
        if raw and line.strip() == raw:
            current = line
            break
    out = list(head)
    if current and current not in out:
        out.append(current)
    return "\n".join(out)


_FUNC_START_RE = re.compile(
    r"(?m)^(?P<indent>\s*)(?:local\s+)?function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("
)
_FUNC_NAME_HINT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def extract_broken_function_snippet(
    content: str,
    error: str = "",
    *,
    max_chars: int = 700,
) -> str:
    """Pull one broken function (or a tight window) for REPAIR MODE — not the whole file."""
    text = content or ""
    if not text.strip():
        return ""
    err = (error or "").lower()
    # Prefer a named function mentioned in the error / stub markers nearby.
    names: List[str] = []
    for m in _FUNC_NAME_HINT_RE.finditer(error or ""):
        n = m.group(1)
        if n.lower() not in {"function", "local", "if", "for", "while", "end", "then", "and", "or"}:
            names.append(n)
    starts = list(_FUNC_START_RE.finditer(text))
    chosen = None
    if names and starts:
        for st in starts:
            if st.group("name") in names:
                chosen = st
                break
    if chosen is None and starts:
        # Prefer function containing stub/TODO markers
        stub_idx = -1
        for pat in (
            r"--\s*TODO\b",
            r"--\s*Respawn logic here",
            r"--\s*real code here",
            r"--\s*Update checkpoint data here",
            r"--\s*Handle checkpoint logic",
        ):
            m = re.search(pat, text, re.I)
            if m:
                stub_idx = m.start()
                break
        if stub_idx >= 0:
            prev = [st for st in starts if st.start() <= stub_idx]
            chosen = prev[-1] if prev else starts[0]
        else:
            # Keyword from error inside a function body
            keywords = [w for w in re.findall(r"[A-Za-z_]{4,}", err) if w not in {
                "must", "missing", "stub", "placeholder", "comment", "write", "real", "code",
                "error", "validator", "file", "server", "client", "luau",
            }]
            for st in starts:
                # Approximate body until next same-indent function or EOF
                body_end = len(text)
                for nxt in starts:
                    if nxt.start() > st.start():
                        body_end = nxt.start()
                        break
                body = text[st.start():body_end]
                if any(k in body.lower() for k in keywords[:6]):
                    chosen = st
                    break
            if chosen is None:
                chosen = starts[0]

    if chosen is not None:
        start = chosen.start()
        indent = chosen.group("indent") or ""
        body_end = len(text)
        for nxt in starts:
            if nxt.start() > start:
                body_end = nxt.start()
                break
        # Stop at `end` at the same indent as the function header (Luau convention).
        pos = chosen.end()
        while pos < body_end:
            line_end = text.find("\n", pos)
            if line_end < 0 or line_end > body_end:
                line_end = body_end
            raw_line = text[pos:line_end]
            if re.match(rf"^{re.escape(indent)}end\b", raw_line):
                body_end = line_end
                break
            pos = line_end + 1
        chunk = text[start:body_end].rstrip()
        if len(chunk) > max_chars:
            chunk = chunk[: max_chars - 20].rstrip() + "\n-- ...(snip)..."
        return chunk

    # No functions — tight window around stub / mid file
    m = re.search(r"(?im)--\s*(TODO|Respawn logic here|real code here)", text)
    if m:
        mid = m.start()
        lo = max(0, mid - max_chars // 3)
        hi = min(len(text), mid + (2 * max_chars) // 3)
        chunk = text[lo:hi].strip()
        if lo > 0:
            chunk = "-- ...(snip)...\n" + chunk
        if hi < len(text):
            chunk = chunk + "\n-- ...(snip)..."
        return chunk[:max_chars]
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n-- ...(snip)...\n" + text[-half:]


REPAIR_FIX_INSTRUCTION = (
    'Fix this error. Output the COMPLETE file with <FILE path="...">...</FILE>.'
)


def file_budget_chars() -> int:
    """Cloud 1M-ctx: large. Ollama A17 hard-fit: tiny file window inside 2k ctx."""
    try:
        from . import llm

        be = llm.backend_name()
        if be == "spacebunny":
            return int(SPACEBUNNY_CFG.get("file_budget") or 180_000)
        if be == "openrouter":
            return int(OPENROUTER_CFG.get("file_budget") or 180_000)
        ollama_cfg = dict(_CFG.get("ollama") or {})
        # A17: default 1800 chars — contracts/TZ/task must still fit ≤2000 tok / leave predict room
        return int(ollama_cfg.get("file_budget") or 1_800)
    except Exception:
        pass
    return 1_800


def compress_tz_for_prompt(tz: str, *, max_chars: int = 900) -> str:
    """
    A17: shrink PROJECT_TZ before Ollama — keep headers + open [ ] (+ sparse done markers).
    Done/failed lines collapse to a one-line count so open work stays visible.
    """
    lines = (tz or "").splitlines()
    keep: List[str] = []
    done_n = 0
    fail_n = 0
    header_n = 0
    for line in lines:
        s = line.strip()
        # Task markers always classified first (even in first lines)
        if "- [ ]" in line:
            keep.append(line)
            continue
        if "- [-]" in line:
            fail_n += 1
            m = re.search(r"\b([A-Z]\d+(?:\.\d+)?)\b", line)
            if m and len(keep) < 40:
                keep.append(f"- [-] {m.group(1)}")
            continue
        if "- [x]" in line:
            done_n += 1
            continue
        # Headers / preamble only (cap so done lists elsewhere don't sneak in)
        if s.startswith("#") or (header_n < 6 and not s.startswith("-")):
            keep.append(line)
            header_n += 1
            continue
    if done_n or fail_n:
        keep.append(f"(TZ compact: done={done_n} failed_repair={fail_n})")
    text = "\n".join(keep)
    if len(text) > max_chars:
        head = "\n".join(keep[:6])
        rest = "\n".join(keep[6:])
        room = max(0, max_chars - len(head) - 40)
        text = head + "\n...\n" + rest[-room:]
    return text[:max_chars]


def render_files(paths: Sequence[Path], root: Path, budget_chars: Optional[int] = None) -> str:
    if budget_chars is None:
        budget_chars = file_budget_chars()
    parts: List[str] = []
    used = 0
    for p in paths:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.name
        text = p.read_text(encoding="utf-8", errors="replace")
        chunk = f"=== {rel} ===\n{text}\n\n"
        if used + len(chunk) > budget_chars:
            remain = max(0, budget_chars - used - 80)
            if remain > 200:
                parts.append(f"=== {rel} ===\n{text[:remain]}\n...(truncated)\n\n")
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts) if parts else "(no files yet)"


def mode_instructions(task: Task, *, file_exists: bool = False, prefer_diff: bool = True) -> str:
    # A27: APPEND mode fully disabled — coerce to REWRITE so the model returns
    # the COMPLETE file (APPEND caused duplicate `local function` pastes).
    mode = WriteMode.REWRITE if task.mode == WriteMode.APPEND else task.mode
    # A28: Cursor SEARCH/REPLACE markers break the parser — always COMPLETE file.
    if mode == WriteMode.REWRITE and file_exists:
        return (
            "WRITE MODE = REWRITE (APPEND disabled — A27; COMPLETE file only — A28).\n"
            "- Always return the COMPLETE new file content inside <FILE>.\n"
            "- NEVER use <<<<<<< SEARCH / ======= / >>>>>>> REPLACE "
            "(Cursor diff format — rejected by the parser).\n"
            "- NEVER append-only / never paste the file twice.\n"
            f"- Target file: {task.target_path}\n"
        )
    if mode == WriteMode.REWRITE:
        return (
            "WRITE MODE = REWRITE.\n"
            "- Return the COMPLETE new file content.\n"
            "- NEVER use <<<<<<< SEARCH / ======= / >>>>>>> REPLACE.\n"
            "- APPEND is disabled — never return append-only fragments.\n"
            f"- Target file: {task.target_path}\n"
        )
    if mode == WriteMode.CREATE:
        return (
            "WRITE MODE = CREATE.\n"
            "- Return the COMPLETE file content for a new/overwrite file.\n"
            f"- Target file: {task.target_path}\n"
        )
    # A27: section/#anchors also full-file rewrite (no SECTION APPEND).
    if task.section:
        return (
            "WRITE MODE = REWRITE (section target; APPEND disabled — A27).\n"
            f"- Return the COMPLETE file content for {task.target_path}"
            f" (section #{task.section} may be updated in place).\n"
            "- Do NOT return append-only fragments.\n"
        )
    return "WRITE MODE = NORMAL. Return complete file content for each <FILE>."


# A22.0: 7B panics on 3+ validator errors — feed one step at a time.
FIRST_ERROR_ONLY_INSTRUCTION = (
    "Fix ONLY the first error in the list. Ignore the rest for now."
)

# A23/A27 STRICT: Remotes must always be WaitForChild chain (never bare Remotes).
REMOTES_WAIT_RULE = (
    'ALWAYS require Remotes via ReplicatedStorage:WaitForChild("Gameplay")'
    ':WaitForChild("Remotes")'
)

# A25/A27: 7B repair must lead with this exact MANDATORY FILE line.
MANDATORY_FILE_LINE = (
    'MANDATORY: Your reply MUST contain <FILE path="...">content</FILE>. '
    "If you don't include the FILE tag, your fix will be rejected."
)

# A28/A31: exact-copy lead-in (Coins + Remotes Live Ops REWRITE).
EXACT_COPY_INSTRUCTION = (
    "Copy this template EXACTLY. Do not modify the structure. "
    "Only change the sound IDs and attribute names if needed."
)

# A31: Remotes exact-copy (same lead-in; structure is the contract).
REMOTES_EXACT_COPY = EXACT_COPY_INSTRUCTION

# A31: one-liner so 7B does not flip-flop table-vs-Folder vs missing events.
REMOTES_SHAPE_ONE_LINER = (
    "Remotes.luau REQUIRED SHAPE: "
    "local folder = FindFirstChild/create Folder under ReplicatedStorage; "
    "getOrCreate (or FindFirstChild create) for Checkpoint, CheckpointReached, "
    "UpdateLeaderboard, CoinCollected; "
    "local Remotes = { Checkpoint=..., CheckpointReached=..., "
    "UpdateLeaderboard=..., CoinCollected=... }; "
    "return Remotes — NEVER Remotes = folder / return folder / Folder instance."
)

# Compact snippet fed on Remotes repair (anti-oscillation).
REMOTES_MINI_TEMPLATE = """\
-- Remotes mini (copy structure):
local folder = ReplicatedStorage:FindFirstChild("Remotes")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Remotes"
	folder.Parent = ReplicatedStorage
end
local function getOrCreate(name: string): RemoteEvent
	local r = folder:FindFirstChild(name)
	if not r then
		r = Instance.new("RemoteEvent")
		r.Name = name
		r.Parent = folder
	end
	return r :: RemoteEvent
end
local Remotes = {
	Checkpoint = getOrCreate("Checkpoint"),
	CheckpointReached = getOrCreate("CheckpointReached"),
	UpdateLeaderboard = getOrCreate("UpdateLeaderboard"),
	CoinCollected = getOrCreate("CoinCollected"),
}
return Remotes
"""

_REMOTES_TABLE_ERR_MARKERS = (
    "must be a table",
    "Folder instance",
    "return folder",
    "not the Folder",
)
_REMOTES_MISSING_ERR_MARKERS = (
    "CheckpointReached",
    "CoinCollected",
    "getOrCreate",
    "create-or-reuse",
    "network_remote",
    "missing required",
)


def is_remotes_target(path: Optional[str]) -> bool:
    if not path:
        return False
    return path.replace("\\", "/").endswith("Remotes.luau")


def _remotes_error_classes(fails: Sequence[str]) -> tuple:
    """Return (has_table_vs_folder, has_missing_events_or_getOrCreate)."""
    items = [str(f) for f in (fails or []) if str(f).strip()]
    has_table = any(
        any(m.lower() in f.lower() for m in _REMOTES_TABLE_ERR_MARKERS) for f in items
    )
    has_missing = any(
        any(m.lower() in f.lower() for m in _REMOTES_MISSING_ERR_MARKERS) for f in items
    )
    return has_table, has_missing


def remotes_combined_repair_message(fails: Sequence[str]) -> str:
    """Combined Remotes repair bullet: full shape + mini template (A31)."""
    return (
        f"{REMOTES_SHAPE_ONE_LINER}\n"
        "Apply this mini template (keep Folder in `folder`, TABLE in `Remotes`):\n"
        f"{REMOTES_MINI_TEMPLATE.strip()}"
    )


def repair_errors_for_7b(
    fails: Sequence[str],
    *,
    target_path: Optional[str] = None,
) -> List[str]:
    """Return the error list to feed 7B repair.

    Default (A22.0): when more than one fail is present, return ONLY the first so
    the repair model works one step at a time.

    Remotes.luau (A31): if both table-vs-Folder AND missing events/getOrCreate
    appear, feed ONE combined shape message so 7B does not oscillate.
    """
    items = [str(f).strip() for f in (fails or []) if str(f).strip()]
    if is_remotes_target(target_path):
        has_table, has_missing = _remotes_error_classes(items)
        if has_table and has_missing:
            return [remotes_combined_repair_message(items)]
        if items:
            # Still attach mini template so fixing one class does not drop the other.
            return [f"{items[0]}\n{REMOTES_SHAPE_ONE_LINER}\n{REMOTES_MINI_TEMPLATE.strip()}"]
    if len(items) > 1:
        return items[:1]
    return items


def format_validator_checklist(
    fails: Sequence[str],
    *,
    first_only: bool = False,
    target_path: Optional[str] = None,
) -> str:
    """Numbered checklist for 7B repair — model must fix every bullet, nothing else.

    When first_only=True and multiple fails exist, only the first error is listed
    and FIRST_ERROR_ONLY_INSTRUCTION is appended (A22.0 multi-error step split).

    Remotes.luau (A31): combined shape when both table-vs-Folder and missing events.
    """
    raw = [str(f).strip() for f in (fails or []) if str(f).strip()]
    deferred = 0
    remotes_combined = False
    if is_remotes_target(target_path):
        items = repair_errors_for_7b(raw, target_path=target_path)
        has_table, has_missing = _remotes_error_classes(raw)
        remotes_combined = bool(has_table and has_missing and len(raw) > 1)
        if not remotes_combined and first_only and len(raw) > 1:
            deferred = len(raw) - 1
    elif first_only and len(raw) > 1:
        deferred = len(raw) - 1
        items = raw[:1]
    else:
        items = list(raw)
    if not items:
        items = ["(no structured validator_fails — re-read last VALIDATOR FAIL lines)"]
    lines = [f"{i}. {msg}" for i, msg in enumerate(items, 1)]
    body = (
        "REPAIR CHECKLIST (validator_fails) — fix EVERY bullet, in order:\n"
        + "\n".join(lines)
        + "\nRules: surgical PATCH only; do not rewrite architecture; "
        "after edits the file must satisfy ALL bullets above."
    )
    if remotes_combined:
        body += (
            "\nRemotes anti-oscillation: fix TABLE + getOrCreate + CheckpointReached "
            "+ CoinCollected in ONE pass — do not alternate Folder vs missing events."
        )
    elif deferred:
        body += (
            f"\n{FIRST_ERROR_ONLY_INSTRUCTION}"
            f"\n(Deferred {deferred} other validator error(s) for later repair steps.)"
        )
    return body


def build_prompt(
    root: Path,
    owner: str,
    task: Task,
    *,
    attempt: int = 1,
    validator_feedback: Optional[str] = None,
    prior_snapshot: Optional[str] = None,
    repair_draft: Optional[str] = None,
    is_7b: bool = False,
    prompt_budget_tokens: Optional[int] = None,
    num_ctx: Optional[int] = None,
    num_predict: Optional[int] = None,
) -> str:
    # A17: detect local Ollama so we hard-fit; cloud keeps larger prompts
    local_ollama = True
    try:
        from . import llm

        local_ollama = llm.backend_name() == "ollama"
    except Exception:
        local_ollama = True

    from . import llm_backends

    budget = prompt_budget_tokens
    if budget is None and local_ollama:
        budget = llm_backends.effective_prompt_token_budget(
            is_7b=is_7b,
            num_ctx=num_ctx,
            num_predict=num_predict,
            diff_mode=is_7b or attempt >= 2,
        )
    elif budget is None:
        budget = None  # cloud: no hard fit

    agents_raw = extract_agent_section((root / "AGENTS.md").read_text(encoding="utf-8"), owner)
    # A17: agents.md is huge — keep a stub for local ctx
    if local_ollama:
        agents = agents_raw[:500]
    else:
        agents = agents_raw

    tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
    if local_ollama:
        # A34/A27.0: first 8 lines + current task (not A33 last-5).
        tz_compact = tz_compact_for_task(tz, task, first_n=8)
    else:
        tz_lines = tz.splitlines()
        compact: List[str] = []
        for i, line in enumerate(tz_lines):
            if i < 12 or line.startswith("#") or line.startswith("##") or "- [ ]" in line:
                compact.append(line)
            elif "- [x]" in line or "- [-]" in line:
                compact.append(line)
        tz_compact = "\n".join(compact)

    file_cap = 900 if is_7b else file_budget_chars()
    if local_ollama and not is_7b:
        file_cap = min(file_cap, 1_800)
    if local_ollama and is_7b:
        file_cap = min(file_cap, 700)
    files = render_files(relevant_paths(root, task, owner), root, budget_chars=file_cap)

    feedback = ""
    # A34: when REPAIR MODE has a draft, skip the fat VALIDATOR FEEDBACK wall —
    # one error + broken function live inside REPAIR MODE (~1200).
    if validator_feedback and not repair_draft:
        # Prefer short checklist; trim long freeform validator walls.
        # Keep MANDATORY FILE + A22 first-error pin lines even when truncating.
        vf = validator_feedback.strip()
        if local_ollama and len(vf) > 800:
            head = vf[:800]
            # Prefer cutting on a newline so we don't bisect MANDATORY / Fix ONLY lines
            cut = head.rfind("\n")
            if cut >= 500:
                head = head[:cut]
            pin_needles = (
                "MANDATORY:",
                "MANDATORY FILE TAG",
                FIRST_ERROR_ONLY_INSTRUCTION,
            )
            pins = [
                ln
                for ln in vf.splitlines()
                if any(n in ln for n in pin_needles)
            ]
            for pin in pins:
                if pin not in head:
                    head = pin + "\n" + head
            vf = head.rstrip() + "\n...(validator trimmed)..."
        feedback = f"\n=== VALIDATOR FEEDBACK (fix ONLY these issues) ===\n{vf}\n"
    if repair_draft:
        # A34/A27.0 REPAIR MODE ~1200: ONE error + broken function snippet (not whole file).
        one_error = ""
        if validator_feedback:
            for ln in validator_feedback.splitlines():
                s = ln.strip()
                if not s:
                    continue
                # Prefer checklist bullet / first concrete error line
                m_num = re.match(r"^\d+\.\s+(.*)$", s)
                if m_num:
                    one_error = m_num.group(1).strip()
                    break
                if s.startswith("- "):
                    one_error = s[2:].strip()
                    break
            if not one_error:
                # Skip MANDATORY / START YOUR REPLY boilerplate
                for ln in validator_feedback.splitlines():
                    s = ln.strip()
                    if not s or s.startswith("MANDATORY") or s.startswith("START YOUR"):
                        continue
                    if "FILE path" in s or s.startswith("REPAIR CHECKLIST"):
                        continue
                    if s.startswith("Rules:") or s.startswith("Keep the rest"):
                        continue
                    one_error = s
                    break
        if not one_error:
            one_error = "fix the validator failure in the broken function below"
        snippet = extract_broken_function_snippet(repair_draft, one_error, max_chars=700)
        # Cap whole REPAIR MODE payload ~1200 chars
        repair_cap = 1200
        header = (
            "\n=== REPAIR MODE (A15 PATCH / 7B) ===\n"
            f"{MANDATORY_FILE_LINE}\n"
            f"START YOUR REPLY WITH <DONE>{task.task_id}</DONE>.\n"
            f"Error: {one_error}\n"
            "Broken function:\n"
        )
        footer = f"\n{REPAIR_FIX_INSTRUCTION}\n"
        room = max(200, repair_cap - len(header) - len(footer))
        if len(snippet) > room:
            snippet = snippet[: room - 20].rstrip() + "\n-- ...(snip)..."
        feedback += header + snippet + footer
    elif prior_snapshot and task.mode in {
        WriteMode.REWRITE,
        WriteMode.CREATE,
        WriteMode.APPEND,  # A27: APPEND coerced — same baseline as REWRITE
    }:
        snap = prior_snapshot
        if local_ollama:
            snap_cap = 900 if is_7b else 1400
            if len(snap) > snap_cap:
                snap = snap[: snap_cap // 2] + "\n...(baseline truncated)...\n" + snap[-snap_cap // 2 :]
        feedback += (
            "\n=== BASELINE FILE (rewrite from THIS — A15; APPEND disabled A27; "
            "no SEARCH/REPLACE A28) ===\n"
            "Return the COMPLETE updated file. Do not invent a new architecture.\n"
            "NEVER use <<<<<<< SEARCH / ======= / >>>>>>> REPLACE "
            "(Cursor diff format — rejected by the parser).\n"
            "Preserve: Map folder, Name=\"Path\" floor, SpawnPlaza, SpawnLocation, "
            'checkpoint Name = "Checkpoint" .. tostring(id) (NO underscore), coins, print section ids.\n'
            "Only apply the task delta (e.g. add Obstacle parts).\n"
            f"{snap}\n"
        )

    # A33: SKILLS_BLOCK only for client tasks (server prompts stay lean ~1500 tok).
    skills_block = ""
    target_norm = (task.target_path or "").replace("\\", "/")
    is_client_task = owner == "client_programmer" or (
        bool(target_norm)
        and (
            target_norm.endswith(".client.luau")
            or "/client/" in target_norm
            or target_norm.startswith("src/client/")
        )
    )
    if is_client_task:
        try:
            from . import skills_hub
            from . import token_economy as te

            skill_ids = ["forge-player-attrs", "forge-luau-touch"]
            active = root / ".forge" / "active_project.json"
            if active.exists():
                import json as _json

                pid = (_json.loads(active.read_text(encoding="utf-8")) or {}).get("id")
                meta_p = root / "projects" / str(pid) / "meta.json"
                if meta_p.exists():
                    meta = _json.loads(meta_p.read_text(encoding="utf-8"))
                    skill_ids = list(meta.get("skills_compact") or skill_ids)[:3]
            focus = te.extract_focus_terms(task.raw or "", task.description or "", tz_compact[:800])
            max_skills = 1 if (local_ollama and is_7b) else (2 if local_ollama else 3)
            skills_block = skills_hub.bundle_for_14b(
                root,
                skill_ids[:max_skills],
                max_skills=max_skills,
                card_budget=220 if local_ollama else 350,
                rules_budget=180 if local_ollama else 400,
                focus_terms=focus,
                economy=True,
                prune=True,
                skeleton_budget=0,
            )
            skill_cap = 500 if is_7b else (900 if local_ollama else 3600)
            if len(skills_block) > skill_cap:
                skills_block = skills_block[:skill_cap]
            if skills_block:
                skills_block = "\n" + skills_block
        except Exception:
            skills_block = ""

    # A11.0: 3D asset catalog — skip or tiny on local hard-fit
    assets_block = ""
    if not local_ollama:
        try:
            from . import asset_hub

            assets_block = "\n=== " + asset_hub.catalog_for_prompt(root, max_chars=400) + " ===\n"
        except Exception:
            assets_block = ""
    else:
        try:
            from . import asset_hub

            assets_block = "\n=== " + asset_hub.catalog_for_prompt(root, max_chars=120) + " ===\n"
        except Exception:
            assets_block = ""

    retry_note = ""
    if attempt > 1:
        retry_note = (
            f"\nThis is attempt {attempt}. Previous output was rejected.\n"
            "If REPAIR MODE is present: patch that draft, do not start a new design.\n"
            "Follow the format EXACTLY. Begin with <DONE>. Include <FILE> tags.\n"
        )
    # A33: keep ONLY ONE template matching the target file (never concatenate all).
    file_template = ""
    if owner == "qa_engineer":
        file_template = """
=== QA_REPORT TEMPLATE (copy structure; fill real bugs) ===
## BUGS
- [LOW] example only if real

## SUGGESTIONS
- one concrete suggestion

## TEST CASES
- one Studio test

## SCORE
- overall: 86
"""
    elif target_norm.endswith("Remotes.luau"):
        # A31: EXACT COPY at TOP (like Coins). Path: src/shared/Gameplay/Remotes.luau
        file_template = f"""
=== REMOTES TEMPLATE (ModuleScript — Folder in `folder`, TABLE in `Remotes`) ===
{REMOTES_EXACT_COPY}
Target MUST be -> src/shared/Gameplay/Remotes.luau
Pattern (REQUIRED):
1) local folder = ... Folder under ReplicatedStorage (NOT assigned to Remotes)
2) getOrCreate (or FindFirstChild create) for CheckpointReached, CoinCollected, etc.
3) local Remotes = {{ Checkpoint=..., CheckpointReached=..., UpdateLeaderboard=..., CoinCollected=... }}  -- TABLE
4) return Remotes  -- NEVER return folder / NEVER Remotes = folder
--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local folder = ReplicatedStorage:FindFirstChild("Remotes")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Remotes"
	folder.Parent = ReplicatedStorage
end

local function getOrCreate(name: string): RemoteEvent
	local r = folder:FindFirstChild(name)
	if not r then
		r = Instance.new("RemoteEvent")
		r.Name = name
		r.Parent = folder
	end
	return r :: RemoteEvent
end

local Remotes = {{
	Checkpoint = getOrCreate("Checkpoint"),
	CheckpointReached = getOrCreate("CheckpointReached"),
	UpdateLeaderboard = getOrCreate("UpdateLeaderboard"),
	CoinCollected = getOrCreate("CoinCollected"),
}}
return Remotes
"""
    elif "Checkpoints.server.luau" in target_norm:
        file_template = """
=== CHECKPOINTS TEMPLATE (Script — NO top-level return; NO coin logic) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local folder = workspace:FindFirstChild("Checkpoints")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Checkpoints"
	folder.Parent = workspace
end
local function hookPart(part: BasePart)
	local idx = tonumber(string.match(part.Name, "%d+"))
	if not idx then return end
	part.CanTouch = true
	part.Touched:Connect(function(hit: BasePart)
		local char = hit.Parent
		if not char then return end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then return end
		local current = plr:GetAttribute("Checkpoint") or 0
		if typeof(current) ~= "number" then current = 0 end
		if idx > (current :: number) then
			plr:SetAttribute("Checkpoint", idx)
			plr:SetAttribute("Score", idx * 100)
			Remotes.CheckpointReached:FireClient(plr, idx)
		end
	end)
end
for _, child in ipairs(folder:GetChildren()) do
	if child:IsA("BasePart") then hookPart(child) end
end
folder.ChildAdded:Connect(function(child)
	if child:IsA("BasePart") then hookPart(child) end
end)
local function teleportToCheckpoint(plr: Player, char: Model)
	local idx = plr:GetAttribute("Checkpoint") or 0
	if typeof(idx) ~= "number" or (idx :: number) < 1 then return end
	local cp = folder:FindFirstChild("Checkpoint" .. tostring(idx))
	if not cp or not cp:IsA("BasePart") then return end
	local hrp = char:FindFirstChild("HumanoidRootPart")
	if hrp and hrp:IsA("BasePart") then
		hrp.CFrame = CFrame.new(cp.Position + Vector3.new(0, 5, 0))
	end
end
local function hookCharacter(plr: Player, char: Model)
	task.defer(function() teleportToCheckpoint(plr, char) end)
	local hum = char:WaitForChild("Humanoid") :: Humanoid
	hum.Died:Connect(function()
		task.wait(0.1)
		plr:LoadCharacter()
	end)
end
Players.PlayerAdded:Connect(function(plr)
	plr.CharacterAdded:Connect(function(char) hookCharacter(plr, char) end)
	if plr.Character then hookCharacter(plr, plr.Character) end
end)
for _, plr in ipairs(Players:GetPlayers()) do
	plr.CharacterAdded:Connect(function(char) hookCharacter(plr, char) end)
	if plr.Character then hookCharacter(plr, plr.Character) end
end
-- NEVER Remotes.CoinsCollected (typo). NEVER destroy coins here.
"""
    elif "Effects.client.luau" in target_norm:
        file_template = """
=== EFFECTS TEMPLATE (LocalScript — NO top-level return) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local function play(soundId: string, volume: number)
	local ok, err = pcall(function()
		local s = Instance.new("Sound")
		s.SoundId = soundId
		s.Volume = volume
		s.Parent = SoundService
		s:Play()
		s.Ended:Connect(function() s:Destroy() end)
	end)
	if not ok then warn("[Effects] sound skip", err) end
end
local function flash(name: string)
	local gui = Players.LocalPlayer:FindFirstChild("PlayerGui")
	local hud = gui and gui:FindFirstChild("HUD")
	local label = hud and hud:FindFirstChild(name)
	if label and label:IsA("GuiObject") then
		local tw = TweenService:Create(label, TweenInfo.new(0.2), { BackgroundTransparency = 0.1 })
		tw:Play()
		tw.Completed:Connect(function()
			TweenService:Create(label, TweenInfo.new(0.3), { BackgroundTransparency = 0.5 }):Play()
		end)
	end
end
Remotes.CheckpointReached.OnClientEvent:Connect(function()
	play("rbxassetid://9112854440", 0.5)
	flash("CheckpointCount")
end)
if Remotes.CoinCollected then
	Remotes.CoinCollected.OnClientEvent:Connect(function()
		play("rbxassetid://9114224690", 0.4)
		flash("CoinCount")
	end)
end
"""
    elif "Generator.server.luau" in target_norm:
        file_template = """
=== GENERATOR RULES (must follow — validator will FAIL otherwise) ===
- ensureFolder(Workspace, "Map"), ensureFolder(Workspace, "Checkpoints"), ensureFolder(Workspace, "Coins")
  — the words Checkpoints and Coins MUST appear (folders created before spawning parts).
- Path Part Name="Path"; destroy Baseplate if present.
- Spawn MUST be exactly: Instance.new("SpawnLocation") — NEVER Instance.new("Part") with Name="SpawnLocation".
- Checkpoint parts Name="Checkpoint"..id under Checkpoints folder; Coin parts under Coins folder.
- Horror look OK (dark Path, neon CP) but folders+SpawnLocation rules are mandatory.
- print "[Generator] map floor ready"
"""
    elif "Coins.server.luau" in target_norm:
        file_template = f"""
=== COINS TEMPLATE (Script — NO top-level return) ===
{EXACT_COPY_INSTRUCTION}
You MUST use Players:GetPlayerFromCharacter(char) to find the player. You MUST call coin:Destroy() and FireAllClients UpdateLeaderboard. You MUST use task.wait().
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local function hook(coin: BasePart)
	coin.CanTouch = true
	coin.Touched:Connect(function(hit: BasePart)
		local char = hit.Parent
		if not char then return end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then return end
		coin:Destroy()
		local n = (plr:GetAttribute("Coins") or 0) + 1
		plr:SetAttribute("Coins", n) -- PLAYER attrs, not character
		Remotes.CoinCollected:FireClient(plr, n)
		Remotes.UpdateLeaderboard:FireAllClients(plr.Name .. ": " .. tostring(n))
	end)
end
local function ensureCoinsFolder(): Folder
	local f = workspace:FindFirstChild("Coins")
	if f and f:IsA("Folder") then return f end
	local created = Instance.new("Folder")
	created.Name = "Coins"
	created.Parent = workspace
	return created
end
local coinsFolder = ensureCoinsFolder()
for _, child in ipairs(coinsFolder:GetChildren()) do
	if child:IsA("BasePart") then hook(child) end
end
coinsFolder.ChildAdded:Connect(function(child)
	if child:IsA("BasePart") then hook(child) end
end)
"""
    elif "LevelConfig.luau" in target_norm:
        file_template = """
=== LEVELCONFIG TEMPLATE (ModuleScript — Luau `=` NOT JS `:`) ===
--!strict
return {
	{ id = 1, gap = 50, coins = 5 },
	{ id = 2, gap = 70, coins = 5 },
	{ id = 3, gap = 90, coins = 5 },
	{ id = 4, gap = 110, coins = 5 },
	{ id = 5, gap = 130, coins = 8 },
}
-- Generator does: for i, section in ipairs(LevelConfig) do … section.gap / section.coins
-- NEVER write JavaScript: return { sections: { id: 0 } }
"""
    elif "HUD.client.luau" in target_norm:
        file_template = """
=== HUD TEMPLATE (LEFT UI — read PLAYER attrs, never Character attrs) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "HUD"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")
local function makeLabel(name: string, y: number): TextLabel
	local t = Instance.new("TextLabel")
	t.Name = name
	t.Size = UDim2.new(0, 220, 0, 24)
	t.Position = UDim2.new(0, 12, 0, y)
	t.BackgroundTransparency = 0.4
	t.TextColor3 = Color3.new(1, 1, 1)
	t.TextXAlignment = Enum.TextXAlignment.Left
	t.Parent = gui
	return t
end
local timeL = makeLabel("Time", 12)
local cpL = makeLabel("CheckpointCount", 40)
local coinL = makeLabel("CoinCount", 68)
local bestL = makeLabel("BestTime", 96)
local t0 = os.clock()
local function paint()
	-- CRITICAL: attrs live on Player (set by Coins/Checkpoints servers), NOT on Character
	local coins = player:GetAttribute("Coins") or 0
	local cp = player:GetAttribute("Checkpoint") or 0
	local best = player:GetAttribute("BestTime")
	timeL.Text = string.format("Time: %.1f", os.clock() - t0)
	cpL.Text = "CP: " .. tostring(cp)
	coinL.Text = "Coins: " .. tostring(coins)
	bestL.Text = if typeof(best) == "number" and best < math.huge then string.format("Best: %.1f", best) else "Best: --"
end
RunService.RenderStepped:Connect(paint)
Remotes.CheckpointReached.OnClientEvent:Connect(function() paint() end)
Remotes.CoinCollected.OnClientEvent:Connect(function() paint() end)
player.CharacterAdded:Connect(function()
	t0 = os.clock()
	paint() -- do NOT zero Coins/Checkpoint locals; read player attrs
end)
paint()
-- NEVER character:GetAttribute("Coins") — that stays nil and wipes left HUD every frame
"""
    elif "Leaderboard.client.luau" in target_norm:
        file_template = """
=== LEADERBOARD TEMPLATE (stub — create GUI; Remotes.UpdateLeaderboard only) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "LeaderboardGui"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")
local label = Instance.new("TextLabel")
label.Name = "LeaderboardLabel"
label.Size = UDim2.new(0, 260, 0, 28)
label.Position = UDim2.new(1, -280, 0, 12)
label.BackgroundTransparency = 0.35
label.TextColor3 = Color3.new(1, 1, 1)
label.Text = "Leaderboard (waiting...)"
label.Parent = gui
if Remotes.UpdateLeaderboard then
	Remotes.UpdateLeaderboard.OnClientEvent:Connect(function(payload)
		label.Text = tostring(payload or "Leaderboard updated")
	end)
end
-- NEVER WaitForChild("LeaderboardFrame"); NEVER invent RequestLeaderboard / LeaderboardUpdated
"""
    elif "Void.server.luau" in target_norm:
        file_template = """
=== VOID RULES ===
Use RunService.Heartbeat: if HumanoidRootPart.Position.Y < -20 then Player:LoadCharacter().
Do NOT use Touched on HRP for void.
"""
    elif "Puzzles.server.luau" in target_norm:
        file_template = """
=== PUZZLES RULES ===
Create PressurePlate + Gate Parts if missing. Touched => open gate. TouchEnded => close.
Never use .Left. Prefer workspace.Puzzles folder.
"""

    # A17: on local Ollama, prefer one-line template hints over full Luau paste
    # A31: Remotes keeps FULL template (exact-copy + table pattern) — never collapse.
    if local_ollama and file_template and not target_norm.endswith("Remotes.luau"):
        def _short_tmpl(block: str, hint: str) -> str:
            if not block:
                return ""
            first = block.strip().splitlines()[0] if block.strip() else ""
            return f"\n{first}\n{hint}\n"

        if owner == "qa_engineer":
            file_template = _short_tmpl(file_template, "BUGS/SUGGESTIONS/TEST CASES/SCORE sections.")
        elif "Checkpoints.server.luau" in target_norm:
            file_template = _short_tmpl(
                file_template,
                'Touched+SetAttribute; Died→LoadCharacter; FindFirstChild("Checkpoint"..idx).',
            )
        elif "Effects.client.luau" in target_norm:
            file_template = _short_tmpl(
                file_template, "LocalScript; OnClientEvent sounds; no top-level return."
            )
        elif "Generator.server.luau" in target_norm:
            file_template = _short_tmpl(
                file_template,
                'Map/Checkpoints/Coins folders; Instance.new("SpawnLocation") NEVER Part-rename; '
                'Name="Checkpoint"..id; print section ids.',
            )
        elif "Coins.server.luau" in target_norm:
            file_template = _short_tmpl(
                file_template,
                f"{EXACT_COPY_INSTRUCTION} "
                "You MUST use Players:GetPlayerFromCharacter(char) to find the player. "
                "You MUST call coin:Destroy() and FireAllClients UpdateLeaderboard. "
                "You MUST use task.wait(). "
                "Destroy coin ONLY here; player attrs; FireClient CoinCollected; ChildAdded. "
                "Target MUST be -> src/server/Gameplay/Coins.server.luau",
            )
        elif "LevelConfig.luau" in target_norm:
            file_template = _short_tmpl(
                file_template, "return { { id = n, gap = g, coins = c }, ... } Luau `=` only."
            )
        elif "HUD.client.luau" in target_norm:
            file_template = _short_tmpl(
                file_template,
                'ScreenGui; ALWAYS player:GetAttribute("Coins") NEVER character:GetAttribute; CharacterAdded.',
            )
        elif "Leaderboard.client.luau" in target_norm:
            file_template = _short_tmpl(
                file_template, "create UI; UpdateLeaderboard only — no LeaderboardFrame."
            )
        elif "Void.server.luau" in target_norm or "Puzzles.server.luau" in target_norm:
            pass  # already short rules blocks

    # HARD CAPS - repeated mistakes from 14B Generator/HUD/Checkpoints (A19.0 / A22.0 / A26 / A31)
    hard_caps = """HARD CAPS (NEVER violate - validator CRITICAL FAIL):
- NEVER use LocalPlayer in .server.luau files. LocalPlayer is client-only. Use Players.PlayerAdded or GetPlayerFromCharacter.
- NEVER use character:GetAttribute("Coins"). ALWAYS use player:GetAttribute("Coins").
- NEVER use Remotes.CoinsCollected. The remote is exactly Remotes.CoinCollected.
- NEVER destroy Coins in Checkpoints.server.luau. Coins must only be destroyed in Coins.server.luau.
- Spawn MUST be created with Instance.new("SpawnLocation"). NEVER use Instance.new("Part") and rename it to SpawnLocation.
- NEVER use BreakJoints. Use Humanoid.Health = 0 if you need to kill, but prefer not to kill at all.
- Checkpoints: SetAttribute("Checkpoint", idx) where idx is a number (tonumber(match)), NEVER a Part/Instance.
- Checkpoints.server.luau MUST NOT use DataStoreService. DataStore is ONLY for datastore_service archetype.
- Remotes.luau: NEVER set Remotes = folder. ALWAYS return a TABLE of RemoteEvent refs via getOrCreate. MUST include CheckpointReached + CoinCollected."""

    remotes_strict = (
        "Remotes.luau STRICT: NEVER Remotes = folder; ALWAYS "
        "`local Remotes = { Checkpoint=getOrCreate(...), CheckpointReached=..., "
        "UpdateLeaderboard=..., CoinCollected=... }; return Remotes`. "
        "MUST include getOrCreate + CheckpointReached + CoinCollected."
    )

    localplayer_server_rule = (
        "NEVER use LocalPlayer in .server.luau files. LocalPlayer is client-only. "
        "Use Players.PlayerAdded or GetPlayerFromCharacter."
    )

    if local_ollama:
        strict_rules = f"""STRICT (local; gameplay/client ctx<=4k):
- ONLY this task. <DONE>{task.task_id}</DONE> + <FILE> required when -> path.
- NEVER use wait(). Use task.wait(). This is a critical error.
- {localplayer_server_rule}
- server/client: no top-level return; ModuleScript: return table.
- Checkpoint.."id" (no _); {REMOTES_WAIT_RULE} never bare Remotes; LevelConfig Luau `=`; coins Destroy+FireClient.
- {remotes_strict}
- Compact code; APPEND disabled — full-file REWRITE only.
- NEVER use <<<<<<< SEARCH / ======= / >>>>>>> REPLACE. This is Cursor diff format and it will be rejected by the parser. Always output the COMPLETE file content.
{hard_caps}"""
        token_econ = "TOKEN ECONOMY: minimal comments; only code for THIS task."
    else:
        strict_rules = f"""STRICT RULES:
- Do ONLY this one task. Do not touch other tasks.
- Do NOT block due to task ordering. Prerequisites are already done.
- If task says '-> path/file.md#section', '#' is a section name, NOT part of the filename.
- No stubs, no empty TODOs. Ship playable / readable content.
- NEVER use wait(). Use task.wait(). This is a critical error.
- {localplayer_server_rule}
- *.server.luau / *.client.luau MUST NOT end with return.
- *.luau ModuleScripts MUST end with return <table>.
- You MUST include at least one <FILE path="...">...</FILE> when the task has a -> path.
- Reply MUST begin with <DONE>{task.task_id}</DONE>. Never output <BLOCKED>.
- NEVER list PlayerRespawn / PlayerRespawned as a BUG. That API is not in this project.
- For Checkpoints: Touched, SetAttribute, FireClient, Died/LoadCharacter - report only what you see.
- FILE path must be the real target (e.g. {task.target_path or "src/..."}), NEVER relative/path.ext.
- Generator: CREATE Map/Path/Spawn (Instance.new); never WaitForChild Map first.
- Generator checkpoint names: "Checkpoint" .. tostring(id) - NEVER "Checkpoint_".
- {REMOTES_WAIT_RULE} — NEVER bare ReplicatedStorage.Remotes; never return a Folder.
- {remotes_strict}
- LevelConfig: Luau `id = n` only - NEVER JavaScript `id: n`. return array for ipairs.
- Coins: coin:Destroy(); FireClient(player); FindFirstChild Coins + ChildAdded; FireAllClients UpdateLeaderboard.
- HUD: create ScreenGui; player.CharacterAdded - never bare characterAdded.
- Leaderboard: create UI; UpdateLeaderboard only - no LeaderboardFrame WaitForChild.
- Void: Heartbeat Y<-20 LoadCharacter. Puzzles: TouchEnded not .Left.
- APPEND is disabled (A27): always return COMPLETE file content — never append-only.
- NEVER use <<<<<<< SEARCH / ======= / >>>>>>> REPLACE. This is Cursor diff format and it will be rejected by the parser. Always output the COMPLETE file content.
{hard_caps}
- TOKEN ECONOMY: Do not write excessive comments. Use concise local variable names. Output only the necessary code."""
        token_econ = """TOKEN ECONOMY (local 14B ctx<=4k):
- Do not write excessive comments. Critical one-liners only.
- Use concise local variable names; keep public/contract names stable.
- Output only the necessary code for THIS task.
- Prefer Luau-compact forms; no decorative blank lines."""

    prompt = f"""You are the agent @{owner} inside Quality Forge.
You WRITE the game (Luau / design docs). A human only playtests later.
Follow AGENTS.md. Do the task for real — do not reply NOTE-only when a FILE is required.
{retry_note}
=== AGENTS.md ===
{agents}

=== PROJECT_TZ.md (compact) ===
{tz_compact}

=== Existing project files (relevant) ===
{files}
{skills_block}{assets_block}{feedback}{file_template}
=== YOUR TASK ===
{task.raw.strip()}

{mode_instructions(task, file_exists=bool(prior_snapshot), prefer_diff=False)}

{strict_rules}

{token_econ}

Format:
<DONE>{task.task_id}</DONE>
<NOTE>one short sentence</NOTE>
<FILE path="{task.target_path or "src/server/Example.server.luau"}">
complete file content here
</FILE>
(NEVER <<<<<<< SEARCH / ======= / >>>>>>> REPLACE — always COMPLETE file content)
"""
    # A17 hard fit — NEVER send oversized prompts to Ollama
    if budget is not None:
        prompt, meta = llm_backends.fit_prompt(prompt, int(budget))
        if not meta.get("ok") or llm_backends.estimate_tokens(prompt) > int(budget):
            prompt, meta = llm_backends.fit_prompt(prompt, int(budget))
        llm_backends.assert_prompt_fits(prompt, int(budget))
    return prompt

