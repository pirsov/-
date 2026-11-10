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


EMPTY_TZ_TEMPLATE = """# LAST_UPDATE: {project_id} fresh start
# Goal: (set via UI chat / DeepSeek -- generate PROJECT_TZ)

## AGENT

## HUMAN
"""


def _is_forge_done_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    plugin = str(entry.get("plugin") or "")
    return plugin.startswith("forge.") or plugin in {"forge", "system"}


def fresh_runtime_state(
    existing: Optional[Dict[str, Any]] = None,
    *,
    keep_all_done: bool = False,
) -> Dict[str, Any]:
    """Empty runtime overlay: cleared queue/pulse/HITL.

    By default (bare --reset-state) only forge.* done rows are kept so
    leftover game1.* verify_plugin prompts cannot reappear. Pass
    keep_all_done=True when a later project filter will trim done[].
    """
    keep: Dict[str, Any] = {}
    if isinstance(existing, dict):
        for key in ("milestone", "inventory_at", "repo", "roles_map", "knowledge_ref"):
            if key in existing:
                keep[key] = existing[key]
        done = existing.get("done")
        if isinstance(done, list):
            if keep_all_done:
                keep["done"] = list(done)
            else:
                keep["done"] = [e for e in done if _is_forge_done_entry(e)]
    keep.update(
        {
            "pulse": {"cycle": 0, "status": "idle"},
            "task_queue": [],
            "partial": [],
            "open_questions": [],
        }
    )
    # HITL / verify leftovers that would immediately re-park the 24h loop
    for key in (
        "pending_hitl_pack",
        "last_chat",
        "compact_report",
        "verify_plugin",
        "pending_verify_plugin",
        "waiting_human",
        "hitl_pack",
    ):
        keep.pop(key, None)
    return keep


def _filter_done_for_project(done: List[Any], project_id: str) -> List[Any]:
    """Drop done[] rows belonging to project_id; keep forge/system/other projects."""
    prefix = f"{project_id}."
    out: List[Any] = []
    for entry in done:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        plugin = str(entry.get("plugin") or "")
        if plugin.startswith(prefix) or plugin == project_id:
            continue
        out.append(entry)
    return out


def ensure_project_scaffold(root: Path, project_id: str) -> Path:
    """Create projects/<id> with empty TZ/meta if missing. Does not touch other projects."""
    from . import projects_hub

    base = projects_hub.projects_root(root)
    base.mkdir(parents=True, exist_ok=True)
    proj = base / project_id
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "src").mkdir(exist_ok=True)
    (proj / "smoke").mkdir(exist_ok=True)
    tz_path = proj / "PROJECT_TZ.md"
    if not tz_path.is_file():
        tz_path.write_text(EMPTY_TZ_TEMPLATE.format(project_id=project_id), encoding="utf-8")
    meta_p = proj / "meta.json"
    if meta_p.is_file():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {"id": project_id}
    else:
        meta = {
            "id": project_id,
            "name": project_id,
            "title": project_id,
            "created": now_iso(),
            "backend_code": "ollama",
            "backend_prompt": "deepseek",
            "status": "fresh",
            "skills_compact": ["forge-player-attrs", "forge-luau-touch"],
        }
    meta["id"] = project_id
    meta["status"] = "fresh"
    meta["smoke"] = {"pending": True}
    meta["reset_at"] = now_iso()
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return proj


def write_empty_project_tz(root: Path, project_id: str) -> Path:
    """Overwrite project + live TZ with empty new-game template."""
    text = EMPTY_TZ_TEMPLATE.format(project_id=project_id)
    proj = root / "projects" / project_id
    proj.mkdir(parents=True, exist_ok=True)
    proj_tz = proj / "PROJECT_TZ.md"
    proj_tz.write_text(text, encoding="utf-8")
    (root / "PROJECT_TZ.md").write_text(text, encoding="utf-8")
    # Clear generated/chat previews so UI does not show stale TZ
    for name in ("PROJECT_TZ.generated.md", "PROJECT_TZ.chat.md", "PROJECT_TZ.fix.md"):
        p = proj / name
        if p.is_file():
            p.unlink()
    return proj_tz


def reset_ui_progress(root: Path) -> None:
    from . import progress_hub

    progress_hub.save(
        root,
        {
            "activated": False,
            "skills_done": False,
            "tz_done": False,
            "run_done": False,
            "smoke_done": False,
            "fix_tz_done": False,
            "fix_done": False,
            "skipped": [],
        },
    )


def reset_run_hub_counters() -> Dict[str, Any]:
    """Stop 24h loop if any and clear cycle 48/48 smoke stall counters."""
    from . import run_hub

    try:
        run_hub.stop_24h(join_timeout=1.0)
    except Exception:
        pass
    run_hub._stop_event.clear()
    with run_hub._lock:
        run_hub._state.update(
            {
                "status": "idle",
                "started_at": None,
                "ended_at": None,
                "exit_code": None,
                "pid": None,
                "log_path": None,
                "report": {},
                "mode": None,
                "waiting_reason": None,
                "waiting_detail": None,
                "loop_cycle": 0,
                "loop_max": 0,
                "stop_requested": False,
            }
        )
    return dict(run_hub._state)


def reset_state(root: Path, *, project_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Clear task queue, reset pulse/cycles, and prepare a fresh empty runtime
    suitable for a new game. When project_id is set, only that project's TZ/meta
    are rewritten; other projects under projects/ are left untouched.
    Bare --reset-state also drops game.* done rows (verify_plugin leftovers).
    """
    existing = load_state(root)
    if project_id:
        # Keep sibling projects' done[]; filter this project after.
        data = fresh_runtime_state(existing, keep_all_done=True)
        data["done"] = _filter_done_for_project(list(data.get("done") or []), project_id)
        ensure_project_scaffold(root, project_id)
        write_empty_project_tz(root, project_id)
        from . import projects_hub

        projects_hub.activate_project(root, project_id)
        # Soft-clear smoke latest so progress_hub does not auto-mark smoke_done
        smoke_latest = root / "projects" / project_id / "smoke" / "latest.json"
        if smoke_latest.is_file():
            smoke_latest.unlink()
    else:
        # Full workspace wipe of game verify leftovers; keep forge.* inventory only
        data = fresh_runtime_state(existing, keep_all_done=False)
        (root / "PROJECT_TZ.md").write_text(
            EMPTY_TZ_TEMPLATE.format(project_id="(none)"),
            encoding="utf-8",
        )

    save_state(root, data)
    reset_ui_progress(root)
    run_st = reset_run_hub_counters()

    report = {
        "ok": True,
        "project": project_id,
        "pulse_cycle": int((data.get("pulse") or {}).get("cycle") or 0),
        "queue_len": len(data.get("task_queue") or []),
        "done_kept": len(data.get("done") or []),
        "loop_cycle": run_st.get("loop_cycle"),
        "loop_max": run_st.get("loop_max"),
        "run_status": run_st.get("status"),
        "tz": "empty",
        "cleared_verify": project_id is None,
    }
    return report
