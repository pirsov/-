"""A7.1 planner JSON schemas — HITL packs + skill contract cards (no pydantic)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

HITL_OPTION_KEYS = ("A", "B", "C")
CARD_MAX_CHARS = 350
HITL_MAX_QUESTIONS = 2


def _as_dict(obj: Any) -> Optional[Dict[str, Any]]:
    return obj if isinstance(obj, dict) else None


def validate_hitl_question(q: Any) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    if not isinstance(q, dict):
        return False, ["question must be object"]
    if not q.get("id"):
        errs.append("missing id")
    if not str(q.get("ask") or "").strip():
        errs.append("missing ask")
    options = q.get("options")
    if not isinstance(options, list) or len(options) != 3:
        errs.append("options must be exactly 3 items (A/B/C)")
    else:
        keys = []
        for i, opt in enumerate(options):
            if not isinstance(opt, dict):
                errs.append(f"options[{i}] not object")
                continue
            k = str(opt.get("key") or "").upper()
            keys.append(k)
            if k not in HITL_OPTION_KEYS:
                errs.append(f"options[{i}].key must be A|B|C, got {opt.get('key')!r}")
            if not str(opt.get("label") or "").strip():
                errs.append(f"options[{i}] missing label")
        if keys != list(HITL_OPTION_KEYS):
            errs.append(f"option keys must be A,B,C in order, got {keys}")
    other = q.get("other")
    if not isinstance(other, dict):
        errs.append("other must be object {key,label,allows_text}")
    else:
        if str(other.get("key") or "").lower() not in {"other", "другое"}:
            errs.append("other.key must be 'other' (or 'Другое')")
        if not other.get("allows_text", True):
            errs.append("other.allows_text must be true")
        if not str(other.get("label") or "").strip():
            errs.append("other missing label")
    default = q.get("default_if_timeout")
    if default is not None and str(default).upper() not in HITL_OPTION_KEYS:
        errs.append("default_if_timeout must be A|B|C")
    return len(errs) == 0, errs


def validate_hitl_pack(data: Any) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    if not isinstance(data, dict):
        return False, ["hitl_pack must be object"]
    if data.get("kind") not in (None, "hitl_pack"):
        errs.append("kind must be hitl_pack")
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        errs.append("questions must be non-empty array")
        return False, errs
    if len(questions) > HITL_MAX_QUESTIONS:
        errs.append(f"max {HITL_MAX_QUESTIONS} questions per pack")
    for i, q in enumerate(questions):
        ok, qerrs = validate_hitl_question(q)
        if not ok:
            errs.extend(f"questions[{i}]: {e}" for e in qerrs)
    # reject open-ended without options (already covered) and freeform prompts
    for i, q in enumerate(questions):
        if isinstance(q, dict) and q.get("prompt") and not q.get("options"):
            errs.append(f"questions[{i}]: open prompt without options forbidden")
    return len(errs) == 0, errs


def normalize_hitl_pack(data: Dict[str, Any], *, cycle: int = 0) -> Dict[str, Any]:
    """Fill defaults; caller must validate first."""
    out = {
        "kind": "hitl_pack",
        "cycle": int(data.get("cycle") or cycle),
        "questions": [],
    }
    for q in data.get("questions") or []:
        if not isinstance(q, dict):
            continue
        other = q.get("other") if isinstance(q.get("other"), dict) else {}
        nq = {
            "id": str(q.get("id") or "Q1"),
            "topic": str(q.get("topic") or ""),
            "ask": str(q.get("ask") or "").strip(),
            "options": [],
            "other": {
                "key": "other",
                "label": str(other.get("label") or "Другое"),
                "allows_text": True,
            },
            "default_if_timeout": str(q.get("default_if_timeout") or "B").upper(),
        }
        if nq["default_if_timeout"] not in HITL_OPTION_KEYS:
            nq["default_if_timeout"] = "B"
        for opt in q.get("options") or []:
            if isinstance(opt, dict):
                nq["options"].append(
                    {
                        "key": str(opt.get("key") or "").upper(),
                        "label": str(opt.get("label") or "").strip(),
                    }
                )
        for field in ("related_plugin", "related_idea"):
            if q.get(field):
                nq[field] = q[field]
        out["questions"].append(nq)
    return out


def validate_skill_card(card: Any, *, max_chars: int = CARD_MAX_CHARS) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    if not isinstance(card, dict):
        return False, ["card must be object"]
    if not card.get("id"):
        errs.append("missing id")
    exports = card.get("exports")
    if not isinstance(exports, list):
        errs.append("exports must be list")
    else:
        for i, e in enumerate(exports):
            if not isinstance(e, str) or not e.strip():
                errs.append(f"exports[{i}] must be non-empty string")
    for key in ("attrs", "forbid", "files"):
        if key in card and card[key] is not None and not isinstance(card[key], list):
            errs.append(f"{key} must be list")
    # size budget on canonical JSON
    try:
        blob = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return False, ["card not JSON-serializable"]
    if len(blob) > max_chars:
        errs.append(f"card JSON > {max_chars} chars ({len(blob)})")
    return len(errs) == 0, errs


def card_char_len(card: Dict[str, Any]) -> int:
    return len(json.dumps(card, ensure_ascii=False, separators=(",", ":")))


def clamp_skill_card(card: Dict[str, Any], *, max_chars: int = CARD_MAX_CHARS) -> Dict[str, Any]:
    """Trim lists until card fits budget."""
    out = {
        "id": str(card.get("id") or "skill"),
        "exports": [str(x)[:80] for x in (card.get("exports") or []) if x][:6],
        "attrs": [str(x)[:40] for x in (card.get("attrs") or []) if x][:8],
        "forbid": [str(x)[:60] for x in (card.get("forbid") or []) if x][:6],
        "files": [str(x)[:60] for x in (card.get("files") or []) if x][:4],
    }
    while card_char_len(out) > max_chars and (
        out["exports"] or out["attrs"] or out["forbid"] or out["files"]
    ):
        for key in ("exports", "forbid", "attrs", "files"):
            if out[key]:
                out[key].pop()
                break
    return out


def parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # try extract first {...}
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def apply_timeout_defaults(pack: Dict[str, Any], answers: Dict[str, str]) -> Dict[str, str]:
    """Fill missing answers with default_if_timeout."""
    out = dict(answers)
    for q in pack.get("questions") or []:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or "")
        if qid and qid not in out:
            out[qid] = str(q.get("default_if_timeout") or "B").upper()
    return out
