"""A11.0 Asset hub — scan 3D models and expose catalog to Planner / Gate."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
MODELS_DIRNAME = "assets/models"
CATALOG_DIRNAME = "assets/catalog"
CATALOG_NAME = "assets.json"

# External artist pipeline: Claude Code / DeepSeek → LEGO fruits etc.
SUPPORTED_EXTS = {".glb", ".gltf", ".ldr", ".fbx", ".obj"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def models_dir(root: Optional[Path] = None) -> Path:
    return (root or ROOT_DEFAULT) / MODELS_DIRNAME


def catalog_dir(root: Optional[Path] = None) -> Path:
    return (root or ROOT_DEFAULT) / CATALOG_DIRNAME


def catalog_path(root: Optional[Path] = None) -> Path:
    return catalog_dir(root) / CATALOG_NAME


def asset_id_from_filename(name: str) -> str:
    """Apple.glb → Apple; banana_01.ldr → Banana_01 (stem, keep case of stem)."""
    stem = Path(name).stem
    # Prefer PascalCase-ish id: strip spaces
    return re.sub(r"\s+", "", stem) or stem


def _load_place_meshes(root: Path) -> List[Dict[str, Any]]:
    """Meshes referenced from a Studio .rbxl (see assets/catalog/place_meshes.json)."""
    p = catalog_dir(root) / "place_meshes.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: List[Dict[str, Any]] = []
    for m in data.get("meshes") or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        out.append(
            {
                "id": str(m["id"]),
                "file": f"{m['id']}.rbxassetid",
                "ext": ".rbxassetid",
                "rel": "assets/catalog/place_meshes.json",
                "bytes": 0,
                "mesh_id": m.get("mesh_id"),
                "texture_id": m.get("texture_id"),
                "source": "place_rbxl",
                "kind": m.get("kind") or "mesh",
            }
        )
    return out


def scan_models(root: Optional[Path] = None) -> Dict[str, Any]:
    """Read assets/models/* (+ place_meshes.json) and build catalog dict (does not write)."""
    root = root or ROOT_DEFAULT
    mdir = models_dir(root)
    assets: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    if mdir.is_dir():
        for p in sorted(mdir.iterdir()):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext not in SUPPORTED_EXTS:
                continue
            if p.name.startswith("."):
                continue
            aid = asset_id_from_filename(p.name)
            # de-dupe by id (first wins)
            if aid.lower() in seen:
                continue
            seen.add(aid.lower())
            try:
                rel = p.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = p.as_posix().replace("\\", "/")
            assets.append(
                {
                    "id": aid,
                    "file": p.name,
                    "ext": ext,
                    "rel": rel,
                    "bytes": p.stat().st_size,
                }
            )
    # Merge Studio place refs (Fruits_Inventory models from working_game.rbxl, etc.)
    for extra in _load_place_meshes(root):
        key = str(extra["id"]).lower()
        if key in seen:
            continue
        seen.add(key)
        assets.append(extra)
    return {
        "version": 1,
        "scanned_at": now_iso(),
        "models_dir": MODELS_DIRNAME,
        "count": len(assets),
        "ids": [a["id"] for a in assets],
        "assets": assets,
    }


def write_catalog(root: Optional[Path] = None, *, catalog: Optional[Dict[str, Any]] = None) -> Path:
    """Scan (or use provided catalog) and write assets/catalog/assets.json."""
    root = root or ROOT_DEFAULT
    data = catalog or scan_models(root)
    out_dir = catalog_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    models_dir(root).mkdir(parents=True, exist_ok=True)
    path = catalog_path(root)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_catalog(root: Optional[Path] = None, *, rescan: bool = False) -> Dict[str, Any]:
    """Load catalog JSON; optionally rescan disk first."""
    root = root or ROOT_DEFAULT
    if rescan or not catalog_path(root).is_file():
        write_catalog(root)
    p = catalog_path(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return scan_models(root)
    return data if isinstance(data, dict) else scan_models(root)


def list_ids(root: Optional[Path] = None, *, rescan: bool = False) -> List[str]:
    cat = load_catalog(root, rescan=rescan)
    ids = cat.get("ids")
    if isinstance(ids, list) and ids:
        return [str(x) for x in ids]
    return [str(a.get("id")) for a in (cat.get("assets") or []) if isinstance(a, dict) and a.get("id")]


def catalog_for_prompt(root: Optional[Path] = None, *, max_chars: int = 500, rescan: bool = False) -> str:
    """Compact block for DeepSeek Planner system/user prompts."""
    ids = list_ids(root, rescan=rescan)
    if not ids:
        return (
            "Available 3D assets: (none — put .glb/.ldr into assets/models/ then rescan). "
            "Do NOT invent asset ids."
        )
    joined = ", ".join(ids[:40])
    text = f"Available 3D assets: {joined}. Prefer these ids in proposed_assets; do NOT invent names."
    return text[:max_chars]


def extract_proposed_assets(plan: Any) -> List[str]:
    """Pull proposed_assets from plan dict / nested tasks / free text."""
    found: List[str] = []
    if isinstance(plan, dict):
        val = plan.get("proposed_assets") or plan.get("assets")
        if isinstance(val, list):
            found.extend(str(x).strip() for x in val if str(x).strip())
        elif isinstance(val, str) and val.strip():
            found.extend(x.strip() for x in re.split(r"[,;\s]+", val) if x.strip())
        for t in plan.get("tasks") or plan.get("planner_split") or []:
            if isinstance(t, dict):
                found.extend(extract_proposed_assets(t))
        for key in ("description", "note", "tz_line", "prompt", "goal"):
            if plan.get(key):
                found.extend(_assets_from_text(str(plan[key])))
    elif isinstance(plan, str):
        found.extend(_assets_from_text(plan))
    out: List[str] = []
    seen: Set[str] = set()
    for raw in found:
        # normalize Apple.glb → Apple
        aid = asset_id_from_filename(raw) if "." in raw else raw
        key = aid.lower()
        if aid and key not in seen:
            seen.add(key)
            out.append(aid)
    return out


_ASSET_HINT_RE = re.compile(
    r"(?i)(?:asset|model|mesh|prefab|use)\s*[:=]?\s*[\"']?([A-Za-z][A-Za-z0-9_\-]{1,32})"
)


def _assets_from_text(text: str) -> List[str]:
    out: List[str] = []
    # proposed_assets: ["Apple", "Banana"]
    for m in re.finditer(r"proposed_assets\s*[:=]\s*\[([^\]]*)\]", text or "", re.I):
        inner = m.group(1)
        out.extend(re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,32}", inner))
    out.extend(_ASSET_HINT_RE.findall(text or ""))
    return out


def gate_assets(
    root: Path,
    plan: Any,
    *,
    catalog: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    If plan lists proposed_assets, every id must exist in catalog.
    Empty proposed_assets → ok (no claim).
    """
    cat = catalog or load_catalog(root, rescan=False)
    known = {str(i).lower() for i in (cat.get("ids") or [])}
    for a in cat.get("assets") or []:
        if isinstance(a, dict) and a.get("id"):
            known.add(str(a["id"]).lower())
    proposed = extract_proposed_assets(plan)
    unknown = [a for a in proposed if a.lower() not in known]
    report = {
        "ok": len(unknown) == 0,
        "proposed_assets": proposed,
        "unknown_assets": unknown,
        "catalog_ids": list(cat.get("ids") or []),
        "catalog_count": int(cat.get("count") or len(known)),
    }
    if unknown:
        report["message"] = (
            f"[assets] blocked hallucinated assets: {', '.join(unknown)}. "
            f"Known: {', '.join(list(cat.get('ids') or [])[:20]) or '(empty catalog)'}"
        )
    return len(unknown) == 0, unknown, report
