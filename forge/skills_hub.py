"""Raw → compact skills registry for Ollama ctx budget."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import deepseek
from .planner_schema import CARD_MAX_CHARS, card_char_len, clamp_skill_card, validate_skill_card

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
    """Concatenate compact skills under a char budget for prompts.

    A13: when Token Economy is on and CARD.json exists, inject EN+short-key cards
    (no DeepSeek — only already-materialized cards).
    """
    from . import token_economy as te

    if te.economy_enabled() and skill_ids:
        parts: List[str] = ["===CARDS==="]
        used = len(parts[0])
        for sid in list(skill_ids)[:3]:
            card = load_skill_card(sid, root)
            if not card:
                continue
            card = clamp_skill_card(card, max_chars=CARD_MAX_CHARS)
            line = te.dumps_llm(te.economy_card(card))
            if used + len(line) + 1 > budget:
                break
            parts.append(line)
            used += len(line) + 1
        if len(parts) > 1:
            return "\n".join(parts)
    parts = []
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


def load_skill_card(skill_id: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    p = skills_root(root) / "compact" / skill_id / "CARD.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def write_skill_card(skill_id: str, card: Dict[str, Any], root: Optional[Path] = None) -> Path:
    from . import token_economy as te

    dest_dir = skills_root(root) / "compact" / skill_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    card = clamp_skill_card({**card, "id": card.get("id") or skill_id}, max_chars=CARD_MAX_CHARS)
    path = dest_dir / "CARD.json"
    # Disk keeps full keys; minify by default (FORGE_JSON_PRETTY=1 for indent)
    path.write_text(te.dumps_disk(card), encoding="utf-8")
    return path


def ensure_skill_card(skill_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """Load CARD.json or build from SKILL.md via DeepSeek/heuristic."""
    existing = load_skill_card(skill_id, root)
    if existing:
        ok, _ = validate_skill_card(existing, max_chars=CARD_MAX_CHARS)
        if ok:
            return existing
        return clamp_skill_card(existing, max_chars=CARD_MAX_CHARS)
    try:
        raw = load_compact_text(skill_id, root)
    except FileNotFoundError:
        card = clamp_skill_card({"id": skill_id, "exports": [f"{skill_id}()"]}, max_chars=CARD_MAX_CHARS)
        write_skill_card(skill_id, card, root)
        return card
    card = deepseek.compress_skill_card(raw, name=skill_id, max_chars=CARD_MAX_CHARS)
    write_skill_card(skill_id, card, root)
    return card


def bundle_for_14b(
    root: Optional[Path] = None,
    skill_ids: Optional[List[str]] = None,
    *,
    max_skills: int = 3,
    card_budget: int = CARD_MAX_CHARS,
    rules_budget: int = 1200,
    archetype: Optional[str] = None,
    skeleton_version: Optional[str] = None,
    skeleton_budget: int = 500,
    economy: Optional[bool] = None,
    focus_terms: Optional[List[str]] = None,
    focus_text: Optional[str] = None,
    prune: Optional[bool] = None,
) -> str:
    """
    Compact prompt block for local 14B:
    ≤3 contract cards + ONE pinned skeleton + active HITL rules.
    A13: Token Economy — EN cards, short keys, minified JSON, compact rules.
    A15: Semantic prune — keep only exports/attrs matching focus_terms / TZ text.
    """
    from . import feedback
    from . import skeletons_hub
    from . import token_economy as te

    use_econ = te.economy_enabled() if economy is None else bool(economy)
    use_prune = True if prune is None else bool(prune)
    terms = list(focus_terms or [])
    if focus_text:
        terms = list(dict.fromkeys(terms + te.extract_focus_terms(focus_text)))
    r = root or ROOT_DEFAULT
    ids = list(skill_ids or [c["id"] for c in list_compact(r)[:max_skills]])[:max_skills]
    parts: List[str] = ["===CARDS===" if use_econ else "=== CONTRACT CARDS (for 14B) ==="]
    for sid in ids:
        card = ensure_skill_card(sid, r)
        card = clamp_skill_card(card, max_chars=card_budget)
        if use_prune:
            card = te.prune_card(card, terms if terms else None)
        if use_econ:
            card = te.economy_card(card)
            parts.append(te.dumps_llm(card))
        else:
            # Pre-A13 baseline: pretty JSON (shows minify+short-key savings in reports)
            parts.append(json.dumps(card, ensure_ascii=False, indent=2))
    if archetype:
        sk = skeletons_hub.inject_skeleton_block(
            archetype, skeleton_version, r, max_chars=skeleton_budget
        )
        if sk:
            # Drop decorative blank lines in skeleton for economy
            if use_econ:
                sk = "\n".join(ln for ln in sk.splitlines() if ln.strip() != "")
            parts.append(sk.rstrip())
        else:
            parts.append(f"=== SKELETON {archetype}@{skeleton_version or 'latest'} MISSING ===")
    active = feedback.load_active_rules(r)
    if use_econ:
        rules = te.economy_rules_block(active, max_chars=min(rules_budget, 800))
    else:
        rules = feedback.format_rules_for_prompt(active, max_chars=rules_budget)
    if rules.strip():
        parts.append("===RULES===" if use_econ else "=== ACTIVE HITL RULES ===")
        parts.append(rules.strip())
    # A18.1: Roblox API hallucination guard (BrickColor ≠ Material)
    parts.append(
        "=== API GUARD ===\n"
        "Do not use BrickColor for materials. "
        "Use Enum.Material.Neon or valid BrickColor names like 'Gold', 'Bright red'."
    )
    return "\n".join(parts)


def bundle_savings_report(
    root: Optional[Path] = None,
    skill_ids: Optional[List[str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Compare fat vs economy(+prune) bundle sizes (A13/A15 report helper)."""
    from . import token_economy as te

    focus_text = kwargs.pop("focus_text", None)
    focus_terms = kwargs.pop("focus_terms", None)
    fat = bundle_for_14b(
        root, skill_ids, economy=False, prune=False, focus_text=None, focus_terms=None, **kwargs
    )
    lean = bundle_for_14b(
        root,
        skill_ids,
        economy=True,
        prune=True,
        focus_text=focus_text,
        focus_terms=focus_terms,
        **kwargs,
    )
    report = te.measure_bundle_savings(fat, lean)
    report["fat_preview"] = fat[:200]
    report["lean_preview"] = lean[:200]
    report["focus_terms"] = list(focus_terms or []) + (
        te.extract_focus_terms(focus_text) if focus_text else []
    )
    # A15: economy-only vs economy+prune delta
    mid = bundle_for_14b(
        root, skill_ids, economy=True, prune=False, focus_text=None, focus_terms=None, **kwargs
    )
    prune_only = te.measure_bundle_savings(mid, lean)
    report["a15_prune_vs_economy"] = prune_only
    report["a15_num_predict_default"] = None
    try:
        from . import llm_backends

        report["a15_num_predict_default"] = llm_backends.DEFAULT_NUM_PREDICT
        report["a15_num_predict_diff"] = llm_backends.DIFF_NUM_PREDICT
    except Exception:
        pass
    return report


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
    # A7.1: also write typed CARD.json for 14B budget
    try:
        card = deepseek.compress_skill_card(compact, name=name, max_chars=CARD_MAX_CHARS)
        write_skill_card(name, card, root)
    except Exception:
        pass
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
