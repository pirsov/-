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
_FALLBACK_ROLE = {"model": "qwen2.5-coder:14b-4k", "ctx": 4096, "predict": 4096}
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
    """Prefer files related to the task; QA/refactor always get all src/*.luau first."""
    picks: List[Path] = []
    seen: Set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve())
        if key in seen or not p.is_file():
            return
        seen.add(key)
        picks.append(p)

    # Roles that MUST see game code (P30.1 failed because only docs were included)
    needs_all_src = owner in {
        "qa_engineer",
        "refactorer",
        "integrator",
        "gameplay_programmer",
        "client_programmer",
    } or any(
        k in (task.description or "").lower()
        for k in ("qa", "static review", "fix", "integrity", "score")
    )

    src = root / "src"
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


def file_budget_chars() -> int:
    """Cloud 1M-ctx backends can take full src/; local Ollama stays tight."""
    try:
        from . import llm

        if llm.backend_name() in {"spacebunny", "openrouter"}:
            return int(
                (SPACEBUNNY_CFG.get("file_budget") if llm.backend_name() == "spacebunny" else None)
                or (OPENROUTER_CFG.get("file_budget") if llm.backend_name() == "openrouter" else None)
                or 180_000
            )
    except Exception:
        pass
    return 24_000


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
    tz_lines = tz.splitlines()
    compact: List[str] = []
    for i, line in enumerate(tz_lines):
        if i < 12 or line.startswith("#") or line.startswith("##") or "- [ ]" in line:
            compact.append(line)
        elif "- [x]" in line or "- [-]" in line:
            compact.append(line)
    tz_compact = "\n".join(compact)
    files = render_files(relevant_paths(root, task, owner), root)

    feedback = ""
    if validator_feedback:
        feedback = f"\n=== VALIDATOR FEEDBACK (fix this) ===\n{validator_feedback}\n"
    if prior_snapshot and task.mode == WriteMode.APPEND:
        feedback += (
            f"\n=== CURRENT FILE CONTENT (append AFTER this, do not repeat) ===\n"
            f"{prior_snapshot}\n"
        )
    elif prior_snapshot and task.mode in {WriteMode.REWRITE, WriteMode.CREATE}:
        feedback += (
            "\n=== BASELINE FILE (REWRITE from THIS — do not invent a new architecture) ===\n"
            "Preserve: Map folder, Name=\"Path\" floor, SpawnPlaza, SpawnLocation, "
            'checkpoint Name = "Checkpoint" .. tostring(id) (NO underscore), coins, print section ids.\n'
            "Only apply the task delta (e.g. add Obstacle parts).\n"
            f"{prior_snapshot}\n"
        )

    retry_note = ""
    if attempt > 1:
        retry_note = (
            f"\nThis is attempt {attempt}. Previous output was rejected. "
            "Follow the format EXACTLY. Begin with <DONE>. Include <FILE> tags.\n"
        )

    return f"""You are the agent @{owner} inside Quality Forge.
You WRITE the game (Luau / design docs). A human only playtests later.
Follow AGENTS.md. Do the task for real — do not reply NOTE-only when a FILE is required.
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
- No stubs, no empty TODOs. Ship playable / readable content.
- NEVER use wait() — always task.wait().
- *.server.luau / *.client.luau MUST NOT end with return.
- *.luau ModuleScripts MUST end with return <table>.
- You MUST include at least one <FILE path="...">...</FILE> when the task has a → path.
- Reply MUST begin with <DONE>{task.task_id}</DONE>. Never output <BLOCKED>.
- NEVER list PlayerRespawn / PlayerRespawned as a BUG. That API is not in this project.
- For Checkpoints: Touched, SetAttribute, FireClient, Died/LoadCharacter — report only what you see.
- FILE path must be the real target (e.g. {task.target_path or "src/..."}), NEVER relative/path.ext.
- Keep Map/Path + Spawn if editing Generator; extend, do not delete the floor.
- Generator checkpoint names: "Checkpoint" .. tostring(id) — NEVER "Checkpoint_".
- Remotes: require Gameplay.Remotes ModuleScript; never return a Folder.

Format:
<DONE>{task.task_id}</DONE>
<NOTE>one short sentence</NOTE>
<FILE path="{task.target_path or "src/server/Example.server.luau"}">
file content
</FILE>
"""
