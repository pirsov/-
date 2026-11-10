"""A7.2 Plugin skeleton archetypes — versioned loaders + META checks."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
SKELETONS_DIRNAME = "skeletons"
REGISTRY_NAME = "registry.json"


def skeletons_root(root: Optional[Path] = None) -> Path:
    return (root or ROOT_DEFAULT) / SKELETONS_DIRNAME


def load_registry(root: Optional[Path] = None) -> Dict[str, Any]:
    p = skeletons_root(root) / REGISTRY_NAME
    if not p.is_file():
        return {"version": 1, "archetypes": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "archetypes": {}, "corrupt": True}
    return data if isinstance(data, dict) else {"version": 1, "archetypes": {}}


def list_archetypes(root: Optional[Path] = None) -> List[Dict[str, str]]:
    reg = load_registry(root)
    out: List[Dict[str, str]] = []
    for aid, meta in (reg.get("archetypes") or {}).items():
        if not isinstance(meta, dict):
            continue
        out.append(
            {
                "id": aid,
                "latest": str(meta.get("latest") or "v1"),
                "summary": str(meta.get("summary") or ""),
                "versions": ",".join(str(v) for v in (meta.get("versions") or [])),
            }
        )
    return sorted(out, key=lambda x: x["id"])


def catalog_for_prompt(root: Optional[Path] = None, *, max_chars: int = 600) -> str:
    lines = ["Archetypes:"]
    for a in list_archetypes(root):
        lines.append(f"- {a['id']}@{a['latest']}: {a['summary']}")
    text = "\n".join(lines)
    return text[:max_chars]


def resolve_version(
    archetype: str,
    version: Optional[str] = None,
    root: Optional[Path] = None,
) -> str:
    reg = load_registry(root)
    meta = (reg.get("archetypes") or {}).get(archetype) or {}
    if version:
        versions = [str(v) for v in (meta.get("versions") or [])]
        if versions and version not in versions:
            # still allow path if folder exists
            pass
        return version
    return str(meta.get("latest") or "v1")


def archetype_dir(archetype: str, version: str, root: Optional[Path] = None) -> Path:
    return skeletons_root(root) / archetype / version


def load_meta(
    archetype: str,
    version: Optional[str] = None,
    root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    ver = resolve_version(archetype, version, root)
    p = archetype_dir(archetype, ver, root) / "META.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data.setdefault("id", archetype)
        data.setdefault("version", ver)
        return data
    return None


def load_skeleton_text(
    archetype: str,
    version: Optional[str] = None,
    root: Optional[Path] = None,
    *,
    max_chars: int = 500,
) -> str:
    ver = resolve_version(archetype, version, root)
    p = archetype_dir(archetype, ver, root) / "SKELETON.luau"
    if not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8")
    meta = load_meta(archetype, ver, root) or {}
    # META prompt_budget_chars wins when set (A10.2 CoinSync must fit in bundle)
    budget = int(meta.get("prompt_budget_chars") or max_chars)
    return text[:budget]


# A23.0: non-UI LocalScripts (sounds/camera/VFX) vs UI LocalScripts (HUD/menu).
_CLIENT_SCRIPT_TOKENS = (
    "effect",
    "effects",
    "sound",
    "sounds",
    "sfx",
    "vfx",
    "camera",
    "cam",
    "ambience",
    "ambient",
)
_CLIENT_UI_TOKENS = (
    "hud",
    "menu",
    "button",
    "buttons",
    "ui",
    "gui",
    "leaderboard",
    "shop",
    "donation",
    "panel",
    "frame",
)


def client_archetype_from_name(name: str) -> str:
    """
    A23.0: route *.client.luau by filename tokens.
    sound/camera/effects → client_script; buttons/menu/HUD/UI → client_ui.
    Default client_ui (preserves prior A18.1 behaviour for unlabeled clients).
    """
    lower = name.lower()
    # Strip extension for token scan
    stem = lower
    for suf in (".client.luau", ".luau"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    # Prefer UI when both match (e.g. SoundMenu.client.luau)
    if any(tok in stem for tok in _CLIENT_UI_TOKENS):
        return "client_ui"
    if any(tok in stem for tok in _CLIENT_SCRIPT_TOKENS):
        return "client_script"
    return "client_ui"


def hard_archetype_from_path(path: Path) -> Optional[str]:
    """
    A18.1/A23.0/A24.0: HARD-map Roblox Script filenames to Script skeletons.
    *.server.luau → server_script (or datastore_service / init_remotes by name).
    *.client.luau → client_script (effects/camera/sound) or client_ui (HUD/menu/UI).
    Never shared_data / ModuleScript for these extensions.
    """
    name = path.name
    lower = name.lower()
    if name.endswith(".server.luau"):
        if "initremotes" in lower.replace("_", "").replace("-", ""):
            return "init_remotes"
        if any(token in lower for token in ("playersave", "datastore")):
            return "datastore_service"
        return "server_script"
    if name.endswith(".client.luau"):
        return client_archetype_from_name(name)
    return None


def infer_archetype_from_path(path: Path) -> Optional[str]:
    s = str(path).replace("\\", "/")
    name = path.name
    if name == "Remotes.luau" or "/Gameplay/Remotes" in s:
        return "network_remote"
    hard = hard_archetype_from_path(path)
    if hard:
        return hard
    if "/src/client/" in s:
        return client_archetype_from_name(name)
    # Persist/save scripts before generic server_script (which forbids DataStore).
    lower = name.lower()
    if "initremotes" in lower.replace("_", "").replace("-", ""):
        return "init_remotes"
    if any(token in lower for token in ("playersave", "datastore")):
        return "datastore_service"
    if "/src/server/" in s:
        return "server_script"
    if "/src/shared/" in s or name.endswith("Config.luau"):
        return "shared_data"
    return None


def find_contract_pin(root: Path, path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Look up archetype + skeleton_version from contracts matching this file/plugin.
    Prefers exact relative path matches over fuzzy filename hits (A10.2).
    Returns (archetype, version) or (None, None).
    Score must be > 0 — a bare archetype on an unrelated contract must never win
    (A18.1: Void.server.luau was wrongly pinned to shared_data/datastore via score=0).
    """
    contracts = root / "contracts"
    if not contracts.is_dir():
        return None, None
    name = path.name
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix().replace("\\", "/")

    best: Tuple[Optional[str], Optional[str]] = (None, None)
    best_score = 0  # require score > 0 to accept a pin
    for p in contracts.glob("*.json"):
        if p.parent.name == "golden":
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        snap = payload.get("contract_snapshot") if isinstance(payload.get("contract_snapshot"), dict) else payload
        arch = payload.get("archetype") or (snap.get("archetype") if isinstance(snap, dict) else None)
        ver = payload.get("skeleton_version") or (snap.get("skeleton_version") if isinstance(snap, dict) else None)
        if not arch:
            continue
        files = []
        if isinstance(snap, dict):
            files = list(snap.get("files") or [])
        # Prefer explicit path / files[] — snap.name alone is a label, not a path pin
        # (A18.1: avoid treating contract_snapshot.name as a file match unless it looks like a path).
        path_field = payload.get("path") or (snap.get("path") if isinstance(snap, dict) else None)
        if path_field:
            files.append(str(path_field))
        snap_name = snap.get("name") if isinstance(snap, dict) else None
        if isinstance(snap_name, str) and ("/" in snap_name or snap_name.endswith(".luau")):
            files.append(snap_name)

        score = 0
        for f in files:
            fp = str(f).replace("\\", "/")
            if rel == fp or rel.endswith("/" + fp) or rel.endswith(fp):
                score = max(score, 100 + len(fp))
            elif fp.endswith(name) or name in fp:
                score = max(score, 20)

        stem = p.stem.lower()
        if score == 0 and name.replace(".server.luau", "").replace(".client.luau", "").replace(".luau", "") in p.stem:
            score = 5
        if name.lower().startswith("hud") and "hud" in stem:
            score = max(score, 8)
        # Prefer live game Remotes only when path is under src/
        if name == "Remotes.luau" and "remote" in stem and "/src/" in rel:
            score = max(score, 15)
        if name == "LevelConfig.luau" and ("levelconfig" in stem or "shared" in stem):
            score = max(score, 8)
        if name.endswith(".server.luau"):
            base = name[: -len(".server.luau")].lower()
            if base == "playersave" and ("player_save" in stem or "playersave" in stem):
                score = max(score, 25)
            if base == "playerdata" and ("player_data" in stem or "playerdata" in stem):
                score = max(score, 25)

        if score > best_score:
            best_score = score
            best = (str(arch), str(ver) if ver else None)
    return best


# Script-compatible archetypes (never ModuleScript shared_data for *.server/*.client)
_SERVER_OK = frozenset({"server_script", "datastore_service", "init_remotes"})
_CLIENT_OK = frozenset({"client_ui", "client_script"})


def resolve_archetype_for_path(
    path: Path,
    root: Path,
    *,
    archetype: Optional[str] = None,
    version: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve skeleton archetype with A18.1/A23.0/A24.0 extension HARD-map.
    *.server.luau NEVER validates as shared_data.
    InitRemotes* → init_remotes (no Player/Workspace mandate).
    *.client.luau → client_script (effects/camera/sound) or client_ui (HUD/menu/UI).
    Explicit datastore_service pins (DonationShop / PlayerSave) still win.
    """
    pinned_a, pinned_v = find_contract_pin(root, path)
    hard = hard_archetype_from_path(path)
    name = path.name

    if name.endswith(".server.luau"):
        # Compatible explicit override (tests) or datastore / InitRemotes pin
        if archetype in _SERVER_OK:
            return str(archetype), version or (
                pinned_v if pinned_a == archetype else None
            )
        if pinned_a == "init_remotes" or hard == "init_remotes":
            return "init_remotes", version or (
                pinned_v if pinned_a == "init_remotes" else None
            )
        if pinned_a == "datastore_service" or hard == "datastore_service":
            return "datastore_service", version or (
                pinned_v if pinned_a == "datastore_service" else None
            )
        # Force server_script — ignore shared_data / client_ui / network pins
        return "server_script", version or (
            pinned_v if pinned_a == "server_script" else None
        )

    if name.endswith(".client.luau"):
        # Explicit compatible override (tests / callers)
        if archetype in _CLIENT_OK:
            return str(archetype), version or (
                pinned_v if pinned_a == archetype else None
            )
        # A23.0: path HARD-map wins over stale client_ui pins on Effects/camera
        if hard in _CLIENT_OK:
            return hard, version or (pinned_v if pinned_a == hard else None)
        if pinned_a in _CLIENT_OK:
            return pinned_a, version or pinned_v
        return "client_ui", None

    arch = archetype or pinned_a or infer_archetype_from_path(path)
    ver = version or pinned_v
    return arch, ver


def is_skeleton_routing_failure(path: Path, errors: List[str]) -> bool:
    """
    True when validator failure is a skeleton routing bug (wrong archetype /
    ModuleScript `return` required on a Script). 7B cannot fix this — park failed_repair.
    """
    if not errors:
        return False
    name = Path(path).name
    hard = hard_archetype_from_path(Path(name))
    joined = "\n".join(str(e) for e in errors)
    low = joined.lower()
    if "skeleton mismatch" in low or "wrong skeleton" in low:
        return True
    if not (name.endswith(".server.luau") or name.endswith(".client.luau") or hard):
        return False
    # ModuleScript contract applied to a Script → wants top-level return
    if "missing required `return`" in low or "missing required return" in low:
        return True
    for e in errors:
        m = re.search(r"\[skeleton\s+([a-z0-9_]+)@", str(e), re.I)
        if not m:
            continue
        labeled = m.group(1).lower()
        if labeled == "shared_data":
            return True
        if hard == "server_script" and labeled not in _SERVER_OK:
            return True
        if hard == "datastore_service" and labeled not in _SERVER_OK:
            return True
        if hard == "init_remotes" and labeled not in _SERVER_OK:
            return True
        # Wrong server sub-archetype (e.g. server_script Player mandate on InitRemotes)
        if hard in _SERVER_OK and labeled in _SERVER_OK and labeled != hard:
            return True
        if hard in _CLIENT_OK and labeled not in _CLIENT_OK:
            return True
        # Wrong client sub-archetype (e.g. client_ui ScreenGui rules on Effects)
        if hard in _CLIENT_OK and labeled in _CLIENT_OK and labeled != hard:
            return True
    return False


def _strip_luau_comments(content: str) -> str:
    """Remove -- line comments so forbid_regex does not match documentation."""
    return re.sub(r"--[^\n]*", "", content)


def apply_meta_checks(content: str, meta: Dict[str, Any], *, label: str = "") -> List[str]:
    """Run META required/forbid checks against file content."""
    errors: List[str] = []
    prefix = f"[skeleton {label}] " if label else "[skeleton] "
    code = _strip_luau_comments(content)

    for req in meta.get("required") or []:
        if str(req) not in code:
            errors.append(f"{prefix}missing required `{req}`")

    for group in meta.get("required_any") or []:
        if not isinstance(group, list) or not group:
            continue
        if not any(str(x) in code for x in group):
            errors.append(f"{prefix}missing any of {group}")

    for bad in meta.get("forbid") or []:
        if str(bad) and str(bad) in code:
            errors.append(f"{prefix}forbidden `{bad}`")

    for pat in meta.get("forbid_regex") or []:
        try:
            if re.search(str(pat), code):
                errors.append(f"{prefix}forbidden pattern /{pat}/")
        except re.error as e:
            errors.append(f"{prefix}bad forbid_regex: {e}")

    for pat in meta.get("require_regex") or []:
        try:
            if not re.search(str(pat), code):
                errors.append(f"{prefix}missing pattern /{pat}/")
        except re.error as e:
            errors.append(f"{prefix}bad require_regex: {e}")

    return errors


def validate_against_skeleton(
    path: Path,
    content: str,
    root: Path,
    *,
    archetype: Optional[str] = None,
    version: Optional[str] = None,
) -> List[str]:
    """
    Pin-by-contract + A18.1/A23.0/A24.0 extension HARD-map.
    *.server.luau → server_script / init_remotes / datastore_service (never shared_data).
    *.client.luau → client_script (effects/camera/sound) or client_ui (HUD/menu/UI).
    """
    arch, ver = resolve_archetype_for_path(
        path, root, archetype=archetype, version=version
    )
    if not arch:
        return []
    # Soft-skip when this root has no skeletons registry (unit fixtures)
    if not (skeletons_root(root) / REGISTRY_NAME).is_file():
        return []
    meta = load_meta(arch, ver, root)
    if not meta:
        if version or archetype:
            return [f"[skeleton] META not found for {arch}@{ver or 'latest'}"]
        return []
    label = f"{meta.get('id')}@{meta.get('version')}"
    return apply_meta_checks(content, meta, label=label)


def inject_skeleton_block(
    archetype: str,
    version: Optional[str] = None,
    root: Optional[Path] = None,
    *,
    max_chars: int = 500,
) -> str:
    text = load_skeleton_text(archetype, version, root, max_chars=max_chars)
    if not text:
        return ""
    ver = resolve_version(archetype, version, root)
    return f"=== SKELETON {archetype}@{ver} ===\n{text.strip()}\n"
