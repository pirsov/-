"""Thin Ollama generate client with model discovery (fixes HTTP 404 model-not-found)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_GENERATE = "http://localhost:11434/api/generate"
DEFAULT_TAGS = "http://localhost:11434/api/tags"


def ping(url: str = DEFAULT_TAGS, timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_models(url: str = DEFAULT_TAGS, timeout: int = 10) -> List[str]:
    """Return installed model names from Ollama (e.g. qwen2.5-coder:7b-2k)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    names: List[str] = []
    for m in payload.get("models") or []:
        name = m.get("name") or m.get("model")
        if name:
            names.append(name)
    return names


def _base(name: str) -> str:
    return name.split(":", 1)[0].lower()


def _family_score(preferred: str, candidate: str) -> int:
    """Higher = better match for preferred tag among installed models."""
    if candidate == preferred:
        return 1000
    pb, pt = (preferred.split(":", 1) + [""])[:2]
    cb, ct = (candidate.split(":", 1) + [""])[:2]
    score = 0
    if cb.lower() == pb.lower():
        score += 100
    elif pb.lower() in cb.lower() or cb.lower() in pb.lower():
        score += 40
    # prefer coder family for this project
    if "coder" in cb.lower():
        score += 20
    # prefer larger ctx suffix hints when preferred asks for them
    for token in ("8k", "4k", "2k", "14b", "7b", "3b", "1.5b"):
        if token in pt and token in ct:
            score += 15
        elif token in preferred and token in candidate:
            score += 10
    return score


def resolve_model(
    preferred: str,
    installed: Optional[Sequence[str]] = None,
    *,
    allow_any: bool = True,
) -> Optional[str]:
    """Map a preferred tag onto an installed Ollama model. None if nothing usable."""
    if installed is None:
        installed = list_models()
    if not installed:
        return None
    if preferred in installed:
        return preferred
    # exact ignore-case
    lower = {n.lower(): n for n in installed}
    if preferred.lower() in lower:
        return lower[preferred.lower()]
    ranked = sorted(
        (( _family_score(preferred, n), n) for n in installed),
        key=lambda x: x[0],
        reverse=True,
    )
    if ranked and ranked[0][0] >= 40:
        return ranked[0][1]
    if allow_any:
        # prefer any coder, else first installed
        for n in installed:
            if "coder" in n.lower():
                return n
        return installed[0]
    return None


def generate(
    model: str,
    prompt: str,
    *,
    num_ctx: int = 2048,
    temperature: float = 0.1,
    num_predict: int = 1024,
    timeout: int = 1800,
    url: str = DEFAULT_GENERATE,
    diff_mode: bool = False,
) -> str:
    # A25: num_ctx capped at MAX_NUM_CTX (4096) so gameplay/client 14B can use 4k.
    # A15: num_predict capped via llm_backends (default 1024 / diff 512).
    try:
        from . import llm_backends

        opts = llm_backends.ollama_options(
            num_ctx=num_ctx,
            temperature=temperature,
            num_predict=num_predict,
            diff_mode=diff_mode,
        )
        num_ctx = int(opts["num_ctx"])
        temperature = float(opts["temperature"])
        num_predict = int(opts["num_predict"])
        # Refuse oversized prompts — Ollama would log `truncating input prompt`
        is_7b = "7b" in (model or "").lower()
        budget = llm_backends.effective_prompt_token_budget(
            is_7b=is_7b,
            num_ctx=num_ctx,
            num_predict=num_predict,
            diff_mode=diff_mode or is_7b,
        )
        if llm_backends.estimate_tokens(prompt) > budget:
            prompt, _meta = llm_backends.fit_prompt(prompt, budget)
            llm_backends.assert_prompt_fits(prompt, budget)
    except ValueError:
        raise
    except Exception:
        num_ctx = min(int(num_ctx), 4096)
        num_predict = min(int(num_predict), 1024)
    body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("response", "") or ""
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        installed = list_models()
        hint = ""
        if e.code == 404:
            hint = (
                f"\nModel '{model}' not found in Ollama (HTTP 404)."
                f"\nInstalled: {installed or '(none — is ollama running?)'}"
                f"\nFix: ollama pull {model}"
                f"\n  or edit forge/models.json to match `ollama list`"
            )
        raise RuntimeError(f"Ollama API error: HTTP Error {e.code}: {e.reason}.{hint}\n{detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama API error: {e}. Is Ollama running? Try: ollama serve"
        ) from e
