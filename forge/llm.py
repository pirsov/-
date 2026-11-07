"""Unified LLM backend: Ollama (local) or Space Bunny / OpenAI-compatible HTTP."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from . import ollama_client


class AuthError(RuntimeError):
    """API key rejected — do not retry the same key."""


def backend_name() -> str:
    explicit = (os.environ.get("FORGE_BACKEND") or "").strip().lower()
    if explicit in {"ollama", "spacebunny", "openrouter"}:
        return explicit
    if os.environ.get("SPACE_BUNNY_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
        if os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("SPACE_BUNNY_API_KEY"):
            return "openrouter"
        return "spacebunny"
    return "ollama"


def _clean_key(raw: Optional[str]) -> str:
    if not raw:
        return ""
    key = raw.strip()
    # PowerShell users often set $env:KEY = "'sk-...'" with extra quotes
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    return key


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "(too short / empty)"
    return f"{key[:6]}…{key[-4:]} (len={len(key)})"


def _openai_compat_generate(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    extra_headers: Optional[Dict[str, str]] = None,
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
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code in {401, 403}:
            raise AuthError(
                f"LLM auth failed HTTP {e.code}: {e.reason}\n{detail}\n"
                f"Key in use: {_mask_key(api_key)}\n"
                "Fix:\n"
                "  OpenRouter → https://openrouter.ai/keys  then:\n"
                "    $env:FORGE_BACKEND='openrouter'\n"
                "    $env:OPENROUTER_API_KEY='sk-or-v1-...'\n"
                "  Space Bunny (hosted) → https://spacebunnymodel.com/get-jev  then:\n"
                "    $env:FORGE_BACKEND='spacebunny'\n"
                "    $env:SPACE_BUNNY_API_KEY='sb_live_...'\n"
                "  Do not put quotes inside the value. Re-open the terminal after setting User env vars."
            ) from e
        raise RuntimeError(f"LLM HTTP {e.code}: {e.reason}\n{detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM network error: {e}") from e

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM empty choices: {payload!r}")
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    if isinstance(content, list):
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
        key = _clean_key(os.environ.get("SPACE_BUNNY_API_KEY"))
        if not key:
            raise AuthError(
                "FORGE_BACKEND=spacebunny but SPACE_BUNNY_API_KEY is unset. "
                "Get a free key: https://spacebunnymodel.com/get-jev"
            )
        if not key.startswith("sb_"):
            print(f"   warn: SPACE_BUNNY_API_KEY usually starts with sb_live_ (got {_mask_key(key)})")
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
        key = _clean_key(os.environ.get("OPENROUTER_API_KEY"))
        if not key:
            raise AuthError("FORGE_BACKEND=openrouter but OPENROUTER_API_KEY is unset.")
        if not key.startswith("sk-or-"):
            print(f"   warn: OPENROUTER_API_KEY usually starts with sk-or- (got {_mask_key(key)})")
        return _openai_compat_generate(
            base_url=os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
            api_key=key,
            model=model or "stealth/space-bunny-alpha",
            prompt=prompt,
            temperature=temperature,
            max_tokens=num_predict,
            timeout=timeout,
            extra_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_REFERER") or "https://github.com/pirsov/-",
                "X-Title": os.environ.get("OPENROUTER_TITLE") or "QualityForge",
            },
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
        return bool(_clean_key(os.environ.get("SPACE_BUNNY_API_KEY")))
    if be == "openrouter":
        return bool(_clean_key(os.environ.get("OPENROUTER_API_KEY")))
    return ollama_client.ping()


def auth_probe(timeout: int = 20) -> Tuple[bool, str]:
    """Tiny chat call to verify the cloud key. Returns (ok, message)."""
    be = backend_name()
    if be == "ollama":
        return ollama_client.ping(), "ollama ping"
    try:
        out = generate(
            "space-bunny-alpha" if be == "spacebunny" else "stealth/space-bunny-alpha",
            "Reply with exactly: PONG",
            num_predict=8,
            temperature=0,
            timeout=timeout,
        )
        return True, f"ok ({len(out)} chars)"
    except AuthError as e:
        return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


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
