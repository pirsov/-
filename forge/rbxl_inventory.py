"""Scan a Roblox binary place (.rbxl) for Fruits_Inventory models.

Names live in ZSTD-compressed INST/PROP chunks — a raw string grep misses them.
"""
from __future__ import annotations

import io
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import zstandard as zstd
except ImportError:  # pragma: no cover
    zstd = None  # type: ignore

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
DEFAULT_RBXL = Path("artifacts/reference_place/working_game.rbxl")
PLACE_MESHES = Path("assets/catalog/place_meshes.json")
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# Alias catalog ids → place instance names (planner-friendly).
ALIASES = {
    "Apple": "VoxelApple",
}

# Known MeshIds when the named Accessory has no children in the place tree.
KNOWN_MESH_BY_ID = {
    "Banana": {
        "mesh_id": "rbxassetid://178186804",
        "texture_id": "152661377",
        "geometry": "mesh",
    },
}


def _decompress(payload: bytes, uncompressed_len: int) -> bytes:
    if not payload.startswith(ZSTD_MAGIC):
        return payload
    if zstd is None:
        raise RuntimeError("zstandard package required to read compressed .rbxl chunks")
    dctx = zstd.ZstdDecompressor()
    try:
        return dctx.decompress(
            payload, max_output_size=max(uncompressed_len, len(payload) * 20, 1 << 22)
        )
    except zstd.ZstdError:
        with dctx.stream_reader(io.BytesIO(payload)) as reader:
            return reader.read()


def _read_chunks(data: bytes) -> List[Tuple[bytes, bytes]]:
    if not data.startswith(b"<roblox!"):
        raise ValueError("not a Roblox binary place (missing <roblox! magic)")
    pos = 32
    chunks: List[Tuple[bytes, bytes]] = []
    while pos + 16 <= len(data):
        ctype = data[pos : pos + 4]
        cl, ul, _ = struct.unpack_from("<III", data, pos + 4)
        pos += 16
        payload = data[pos : pos + cl]
        pos += cl
        chunks.append((ctype, _decompress(payload, ul)))
        if ctype == b"END\x00":
            break
    return chunks


def _read_string(buf: bytes, i: int) -> Tuple[str, int]:
    (n,) = struct.unpack_from("<I", buf, i)
    i += 4
    s = buf[i : i + n]
    i += n
    return s.decode("utf-8", "replace"), i


def _read_interleaved_i32(buf: bytes, i: int, count: int) -> Tuple[List[int], int]:
    """Roblox stores int32 arrays byte-interleaved (MSB plane first) + zigzag."""
    need = count * 4
    raw = buf[i : i + need]
    if len(raw) < need:
        raise ValueError(f"short interleaved array: {len(raw)} < {need}")
    vals: List[int] = []
    for idx in range(count):
        v = (
            (raw[idx] << 24)
            | (raw[count + idx] << 16)
            | (raw[2 * count + idx] << 8)
            | raw[3 * count + idx]
        )
        if v >= 0x80000000:
            v -= 0x100000000
        v = (v >> 1) ^ (-(v & 1))
        vals.append(v)
    return vals, i + need


def _accumulate(vals: List[int]) -> List[int]:
    out: List[int] = []
    acc = 0
    for v in vals:
        acc += v
        out.append(acc)
    return out


def parse_place(rbxl: Path) -> Dict[str, Any]:
    """Return instances, names, parent/children maps from a .rbxl file."""
    data = rbxl.read_bytes()
    chunks = _read_chunks(data)
    classes: Dict[int, Tuple[str, List[int], int]] = {}
    instances: Dict[int, str] = {}
    for ctype, raw in chunks:
        if ctype != b"INST" or not raw:
            continue
        i = 0
        (type_id,) = struct.unpack_from("<I", raw, i)
        i += 4
        classname, i = _read_string(raw, i)
        (fmt,) = struct.unpack_from("<B", raw, i)
        i += 1
        (count,) = struct.unpack_from("<I", raw, i)
        i += 4
        vals, i = _read_interleaved_i32(raw, i, count)
        refs = _accumulate(vals)
        classes[type_id] = (classname, refs, fmt)
        for r in refs:
            instances[r] = classname

    children: Dict[int, List[int]] = defaultdict(list)
    parent_of: Dict[int, int] = {}
    for ctype, raw in chunks:
        if ctype != b"PRNT" or not raw:
            continue
        i = 0
        (fmt,) = struct.unpack_from("<B", raw, i)
        i += 1
        (count,) = struct.unpack_from("<I", raw, i)
        i += 4
        cv, i = _read_interleaved_i32(raw, i, count)
        pv, i = _read_interleaved_i32(raw, i, count)
        for c, p in zip(_accumulate(cv), _accumulate(pv)):
            parent_of[c] = p
            children[p].append(c)

    names: Dict[int, str] = {}
    mesh_ids: Dict[int, str] = {}
    texture_ids: Dict[int, str] = {}
    for ctype, raw in chunks:
        if ctype != b"PROP" or not raw:
            continue
        i = 0
        (type_id,) = struct.unpack_from("<I", raw, i)
        i += 4
        propname, i = _read_string(raw, i)
        (ptype,) = struct.unpack_from("<B", raw, i)
        i += 1
        classname, refs, _fmt = classes.get(type_id, (None, [], 0))
        if ptype != 0x01:
            continue
        for ref in refs:
            s, i = _read_string(raw, i)
            if propname == "Name":
                names[ref] = s
            elif propname == "MeshId" and s:
                mesh_ids[ref] = s
            elif propname in ("Texture", "TextureID", "TextureId") and s:
                texture_ids[ref] = s

    return {
        "instances": instances,
        "names": names,
        "children": dict(children),
        "parent_of": parent_of,
        "mesh_ids": mesh_ids,
        "texture_ids": texture_ids,
        "bytes": len(data),
    }


def _subtree_stats(
    root_ref: int,
    *,
    instances: Dict[int, str],
    children: Dict[int, List[int]],
    mesh_ids: Dict[int, str],
    texture_ids: Dict[int, str],
) -> Dict[str, Any]:
    stack = list(children.get(root_ref, []))
    seen = set()
    parts = unions = meshparts = specials = 0
    found_mesh: Optional[str] = None
    found_tex: Optional[str] = None
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        cls = instances.get(cur)
        if cls == "Part":
            parts += 1
        elif cls == "UnionOperation":
            unions += 1
        elif cls == "MeshPart":
            meshparts += 1
        elif cls == "SpecialMesh":
            specials += 1
        if mesh_ids.get(cur) and not found_mesh:
            found_mesh = mesh_ids[cur]
            found_tex = texture_ids.get(cur)
        stack.extend(children.get(cur, []))
    return {
        "parts": parts,
        "unions": unions,
        "meshparts": meshparts,
        "special_meshes": specials,
        "mesh_id": found_mesh,
        "texture_id": found_tex,
        "geometry": (
            "mesh"
            if found_mesh
            else ("parts" if parts else ("union" if unions else "unknown"))
        ),
    }


def _normalize_texture_id(tex: Optional[str]) -> Optional[str]:
    if not tex:
        return None
    # http://www.roblox.com/asset/?id=152661377 → 152661377
    if "id=" in tex:
        return tex.split("id=", 1)[-1].strip()
    if tex.startswith("rbxassetid://"):
        return tex.replace("rbxassetid://", "", 1)
    return tex


def extract_fruits_inventory(
    rbxl: Path,
    *,
    folder_name: str = "Fruits_Inventory",
    include_siblings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract fruit catalog entries from Fruits_Inventory (+ optional sibling names)."""
    parsed = parse_place(rbxl)
    instances: Dict[int, str] = parsed["instances"]
    names: Dict[int, str] = parsed["names"]
    children: Dict[int, List[int]] = parsed["children"]
    parent_of: Dict[int, int] = parsed["parent_of"]
    mesh_ids: Dict[int, str] = parsed["mesh_ids"]
    texture_ids: Dict[int, str] = parsed["texture_ids"]

    inv_refs = [r for r, n in names.items() if n == folder_name and instances.get(r) == "Folder"]
    if not inv_refs:
        raise FileNotFoundError(f"Folder {folder_name!r} not found in {rbxl}")
    inv = inv_refs[0]
    inv_parent = parent_of.get(inv)

    fruits: List[Dict[str, Any]] = []
    unnamed = 0
    for ch in children.get(inv, []):
        if instances.get(ch) != "Model":
            continue
        name = names.get(ch) or ""
        stats = _subtree_stats(
            ch,
            instances=instances,
            children=children,
            mesh_ids=mesh_ids,
            texture_ids=texture_ids,
        )
        if not name or name == "Model":
            unnamed += 1
            fruits.append(
                {
                    "id": None,
                    "place_instance": name or "Model",
                    "class": "Model",
                    "folder": folder_name,
                    "kind": "fruit",
                    "unnamed": True,
                    **stats,
                }
            )
            continue
        entry: Dict[str, Any] = {
            "id": name,
            "place_instance": name,
            "class": "Model",
            "folder": folder_name,
            "kind": "fruit",
            **stats,
        }
        if stats.get("texture_id"):
            entry["texture_id"] = _normalize_texture_id(stats["texture_id"])
        fruits.append(entry)

    # Banana (Accessory) + optional trash variants live as siblings under the same Folder.
    sibling_names = set(include_siblings or ["Banana", "Trash_Mango", "Trash_Orange"])
    extras: List[Dict[str, Any]] = []
    if inv_parent is not None:
        for ch in children.get(inv_parent, []):
            n = names.get(ch)
            if n not in sibling_names:
                continue
            stats = _subtree_stats(
                ch,
                instances=instances,
                children=children,
                mesh_ids=mesh_ids,
                texture_ids=texture_ids,
            )
            entry = {
                "id": n,
                "place_instance": n,
                "class": instances.get(ch),
                "folder": None,
                "kind": "fruit",
                "sibling_of": folder_name,
                **stats,
            }
            if stats.get("mesh_id"):
                entry["mesh_id"] = stats["mesh_id"]
            if stats.get("texture_id"):
                entry["texture_id"] = _normalize_texture_id(stats["texture_id"])
            # Accessory may be empty in PRNT while SpecialMesh lives on a nearby Part.
            if not entry.get("mesh_id"):
                known = KNOWN_MESH_BY_ID.get(n)
                if known:
                    entry.update(known)
                else:
                    # Fall back: any SpecialMesh MeshId under a Part named like the fruit.
                    for ref, mid in mesh_ids.items():
                        if not mid:
                            continue
                        owner = parent_of.get(ref)
                        # Walk up a few parents looking for matching Name
                        cur = owner
                        for _ in range(4):
                            if cur is None or cur < 0:
                                break
                            if names.get(cur) == n:
                                entry["mesh_id"] = mid
                                entry["texture_id"] = _normalize_texture_id(
                                    texture_ids.get(ref)
                                )
                                entry["geometry"] = "mesh"
                                break
                            cur = parent_of.get(cur)
                        if entry.get("mesh_id"):
                            break
            extras.append(entry)

    try:
        source = rbxl.resolve().relative_to(ROOT_DEFAULT.resolve()).as_posix()
    except ValueError:
        source = rbxl.as_posix().replace("\\", "/")
    return {
        "source": source,
        "bytes": parsed["bytes"],
        "folder": folder_name,
        "fruits": fruits,
        "extras": extras,
        "unnamed_in_folder": unnamed,
    }


def build_place_meshes_doc(scan: Dict[str, Any]) -> Dict[str, Any]:
    """Build assets/catalog/place_meshes.json document from extract_fruits_inventory()."""
    meshes: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(entry: Dict[str, Any], *, folder: Optional[str]) -> None:
        eid = entry.get("id")
        if not eid or eid in seen:
            return
        seen.add(eid)
        item: Dict[str, Any] = {
            "id": eid,
            "kind": "fruit",
            "place_instance": entry.get("place_instance") or eid,
            "class": entry.get("class") or "Model",
            "geometry": entry.get("geometry") or "parts",
            "parts": int(entry.get("parts") or 0),
        }
        if folder:
            item["folder"] = folder
        if entry.get("sibling_of"):
            item["sibling_of"] = entry["sibling_of"]
        if entry.get("mesh_id"):
            item["mesh_id"] = entry["mesh_id"]
        if entry.get("texture_id"):
            item["texture_id"] = entry["texture_id"]
        meshes.append(item)

    for e in scan.get("extras") or []:
        add(e, folder=None)
    for e in scan.get("fruits") or []:
        if e.get("unnamed"):
            continue
        add(e, folder=scan.get("folder"))

    # Planner-friendly aliases (Apple → VoxelApple instance).
    by_instance = {m["place_instance"]: m for m in meshes}
    for alias, target in ALIASES.items():
        if alias in seen:
            continue
        src = by_instance.get(target)
        if not src:
            continue
        cloned = dict(src)
        cloned["id"] = alias
        cloned["alias_of"] = target
        meshes.append(cloned)
        seen.add(alias)

    meshes.sort(key=lambda m: str(m["id"]).lower())
    return {
        "version": 2,
        "source": scan.get("source"),
        "folder": scan.get("folder"),
        "note": (
            "Fruit Models under Folder Fruits_Inventory are Part-voxel builds (no MeshId). "
            "Banana is a sibling Accessory with SpecialMesh rbxassetid. "
            "Trash_* are sibling variants outside the inventory folder. "
            "Apple aliases VoxelApple."
        ),
        "meshes": meshes,
    }


def write_place_meshes(
    root: Optional[Path] = None,
    *,
    rbxl: Optional[Path] = None,
    out: Optional[Path] = None,
) -> Dict[str, Any]:
    """Scan rbxl → write place_meshes.json; return the document."""
    root = root or ROOT_DEFAULT
    rbxl_path = rbxl or (root / DEFAULT_RBXL)
    out_path = out or (root / PLACE_MESHES)
    scan = extract_fruits_inventory(rbxl_path)
    doc = build_place_meshes_doc(scan)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": out_path.as_posix(), "count": len(doc["meshes"]), "scan": scan, "doc": doc}


def inventory_markdown(scan: Dict[str, Any]) -> str:
    """Render artifacts/reference_place/INVENTORY.md body from a scan."""
    lines = [
        f"# Inventory — `{Path(scan['source']).name}`",
        "",
        f"Binary place ({scan['bytes']:,} bytes). Instance **Name** props are inside "
        "ZSTD-compressed chunks — a raw string scan misses them.",
        "",
        f"## Folder `{scan['folder']}`",
        "",
        "All fruit Models used by the game live here (mechanics under `FruitMechanics`).",
        "",
        "| Name | Class | Geometry | Parts |",
        "|------|--------|----------|------:|",
    ]
    for e in scan.get("fruits") or []:
        name = e.get("id") or (e.get("place_instance") + " *(unnamed)*")
        geom = e.get("geometry") or "?"
        extra = ""
        if e.get("mesh_id"):
            extra = f" `{e['mesh_id']}`"
        lines.append(
            f"| **{name}** | {e.get('class')} | {geom}{extra} | {e.get('parts', 0)} |"
        )
    lines += [
        "",
        "## Sibling fruit assets (same parent Folder)",
        "",
        "| Name | Class | Notes |",
        "|------|--------|--------|",
    ]
    for e in scan.get("extras") or []:
        note = e.get("geometry") or ""
        if e.get("mesh_id"):
            note = f"MeshId `{e['mesh_id']}`, texture `{e.get('texture_id')}`"
        elif e.get("parts"):
            note = f"Part-voxel ({e['parts']} parts), outside inventory"
        lines.append(f"| **{e.get('id')}** | {e.get('class')} | {note} |")
    lines += [
        "",
        "Registered for Forge Gate in `assets/catalog/place_meshes.json` "
        "(ids usable as `proposed_assets`; `Apple` aliases `VoxelApple`).",
        "",
        "## Related fruit scripts / remotes",
        "",
        "`FruitCarryClient`, `FruitCarryHandler`, `FruitMutationHandler`, "
        "`FruitRespawnManager`, `FruitAction*`, `FruitWorldUI`, `FruitSetup`, "
        "`FruitActionEvent`, `ThrowFruitEvent`, `FruitActionMenu`.",
        "",
        "## What this means for Forge",
        "",
        "- Gate accepts these fruit **ids** from `place_meshes.json` without needing `.glb` on disk.",
        "- Geometry stays inside the `.rbxl` (Studio Part voxels / Banana mesh).",
        "- Re-scan: `python -u run.py --scan-place-fruits`",
        "",
    ]
    return "\n".join(lines)
