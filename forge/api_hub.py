"""A9.0 API hub — bridge UI ↔ planner / feedback / state / run_hub."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import deepseek, feedback, planner, run_hub, state_hub
from .planner_schema import validate_hitl_pack

ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def status_snapshot(root: Optional[Path] = None) -> Dict[str, Any]:
    """Enriched status for progress bars / 24h panel."""
    root = root or ROOT_DEFAULT
    state = state_hub.load_state(root)
    kb = feedback.load_knowledge(root)
    done = [d for d in (state.get("done") or []) if isinstance(d, dict)]
    closed = [d for d in done if d.get("status") in {"done", "closed", "closed_verified"}]
    verified = [d for d in done if d.get("status") == "closed_verified"]
    broken = [d for d in done if d.get("status") == "broken_by_user"]
    queue = [t for t in (state.get("task_queue") or []) if isinstance(t, dict)]
    pending = [t for t in queue if t.get("status") in {"ready", "in_progress", "failed", None}]
    pulse = state.get("pulse") or {}
    run = run_hub.status()
    pack = state.get("pending_hitl_pack")
    return {
        "ok": True,
        "pulse_cycle": pulse.get("cycle"),
        "pulse_status": pulse.get("status"),
        "mode": state.get("mode"),
        "plugins_closed": len(closed),
        "plugins_verified": len(verified),
        "plugins_broken": len(broken),
        "queue_total": len(queue),
        "queue_pending": len(pending),
        "queue": [
            {"id": t.get("id"), "status": t.get("status"), "title": t.get("title")}
            for t in queue[-12:]
        ],
        "open_questions": state.get("open_questions") or [],
        "pending_hitl": bool(isinstance(pack, dict) and pack.get("questions")),
        "hitl_pack": pack if isinstance(pack, dict) else None,
        "knowledge_rules": len(kb.get("rules") or []),
        "run": run,
        "waiting_human": run.get("status") == "waiting_human",
    }


def chat(
    root: Optional[Path] = None,
    *,
    message: str,
    project_id: str = "game1",
    auto_tz: bool = True,
) -> Dict[str, Any]:
    """
    User desire → improve goal + HITL pack (and optional TZ draft).
    If questions needed → status waiting_human (does not burn CPU).
    """
    root = root or ROOT_DEFAULT
    text = (message or "").strip()
    if not text:
        return {"ok": False, "error": "empty message"}

    improved = deepseek.improve_goal(text, project_id=project_id)
    goal = improved.get("goal") or text
    skills_hint = improved.get("skills_hint") or []

    # Persist desire
    state = state_hub.load_state(root)
    state["last_chat"] = {"message": text, "goal": goal, "skills_hint": skills_hint}
    state_hub.save_state(root, state)

    plan = planner.plan_next(root, focus=goal[:120])
    action = plan.get("action")

    # verify_plugin takes priority — do not drown it in a design HITL pack
    if action == "verify_plugin":
        run_hub.set_waiting_human(
            reason="verify_plugin",
            detail={"plugin": plan.get("plugin"), "goal": goal[:200]},
        )
        return {
            "ok": True,
            "status": "waiting_human",
            "goal": goal,
            "skills_hint": skills_hint,
            "verify_plugin": plan.get("plugin"),
            "hint": plan.get("hint"),
            "plan_action": action,
            "message": f"Проверьте плагин {plan.get('plugin')}: /api/answer с channel=verify",
        }

    # Prefer HITL pack when planner asks. Do NOT force a new pack when plan says
    # idle/ready_for_week — that re-triggered endless A/B/C after /api/answer.
    pack = plan.get("pack") if isinstance(plan.get("pack"), dict) else None
    if action == "ask_hitl" and not pack:
        pack = deepseek.ask_hitl_pack(
            cycle=int((state.get("pulse") or {}).get("cycle") or 0), focus=goal[:80]
        )
        ok, _errs = validate_hitl_pack(pack)
        if ok:
            state = state_hub.load_state(root)
            state["pending_hitl_pack"] = pack
            state_hub.save_state(root, state)
        else:
            pack = None
            action = "idle"
    elif action not in {"ask_hitl", "verify_plugin", "idle", "enqueue", "enqueue_blocked"}:
        # Unknown planner action on a fresh chat → offer one design pack
        pack = deepseek.ask_hitl_pack(
            cycle=int((state.get("pulse") or {}).get("cycle") or 0), focus=goal[:80]
        )
        ok, _errs = validate_hitl_pack(pack)
        if ok:
            state = state_hub.load_state(root)
            state["pending_hitl_pack"] = pack
            state_hub.save_state(root, state)
            action = "ask_hitl"
        else:
            pack = None

    tz_preview = None
    tz_tasks = 0
    if auto_tz and deepseek.available():
        try:
            from . import skills_hub

            compact = [c["id"] for c in skills_hub.list_compact(root)][:5]
            files = (
                [str(p.relative_to(root)) for p in (root / "src").rglob("*.luau")]
                if (root / "src").exists()
                else []
            )
            tz = deepseek.generate_project_tz(
                project_id=project_id, goal=goal, compact_skills=compact, existing_files=files
            )
            tz_tasks = deepseek.count_tz_tasks(tz)
            preview_path = root / "projects" / project_id / "PROJECT_TZ.chat.md"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.write_text(tz, encoding="utf-8")
            tz_preview = tz[:1200]
        except Exception as e:
            tz_preview = f"(tz skipped: {type(e).__name__}: {e})"

    if action == "ask_hitl" and pack:
        run_hub.set_waiting_human(reason="hitl_pack", detail={"goal": goal[:200]})
        return {
            "ok": True,
            "status": "waiting_human",
            "goal": goal,
            "skills_hint": skills_hint,
            "hitl_pack": pack,
            "tz_tasks": tz_tasks,
            "tz_preview": tz_preview,
            "plan_action": action,
            "message": "Ответьте A/B/C или Другое через /api/answer",
        }

    return {
        "ok": True,
        "status": "ready",
        "goal": goal,
        "skills_hint": skills_hint,
        "hitl_pack": pack,
        "tz_tasks": tz_tasks,
        "tz_preview": tz_preview,
        "plan_action": action,
        "message": "HITL закрыт — можно Старт 24h / генерацию --week",
        "snapshot": status_snapshot(root),
    }


def answer(
    root: Optional[Path] = None,
    *,
    answers: Optional[Dict[str, str]] = None,
    note: str = "",
    channel: str = "hitl",
    plugin: str = "",
    verdict: str = "",
    answer_str: str = "",
) -> Dict[str, Any]:
    """
    channel=hitl: Q1=B / other → planner.record_hitl_answers
    channel=verify: y/n + plugin → feedback.submit_verdict
    """
    root = root or ROOT_DEFAULT
    channel = (channel or "hitl").strip().lower()

    if channel == "verify":
        if not plugin:
            return {"ok": False, "error": "verify channel requires plugin"}
        v = verdict or answer_str or "y"
        report = feedback.submit_verdict(root, plugin, v, note=note)
        run_hub.clear_waiting_human()
        return {"ok": True, "channel": "verify", "report": report, "snapshot": status_snapshot(root)}

    # Parse answer_str like "Q1=B" if answers dict empty
    ans = dict(answers or {})
    other_notes: Dict[str, str] = {}
    if answer_str and "=" in answer_str:
        for part in answer_str.split(","):
            part = part.strip()
            if "=" not in part:
                continue
            qid, val = part.split("=", 1)
            qid, val = qid.strip(), val.strip()
            ans[qid] = val
            if val.lower() in {"other", "другое", "o"} and note:
                other_notes[qid] = note
    if not ans:
        return {"ok": False, "error": "no answers (use answers{} or answer='Q1=B')"}

    # Attach note to first other if needed
    if note:
        for qid, val in ans.items():
            if val.lower() in {"other", "другое", "o"} and qid not in other_notes:
                other_notes[qid] = note

    report = planner.record_hitl_answers(root, ans, other_notes=other_notes)
    if report.get("followups"):
        run_hub.set_waiting_human(reason="hitl_clarify", detail={"answers": ans})
        return {
            "ok": True,
            "channel": "hitl",
            "status": "waiting_human",
            "report": report,
            "hitl_pack": report["followups"][0] if report["followups"] else None,
            "snapshot": status_snapshot(root),
        }

    run_hub.clear_waiting_human()
    # Must use after_hitl so plan_next returns idle (not a brand-new ask_hitl pack).
    nxt = planner.plan_next(root, focus="after_hitl")
    # If 24h loop is alive, it resumes on clear_waiting_human → looping and will
    # call start_week. Do not re-enter waiting_human here.
    snap = status_snapshot(root)
    # Drop stale pack from snapshot so UI does not re-render Q1 after "Ответ принят"
    if isinstance(snap, dict):
        snap = dict(snap)
        if nxt.get("action") != "ask_hitl":
            snap["hitl_pack"] = None
            snap["pending_hitl"] = False
            snap["waiting_human"] = False
    return {
        "ok": True,
        "channel": "hitl",
        "status": "answered",
        "report": report,
        "next": nxt,
        "message": "Ответ принят — агент продолжает (week/24h)",
        "snapshot": snap,
    }


def start_24h(
    root: Optional[Path] = None,
    *,
    sleep: float = 30.0,
    max_cycles: int = 48,
    week_max_steps: int = 5,
) -> Dict[str, Any]:
    """Start autonomous loop in background (threading)."""
    root = root or ROOT_DEFAULT
    return run_hub.start_24h(
        root,
        sleep=sleep,
        max_cycles=max_cycles,
        week_max_steps=week_max_steps,
    )


def stop_24h(**kwargs: Any) -> Dict[str, Any]:
    return run_hub.stop_24h(**kwargs)


# ---- A17.0 file explorer -------------------------------------------------

_CODE_SUFFIXES = {".luau", ".lua", ".json", ".md", ".txt"}


def _active_project_id(root: Path) -> Optional[str]:
    active = root / ".forge" / "active_project.json"
    if not active.exists():
        return None
    try:
        data = json.loads(active.read_text(encoding="utf-8"))
    except Exception:
        return None
    pid = data.get("id") if isinstance(data, dict) else None
    return str(pid) if pid else None


def _file_scan_roots(root: Path) -> List[Tuple[str, Path]]:
    """Allowed scan roots as (label_prefix, absolute_dir)."""
    roots: List[Tuple[str, Path]] = []
    live = (root / "src").resolve()
    if live.is_dir():
        roots.append(("src", live))
    pid = _active_project_id(root)
    if pid:
        # keep project id path-safe (no traversal via active_project.json)
        safe = str(pid).replace("\\", "/").strip("/")
        if safe and ".." not in safe.split("/") and "/" not in safe and "\\" not in safe:
            proj_src = (root / "projects" / safe / "src").resolve()
            if proj_src.is_dir():
                roots.append((f"projects/{safe}/src", proj_src))
    return roots


def _collect_under(dir_path: Path, *, prefix: str, limit: int) -> List[str]:
    out: List[str] = []
    if not dir_path.is_dir():
        return out
    for p in sorted(dir_path.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in _CODE_SUFFIXES:
            continue
        try:
            rel = p.relative_to(dir_path).as_posix()
        except ValueError:
            continue
        out.append(f"{prefix}/{rel}" if prefix else rel)
        if len(out) >= limit:
            break
    return out


def _files_to_tree(files: List[str]) -> List[Dict[str, Any]]:
    """Build nested accordion tree from flat posix paths."""
    root: Dict[str, Any] = {}
    for rel in files:
        parts = [p for p in rel.split("/") if p]
        node = root
        for i, part in enumerate(parts):
            is_file = i == len(parts) - 1
            key = part + ("\0f" if is_file else "\0d")
            if key not in node:
                entry: Dict[str, Any] = {"name": part, "type": "file" if is_file else "dir"}
                if is_file:
                    entry["path"] = "/".join(parts)
                else:
                    entry["children"] = {}
                node[key] = entry
            if not is_file:
                node = node[key]["children"]

    def freeze(children: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for entry in sorted(children.values(), key=lambda e: (e["type"] != "dir", e["name"].lower())):
            item = {"name": entry["name"], "type": entry["type"]}
            if entry["type"] == "file":
                item["path"] = entry["path"]
            else:
                item["children"] = freeze(entry["children"])
            out.append(item)
        return out

    return freeze(root)


def list_files(root: Optional[Path] = None, *, limit: int = 200) -> Dict[str, Any]:
    """
    File tree for UI explorer: workspace src/ + projects/<active>/src if present.
    Returns paths as posix strings relative to workspace root + nested tree.
    """
    root = (root or ROOT_DEFAULT).resolve()
    files: List[str] = []
    seen = set()
    for prefix, dir_path in _file_scan_roots(root):
        remaining = max(0, limit - len(files))
        if remaining <= 0:
            break
        for rel in _collect_under(dir_path, prefix=prefix, limit=remaining):
            if rel in seen:
                continue
            seen.add(rel)
            files.append(rel)
    return {
        "ok": True,
        "files": files,
        "tree": _files_to_tree(files),
        "count": len(files),
        "active_project": _active_project_id(root),
        "roots": [prefix for prefix, _ in _file_scan_roots(root)],
    }


def _resolve_under_allowed(root: Path, rel: str) -> Path:
    """Resolve rel under allowed src roots; raise ValueError on traversal / escape."""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("/") or ":" in rel.split("/")[0]:
        raise ValueError("bad path")
    parts = rel.split("/")
    if ".." in parts or any(p == "" for p in parts):
        raise ValueError("path traversal rejected")

    allowed = [dir_path for _, dir_path in _file_scan_roots(root)]
    # Also allow reading any file under root/src or projects/*/src even if active differs,
    # but only via explicit projects/<id>/src/... form that still resolves under root/projects.
    proj = (root / "projects").resolve()
    if proj.is_dir():
        for child in proj.iterdir():
            if child.is_dir():
                src = (child / "src").resolve()
                if src.is_dir() and src not in allowed:
                    allowed.append(src)
    live = (root / "src").resolve()
    if live.is_dir() and live not in allowed:
        allowed.append(live)

    candidate = (root / rel).resolve()
    root_s = str(root.resolve())
    if not (str(candidate) == root_s or str(candidate).startswith(root_s + os.sep)):
        raise ValueError("path outside root")
    under = False
    for base in allowed:
        base_s = str(base)
        if str(candidate) == base_s or str(candidate).startswith(base_s + os.sep):
            under = True
            break
    if not under:
        raise ValueError("path not under allowed src roots")
    if not candidate.is_file():
        raise FileNotFoundError(rel)
    return candidate


def read_file(
    rel: str,
    root: Optional[Path] = None,
    *,
    max_chars: int = 120000,
) -> Dict[str, Any]:
    """Read text of a code file under allowed roots (path-traversal safe)."""
    root = (root or ROOT_DEFAULT).resolve()
    path = _resolve_under_allowed(root, rel)
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    return {
        "ok": True,
        "path": rel.replace("\\", "/").lstrip("/"),
        "chars": len(text),
        "truncated": truncated,
        "content": text[:max_chars],
    }
