"""A15/A17 — Ollama backend caps + hard prompt budgets (no DeepSeek for dirty work).

num_predict defaults keep 6GB cards from generating prose walls.
Diff/repair paths use a tighter cap than first-pass codegen.

A17.0 Hard Context Fit:
  - local num_ctx = 2048 for 14B and 7B (leave room for num_predict≤1024)
  - STRICT prompt ceilings: 14B ≤ 2000 tok, 7B ≤ 1000 tok
  - effective budget = min(STRICT, num_ctx - num_predict - slack)
  - NEVER send prompts that would trigger Ollama `truncating input prompt`
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .prompts import load_model_config

_CFG = load_model_config()
_OLLAMA = dict(_CFG.get("ollama") or {})
_COMPACT = dict(_CFG.get("compact") or {})
_WEEK = dict(_CFG.get("week_mode") or {})

# Env overrides (FORGE_NUM_PREDICT / FORGE_NUM_PREDICT_DIFF)
DEFAULT_NUM_PREDICT = int(
    os.environ.get("FORGE_NUM_PREDICT")
    or _OLLAMA.get("num_predict")
    or _WEEK.get("max_predict_code")
    or 1024
)
DIFF_NUM_PREDICT = int(
    os.environ.get("FORGE_NUM_PREDICT_DIFF") or _OLLAMA.get("num_predict_diff") or 512
)
COMPACT_NUM_PREDICT = int(_COMPACT.get("predict") or 256)
COMPACT_MODEL = str(_COMPACT.get("model") or "qwen2.5-coder:7b-2k")
COMPACT_CTX = int(_COMPACT.get("ctx") or 2048)

# ---- A17.0 hard context ----------------------------------------------------
CHARS_PER_TOKEN = 4
LOCAL_NUM_CTX = int(os.environ.get("FORGE_NUM_CTX") or _OLLAMA.get("num_ctx") or 2048)
# Absolute STRICT ceilings (never exceed even if ctx is larger)
HARD_PROMPT_TOKENS_14B = int(os.environ.get("FORGE_PROMPT_TOKENS_14B") or 2000)
HARD_PROMPT_TOKENS_7B = int(os.environ.get("FORGE_PROMPT_TOKENS_7B") or 1000)
# Slack so prompt + predict never fill the whole window
PROMPT_CTX_RESERVE = int(os.environ.get("FORGE_PROMPT_CTX_RESERVE") or 32)


def cap_num_predict(n: int, *, diff_mode: bool = False) -> int:
    """Hard ceiling for Ollama output length (A15)."""
    cap = DIFF_NUM_PREDICT if diff_mode else DEFAULT_NUM_PREDICT
    try:
        val = int(n)
    except (TypeError, ValueError):
        val = cap
    return max(64, min(val, cap, 4096))


def cap_num_ctx(n: int) -> int:
    """A17: local Ollama ctx hard-capped at 2048 (14B + 7B)."""
    try:
        val = int(n)
    except (TypeError, ValueError):
        val = LOCAL_NUM_CTX
    return max(512, min(val, LOCAL_NUM_CTX))


def ollama_options(
    *,
    num_ctx: int = 2048,
    temperature: float = 0.1,
    num_predict: int = 1024,
    diff_mode: bool = False,
) -> Dict[str, Any]:
    return {
        "num_ctx": cap_num_ctx(num_ctx),
        "temperature": float(temperature),
        "num_predict": cap_num_predict(num_predict, diff_mode=diff_mode),
    }


def estimate_tokens(text: str) -> int:
    """Cheap local token estimate (≈4 chars/token). Never under-counts for safety."""
    n = len(text or "")
    if n <= 0:
        return 0
    return (n + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def hard_prompt_token_cap(*, is_7b: bool = False) -> int:
    return HARD_PROMPT_TOKENS_7B if is_7b else HARD_PROMPT_TOKENS_14B


def room_for_prompt(*, num_ctx: int, num_predict: int) -> int:
    """Tokens left for the prompt after reserving output + slack."""
    return max(256, int(num_ctx) - int(num_predict) - PROMPT_CTX_RESERVE)


def effective_prompt_token_budget(
    *,
    is_7b: bool = False,
    num_ctx: Optional[int] = None,
    num_predict: Optional[int] = None,
    diff_mode: bool = False,
) -> int:
    """
    STRICT fit budget:
      min(14B≤2000 | 7B≤1000,  num_ctx - num_predict - reserve)
    With defaults (ctx=2048, predict=1024) → ~992 tok for 14B.
    """
    ctx = cap_num_ctx(LOCAL_NUM_CTX if num_ctx is None else num_ctx)
    pred = cap_num_predict(
        DEFAULT_NUM_PREDICT if num_predict is None else num_predict,
        diff_mode=diff_mode or is_7b,
    )
    return min(hard_prompt_token_cap(is_7b=is_7b), room_for_prompt(num_ctx=ctx, num_predict=pred))


def tokens_to_chars(tokens: int) -> int:
    return max(0, int(tokens) * CHARS_PER_TOKEN)


# Sections dropped first when over budget (least critical → most critical kept).
_DROP_SECTION_ORDER = (
    "ACTIVE HITL RULES",
    "RULES",
    "CONTRACT CARDS",
    "CARDS",
    "SKELETON",
    "AGENTS.md",
    "Existing project files",
    "PROJECT_TZ.md",
    "QA_REPORT TEMPLATE",
    "REMOTES TEMPLATE",
    "CHECKPOINTS TEMPLATE",
    "EFFECTS TEMPLATE",
    "GENERATOR RULES",
    "COINS TEMPLATE",
    "LEVELCONFIG TEMPLATE",
    "HUD TEMPLATE",
    "LEADERBOARD TEMPLATE",
    "VOID RULES",
    "PUZZLES RULES",
    "ASSET",
)


def _strip_named_section(prompt: str, title_substr: str) -> str:
    """Remove a === TITLE === block whose title contains title_substr (case-insensitive)."""
    pat = re.compile(
        rf"(?ms)^===([^\n]*{re.escape(title_substr)}[^\n]*)===\s*\n.*?(?=^===|\Z)",
        re.IGNORECASE,
    )
    return pat.sub("", prompt)


_PROTECT_SECTION_RE = re.compile(
    r"(?ms)^(===\s*(?:VALIDATOR FEEDBACK|REPAIR MODE|YOUR TASK)[^\n]*===\s*\n.*?)(?=^===|\Z)"
)


def _extract_protected(prompt: str) -> Tuple[str, str]:
    """Pull validator/repair/task blocks aside so hard-truncate cannot drop them."""
    parts = _PROTECT_SECTION_RE.findall(prompt or "")
    if not parts:
        return prompt, ""
    protected = "\n".join(p.strip() for p in parts if p.strip())
    rest = _PROTECT_SECTION_RE.sub("", prompt or "")
    return rest, protected


def fit_prompt(
    prompt: str,
    max_tokens: int,
    *,
    keep_tail_chars: int = 900,
) -> Tuple[str, Dict[str, Any]]:
    """
    Force prompt under max_tokens. Prefer dropping bulky ===sections===,
    then hard-truncate middle while keeping head + format tail.
    Validator / REPAIR / YOUR TASK blocks are protected.
    Returns (fitted_prompt, meta).
    """
    raw = prompt or ""
    budget = max(256, int(max_tokens))
    before = estimate_tokens(raw)
    meta: Dict[str, Any] = {
        "tokens_before": before,
        "budget": budget,
        "dropped_sections": [],
        "hard_truncated": False,
        "tokens_after": before,
        "ok": before <= budget,
    }
    if before <= budget:
        return raw, meta

    rest, protected = _extract_protected(raw)
    text = rest
    for title in _DROP_SECTION_ORDER:
        if estimate_tokens(text) + estimate_tokens(protected) <= budget:
            break
        nxt = _strip_named_section(text, title)
        if nxt != text:
            meta["dropped_sections"].append(title)
            text = nxt

    # Collapse excess blank lines after section drops
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"

    def _combine(body: str, prot: str) -> str:
        body = body.rstrip()
        prot = (prot or "").strip()
        if not prot:
            return body + "\n"
        return body + "\n\n" + prot + "\n"

    combined = _combine(text, protected)
    if estimate_tokens(combined) > budget:
        # Shrink protected draft/feedback if still over (keep checklist lines)
        if protected and estimate_tokens(protected) > budget // 2:
            # Prefer keeping lines with CHECKLIST / numbered fails / YOUR TASK
            keep_lines = []
            for ln in protected.splitlines():
                if (
                    "CHECKLIST" in ln
                    or "YOUR TASK" in ln
                    or "REPAIR MODE" in ln
                    or "VALIDATOR" in ln
                    or re.match(r"^\s*\d+\.", ln)
                    or ln.startswith("===")
                    or ln.startswith("- [")
                    or "FindFirstChild" in ln
                    or "Humanoid.Died" in ln
                ):
                    keep_lines.append(ln)
                elif len("\n".join(keep_lines)) < tokens_to_chars(budget // 3):
                    keep_lines.append(ln)
            protected = "\n".join(keep_lines)
            combined = _combine(text, protected)

    if estimate_tokens(combined) > budget:
        max_chars = tokens_to_chars(budget)
        prot_budget = min(len(protected), max_chars // 2) if protected else 0
        body_budget = max(200, max_chars - prot_budget - 64)
        body = text
        if len(body) > body_budget:
            keep_tail = min(keep_tail_chars, body_budget // 3)
            keep_head = max(120, body_budget - keep_tail - 48)
            body = (
                body[:keep_head].rstrip()
                + "\n\n...(HARD_FIT truncated — prompt over budget)...\n\n"
                + body[-keep_tail:].lstrip()
            )
            meta["hard_truncated"] = True
        if protected and len(protected) > prot_budget > 0:
            protected = protected[:prot_budget].rstrip() + "\n...(protected trimmed)...\n"
            meta["hard_truncated"] = True
        combined = _combine(body, protected)

    # Absolute last resort: char clamp (still try to end with protected)
    max_chars = tokens_to_chars(budget)
    if len(combined) > max_chars:
        if protected:
            prot_part = protected[: max_chars // 2]
            head_room = max_chars - len(prot_part) - 48
            combined = (
                combined[: max(0, head_room)].rstrip()
                + "\n...(HARD_FIT hard cap)...\n"
                + prot_part
                + "\n"
            )
        else:
            combined = combined[: max_chars - 40].rstrip() + "\n...(HARD_FIT hard cap)...\n"
        meta["hard_truncated"] = True

    meta["tokens_after"] = estimate_tokens(combined)
    meta["ok"] = meta["tokens_after"] <= budget
    # Guarantee never over — if still over due to estimate rounding, trim more
    while meta["tokens_after"] > budget and len(combined) > 200:
        combined = combined[: max(200, len(combined) - CHARS_PER_TOKEN * 8)].rstrip() + "\n"
        meta["tokens_after"] = estimate_tokens(combined)
        meta["hard_truncated"] = True
        meta["ok"] = meta["tokens_after"] <= budget
    return combined, meta


def assert_prompt_fits(prompt: str, max_tokens: int) -> None:
    """Raise if prompt still exceeds budget (call after fit_prompt)."""
    tok = estimate_tokens(prompt)
    if tok > int(max_tokens):
        raise ValueError(
            f"prompt still over budget after hard-fit: {tok} > {max_tokens} tokens "
            "(refusing Ollama call to avoid truncating input prompt)"
        )


def resolve_7b(installed: Optional[List[str]] = None) -> str:
    from . import ollama_client

    preferred = COMPACT_MODEL
    resolved = ollama_client.resolve_model(preferred, installed, allow_any=True)
    return resolved or preferred


def summarize_local(text: str, *, max_chars: int = 120, timeout: int = 60) -> str:
    """
    Summarize with local 7B (A15). Falls back to englishize if Ollama down/stub.
    Never calls DeepSeek.
    """
    from . import token_economy as te

    raw = (text or "").strip()
    if not raw:
        return ""
    # Short / already-EN: deterministic path is enough
    if len(raw) <= max_chars and not te.has_cyrillic(raw):
        return raw[:max_chars]

    use_7b = (os.environ.get("FORGE_COMPACT_7B") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if not use_7b:
        return te.englishize_text(raw, max_chars=max_chars)

    try:
        from . import llm
        from . import ollama_client

        if not ollama_client.ping():
            return te.englishize_text(raw, max_chars=max_chars)
        be, _ = llm.resolve_runtime_backend()
        if be == "stub":
            return te.englishize_text(raw, max_chars=max_chars)

        model = resolve_7b()
        prompt = (
            "Summarize in English, one short line, no quotes, max "
            f"{max_chars} chars. Keep API names intact.\n\nTEXT:\n{raw[:800]}\n\nSUMMARY:"
        )
        # Compact helper itself must stay tiny (7B budget)
        budget = effective_prompt_token_budget(
            is_7b=True, num_ctx=COMPACT_CTX, num_predict=min(COMPACT_NUM_PREDICT, 128)
        )
        prompt, _meta = fit_prompt(prompt, budget)
        out = llm.generate(
            model,
            prompt,
            num_ctx=cap_num_ctx(COMPACT_CTX),
            temperature=0.0,
            num_predict=min(COMPACT_NUM_PREDICT, 128),
            timeout=timeout,
        )
        line = (out or "").strip().splitlines()[0] if out else ""
        line = re.sub(r'^["\']|["\']$', "", line).strip()
        if not line:
            return te.englishize_text(raw, max_chars=max_chars)
        return te.englishize_text(line, max_chars=max_chars)
    except Exception:
        return te.englishize_text(raw, max_chars=max_chars)
