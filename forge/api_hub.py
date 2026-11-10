"""A9.0 API hub — bridge UI ↔ planner / feedback / state / run_hub."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

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

    # Prefer HITL pack when planner asks, else offer a pack for design chat
    pack = plan.get("pack")
    if action != "ask_hitl" or not isinstance(pack, dict):
        pack = deepseek.ask_hitl_pack(
            cycle=int((state.get("pulse") or {}).get("cycle") or 0), focus=goal[:80]
        )
        ok, errs = validate_hitl_pack(pack)
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
    # Next planner step after answers
    nxt = planner.plan_next(root, focus="after_hitl")
    return {
        "ok": True,
        "channel": "hitl",
        "status": "answered",
        "report": report,
        "next": nxt,
        "snapshot": status_snapshot(root),
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
