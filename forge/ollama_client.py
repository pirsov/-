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
    def _tie_break(name: str) -> tuple:
        # Prefer project's installed favorites when family scores tie
        low = name.lower()
        pref = 0
        if low == "qwen2.5-coder:14b-4k":
            pref = 50
        elif "14b-4k" in low:
            pref = 40
        elif "14b" in low and "coder" in low:
            pref = 30
        elif low == "qwen2.5-coder:7b-2k":
            pref = 25
        elif "7b-2k" in low:
            pref = 20
        elif "coder" in low:
            pref = 10
        return (pref, name)

    ranked = sorted(
        ((_family_score(preferred, n), n) for n in installed),
        key=lambda x: (x[0], _tie_break(x[1])),
        reverse=True,
    )
    if ranked and ranked[0][0] >= 40:
        return ranked[0][1]
    if allow_any:
        # prefer project favorites, else any coder, else first installed
        favorites = (
            "qwen2.5-coder:14b-4k",
            "qwen2.5-coder:7b-2k",
            "qwen2.5-coder:14b",
            "qwen2.5-coder:7b",
        )
        for fav in favorites:
            if fav in installed:
                return fav
        for n in installed:
            if "coder" in n.lower():
                return n
        return installed[0]
    return None


def looks_like_cloud_tag(name: str) -> bool:
    """OpenRouter-style org/model tags must never be sent to local Ollama."""
    n = (name or "").strip()
    if not n:
        return True
    if "/" in n:
        return True
    low = n.lower()
    if "space-bunny" in low or low.startswith("stealth"):
        return True
    return False


def _post_generate(
    body: Dict[str, Any],
    *,
    url: str,
    timeout: int,
) -> str:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("response", "") or ""


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
    # A29: never send cloud tags to Ollama; on HTTP 404 rematch via /api/tags once.
    preferred = (model or "").strip() or "qwen2.5-coder:14b-4k"
    installed: Optional[List[str]] = None

    def _installed() -> List[str]:
        nonlocal installed
        if installed is None:
            installed = list_models()
        return list(installed or [])

    if looks_like_cloud_tag(preferred):
        alt = resolve_model("qwen2.5-coder:14b-4k", _installed(), allow_any=True)
        if alt:
            print(f"   ollama model remap (cloud/invalid tag): {preferred} -> {alt}", flush=True)
            preferred = alt

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
        is_7b = "7b" in (preferred or "").lower()
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
        "model": preferred,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }

    try:
        return _post_generate(body, url=url, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code == 404:
            names = _installed()
            alt = resolve_model(preferred, names, allow_any=True)
            if alt and alt != preferred:
                print(f"   ollama 404 fallback: {preferred} -> {alt} (from tags)", flush=True)
                body["model"] = alt
                try:
                    return _post_generate(body, url=url, timeout=timeout)
                except urllib.error.HTTPError as e2:
                    detail2 = e2.read().decode("utf-8", errors="replace") if e2.fp else ""
                    raise RuntimeError(
                        f"Ollama API error: HTTP Error {e2.code}: {e2.reason} "
                        f"(after 404 fallback to '{alt}').\n"
                        f"Installed: {names or '(none)'}\n{detail2}"
                    ) from e2
            hint = (
                f"\nModel '{preferred}' not found in Ollama (HTTP 404)."
                f"\nInstalled: {names or '(none — is ollama running?)'}"
                f"\nFix: ollama pull qwen2.5-coder:14b-4k"
                f"\n  or edit forge/models.json to match `ollama list`"
            )
            raise RuntimeError(
                f"Ollama API error: HTTP Error {e.code}: {e.reason}.{hint}\n{detail}"
            ) from e
        raise RuntimeError(f"Ollama API error: HTTP Error {e.code}: {e.reason}.\n{detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama API error: {e}. Is Ollama running? Try: ollama serve"
        ) from e
