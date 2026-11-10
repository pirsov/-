"""A13.0 Token Economy — shrink LLM context (EN cards, minify, short keys).

Disk schema for state/contracts keeps full English keys (readers unchanged).
Short keys + EN apply to *prompt bundles* fed to local 14B.
Set FORGE_JSON_PRETTY=1 to keep indented JSON on disk.
Set FORGE_TOKEN_ECONOMY=0 to disable prompt compaction.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Full → short keys for skill/contract cards in 14B bundles only
CARD_KEY_MAP = {
    "exports": "exp",
    "attrs": "a",
    "forbid": "f",
    "files": "fl",
    "purpose": "p",
    "name": "n",
    "id": "id",
    "plugin": "pl",
    "archetype": "arch",
    "skeleton_version": "sv",
    "forbidden": "f",
    "contract_snapshot": "cs",
}

# Frequent RU → EN for forge HITL / skill text (deterministic, no API)
_RU_EN = (
    (r"(?i)не\s+используй", "do not use"),
    (r"(?i)запрещено", "forbidden"),
    (r"(?i)обязательно", "required"),
    (r"(?i)клиент", "client"),
    (r"(?i)сервер", "server"),
    (r"(?i)монет", "coins"),
    (r"(?i)сохранени[ея]", "save"),
    (r"(?i)кнопк\w*", "button"),
    (r"(?i)игрок", "player"),
    (r"(?i)атрибут", "attribute"),
    (r"(?i)никогда", "never"),
    (r"(?i)только", "only"),
    (r"(?i)таймер", "timer"),
    (r"(?i)на\s+сервере", "on server"),
    (r"(?i)в\s+UI", "in UI"),
    (r"(?i)подводн\w+\s+камн\w+", "pitfall"),
    (r"(?i)утечк\w*\s+памяти", "memory leak"),
    (r"(?i)безопасн\w*", "safe"),
    (r"(?i)провер\w+", "check"),
    (r"(?i)сброс", "reset"),
    (r"(?i)смерть|умер", "death"),
    (r"(?i)персонаж", "character"),
)


def economy_enabled() -> bool:
    v = (os.environ.get("FORGE_TOKEN_ECONOMY") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def json_pretty() -> bool:
    v = (os.environ.get("FORGE_JSON_PRETTY") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def dumps_disk(obj: Any) -> str:
    """Serialize for disk: minified by default, pretty if FORGE_JSON_PRETTY=1."""
    if json_pretty():
        return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def dumps_llm(obj: Any) -> str:
    """Minified JSON for prompt injection."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


_CYR = re.compile(r"[\u0400-\u04FF]")


def has_cyrillic(text: str) -> bool:
    return bool(_CYR.search(text or ""))


def englishize_text(text: str, *, max_chars: int = 240) -> str:
    """
    Deterministic RU→EN compacting for LLM context (no API).
    Latin text passes through (trimmed). Remaining Cyrillic stripped.
    """
    s = (text or "").strip()
    if not s:
        return ""
    if has_cyrillic(s):
        for pat, repl in _RU_EN:
            s = re.sub(pat, repl, s)
        # drop leftover cyrillic runs
        s = _CYR.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip()
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_chars]


def short_keys(obj: Any) -> Any:
    """Recursively rename known long keys for LLM cards."""
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            nk = CARD_KEY_MAP.get(str(k), str(k))
            out[nk] = short_keys(v)
        return out
    if isinstance(obj, list):
        return [short_keys(x) for x in obj]
    return obj


def englishize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Englishize string fields on a skill/contract card."""
    out = dict(card)
    for key in ("purpose", "name", "id"):
        if isinstance(out.get(key), str) and has_cyrillic(out[key]):
            out[key] = englishize_text(out[key], max_chars=120)
    for list_key in ("exports", "forbid", "forbidden", "attrs", "files"):
        val = out.get(list_key)
        if isinstance(val, list):
            out[list_key] = [
                englishize_text(str(x), max_chars=100) if isinstance(x, str) else x for x in val
            ]
    return out


def economy_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Card ready for 14B: EN strings + short keys. Caller decides when to apply."""
    return short_keys(englishize_card(card))


def economy_rules_block(rules: List[Dict[str, Any]], *, max_chars: int = 800) -> str:
    """Compact active HITL rules in English for 14B."""
    lines: List[str] = []
    for r in rules:
        if r.get("status") != "active":
            continue
        rid = r.get("id") or "?"
        comment = englishize_text(str(r.get("human_comment") or ""), max_chars=80)
        lines.append(f"-{rid}:{comment}")
        for c in (r.get("checks") or [])[:2]:
            if not isinstance(c, dict):
                continue
            t = c.get("type") or "?"
            # shorten types
            t = {"forbid_regex": "fr", "require_regex": "rr", "forbid_substr": "fs", "require_substr": "rs"}.get(
                t, t
            )
            pat = c.get("pattern") or c.get("text") or ""
            lines.append(f" {t}:{englishize_text(str(pat), max_chars=60)}")
    text = "\n".join(lines)
    return text[:max_chars]


CODE_ECONOMY_RULES = (
    "TOKEN ECONOMY (local 14B ctx≤4k):\n"
    "- Do not write excessive comments. Critical one-liners only.\n"
    "- Use concise local variable names; keep public/contract names stable.\n"
    "- Output only the necessary code for THIS task.\n"
    "- Prefer Luau-compact forms; no decorative blank lines.\n"
)


def measure_bundle_savings(fat: str, lean: str) -> Dict[str, Any]:
    fb, lb = len(fat.encode("utf-8")), len(lean.encode("utf-8"))
    saved = max(0, fb - lb)
    pct = round(100.0 * saved / fb, 1) if fb else 0.0
    return {
        "bytes_before": fb,
        "bytes_after": lb,
        "bytes_saved": saved,
        "percent_saved": pct,
        "chars_before": len(fat),
        "chars_after": len(lean),
    }
