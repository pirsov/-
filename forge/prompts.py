"""Prompt builder with context budget (fixes 39KB prompt blowups)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from .task_parser import Task, WriteMode

SKIP_NAMES = {"run.ps1", "run.py", "PROJECT_TZ.md", "AGENTS.md"}
SKIP_DIRS = {"logs", ".git", "forge", "build", ".forge", "__pycache__", "tests"}


AGENT_MODELS = {
    "game_designer": {"model": "qwen2.5-coder:7b", "ctx": 8192, "predict": 2048},
    "tech_architect": {"model": "qwen2.5-coder:7b", "ctx": 8192, "predict": 2048},
    "gameplay_programmer": {"model": "qwen2.5-coder:14b", "ctx": 8192, "predict": 4096},
    "client_programmer": {"model": "qwen2.5-coder:7b", "ctx": 8192, "predict": 3072},
    "qa_engineer": {"model": "qwen2.5-coder:7b", "ctx": 8192, "predict": 3072},
    "refactorer": {"model": "qwen2.5-coder:14b", "ctx": 8192, "predict": 4096},
    "builder": {"model": "qwen2.5-coder:7b", "ctx": 8192, "predict": 2048},
    "systems_designer": {"model": "qwen2.5-coder:7b", "ctx": 8192, "predict": 3072},
    "content_author": {"model": "qwen2.5-coder:7b", "ctx": 8192, "predict": 3072},
    "integrator": {"model": "qwen2.5-coder:14b", "ctx": 8192, "predict": 4096},
}

# Escalation ladder when a task fails repeatedly
ESCALATION = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:32b",
]


def extract_agent_section(agents_md: str, owner: str) -> str:
    universal_end = agents_md.find("## @")
    universal = agents_md[: universal_end if universal_end >= 0 else len(agents_md)]
    m = re.search(rf"(?ms)## @{re.escape(owner)}\b.*?(?=## @|\Z)", agents_md)
    section = m.group(0) if m else ""
    return universal + "\n" + section


def relevant_paths(root: Path, task: Task) -> List[Path]:
    """Prefer files related to the task; fall back to src/ + docs/ + project json."""
    picks: List[Path] = []
    seen: Set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve())
        if key in seen or not p.is_file():
            return
        seen.add(key)
        picks.append(p)

    if task.target_path:
        add(root / task.target_path)
        # siblings in same folder
        parent = (root / task.target_path).parent
        if parent.is_dir():
            for child in sorted(parent.glob("*")):
                add(child)

    # Always include remotes + project config for gameplay tasks
    for rel in (
        "default.project.json",
        "src/shared/Gameplay/Remotes.luau",
        "docs/ARCHITECTURE.md",
        "docs/GDD.md",
        "docs/QA_REPORT.md",
    ):
        add(root / rel)

    # If still sparse, include all src files
    if len(picks) < 4:
        src = root / "src"
        if src.is_dir():
            for p in sorted(src.rglob("*.luau")):
                add(p)

    return picks


def render_files(paths: Sequence[Path], root: Path, budget_chars: int = 24000) -> str:
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
            # include truncated
            remain = max(0, budget_chars - used - 80)
            if remain > 200:
                parts.append(f"=== {rel} ===\n{text[:remain]}\n...(truncated)\n\n")
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts) if parts else "(no files yet)"


def mode_instructions(task: Task) -> str:
    if task.mode == WriteMode.APPEND:
        return (
            "WRITE MODE = APPEND.\n"
            "- Return ONLY the new lines to append.\n"
            "- Do NOT repeat existing file content.\n"
            "- Do NOT rewrite the whole file.\n"
            f"- Target file: {task.target_path}\n"
        )
    if task.mode == WriteMode.REWRITE:
        return (
            "WRITE MODE = REWRITE.\n"
            "- Return the COMPLETE new file content.\n"
            f"- Target file: {task.target_path}\n"
        )
    if task.mode == WriteMode.CREATE:
        return (
            "WRITE MODE = CREATE.\n"
            "- Return the COMPLETE file content for a new/overwrite file.\n"
            f"- Target file: {task.target_path}\n"
        )
    if task.section:
        return (
            "WRITE MODE = SECTION APPEND.\n"
            f"- Append a markdown section to {task.target_path} (section #{task.section}).\n"
            "- Return only the new section body.\n"
        )
    return "WRITE MODE = NORMAL. Return complete file content for each <FILE>."


def build_prompt(
    root: Path,
    owner: str,
    task: Task,
    *,
    attempt: int = 1,
    validator_feedback: Optional[str] = None,
    prior_snapshot: Optional[str] = None,
) -> str:
    agents = extract_agent_section((root / "AGENTS.md").read_text(encoding="utf-8"), owner)
    tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
    # Shrink TZ: keep legend + pending tasks + recent DONE notes
    tz_lines = tz.splitlines()
    compact: List[str] = []
    for i, line in enumerate(tz_lines):
        if i < 12 or line.startswith("#") or line.startswith("##") or "- [ ]" in line:
            compact.append(line)
        elif "- [x]" in line or "- [-]" in line:
            compact.append(line)
    tz_compact = "\n".join(compact)
    files = render_files(relevant_paths(root, task), root)

    feedback = ""
    if validator_feedback:
        feedback = f"\n=== VALIDATOR FEEDBACK (fix this) ===\n{validator_feedback}\n"
    if prior_snapshot and task.mode == WriteMode.APPEND:
        feedback += (
            f"\n=== CURRENT FILE CONTENT (append AFTER this, do not repeat) ===\n"
            f"{prior_snapshot}\n"
        )

    retry_note = ""
    if attempt > 1:
        retry_note = (
            f"\nThis is attempt {attempt}. Previous output was rejected. "
            "Follow the format EXACTLY. Begin with <DONE>. Include <FILE> tags.\n"
        )

    return f"""You are the agent @{owner}. Follow AGENTS.md protocol exactly.
{retry_note}
=== AGENTS.md ===
{agents}

=== PROJECT_TZ.md (compact) ===
{tz_compact}

=== Existing project files (relevant) ===
{files}
{feedback}
=== YOUR TASK ===
{task.raw.strip()}

{mode_instructions(task)}

STRICT RULES:
- Do ONLY this one task. Do not touch other tasks.
- Do NOT block due to task ordering. Prerequisites are already done.
- If task says '-> path/file.md#section', '#' is a section name, NOT part of the filename.
- No stubs, no TODOs. Real, complete content.
- You already have needed files above. Do NOT say you need to read files.
- FILE path must be an actual FILE with extension. Never a directory.
- NEVER use wait() — always task.wait().
- *.server.luau / *.client.luau MUST NOT end with return.
- *.luau ModuleScripts MUST end with return <table>.
- You MUST include at least one <FILE path="...">...</FILE> when the task has a → path.
- Reply MUST begin with <DONE>{task.task_id}</DONE>. Never output <BLOCKED>.

Format:
<DONE>{task.task_id}</DONE>
<NOTE>one short sentence</NOTE>
<FILE path="relative/path.ext">
file content
</FILE>
"""
