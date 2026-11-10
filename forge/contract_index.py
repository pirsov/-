"""A7.1 contract allowlist + hallucination gate for DeepSeek plans."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Always-allowed Remotes / Roblox builtins (not every contract repeats them)
BUILTIN_EXPORTS = {
    "Checkpoint",
    "CheckpointReached",
    "UpdateLeaderboard",
    "CoinCollected",
    "getOrCreate",
    "SetAttribute",
    "GetAttribute",
    "GetAttributeChangedSignal",
    "FireClient",
    "FireAllClients",
    # Engine services / player APIs — not plugin exports, but legal in plans
    "Players",
    "LocalPlayer",
    "PlayerGui",
    "Workspace",
    "ReplicatedStorage",
    "RunService",
    "TweenService",
    "SoundService",
    "ScreenGui",
    "TextLabel",
    "TextButton",
    "Instance",
    "UDim2",
    "Color3",
    "WaitForChild",
    "FindFirstChild",
}


def _safe_load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_export_token(s: str) -> str:
    """Reduce 'set_best_time(player, val: float) — ...' → 'set_best_time'."""
    t = (s or "").strip()
    # drop after dash comment
    t = re.split(r"\s+[—\-–]\s+", t, maxsplit=1)[0].strip()
    # player:GetBestTime → GetBestTime (method after colon)
    m_method = re.match(r"^[A-Za-z_][A-Za-z0-9_]*:([A-Za-z_][A-Za-z0-9_]*)", t)
    if m_method:
        return m_method.group(1)
    # function name before (
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_:]*)", t)
    if m:
        name = m.group(1)
        # Attr:Type → Attr (lowercase type annotation style)
        if ":" in name and not name.startswith(":"):
            left, right = name.split(":", 1)
            if right and right[0].islower():
                return left
            if right:
                return right
        return name
    return t


def build(root: Path) -> Dict[str, Any]:
    """Index contracts/*.json and contracts/golden/*.json."""
    exports: Set[str] = set(BUILTIN_EXPORTS)
    forbids: Set[str] = set()
    plugins: Dict[str, Dict[str, Any]] = {}
    files: Set[str] = set()
    paths_scanned: List[str] = []

    for folder in (root / "contracts", root / "contracts" / "golden"):
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.json")):
            paths_scanned.append(str(p.relative_to(root)))
            payload = _safe_load(p)
            if not payload:
                continue
            snap = payload.get("contract_snapshot")
            if not isinstance(snap, dict):
                snap = payload if payload.get("exports") or payload.get("name") else None
            if not isinstance(snap, dict):
                continue
            plugin = str(payload.get("plugin") or snap.get("name") or p.stem)
            plugins[plugin] = {
                "path": str(p.relative_to(root)),
                "purpose": snap.get("purpose") or "",
            }
            for e in snap.get("exports") or []:
                if isinstance(e, str) and e.strip():
                    exports.add(_normalize_export_token(e))
                    # also keep full first token with dots e.g. Remotes.X rare
                    exports.add(e.strip().split()[0][:80])
            for f in snap.get("forbidden") or snap.get("forbid") or []:
                if isinstance(f, str) and f.strip():
                    forbids.add(f.strip())
            for fp in snap.get("files") or []:
                if isinstance(fp, str) and fp.strip():
                    files.add(fp.strip())

    return {
        "exports": sorted(exports),
        "forbids": sorted(forbids),
        "plugins": plugins,
        "files": sorted(files),
        "scanned": paths_scanned,
    }


def extract_proposed_calls(plan: Any) -> List[str]:
    """Pull proposed API/export names from a planner plan dict or free text."""
    found: List[str] = []
    if isinstance(plan, dict):
        for key in ("proposed_calls", "exports", "apis", "functions"):
            val = plan.get(key)
            if isinstance(val, list):
                found.extend(str(x) for x in val if x)
            elif isinstance(val, str) and val.strip():
                found.append(val.strip())
        # nested tasks
        for t in plan.get("tasks") or []:
            if isinstance(t, dict):
                found.extend(extract_proposed_calls(t))
        text_bits = []
        for k in ("description", "note", "tz_line", "prompt"):
            if plan.get(k):
                text_bits.append(str(plan[k]))
        if text_bits:
            found.extend(_extract_from_text("\n".join(text_bits)))
    elif isinstance(plan, str):
        found.extend(_extract_from_text(plan))
    # normalize
    out: List[str] = []
    seen = set()
    for raw in found:
        tok = _normalize_export_token(raw)
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


_CALL_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(|"
    r"\b(GetBestTime|SetBestTime|CoinsCollected|player_data\.[A-Za-z_]+|"
    r"Remotes\.[A-Za-z_]+)\b"
)


def _extract_from_text(text: str) -> List[str]:
    out: List[str] = []
    for m in _CALL_RE.finditer(text or ""):
        g = m.group(1) or m.group(2)
        if g:
            out.append(g)
    return out


def gate_plan(
    root: Path,
    plan: Any,
    *,
    index: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Return (ok, unknown_exports, report).
    ok=False → do not enqueue TZ / do not call 14B.
    """
    idx = index or build(root)
    allowed = set(idx.get("exports") or [])
    # also allow plugin short names as non-calls
    proposed = extract_proposed_calls(plan)
    unknown: List[str] = []
    for call in proposed:
        if call in allowed:
            continue
        # allow if any allowed export endswith / contains call as function name
        if any(_normalize_export_token(a) == call or a.endswith("." + call) for a in allowed):
            continue
        # ignore very common Luau/Roblox noise
        if call in {
            "print",
            "require",
            "pairs",
            "ipairs",
            "typeof",
            "tostring",
            "Instance",
            "Vector3",
            "CFrame",
            "Color3",
            "task",
            "wait",
            "spawn",
            "Connect",
            "REWRITE",
            "APPEND",
        }:
            continue
        unknown.append(call)
    report = {
        "ok": len(unknown) == 0,
        "proposed": proposed,
        "unknown": unknown,
        "allowed_count": len(allowed),
    }
    if unknown:
        report["message"] = f"[planner] blocked hallucinated exports: {', '.join(unknown)}"
    return len(unknown) == 0, unknown, report


def repair_prompt(unknown: List[str], allowed_sample: List[str]) -> str:
    sample = ", ".join(allowed_sample[:40])
    return (
        f"FORBIDDEN hallucinated exports: {', '.join(unknown)}. "
        f"Rewrite the plan using ONLY these known exports/APIs: {sample}. "
        "Do not invent remotes, attrs, or helpers."
    )
