"""Progressive UI stages 1..6 with focus, skip, smoke-fix next_action."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from . import deepseek, fix_hub, run_hub, skills_hub

STAGE_META = [
    {
        "id": 1,
        "key": "activated",
        "label": "Проект",
        "hint": "Активируй game1",
        "why": "Выбери снимок проекта и сделай его живым деревом src/.",
        "skip_hint": "Можно пропустить, если game1 уже активирован.",
    },
    {
        "id": 2,
        "key": "skills_done",
        "label": "Цель + skills",
        "hint": "Сначала активируй проект (окно 1)",
        "why": "Сформулируй цель и сжатые skills для Ollama.",
        "skip_hint": "Можно пропустить, если skills уже выбраны / проект готов.",
    },
    {
        "id": 3,
        "key": "tz_done",
        "label": "TZ",
        "hint": "Сначала выбери/сожми skills (окно 2)",
        "why": "Сгенерируй checkbox-задачи PROJECT_TZ под 4k контекст.",
        "skip_hint": "Можно пропустить, если TZ уже есть и код готов.",
    },
    {
        "id": 4,
        "key": "run_done",
        "label": "Генерация",
        "hint": "Сначала сгенерируй TZ (окно 3)",
        "why": "Ollama --week пишет Luau по задачам TZ.",
        "skip_hint": "Можно пропустить, если доработка не нужна — сразу Smoke.",
    },
    {
        "id": 5,
        "key": "smoke_done",
        "label": "Smoke",
        "hint": "Сначала дождись генерации (окно 4)",
        "why": "Studio playtest → y/n → promote skills.",
        "skip_hint": "",
    },
    {
        "id": 6,
        "key": "fix_done",
        "label": "Исправить ошибки",
        "hint": "Сначала сохрани smoke (окно 5)",
        "why": "По N/Другое из smoke собери TZ фиксов и запусти --week.",
        "skip_hint": "Можно пропустить, если ошибок нет или фиксы не нужны.",
    },
]

NEXT_ACTIONS = {
    1: {"id": "activate", "label": "Активировать game1", "button": "btn-activate", "stage": 1},
    2: {"id": "skills", "label": "DeepSeek: сам выбери skills", "button": "btn-auto", "stage": 2},
    3: {"id": "tz", "label": "DeepSeek: сгенерировать PROJECT_TZ", "button": "btn-tz", "stage": 3},
    4: {"id": "run", "label": "Старт генерации --week", "button": "btn-run", "stage": 4},
    5: {"id": "smoke_load", "label": "Загрузить вопросы", "button": "btn-smoke-load", "stage": 5},
    "smoke_submit": {
        "id": "smoke_submit",
        "label": "Сохранить ответы + promote",
        "button": "btn-smoke-submit",
        "stage": 5,
    },
    6: {
        "id": "fix_tz",
        "label": "Составить TZ на фиксы",
        "button": "btn-fix-tz",
        "stage": 6,
    },
    "fix_run": {
        "id": "fix_run",
        "label": "Старт фиксов --week",
        "button": "btn-fix-run",
        "stage": 6,
    },
    "done": {"id": "done", "label": "Готово", "button": None, "stage": 6},
}


def _progress_path(root: Path) -> Path:
    d = root / ".forge"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ui_progress.json"


def load(root: Path) -> Dict[str, Any]:
    p = _progress_path(root)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "skipped" not in data or not isinstance(data.get("skipped"), list):
                data["skipped"] = []
            data.setdefault("fix_tz_done", False)
            data.setdefault("fix_done", False)
            return data
        except json.JSONDecodeError:
            pass
    return {
        "activated": False,
        "skills_done": False,
        "tz_done": False,
        "run_done": False,
        "smoke_done": False,
        "fix_tz_done": False,
        "fix_done": False,
        "skipped": [],
    }


def save(root: Path, data: Dict[str, Any]) -> None:
    if "skipped" not in data:
        data["skipped"] = []
    _progress_path(root).write_text(json.dumps(data, indent=2), encoding="utf-8")


def mark(root: Path, **flags: bool) -> Dict[str, Any]:
    data = load(root)
    data.update({k: bool(v) for k, v in flags.items() if k != "skipped"})
    skipped = {int(x) for x in data.get("skipped") or []}
    for meta in STAGE_META:
        if data.get(meta["key"]) and meta["id"] in skipped:
            skipped.discard(meta["id"])
    data["skipped"] = sorted(skipped)
    save(root, data)
    return snapshot(root)


def skip(
    root: Path,
    stage: int,
    *,
    through: Optional[int] = None,
    undo: bool = False,
) -> Dict[str, Any]:
    data = load(root)
    skipped: Set[int] = {int(x) for x in data.get("skipped") or []}
    start = max(1, min(6, int(stage)))
    end = start if through is None else max(start, min(6, int(through)))
    for n in range(start, end + 1):
        if n == 5:
            continue
        if undo:
            skipped.discard(n)
        else:
            skipped.add(n)
    data["skipped"] = sorted(skipped)
    save(root, data)
    return snapshot(root)


def _active_project_id(root: Path) -> str:
    active = root / ".forge" / "active_project.json"
    if active.exists():
        try:
            data = json.loads(active.read_text(encoding="utf-8"))
            pid = str(data.get("id") or "").strip()
            if pid:
                return pid
        except (json.JSONDecodeError, OSError):
            pass
    return "game1"


def _derive_flags(root: Path, data: Dict[str, Any]) -> Any:
    flags = {
        k: bool(data.get(k, False))
        for k in (
            "activated",
            "skills_done",
            "tz_done",
            "run_done",
            "smoke_done",
            "fix_tz_done",
            "fix_done",
        )
    }
    project_id = _active_project_id(root)
    active = root / ".forge" / "active_project.json"
    if active.exists():
        flags["activated"] = True
    compact = skills_hub.list_compact(root)
    if len(compact) >= 2:
        flags["skills_done"] = True
    tz = root / "PROJECT_TZ.md"
    tz_tasks = 0
    if tz.exists():
        tz_text = tz.read_text(encoding="utf-8", errors="replace")
        tz_tasks = deepseek.count_tz_tasks(tz_text)
        if tz_tasks >= 5:
            flags["tz_done"] = True
        # Fix TZ from smoke uses F* tasks
        if "AGENT F" in tz_text or "FIX from smoke" in tz_text:
            flags["fix_tz_done"] = True
    st = run_hub.status()
    if st.get("status") == "done" and (
        st.get("exit_code") == 0 or (st.get("report") or {}).get("quality")
    ):
        flags["run_done"] = True
    luau = list((root / "src").rglob("*.luau")) if (root / "src").exists() else []
    snap = list((root / "projects" / project_id / "src").rglob("*.luau"))
    luau_n = max(len(luau), len(snap))
    report = root / "docs" / "AGENT_RUN_REPORT.md"
    # Fresh empty TZ after --reset-state must not inherit run_done from leftover Luau
    if luau_n >= 8 and flags.get("tz_done") and (report.exists() or tz_tasks >= 5):
        flags["run_done"] = True
    smoke = root / "projects" / project_id / "smoke" / "latest.json"
    if smoke.exists():
        flags["smoke_done"] = True

    issues = fix_hub.extract_issues(fix_hub.latest_smoke(root, project_id=project_id))
    # No issues → fix stage auto-done
    if flags.get("smoke_done") and not issues:
        flags["fix_tz_done"] = True
        flags["fix_done"] = True

    if flags.get("fix_done"):
        flags["fix_tz_done"] = True
    if flags.get("smoke_done"):
        flags["run_done"] = True
    if flags.get("run_done"):
        flags["tz_done"] = True
    if flags.get("tz_done"):
        flags["skills_done"] = True
    if flags.get("skills_done"):
        flags["activated"] = True

    # For stage-6 "done" key mapping
    flags_for_stage = dict(flags)
    flags_for_stage["fix_done"] = bool(flags.get("fix_done"))
    return flags_for_stage, tz_tasks, compact, luau_n, st, issues


def _effective_done(flags: Dict[str, Any], skipped: Set[int], stage_id: int, key: str) -> bool:
    return bool(flags.get(key)) or stage_id in skipped


def snapshot(
    root: Path,
    *,
    smoke_loaded: bool = False,
    focus: Optional[int] = None,
    fix_tz_ready: bool = False,
) -> Dict[str, Any]:
    data = load(root)
    flags, tz_tasks, compact, luau_n, st, issues = _derive_flags(root, data)
    if data.get("fix_tz_done"):
        flags["fix_tz_done"] = True
    skipped: Set[int] = {int(x) for x in data.get("skipped") or []}
    cleaned = set()
    for n in skipped:
        if n < 1 or n > len(STAGE_META):
            continue
        key = STAGE_META[n - 1]["key"]
        if not flags.get(key):
            cleaned.add(n)
    if cleaned != skipped:
        data["skipped"] = sorted(cleaned)
        save(root, data)
        skipped = cleaned

    # First incomplete stage among 1..6
    current = 6
    for meta in STAGE_META:
        key = meta["key"]
        done_flag = flags.get("fix_done") if meta["id"] == 6 else flags.get(key)
        if done_flag or meta["id"] in skipped:
            continue
        current = meta["id"]
        break

    focus_stage = int(focus) if focus else current
    focus_stage = max(1, min(6, focus_stage))

    stages: List[Dict[str, Any]] = []
    unlocked: Dict[str, bool] = {}
    labels: Dict[str, str] = {}
    for meta in STAGE_META:
        n = meta["id"]
        done = bool(flags.get("fix_done") if n == 6 else flags.get(meta["key"]))
        is_skipped = n in skipped and not done
        if done:
            state = "done"
        elif is_skipped:
            state = "skipped"
        elif n == current:
            state = "current"
        else:
            state = "locked"

        unlocked[str(n)] = True
        labels[str(n)] = meta["label"]
        stages.append(
            {
                "id": n,
                "label": meta["label"],
                "state": state,
                "hint": meta["hint"] if state == "locked" else "",
                "why": meta["why"],
                "skip_hint": meta["skip_hint"],
                "done": done,
                "skipped": is_skipped,
                "can_skip": n != 5 and not done,
            }
        )

    fix_ready = bool(flags.get("fix_tz_done") or fix_tz_ready or data.get("fix_tz_done"))
    if flags.get("fix_done") or (flags.get("smoke_done") and not issues):
        next_action = NEXT_ACTIONS["done"]
    elif current == 6 and fix_ready:
        next_action = NEXT_ACTIONS["fix_run"]
    elif current == 6:
        next_action = NEXT_ACTIONS[6]
    elif current == 5 and smoke_loaded:
        next_action = NEXT_ACTIONS["smoke_submit"]
    else:
        next_action = NEXT_ACTIONS.get(current, NEXT_ACTIONS["done"])

    return {
        "flags": flags,
        "stage": current,
        "focus_stage": focus_stage,
        "unlocked": unlocked,
        "labels": labels,
        "stages": stages,
        "next_action": next_action,
        "can_skip": current not in (5,) and not flags.get(STAGE_META[current - 1]["key"]),
        "skipped": sorted(skipped),
        "lock_hints": {str(m["id"]): m["hint"] for m in STAGE_META if m["id"] > 1},
        "issues": issues,
        "issue_count": len(issues),
        "counts": {
            "tz_tasks": tz_tasks,
            "luau_files": luau_n,
            "compact_skills": len(compact),
            "raw_skills": len(skills_hub.list_raw(root)),
            "issues": len(issues),
        },
        "run_status": st.get("status") or "idle",
    }
