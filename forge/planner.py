"""A7.1 planner orchestrator — HITL packs, contract gate, feedback wiring."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import contract_index, deepseek, feedback, state_hub
from .planner_schema import apply_timeout_defaults, validate_hitl_pack


def plan_next(root: Path, *, focus: str = "") -> Dict[str, Any]:
    """
    Decide next action for the agent core loop.
    Returns {action: ask_hitl|verify_plugin|enqueue_blocked|idle, ...}
    """
    state = state_hub.load_state(root)
    cycle = int((state.get("pulse") or {}).get("cycle") or 0)
    kb = feedback.load_knowledge(root)

    # Prefer verifying plugins that are done but not closed_verified
    for entry in state.get("done") or []:
        if not isinstance(entry, dict):
            continue
        plugin = str(entry.get("plugin") or "")
        if not plugin.startswith("game1."):
            continue
        st = entry.get("status")
        kb_st = (kb.get("plugins") or {}).get(plugin, {}).get("status")
        if st in {"done", "closed"} and kb_st not in {"closed_verified", "broken_by_user"}:
            return {
                "action": "verify_plugin",
                "plugin": plugin,
                "hint": "Run: python run.py --feedback y|n --plugin "
                f"{plugin} --note \"...\"",
                "cycle": cycle,
            }

    # Otherwise ask design HITL pack
    pack = deepseek.ask_hitl_pack(cycle=cycle, focus=focus)
    ok, errs = validate_hitl_pack(pack)
    if not ok:
        return {"action": "idle", "error": errs, "cycle": cycle}
    # persist pending pack
    state["pending_hitl_pack"] = pack
    state_hub.save_state(root, state)
    return {"action": "ask_hitl", "pack": pack, "cycle": cycle}


def record_hitl_answers(
    root: Path,
    answers: Dict[str, str],
    *,
    other_notes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Apply CLI answers to pending pack.
    other → clarify_other; A/B/C → store in open_questions.
    Does NOT call feedback unless answer maps to verify channel explicitly.
    """
    state = state_hub.load_state(root)
    pack = state.get("pending_hitl_pack")
    if not isinstance(pack, dict):
        return {"ok": False, "error": "no pending_hitl_pack — run --ask-pack first"}
    other_notes = other_notes or {}
    resolved: Dict[str, Any] = {}
    followups: List[Dict[str, Any]] = []

    for q in pack.get("questions") or []:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or "")
        ans = (answers.get(qid) or "").strip()
        if not ans:
            continue
        key = ans.upper() if ans.upper() in {"A", "B", "C"} else ans.lower()
        if key in {"other", "другое", "o"}:
            note = other_notes.get(qid) or answers.get(f"{qid}_note") or ""
            clarified = deepseek.clarify_other(
                question=q,
                other_text=note or "(empty)",
                cycle=int(pack.get("cycle") or 0),
            )
            if isinstance(clarified.get("resolved"), dict):
                resolved[qid] = clarified["resolved"]
            else:
                followups.append(clarified)
                state["pending_hitl_pack"] = clarified
        elif key in {"A", "B", "C"}:
            label = next(
                (o.get("label") for o in (q.get("options") or []) if str(o.get("key")).upper() == key),
                key,
            )
            resolved[qid] = {"key": key, "label": label}

    # timeout defaults for unanswered
    filled = apply_timeout_defaults(pack, {k: v.get("key", v) if isinstance(v, dict) else v for k, v in resolved.items()})
    for q in pack.get("questions") or []:
        qid = str(q.get("id") or "")
        if qid and qid not in resolved and filled.get(qid):
            key = filled[qid]
            label = next(
                (o.get("label") for o in (q.get("options") or []) if str(o.get("key")).upper() == key),
                key,
            )
            resolved[qid] = {"key": key, "label": label, "via": "timeout_default"}

    oq = []
    for q in pack.get("questions") or []:
        qid = str(q.get("id") or "")
        if qid in resolved:
            oq.append(
                {
                    "id": qid,
                    "topic": q.get("topic"),
                    "ask": q.get("ask"),
                    "status": "answered",
                    "answer": resolved[qid],
                    "related_plugin": q.get("related_plugin"),
                }
            )
    state["open_questions"] = oq
    if not followups:
        state.pop("pending_hitl_pack", None)
    state_hub.save_state(root, state)
    return {"ok": True, "resolved": resolved, "followups": followups}


def submit_plugin_verdict(root: Path, plugin: str, verdict: str, note: str = "") -> Dict[str, Any]:
    """Wire verify channel → feedback.submit_verdict."""
    return feedback.submit_verdict(root, plugin, verdict, note=note)


def gate_and_plan(
    root: Path,
    plan: Dict[str, Any],
    *,
    retry: bool = True,
) -> Dict[str, Any]:
    """
    Hallucination gate. If blocked and retry, ask DeepSeek once with repair prompt
    (only if API available); else return blocked (do not enqueue generation).
    A11: also blocks unknown proposed_assets vs assets/catalog.
    """
    from . import asset_hub

    ok, unknown, report = contract_index.gate_plan(root, plan)
    if ok:
        a_ok, a_unknown, a_report = asset_hub.gate_assets(root, plan)
        if not a_ok:
            msg = a_report.get("message") or f"blocked assets: {a_unknown}"
            print(msg)
            return {
                "action": "enqueue_blocked",
                "unknown": a_unknown,
                "gate": report,
                "assets": a_report,
                "hint": "add .glb/.ldr to assets/models/ or drop invented proposed_assets",
            }
        return {"action": "enqueue", "plan": plan, "gate": report, "assets": a_report}
    msg = report.get("message") or f"blocked: {unknown}"
    print(msg)
    if retry and deepseek.available():
        idx = contract_index.build(root)
        repair = contract_index.repair_prompt(unknown, list(idx.get("exports") or []))
        try:
            raw = deepseek.chat(
                json.dumps(plan, ensure_ascii=False)[:4000] + "\n\n" + repair,
                system=(
                    "Return ONLY JSON plan with proposed_calls array using allowed exports only. "
                    + asset_hub.catalog_for_prompt(root)
                ),
                max_tokens=800,
                temperature=0.1,
            )
            from .planner_schema import parse_json_object

            revised = parse_json_object(raw) or {}
            ok2, unknown2, report2 = contract_index.gate_plan(root, revised)
            if ok2:
                a_ok2, a_unknown2, a_report2 = asset_hub.gate_assets(root, revised)
                if not a_ok2:
                    print(a_report2.get("message") or f"blocked assets: {a_unknown2}")
                    return {
                        "action": "enqueue_blocked",
                        "unknown": a_unknown2,
                        "gate": report2,
                        "assets": a_report2,
                        "hint": "add models or fix proposed_assets",
                    }
                return {
                    "action": "enqueue",
                    "plan": revised,
                    "gate": report2,
                    "assets": a_report2,
                    "repaired": True,
                }
            print(report2.get("message") or f"blocked again: {unknown2}")
            return {
                "action": "enqueue_blocked",
                "unknown": unknown2,
                "gate": report2,
                "hint": "ask_hitl or fix contracts",
            }
        except Exception as e:
            return {"action": "enqueue_blocked", "unknown": unknown, "error": str(e), "gate": report}
    return {"action": "enqueue_blocked", "unknown": unknown, "gate": report}


def format_hitl_pack_cli(pack: Dict[str, Any]) -> str:
    lines = [f"HITL pack (cycle {pack.get('cycle')})", "-" * 40]
    for q in pack.get("questions") or []:
        if not isinstance(q, dict):
            continue
        lines.append(f"{q.get('id')}: {q.get('ask')}")
        for opt in q.get("options") or []:
            lines.append(f"  [{opt.get('key')}] {opt.get('label')}")
        other = q.get("other") or {}
        lines.append(f"  [Другое] {other.get('label') or 'Другое'}  (default={q.get('default_if_timeout')})")
        lines.append("")
    lines.append('Answer: python run.py --answer Q1=B')
    lines.append('Other:  python run.py --answer Q1=other --note "ваш текст"')
    return "\n".join(lines)
