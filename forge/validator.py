"""Static validator for generated Roblox/Luau and project files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple


_STUB_MARKERS = (
    r"--\s*Respawn logic here",
    r"--\s*Update checkpoint data here",
    r"--\s*Handle checkpoint logic",
    r"--\s*TODO\b",
    r"--\s*real code here",
    r"\bpass\s*--\s*implement",
)


def validate_file(path: Path) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    name = path.name
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, [f"cannot read file: {e}"]

    if not content or len(content.strip()) < 10:
        errors.append("empty or nearly empty file")

    # QA hallucination guard: only reject if PlayerRespawn is claimed as a real bug.
    # Allow warnings like "FALSE POSITIVES — PlayerRespawn" / "Do NOT invent PlayerRespawn".
    if name == "QA_REPORT.md":
        for line in content.splitlines():
            if "PlayerRespawn" not in line:
                continue
            is_bug = re.search(r"\[(CRIT|HIGH|MED|LOW)\]", line) is not None
            is_disclaimer = re.search(
                r"(?i)false\s*positive|ignore|not real|do not|don't|never invent|not in (the )?sources|hallucin",
                line,
            )
            if is_bug and not is_disclaimer:
                errors.append(
                    "QA_REPORT lists PlayerRespawn as a bug — that remote/API is not in sources"
                )
                break
        # Accept ## SCORE / # SCORE / SCORE: 86 / **SCORE**
        if not re.search(
            r"(?im)^(?:#{1,3}\s*SCORE\b|\*\*SCORE\*\*\s*:?|SCORE\s*[:：]\s*\d+)",
            content,
        ):
            errors.append(
                "QA_REPORT missing ## SCORE section "
                "(need a heading '## SCORE' and a number 0-100)"
            )
        elif not re.search(r"(?im)(?:overall\s*:\s*\d{1,3}|\bSCORE\b[^\n]*\b(\d{1,3})\b)", content):
            if not re.search(r"(?im)^##\s*SCORE\s*$[\s\S]{0,80}?\b(\d{1,3})\b", content):
                errors.append("QA_REPORT ## SCORE must include a numeric score 0-100")

    if re.search(r"\.(server|client)\.luau$", name):
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if lines and re.match(r"^return\s", lines[-1].strip()):
            errors.append("top-level return in Script/LocalScript")

    if name.endswith(".luau") and not re.search(r"\.(server|client)\.luau$", name):
        if not re.search(r"(?m)^return\b", content):
            errors.append("ModuleScript must end with return")
        # Remotes module must return a TABLE of events, not a Folder Instance
        if name == "Remotes.luau":
            if re.search(r"(?m)^return\s+Remotes\s*$", content):
                errors.append("Remotes.luau must return { Checkpoint=..., ... } table, not Folder")
            if "getOrCreate" not in content and "FindFirstChild" not in content:
                errors.append("Remotes.luau must create-or-reuse RemoteEvents (getOrCreate/FindFirstChild)")
            if "CheckpointReached" not in content:
                errors.append("Remotes.luau missing CheckpointReached")
            # Dead code after first top-level return (classic failed APPEND)
            returns = list(re.finditer(r"(?m)^return\b", content))
            if len(returns) > 1:
                errors.append("Remotes.luau has multiple top-level return — APPEND corrupted file")

    forbidden = [
        (r"game\.Players\.PlayerRespawned", "PlayerRespawned does not exist"),
        (r"Remotes\.PlayerRespawn\b", "PlayerRespawn remote is not in the contract — do not invent it"),
        (r":BreakJoints\(\)", "BreakJoints is deprecated"),
        (r"Humanoid\.Parent\s*=\s*nil", "setting Humanoid.Parent=nil breaks character"),
        (r"Humanoid\.Health\s*=\s*0", "killing player (Humanoid.Health=0) not allowed"),
        (r"require\([^)]*ReplicatedStorage[^)]*src\.", "wrong require path (src.* not in ReplicatedStorage)"),
        (r"(?<![\w.])wait\s*\(", "use task.wait, not wait"),
        (r"CheckpointReached\.OnServerEvent", "CheckpointReached is Server→Client; use FireClient, not OnServerEvent"),
    ]
    for pat, msg in forbidden:
        if re.search(pat, content):
            errors.append(msg)

    for pat in _STUB_MARKERS:
        if re.search(pat, content, re.I):
            errors.append("stub/placeholder comment — write real code")
            break

    if name.endswith(".luau"):
        opens = content.count("(")
        closes = content.count(")")
        if abs(opens - closes) > 2:
            errors.append(f"unbalanced parentheses ({opens} vs {closes})")

    if name.endswith(".luau"):
        if re.search(r"\bfolder\b", content) and not re.search(
            r"\blocal\s+folder\b|\bfolder\s*=", content
        ):
            errors.append("uses 'folder' but never defines it (likely APPEND overwrite)")

        # Only flag undefined Remotes when used as a local identifier (Remotes.X),
        # not when it appears as a path segment (ReplicatedStorage.Remotes.X).
        if re.search(r"(?<![\w.])Remotes\.", content) and not re.search(
            r"\blocal\s+Remotes\b", content
        ):
            errors.append("uses Remotes. without `local Remotes = ...`")

        if name.endswith(".client.luau"):
            code_only = re.sub(r"--[^\n]*", "", content)
            # Match identifier `screen`, not flashScreen / screenGui / comment "Flash screen"
            if re.search(r"(?<![A-Za-z_])screen(?![A-Za-z_])", code_only):
                if not re.search(r"\blocal\s+screen\b|\bscreen\s*=", code_only):
                    errors.append("uses 'screen' but never defines it (likely APPEND overwrite)")
        if (
            re.search(r"PlayerAdded|GetPlayerFromCharacter|LocalPlayer", content)
            and not re.search(r"GetService\(\s*[\"']Players[\"']\s*\)", content)
            and not re.search(r"\blocal\s+Players\b", content)
        ):
            errors.append("uses Players service without GetService")

    # Generator must keep walkable map + CheckpointN naming (not Checkpoint_N)
    if name == "Generator.server.luau":
        if "SpawnLocation" not in content and "SpawnPlaza" not in content:
            errors.append("Generator must create SpawnLocation or SpawnPlaza")
        if not re.search(r'Name\s*=\s*["\']Path["\']', content) and 'Name = "Path"' not in content:
            if "Map" not in content or "Path" not in content:
                errors.append("Generator must keep Map Path floor (Name = \"Path\")")
        if re.search(r'Name\s*=\s*["\']Checkpoint_["\']', content) or re.search(
            r'Checkpoint_"\s*\.\.', content
        ):
            errors.append('Checkpoint parts must be named "Checkpoint"..id (no underscore)')
        if "Obstacle" not in content and "obstacle" not in content.lower():
            # soft: only when file is a full rewrite that claims obstacles — enforced by tasks
            pass

    # Checkpoints must keep touch + death wiring with a *numeric* checkpoint index
    if name == "Checkpoints.server.luau":
        if "Touched" not in content:
            errors.append("Checkpoints.server.luau missing Touched handlers")
        if "Died" not in content and "LoadCharacter" not in content:
            errors.append("Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling")
        # Must store a number index, not a BasePart Instance
        if not re.search(
            r'SetAttribute\(\s*["\']Checkpoint["\']\s*,\s*(idx|index|checkpointIndex|n)\s*\)',
            content,
        ):
            errors.append(
                "Checkpoints must SetAttribute(\"Checkpoint\", idx) with a number — "
                "not a Part/Instance"
            )
        if re.search(r'SetAttribute\(\s*["\']Checkpoint["\']\s*,\s*cp\s*\)', content):
            errors.append("SetAttribute(\"Checkpoint\", cp) is wrong — pass numeric idx")
        if "FireClient" not in content:
            errors.append("Checkpoints.server.luau must FireClient CheckpointReached")
        # Teleport must resolve CheckpointN from workspace folder
        if not re.search(r'FindFirstChild\(\s*["\']Checkpoint["\']\s*\.\.', content) and not re.search(
            r'FindFirstChild\(\s*["\']Checkpoint["\'].*idx|FindFirstChild\(\s*"Checkpoint"\s*\.\.\s*tostring',
            content,
        ):
            if not re.search(r'Checkpoint"\s*\.\.\s*|Checkpoint\'\s*\.\.\s*|Checkpoint"\s*\.\.\s*tostring', content):
                errors.append("Checkpoints teleport must FindFirstChild(\"Checkpoint\"..idx)")
        # Reject module-style return (Script, not ModuleScript)
        if re.search(r"(?m)^return\s+Checkpoints\s*$", content):
            errors.append("Checkpoints.server.luau must not return a table (it is a Script)")
        # Common broken Touched: treat character as checkpoint part
        if re.search(
            r"onCheckpointTouched|Touched:Connect",
            content,
        ) and re.search(r"local\s+cp\s*=\s*hit\.Parent", content):
            errors.append(
                "Touched handler bug: hit is the touching limb; checkpoint is `part`/`child`, not hit.Parent"
            )

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
        ok, errs = validate_file(remotes)
        if not ok:
            errors.extend(f"Remotes: {e}" for e in errs)

    for rel in (
        "src/server/Level/Generator.server.luau",
        "src/server/Gameplay/Checkpoints.server.luau",
        "src/server/Gameplay/Coins.server.luau",
        "src/server/Gameplay/Void.server.luau",
        "src/server/Gameplay/Puzzles.server.luau",
        "src/client/HUD.client.luau",
        "src/client/Effects.client.luau",
        "src/server/Data/PlayerData.server.luau",
        "src/shared/Content/LevelConfig.luau",
    ):
        p = root / rel
        if not p.exists():
            errors.append(f"missing {rel}")
            continue
        ok, errs = validate_file(p)
        if not ok:
            errors.extend(f"{rel}: {e}" for e in errs)

    return len(errors) == 0, errors
