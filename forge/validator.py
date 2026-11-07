"""Static validator for generated Roblox/Luau and project files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple


def validate_file(path: Path) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    name = path.name
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, [f"cannot read file: {e}"]

    if not content or len(content.strip()) < 10:
        errors.append("empty or nearly empty file")

    # QA hallucination guard: old report invented PlayerRespawn — reject copy-paste
    if name == "QA_REPORT.md" and re.search(r"PlayerRespawn", content):
        errors.append("QA_REPORT cites PlayerRespawn (not in sources) — re-read actual .luau files")
    if name == "QA_REPORT.md" and not re.search(r"(?im)^##\s*SCORE", content):
        errors.append("QA_REPORT missing ## SCORE section")

    if re.search(r"\.(server|client)\.luau$", name):
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if lines and re.match(r"^return\s", lines[-1].strip()):
            errors.append("top-level return in Script/LocalScript")

    if name.endswith(".luau") and not re.search(r"\.(server|client)\.luau$", name):
        # Allow multi-line `return { ... }` — require a top-level return statement
        if not re.search(r"(?m)^return\b", content):
            errors.append("ModuleScript must end with return")

    forbidden = [
        (r"game\.Players\.PlayerRespawned", "PlayerRespawned does not exist"),
        (r":BreakJoints\(\)", "BreakJoints is deprecated"),
        (r"Humanoid\.Parent\s*=\s*nil", "setting Humanoid.Parent=nil breaks character"),
        (r"Humanoid\.Health\s*=\s*0", "killing player (Humanoid.Health=0) not allowed"),
        (r"require\([^)]*ReplicatedStorage[^)]*src\.", "wrong require path (src.* not in ReplicatedStorage)"),
        (r"(?<![\w.])wait\s*\(", "use task.wait, not wait"),
    ]
    for pat, msg in forbidden:
        if re.search(pat, content):
            errors.append(msg)

    if "APPEND" not in content:  # balance only for code-ish files
        if path.suffix in {".luau", ".lua", ".json", ".ps1", ".py"} or name.endswith(".luau"):
            opens = content.count("(")
            closes = content.count(")")
            if abs(opens - closes) > 2:
                errors.append(f"unbalanced parentheses ({opens} vs {closes})")

    # Integrity: referenced locals must be defined for common broken APPEND residue
    if name.endswith(".luau"):
        if re.search(r"\bfolder\b", content) and not re.search(
            r"\blocal\s+folder\b|folder\s*=", content
        ):
            errors.append("uses 'folder' but never defines it (likely APPEND overwrite)")
        if re.search(r"\bRemotes\b", content) and not re.search(
            r"\blocal\s+Remotes\b|Remotes\s*=", content
        ):
            if "getOrCreate" not in content:
                errors.append("uses 'Remotes' but never defines it (likely APPEND overwrite)")
        if re.search(r"\bscreen\b", content) and name.endswith(".client.luau"):
            if not re.search(r"\blocal\s+screen\b|screen\s*=", content):
                errors.append("uses 'screen' but never defines it (likely APPEND overwrite)")
        if re.search(r"\bPlayers\b", content) and not re.search(
            r"GetService\(\s*[\"']Players[\"']\s*\)|local\s+Players\b", content
        ):
            if "LocalPlayer" in content or "PlayerAdded" in content or "GetPlayerFromCharacter" in content:
                errors.append("uses Players service without GetService")

    return len(errors) == 0, errors


def validate_project_integrity(root: Path) -> Tuple[bool, List[str]]:
    """Cross-file integrity checks for the Rojo game tree."""
    errors: List[str] = []
    remotes = root / "src/shared/Gameplay/Remotes.luau"
    if remotes.exists():
        text = remotes.read_text(encoding="utf-8")
        for need in ("getOrCreate", "CheckpointReached", "return"):
            if need not in text:
                errors.append(f"Remotes.luau missing '{need}'")
        if "top-level return" not in " ".join(errors):
            ok, errs = validate_file(remotes)
            if not ok:
                errors.extend(f"Remotes: {e}" for e in errs)

    for rel in (
        "src/server/Level/Generator.server.luau",
        "src/server/Gameplay/Checkpoints.server.luau",
        "src/client/HUD.client.luau",
        "src/client/Effects.client.luau",
        "src/server/Data/PlayerData.server.luau",
    ):
        p = root / rel
        if not p.exists():
            errors.append(f"missing {rel}")
            continue
        ok, errs = validate_file(p)
        if not ok:
            errors.extend(f"{rel}: {e}" for e in errs)

    return len(errors) == 0, errors
