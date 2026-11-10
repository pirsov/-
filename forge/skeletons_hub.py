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
    budget = int(meta.get("prompt_budget_chars") or max_chars)
    return text[: min(budget, max_chars)]


def infer_archetype_from_path(path: Path) -> Optional[str]:
    s = str(path).replace("\\", "/")
    name = path.name
    if name == "Remotes.luau" or "/Gameplay/Remotes" in s:
        return "network_remote"
    if name.endswith(".client.luau") or "/src/client/" in s:
        return "client_ui"
    if name.endswith(".server.luau") or "/src/server/" in s:
        return "server_script"
    if "/src/shared/" in s or name.endswith("Config.luau"):
        return "shared_data"
    return None


def find_contract_pin(root: Path, path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Look up archetype + skeleton_version from contracts matching this file/plugin.
    Returns (archetype, version) or (None, None).
    """
    contracts = root / "contracts"
    if not contracts.is_dir():
        return None, None
    name = path.name
    best: Tuple[Optional[str], Optional[str]] = (None, None)
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
        path_field = payload.get("path") or (snap.get("path") if isinstance(snap, dict) else None)
        if path_field:
            files.append(str(path_field))
        # match by filename or plugin stem
        hit = any(str(f).endswith(name) or name in str(f) for f in files)
        if not hit and name.replace(".server.luau", "").replace(".client.luau", "").replace(".luau", "") in p.stem:
            hit = True
        # game1.hud → HUD.client.luau
        stem = p.stem.lower()
        if name.lower().startswith("hud") and "hud" in stem:
            hit = True
        if name == "Remotes.luau" and "remote" in stem:
            hit = True
        if name == "LevelConfig.luau" and ("levelconfig" in stem or "shared" in stem):
            hit = True
        if hit:
            best = (str(arch), str(ver) if ver else None)
            if ver:
                return best
    return best


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
    Pin-by-contract: use contract's skeleton_version when present;
    else infer archetype from path and registry latest.
    """
    arch = archetype
    ver = version
    if not arch or not ver:
        pinned_a, pinned_v = find_contract_pin(root, path)
        arch = arch or pinned_a or infer_archetype_from_path(path)
        ver = ver or pinned_v
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
