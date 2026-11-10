"""A15.0 — apply SEARCH/REPLACE patches (Cursor/Aider style) to existing files."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Cursor / Aider fence
_PATCH_BLOCK = re.compile(
    r"<<<<<<<\s*SEARCH\s*\n([\s\S]*?)\n=======\s*\n([\s\S]*?)\n>>>>>>>\s*REPLACE",
    re.MULTILINE,
)
# Compact alternative inside FILE bodies
_ALT_BLOCK = re.compile(
    r"<<<SEARCH>>>\s*\n([\s\S]*?)\n<<<REPLACE>>>\s*\n([\s\S]*?)(?=\n<<<SEARCH>>>|\Z)",
    re.MULTILINE,
)


def extract_patches(text: str) -> List[Tuple[str, str]]:
    """Return list of (search, replace) pairs from model output."""
    out: List[Tuple[str, str]] = []
    for m in _PATCH_BLOCK.finditer(text or ""):
        out.append((m.group(1), m.group(2)))
    if out:
        return out
    for m in _ALT_BLOCK.finditer(text or ""):
        out.append((m.group(1).rstrip("\n"), m.group(2).rstrip("\n")))
    return out


def looks_like_patch(text: str) -> bool:
    t = text or ""
    return "<<<<<<< SEARCH" in t or "<<<SEARCH>>>" in t


def apply_patches(existing: str, patches: List[Tuple[str, str]]) -> Tuple[Optional[str], List[str]]:
    """
    Apply patches in order. Returns (new_text|None, errors).
    None means at least one SEARCH block failed to match.
    """
    if not patches:
        return None, ["no patches"]
    cur = existing
    errors: List[str] = []
    for i, (search, repl) in enumerate(patches, 1):
        if search not in cur:
            # try whitespace-normalized single-line fallback
            soft = re.sub(r"[ \t]+", " ", search.strip())
            found = False
            for line in cur.splitlines():
                if soft and soft in re.sub(r"[ \t]+", " ", line):
                    found = False  # too weak — require exact
                    break
            errors.append(f"patch#{i}: SEARCH not found ({len(search)} chars)")
            return None, errors
        cur = cur.replace(search, repl, 1)
    return cur, errors


def materialize_file_content(existing: Optional[str], model_body: str) -> Tuple[str, str]:
    """
    If model_body contains SEARCH/REPLACE and existing text is present, apply patches.
    Returns (final_content, mode) where mode is 'patch' | 'full'.
    """
    body = model_body or ""
    if existing is not None and looks_like_patch(body):
        patches = extract_patches(body)
        applied, errs = apply_patches(existing, patches)
        if applied is not None:
            return applied, "patch"
        # fall through to full body (strip fences if broken)
        if errs:
            pass
    return body, "full"
