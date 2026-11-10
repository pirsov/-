"""A15.0 — Ollama backend caps + local 7B helpers (no DeepSeek for dirty work).

num_predict defaults keep 6GB cards from generating prose walls.
Diff/repair paths use a tighter cap than first-pass codegen.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

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


def cap_num_predict(n: int, *, diff_mode: bool = False) -> int:
    """Hard ceiling for Ollama output length (A15)."""
    cap = DIFF_NUM_PREDICT if diff_mode else DEFAULT_NUM_PREDICT
    try:
        val = int(n)
    except (TypeError, ValueError):
        val = cap
    return max(64, min(val, cap, 4096))


def ollama_options(
    *,
    num_ctx: int = 4096,
    temperature: float = 0.1,
    num_predict: int = 1024,
    diff_mode: bool = False,
) -> Dict[str, Any]:
    return {
        "num_ctx": min(int(num_ctx), 4096),
        "temperature": float(temperature),
        "num_predict": cap_num_predict(num_predict, diff_mode=diff_mode),
    }


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
        out = llm.generate(
            model,
            prompt,
            num_ctx=COMPACT_CTX,
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
