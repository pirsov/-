"""Unified LLM backend: Ollama (local) or Space Bunny / OpenAI-compatible HTTP + stub degrade."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from . import ollama_client


class AuthError(RuntimeError):
    """API key rejected — do not retry the same key."""


class StubModeError(RuntimeError):
    """No live backend available — generation skipped (never closes plugins)."""


# Cached after resolve_runtime_backend(); invalidated on env fingerprint change
_RESOLVED: Optional[Tuple[str, str]] = None
_ENV_FP: Optional[Tuple[Optional[str], bool, bool]] = None


def reset_runtime_backend() -> None:
    global _RESOLVED, _ENV_FP
    _RESOLVED = None
    _ENV_FP = None


def _env_fingerprint() -> Tuple[Optional[str], bool, bool]:
    return (
        (os.environ.get("FORGE_BACKEND") or "").strip().lower() or None,
        bool(_clean_key(os.environ.get("SPACE_BUNNY_API_KEY"))),
        bool(_clean_key(os.environ.get("OPENROUTER_API_KEY"))),
    )


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
    return f"{key[:6]}...{key[-4:]} (len={len(key)})"


def _spacebunny_key() -> str:
    return _clean_key(os.environ.get("SPACE_BUNNY_API_KEY"))


def _openrouter_key() -> str:
    return _clean_key(os.environ.get("OPENROUTER_API_KEY"))


def _cloud_model_default(be: str) -> str:
    """Optional cloud model names (never used for local Ollama)."""
    try:
        from .prompts import OPENROUTER_CFG, SPACEBUNNY_CFG
    except Exception:
        OPENROUTER_CFG, SPACEBUNNY_CFG = {}, {}
    if be == "spacebunny":
        return str(
            os.environ.get("SPACE_BUNNY_MODEL")
            or (SPACEBUNNY_CFG or {}).get("model")
            or "space-bunny-alpha"
        )
    if be == "openrouter":
        return str(
            os.environ.get("OPENROUTER_MODEL")
            or (OPENROUTER_CFG or {}).get("model")
            or "qwen/qwen-2.5-coder-32b-instruct"
        )
    return "qwen2.5-coder:14b-4k"


def backend_name() -> str:
    """
    Preferred / configured backend name (legacy).
    Prefer resolve_runtime_backend()[0] for the *active* runtime after degrade.
    """
    explicit = (os.environ.get("FORGE_BACKEND") or "").strip().lower()
    if explicit in {"ollama", "spacebunny", "openrouter", "stub", "auto"}:
        if explicit == "auto":
            return resolve_runtime_backend()[0]
        return explicit
    if _spacebunny_key() or _openrouter_key():
        if _openrouter_key() and not _spacebunny_key():
            return "openrouter"
        if _spacebunny_key():
            return "spacebunny"
    return "ollama"


def resolve_runtime_backend(
    *,
    ollama_ping_fn=None,
    log: bool = True,
) -> Tuple[str, str]:
    """
    Cascade: explicit FORGE_BACKEND → ollama if up → spacebunny key → openrouter key → stub.

    Returns (backend, reason). Logs when falling off Ollama. Never crashes — stub is valid.
    """
    global _RESOLVED, _ENV_FP
    fp = _env_fingerprint()
    if _RESOLVED is not None and ollama_ping_fn is None and fp == _ENV_FP:
        return _RESOLVED

    ping_fn = ollama_ping_fn or ollama_client.ping
    explicit = (os.environ.get("FORGE_BACKEND") or "").strip().lower()

    def _finish(be: str, reason: str) -> Tuple[str, str]:
        global _RESOLVED, _ENV_FP
        if log:
            print(f"[llm] runtime backend={be} ({reason})")
        _RESOLVED = (be, reason)
        _ENV_FP = fp
        return be, reason

    def _cloud_or_stub(why: str) -> Tuple[str, str]:
        if _spacebunny_key():
            if log:
                print("[llm] Ollama unavailable, cascading to spacebunny")
            return _finish("spacebunny", f"{why} -> spacebunny")
        if _openrouter_key():
            if log:
                print("[llm] Ollama unavailable, cascading to openrouter")
            return _finish("openrouter", f"{why} -> openrouter")
        if log:
            print("[llm] Ollama unavailable, cascading to stub")
        return _finish("stub", f"{why} -> stub (dry skip, never closed)")

    # 1) Explicit usable backends
    if explicit == "stub":
        return _finish("stub", "FORGE_BACKEND=stub")
    if explicit == "spacebunny" and _spacebunny_key():
        return _finish("spacebunny", "FORGE_BACKEND=spacebunny")
    if explicit == "openrouter" and _openrouter_key():
        return _finish("openrouter", "FORGE_BACKEND=openrouter")
    if explicit in {"spacebunny", "openrouter"} and log:
        print(f"[llm] FORGE_BACKEND={explicit} but key missing - cascade to ollama/stub")

    # 2) Ollama when reachable
    if ping_fn():
        return _finish("ollama", "ollama ping ok")

    # 3–4) Cloud keys, else stub
    return _cloud_or_stub("Ollama unavailable")


def active_backend() -> str:
    return resolve_runtime_backend(log=False)[0]


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
                "OpenRouter 'User not found' = key revoked / wrong account / truncated.\n"
                "Fix NOW (local Ollama - no cloud key):\n"
                "  $env:FORGE_BACKEND = 'ollama'\n"
                "  Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue\n"
                "  Remove-Item Env:SPACE_BUNNY_API_KEY -ErrorAction SilentlyContinue\n"
                "  ollama serve\n"
                "  python run.py --week\n"
                "Or new OpenRouter key: https://openrouter.ai/keys (must start sk-or-v1-)\n"
                "Or Space Bunny: https://spacebunnymodel.com/get-jev -> SPACE_BUNNY_API_KEY=sb_live_...\n"
                "If OPENROUTER_API_KEY is set in Windows User env, remove it in System Properties -> Environment Variables."
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
    num_ctx: int = 2048,
    temperature: float = 0.1,
    num_predict: int = 2048,
    timeout: int = 1800,
    diff_mode: bool = False,
) -> str:
    be, reason = resolve_runtime_backend()
    if be == "stub":
        raise StubModeError(
            f"[STUB] Dry run: skipping code generation ({reason}). "
            "Plugin must NOT be marked closed."
        )
    # A15/A36: hard output ceiling (diff/repair tighter; code up to 2048)
    try:
        from . import llm_backends

        num_predict = llm_backends.cap_num_predict(num_predict, diff_mode=diff_mode)
    except Exception:
        num_predict = min(int(num_predict), 512 if diff_mode else 2048)
    if be == "spacebunny":
        key = _spacebunny_key()
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
            model=model or _cloud_model_default("spacebunny"),
            prompt=prompt,
            temperature=temperature,
            max_tokens=num_predict,
            timeout=timeout,
        )
    if be == "openrouter":
        key = _openrouter_key()
        if not key:
            raise AuthError("FORGE_BACKEND=openrouter but OPENROUTER_API_KEY is unset.")
        if not key.startswith("sk-or-"):
            print(f"   warn: OPENROUTER_API_KEY usually starts with sk-or- (got {_mask_key(key)})")
        return _openai_compat_generate(
            base_url=os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
            api_key=key,
            model=model or _cloud_model_default("openrouter"),
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
        diff_mode=diff_mode,
    )


def ping() -> bool:
    be = active_backend()
    if be == "stub":
        return True  # stub is "ready" — pipeline continues with skips
    if be == "spacebunny":
        return bool(_spacebunny_key())
    if be == "openrouter":
        return bool(_openrouter_key())
    return ollama_client.ping()


def auth_probe(timeout: int = 20) -> Tuple[bool, str]:
    """Tiny chat call to verify the cloud key. Returns (ok, message)."""
    be, reason = resolve_runtime_backend()
    if be == "stub":
        return True, f"stub ready ({reason}) - generation will skip, never closed"
    if be == "ollama":
        return ollama_client.ping(), "ollama ping"
    try:
        out = generate(
            _cloud_model_default(be),
            "Reply with exactly: PONG",
            num_predict=8,
            temperature=0,
            timeout=timeout,
        )
        return True, f"ok ({len(out)} chars)"
    except AuthError as e:
        return False, str(e)
    except StubModeError as e:
        return True, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def list_models() -> List[str]:
    be = active_backend()
    if be == "stub":
        return ["stub"]
    if be == "spacebunny":
        return [_cloud_model_default("spacebunny")]
    if be == "openrouter":
        return [_cloud_model_default("openrouter")]
    return ollama_client.list_models()


def resolve_model(preferred: str, installed: Optional[List[str]] = None, *, allow_any: bool = True) -> Optional[str]:
    be = active_backend()
    if be == "stub":
        return "stub"
    if be == "spacebunny":
        return _cloud_model_default("spacebunny")
    if be == "openrouter":
        return _cloud_model_default("openrouter")
    # A29: cloud-style tags must rematch onto installed Ollama tags
    if ollama_client.looks_like_cloud_tag(preferred):
        # Prefer 14B coder family when remapping invalid/cloud names
        return ollama_client.resolve_model(
            "qwen2.5-coder:14b-4k", installed, allow_any=allow_any
        ) or ollama_client.resolve_model(
            preferred or "qwen2.5-coder:14b-4k", installed, allow_any=allow_any
        )
    return ollama_client.resolve_model(preferred, installed, allow_any=allow_any)
