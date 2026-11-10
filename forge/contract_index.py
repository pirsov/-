"""A7.1 contract allowlist + hallucination gate for DeepSeek plans."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import token_economy as te

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
    # DataStore (server-only; client_ui META still forbids)
    "DataStoreService",
    "GetDataStore",
    "GetAsync",
    "SetAsync",
    "UpdateAsync",
    "BindToClose",
    "PlayerAdded",
    "PlayerRemoving",
    "UserId",
    "typeof",
    # Networking (A10.2)
    "CoinSync",
    "DonateRequest",
    "SaveAck",
    "FireClient",
    "OnClientEvent",
    "OnServerEvent",
    "RemoteEvent",
    "RemoteFunction",
    "ReplicatedStorage",
    "FireServer",
}

# Never legal on client_ui / *.client.luau plans — even if listed as server exports
CLIENT_FORBIDDEN_EXPORTS = {
    "DataStoreService",
    "GetDataStore",
    "GetAsync",
    "SetAsync",
    "UpdateAsync",
    "BindToClose",
}


def _safe_load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_contract_payload(path: Path, payload: Dict[str, Any]) -> None:
    """Persist contract JSON minified (A13). Full keys kept for schema readers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Englishize purpose for token economy; keep export/forbid identifiers intact
    out = dict(payload)
    snap = out.get("contract_snapshot")
    if isinstance(snap, dict) and isinstance(snap.get("purpose"), str):
        snap = dict(snap)
        snap["purpose"] = te.englishize_text(snap["purpose"], max_chars=160)
        out["contract_snapshot"] = snap
    path.write_text(te.dumps_disk(out), encoding="utf-8")


def compact_index_for_llm(root: Path, *, max_chars: int = 800) -> str:
    """Minified short-key index slice for optional 14B injection."""
    idx = build(root)
    slim = {
        "exp": (idx.get("exports") or [])[:40],
        "f": (idx.get("forbids") or [])[:20],
        "pl": sorted((idx.get("plugins") or {}).keys())[:20],
    }
    return te.dumps_llm(slim)[:max_chars]


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


def _plan_is_client_side(plan: Any) -> bool:
    """Heuristic: client_ui archetype / .client.luau path / side=client."""
    if not isinstance(plan, dict):
        return False
    arch = str(plan.get("archetype") or "").lower()
    if arch == "client_ui":
        return True
    side = str(plan.get("side") or plan.get("role") or "").lower()
    if side in {"client", "local", "ui"}:
        return True
    for key in ("target_path", "path", "file"):
        p = str(plan.get(key) or "").replace("\\", "/")
        if p.endswith(".client.luau") or "/src/client/" in p:
            return True
    return False


def gate_plan(
    root: Path,
    plan: Any,
    *,
    index: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Return (ok, unknown_exports, report).
    ok=False → do not enqueue TZ / do not call 14B.
    Also blocks contract forbids and client-side DataStore APIs (A10.2).
    """
    idx = index or build(root)
    allowed = set(idx.get("exports") or [])
    client_side = _plan_is_client_side(plan)
    # Scope forbids to this plan's plugin (global forbids would block LocalPlayer on UI plans)
    forbids: Set[str] = set()
    if client_side:
        forbids |= set(CLIENT_FORBIDDEN_EXPORTS)
    plugin = ""
    if isinstance(plan, dict):
        plugin = str(plan.get("plugin") or "")
    if plugin:
        for name, meta in (idx.get("plugins") or {}).items():
            if name == plugin or name.startswith(plugin + ".") or plugin.startswith(name + "."):
                # re-read forbid list from that contract file
                rel = (meta or {}).get("path")
                if not rel:
                    continue
                payload = _safe_load(root / rel)
                if not payload:
                    continue
                snap = payload.get("contract_snapshot")
                if not isinstance(snap, dict):
                    snap = payload
                for f in snap.get("forbidden") or snap.get("forbid") or []:
                    if not isinstance(f, str) or not f.strip():
                        continue
                    raw = f.strip()
                    forbids.add(raw)
                    # Only normalize identifier-like forbids (Remotes.X / CamelCase),
                    # never phrases like "DataStoreService on client" → bare DataStoreService
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_\.]*$", raw):
                        forbids.add(_normalize_export_token(raw))
    # also allow plugin short names as non-calls
    proposed = extract_proposed_calls(plan)
    unknown: List[str] = []
    forbidden_hits: List[str] = []
    for call in proposed:
        if call in forbids or f"Remotes.{call}" in forbids:
            forbidden_hits.append(call)
            continue
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
            "UDim2",
            "GetService",
            "Players",
            "LocalPlayer",
            "PlayerGui",
            "WaitForChild",
            "GetAttribute",
            "SetAttribute",
            "GetAttributeChangedSignal",
            "ScreenGui",
            "TextLabel",
            "TextButton",
        }:
            continue
        unknown.append(call)
    blocked = unknown + forbidden_hits
    report = {
        "ok": len(blocked) == 0,
        "proposed": proposed,
        "unknown": unknown,
        "forbidden_hits": forbidden_hits,
        "client_side": client_side,
        "allowed_count": len(allowed),
    }
    if forbidden_hits:
        report["message"] = (
            f"[planner] blocked forbidden exports on "
            f"{'client' if client_side else 'plan'}: {', '.join(forbidden_hits)}"
        )
    elif unknown:
        report["message"] = f"[planner] blocked hallucinated exports: {', '.join(unknown)}"
    return len(blocked) == 0, blocked, report


def repair_prompt(unknown: List[str], allowed_sample: List[str]) -> str:
    sample = ", ".join(allowed_sample[:40])
    return (
        f"FORBIDDEN hallucinated exports: {', '.join(unknown)}. "
        f"Rewrite the plan using ONLY these known exports/APIs: {sample}. "
        "Do not invent remotes, attrs, or helpers."
    )
