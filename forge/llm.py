"""Unified LLM backend: Ollama (local) or Space Bunny / OpenAI-compatible HTTP."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from . import ollama_client


def backend_name() -> str:
    explicit = (os.environ.get("FORGE_BACKEND") or "").strip().lower()
    if explicit in {"ollama", "spacebunny", "openrouter"}:
        return explicit
    if os.environ.get("SPACE_BUNNY_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
        if os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("SPACE_BUNNY_API_KEY"):
            return "openrouter"
        return "spacebunny"
    return "ollama"


def _openai_compat_generate(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body: Dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a coding agent in a Roblox Luau pipeline. "
                    "Reply with the exact XML tags requested. No markdown fences around the whole reply."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"LLM HTTP {e.code}: {e.reason}\n{detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM network error: {e}") from e

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM empty choices: {payload!r}")
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    if isinstance(content, list):
        # multimodal-style content parts
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text") or "")
            elif isinstance(p, str):
                parts.append(p)
        content = "".join(parts)
    return str(content)


def generate(
    model: str,
    prompt: str,
    *,
    num_ctx: int = 4096,
    temperature: float = 0.1,
    num_predict: int = 2048,
    timeout: int = 1800,
) -> str:
    be = backend_name()
    if be == "spacebunny":
        key = os.environ.get("SPACE_BUNNY_API_KEY") or ""
        if not key:
            raise RuntimeError(
                "FORGE_BACKEND=spacebunny but SPACE_BUNNY_API_KEY is unset. "
                "Get a free key: https://spacebunnymodel.com/get-jev"
            )
        return _openai_compat_generate(
            base_url=os.environ.get("SPACE_BUNNY_BASE_URL") or "https://spacebunnymodel.com/api/v1",
            api_key=key,
            model=model or "space-bunny-alpha",
            prompt=prompt,
            temperature=temperature,
            max_tokens=num_predict,
            timeout=timeout,
        )
    if be == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY") or ""
        if not key:
            raise RuntimeError("FORGE_BACKEND=openrouter but OPENROUTER_API_KEY is unset.")
        return _openai_compat_generate(
            base_url=os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
            api_key=key,
            model=model or "stealth/space-bunny-alpha",
            prompt=prompt,
            temperature=temperature,
            max_tokens=num_predict,
            timeout=timeout,
        )
    return ollama_client.generate(
        model,
        prompt,
        num_ctx=num_ctx,
        temperature=temperature,
        num_predict=num_predict,
        timeout=timeout,
    )


def ping() -> bool:
    be = backend_name()
    if be == "spacebunny":
        return bool(os.environ.get("SPACE_BUNNY_API_KEY"))
    if be == "openrouter":
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    return ollama_client.ping()


def list_models() -> List[str]:
    be = backend_name()
    if be == "spacebunny":
        return ["space-bunny-alpha"]
    if be == "openrouter":
        return ["stealth/space-bunny-alpha"]
    return ollama_client.list_models()


def resolve_model(preferred: str, installed: Optional[List[str]] = None, *, allow_any: bool = True) -> Optional[str]:
    be = backend_name()
    if be == "spacebunny":
        return "space-bunny-alpha"
    if be == "openrouter":
        return "stealth/space-bunny-alpha"
    return ollama_client.resolve_model(preferred, installed, allow_any=allow_any)
