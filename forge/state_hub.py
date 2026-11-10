"""Forge state.json helpers — pulse tracking + contract compaction."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


STATE_NAME = "state.json"
COMPACT_EVERY_N = 5


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(root: Path) -> Path:
    return root / STATE_NAME


def load_state(root: Path) -> Dict[str, Any]:
    p = state_path(root)
    if not p.is_file():
        return {
            "pulse": {"cycle": 0},
            "done": [],
            "task_queue": [],
            "partial": [],
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"pulse": {"cycle": 0}, "done": [], "task_queue": [], "partial": [], "corrupt": True}
    if not isinstance(data, dict):
        return {"pulse": {"cycle": 0}, "done": [], "task_queue": [], "partial": []}
    data.setdefault("pulse", {"cycle": 0})
    data.setdefault("done", [])
    data.setdefault("task_queue", [])
    return data


def save_state(root: Path, data: Dict[str, Any]) -> None:
    from . import token_economy as te

    state_path(root).write_text(te.dumps_disk(data), encoding="utf-8")


def _one_liner(snapshot: Any) -> str:
    """A15: prefer local 7B summary; fall back to deterministic englishize."""
    from . import llm_backends

    if isinstance(snapshot, dict):
        purpose = snapshot.get("purpose") or snapshot.get("name") or ""
        return llm_backends.summarize_local(str(purpose), max_chars=120)
    if isinstance(snapshot, str):
        return llm_backends.summarize_local(snapshot, max_chars=120)
    return ""


def _write_contract_file(root: Path, plugin: str, snapshot: Dict[str, Any]) -> str:
    from . import contract_index

    contracts = root / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in plugin) or "plugin"
    rel = f"contracts/{safe}.json"
    payload = {
        "plugin": plugin,
        "compacted_at": now_iso(),
        "contract_snapshot": dict(snapshot),
    }
    contract_index.write_contract_payload(root / rel, payload)
    return rel


def compact_done_entry(root: Path, entry: Dict[str, Any], *, keep_recent_cycles: int = 1, current_cycle: int = 0) -> bool:
    """Collapse inline contract_snapshot into contract_ref. Returns True if mutated."""
    from . import token_economy as te

    snap = entry.get("contract_snapshot")
    if not isinstance(snap, dict):
        # Still englishize existing summary on compact pass
        if isinstance(entry.get("contract_summary"), str) and te.has_cyrillic(entry["contract_summary"]):
            entry["contract_summary"] = te.englishize_text(entry["contract_summary"], max_chars=120)
            return True
        return False
    closed_cycle = int(entry.get("closed_cycle") or 0)
    if keep_recent_cycles and closed_cycle and current_cycle and (current_cycle - closed_cycle) < keep_recent_cycles:
        return False
    plugin = str(entry.get("plugin") or snap.get("name") or "unknown")
    rel = _write_contract_file(root, plugin, snap)
    entry["contract_ref"] = rel
    entry["contract_summary"] = _one_liner(snap)
    entry.pop("contract_snapshot", None)
    return True


def compact_state(
    root: Path,
    *,
    force: bool = False,
    every_n: int = COMPACT_EVERY_N,
    keep_recent_cycles: int = 1,
) -> Dict[str, Any]:
    """
    Every `every_n` pulse cycles (or force), move heavy contract_snapshot dicts
    from state.json done[] into contracts/*.json and leave short refs.
    """
    data = load_state(root)
    pulse = data.setdefault("pulse", {})
    cycle = int(pulse.get("cycle") or 0)
    last = int(pulse.get("last_compact_cycle") or 0)

    due = force or (cycle > 0 and cycle % every_n == 0 and cycle != last)
    report: Dict[str, Any] = {
        "ran": False,
        "cycle": cycle,
        "compacted": 0,
        "skipped_recent": 0,
        "bytes_before": 0,
        "bytes_after": 0,
        "reason": "not_due",
    }
    raw = state_path(root)
    before = len(raw.read_text(encoding="utf-8")) if raw.is_file() else 0
    report["bytes_before"] = before

    if not due:
        return report

    from . import llm_backends

    compacted = 0
    for entry in data.get("done") or []:
        if not isinstance(entry, dict):
            continue
        if compact_done_entry(root, entry, keep_recent_cycles=keep_recent_cycles, current_cycle=cycle):
            compacted += 1
        elif isinstance(entry.get("contract_summary"), str):
            # A13/A15: EN summaries via local 7B (fallback englishize)
            en = llm_backends.summarize_local(entry["contract_summary"], max_chars=120)
            if en != entry["contract_summary"]:
                entry["contract_summary"] = en
                compacted += 1

    pulse["last_compact_cycle"] = cycle
    pulse["last_compact_at"] = now_iso()
    data["compact_report"] = {
        "at": now_iso(),
        "compacted": compacted,
        "every_n": every_n,
    }
    save_state(root, data)
    after = len(state_path(root).read_text(encoding="utf-8"))
    report.update(
        {
            "ran": True,
            "compacted": compacted,
            "bytes_after": after,
            "reason": "force" if force else f"cycle%{every_n}==0",
        }
    )
    return report


def bump_pulse_cycle(root: Path, *, delta: int = 1, auto_compact: bool = True) -> int:
    data = load_state(root)
    pulse = data.setdefault("pulse", {})
    cycle = int(pulse.get("cycle") or 0) + delta
    pulse["cycle"] = cycle
    save_state(root, data)
    if auto_compact:
        compact_state(root, force=False)
    return cycle


def record_task_status(
    root: Path,
    task_id: str,
    *,
    status: str,
    note: str = "",
    backend: str = "",
) -> None:
    """Update/create task_queue entry. Never marks plugins closed."""
    data = load_state(root)
    queue: List[Dict[str, Any]] = data.setdefault("task_queue", [])
    found = None
    for t in queue:
        if isinstance(t, dict) and t.get("id") == task_id:
            found = t
            break
    if found is None:
        found = {"id": task_id}
        queue.append(found)
    found["status"] = status  # in_progress | failed | ready — never closed via stub
    found["updated_at"] = now_iso()
    if note:
        found["note"] = note
    if backend:
        found["backend"] = backend
    if status == "failed":
        found["closed"] = False
        found.pop("plugin_closed", None)
    data.setdefault("knowledge_ref", "knowledge_base.json")
    save_state(root, data)


def link_knowledge_base(root: Path, kb_name: str = "knowledge_base.json") -> None:
    data = load_state(root)
    data["knowledge_ref"] = kb_name
    save_state(root, data)


def maybe_compact_after_week_gate(root: Path, completed_steps: int, every_n: int = COMPACT_EVERY_N) -> Optional[Dict[str, Any]]:
    """Hook: when week completed_steps hits multiple of every_n, bump cycle + compact."""
    if completed_steps <= 0 or completed_steps % every_n != 0:
        return None
    bump_pulse_cycle(root, delta=1, auto_compact=True)
    return compact_state(root, force=True)
