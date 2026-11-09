"""Raw → compact skills registry for Ollama ctx budget."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import deepseek

ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def skills_root(root: Optional[Path] = None) -> Path:
    return (root or ROOT_DEFAULT) / "skills"


def list_raw(root: Optional[Path] = None) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    base = skills_root(root) / "raw"
    if not base.exists():
        return out
    for skill_md in sorted(base.rglob("SKILL.md")):
        rel = skill_md.relative_to(base).as_posix()
        name = skill_md.parent.name
        out.append(
            {
                "id": rel.replace("/SKILL.md", "").replace("/", "__"),
                "name": name,
                "path": str(skill_md),
                "chars": str(skill_md.stat().st_size),
                "source": rel.split("/", 1)[0],
            }
        )
    return out


def list_compact(root: Optional[Path] = None) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    base = skills_root(root) / "compact"
    if not base.exists():
        return out
    for skill_md in sorted(base.rglob("SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        out.append(
            {
                "id": skill_md.parent.name,
                "name": skill_md.parent.name,
                "path": str(skill_md),
                "chars": str(len(text)),
                "promoted": "true" if (skill_md.parent / "PROMOTED.json").exists() else "false",
            }
        )
    return out


def load_compact_text(skill_id: str, root: Optional[Path] = None) -> str:
    p = skills_root(root) / "compact" / skill_id / "SKILL.md"
    if not p.exists():
        raise FileNotFoundError(skill_id)
    return p.read_text(encoding="utf-8")


def inject_block(skill_ids: List[str], root: Optional[Path] = None, *, budget: int = 3600) -> str:
    """Concatenate compact skills under a char budget for prompts."""
    parts: List[str] = []
    used = 0
    for sid in skill_ids:
        try:
            text = load_compact_text(sid, root)
        except FileNotFoundError:
            continue
        if used + len(text) > budget:
            break
        parts.append(f"=== COMPACT SKILL {sid} ===\n{text.strip()}\n")
        used += len(text)
    return "\n".join(parts)


def compress_raw_to_compact(
    raw_id: str,
    root: Optional[Path] = None,
    *,
    max_chars: int = 1200,
    dry_run: bool = False,
) -> Tuple[str, Path]:
    """Compress one raw skill via DeepSeek into skills/compact/<name>/."""
    base = skills_root(root) / "raw"
    # raw_id like ash__roblox-luau-architecture
    rel = raw_id.replace("__", "/") + "/SKILL.md"
    src = base / rel
    if not src.exists():
        # allow name-only search
        matches = list(base.rglob(f"*/{raw_id}/SKILL.md")) + list(base.rglob(f"{raw_id}/SKILL.md"))
        if not matches:
            raise FileNotFoundError(raw_id)
        src = matches[0]
    raw = src.read_text(encoding="utf-8")
    name = src.parent.name
    if dry_run or not deepseek.available():
        # heuristic trim without API
        compact = _heuristic_compress(raw, name=name, max_chars=max_chars)
    else:
        compact = deepseek.compress_skill(raw, name=name, max_chars=max_chars)
    dest_dir = skills_root(root) / "compact" / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "SKILL.md"
    dest.write_text(compact, encoding="utf-8")
    meta = {"source": str(src), "max_chars": max_chars, "via": "deepseek" if deepseek.available() and not dry_run else "heuristic"}
    (dest_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return compact, dest


def auto_select_and_compress(
    goal: str,
    root: Optional[Path] = None,
    *,
    max_pick: int = 3,
    max_chars: int = 1200,
    project_id: Optional[str] = None,
) -> Dict[str, object]:
    """DeepSeek (or heuristic) picks raw skills for the goal, compresses them, updates project meta."""
    catalog = list_raw(root)
    # Always keep forge-learned compact skills available
    forge_keep = ["forge-player-attrs", "forge-luau-touch"]
    picked = deepseek.select_skills(goal=goal, catalog=catalog, max_pick=max_pick)
    results = []
    compact_ids = list(forge_keep)
    for raw_id in picked:
        text, dest = compress_raw_to_compact(raw_id, root, max_chars=max_chars)
        name = dest.parent.name
        if name not in compact_ids:
            compact_ids.append(name)
        results.append({"raw_id": raw_id, "compact_id": name, "chars": len(text), "path": str(dest)})
    compact_ids = compact_ids[: max_pick + len(forge_keep)]
    if project_id:
        meta_p = (root or ROOT_DEFAULT) / "projects" / project_id / "meta.json"
        if meta_p.exists():
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            meta["skills_compact"] = compact_ids[:5]
            meta["skills_auto_goal"] = goal
            meta_p.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {
        "picked_raw": picked,
        "compressed": results,
        "skills_compact": compact_ids,
        "via": "deepseek" if deepseek.available() else "heuristic",
    }


def promote_compact(
    skill_id: str,
    root: Optional[Path] = None,
    *,
    smoke_ok: bool = True,
    notes: str = "",
    missing_ok: bool = False,
) -> Optional[Path]:
    """Mark a compact skill as proven after smoke — DeepSeek 'learns' by keeping winners."""
    sid = (skill_id or "").strip()
    if not sid:
        if missing_ok:
            return None
        raise FileNotFoundError("empty skill_id")
    d = skills_root(root) / "compact" / sid
    if not (d / "SKILL.md").exists():
        if missing_ok:
            return None
        raise FileNotFoundError(sid)
    payload = {"promoted": True, "smoke_ok": smoke_ok, "notes": notes}
    path = d / "PROMOTED.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def existing_compact_ids(root: Optional[Path] = None, ids: Optional[List[str]] = None) -> List[str]:
    """Filter skill ids to those that exist under skills/compact/*/SKILL.md."""
    want = ids or [c["id"] for c in list_compact(root)]
    out: List[str] = []
    base = skills_root(root) / "compact"
    for sid in want:
        if (base / sid / "SKILL.md").exists():
            out.append(sid)
    return out


def _heuristic_compress(raw: str, *, name: str, max_chars: int) -> str:
    # Keep headings + bullet lines; drop long paragraphs
    lines = []
    for ln in raw.splitlines():
        s = ln.rstrip()
        if not s:
            continue
        if s.startswith("#") or s.startswith("-") or s.startswith("*") or s.startswith("---"):
            lines.append(s)
        elif len(s) < 120:
            lines.append(s)
    body = "\n".join(lines)
    header = f"---\nname: {name}\nsource: heuristic\nmax_chars: {max_chars}\n---\n"
    out = header + body
    return out[:max_chars]
