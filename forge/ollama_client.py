"""Thin Ollama generate client with retries."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


DEFAULT_URL = "http://localhost:11434/api/generate"


def generate(
    model: str,
    prompt: str,
    *,
    num_ctx: int = 4096,
    temperature: float = 0.1,
    num_predict: int = 2048,
    timeout: int = 1800,
    url: str = DEFAULT_URL,
) -> str:
    body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
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
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama API error: {e}") from e


def ping(url: str = "http://localhost:11434/api/tags", timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False
