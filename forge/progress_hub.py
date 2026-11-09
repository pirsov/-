"""Progressive UI stages 1..5 for Quality Forge control panel.

Returns done/current/locked stages, one next_action, lock hints, and counters.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import deepseek, run_hub, skills_hub

STAGE_META = [
    {"id": 1, "key": "activated", "label": "Проект", "hint": "Активируй game1"},
    {"id": 2, "key": "skills_done", "label": "Цель + skills", "hint": "Сначала активируй проект (окно 1)"},
    {"id": 3, "key": "tz_done", "label": "TZ", "hint": "Сначала выбери/сожми skills (окно 2)"},
    {"id": 4, "key": "run_done", "label": "Генерация", "hint": "Сначала сгенерируй TZ (окно 3)"},
    {"id": 5, "key": "smoke_done", "label": "Smoke", "hint": "Сначала дождись генерации (окно 4)"},
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
    "done": {"id": "done", "label": "Готово — smoke сохранён", "button": None, "stage": 5},
}


def _progress_path(root: Path) -> Path:
    d = root / ".forge"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ui_progress.json"


def load(root: Path) -> Dict[str, Any]:
    p = _progress_path(root)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "activated": False,
        "skills_done": False,
        "tz_done": False,
        "run_done": False,
        "smoke_done": False,
    }


def save(root: Path, data: Dict[str, Any]) -> None:
    _progress_path(root).write_text(json.dumps(data, indent=2), encoding="utf-8")


def mark(root: Path, **flags: bool) -> Dict[str, Any]:
    data = load(root)
    data.update({k: bool(v) for k, v in flags.items()})
    save(root, data)
    return snapshot(root)


def _derive_flags(root: Path, data: Dict[str, Any]) -> Dict[str, Any]:
    flags = dict(data)
    active = root / ".forge" / "active_project.json"
    if active.exists():
        flags["activated"] = True
    compact = skills_hub.list_compact(root)
    if len(compact) >= 2:
        flags["skills_done"] = True
    tz = root / "PROJECT_TZ.md"
    tz_tasks = 0
    if tz.exists():
        tz_tasks = deepseek.count_tz_tasks(tz.read_text(encoding="utf-8", errors="replace"))
        if tz_tasks >= 5:
            flags["tz_done"] = True
    st = run_hub.status()
    if st.get("status") == "done" and (
        st.get("exit_code") == 0 or (st.get("report") or {}).get("quality")
    ):
        flags["run_done"] = True
    luau = list((root / "src").rglob("*.luau")) if (root / "src").exists() else []
    # Snapshot under projects/game1 also counts (Desktop may not have activated live src/).
    snap = list((root / "projects" / "game1" / "src").rglob("*.luau"))
    luau_n = max(len(luau), len(snap))
    report = root / "docs" / "AGENT_RUN_REPORT.md"
    if luau_n >= 8 and (report.exists() or flags.get("tz_done")):
        # Resume after completed week even if ui_run state is idle.
        flags["run_done"] = True
    smoke = root / "projects" / "game1" / "smoke" / "latest.json"
    if smoke.exists():
        flags["smoke_done"] = True

    # Cascade: later progress implies earlier steps were completed.
    if flags.get("smoke_done"):
        flags["run_done"] = True
    if flags.get("run_done"):
        flags["tz_done"] = True
    if flags.get("tz_done"):
        flags["skills_done"] = True
    if flags.get("skills_done"):
        flags["activated"] = True
    return flags, tz_tasks, compact, luau_n, st


def snapshot(root: Path, *, smoke_loaded: bool = False) -> Dict[str, Any]:
    data = load(root)
    flags, tz_tasks, compact, luau_n, st = _derive_flags(root, data)

    # Current stage = first incomplete; if all done, stay on 5.
    current = 5
    for meta in STAGE_META:
        if not flags.get(meta["key"]):
            current = meta["id"]
            break

    stages: List[Dict[str, Any]] = []
    unlocked: Dict[str, bool] = {}
    labels: Dict[str, str] = {}
    for meta in STAGE_META:
        n = meta["id"]
        done = bool(flags.get(meta["key"]))
        if done:
            state = "done"
        elif n == current:
            state = "current"
        else:
            state = "locked"
        # Unlock panels up to current (and done ones)
        is_unlocked = done or n <= current
        unlocked[str(n)] = is_unlocked
        labels[str(n)] = meta["label"]
        stages.append(
            {
                "id": n,
                "label": meta["label"],
                "state": state,
                "hint": meta["hint"] if state == "locked" else "",
                "done": done,
            }
        )

    if flags.get("smoke_done"):
        next_action = NEXT_ACTIONS["done"]
    elif current == 5 and smoke_loaded:
        next_action = NEXT_ACTIONS["smoke_submit"]
    else:
        next_action = NEXT_ACTIONS[current]

    # Lock hints for locked panels (what to do earlier)
    lock_hints = {str(m["id"]): m["hint"] for m in STAGE_META if m["id"] > 1}

    return {
        "flags": flags,
        "stage": current,
        "unlocked": unlocked,
        "labels": labels,
        "stages": stages,
        "next_action": next_action,
        "lock_hints": lock_hints,
        "counts": {
            "tz_tasks": tz_tasks,
            "luau_files": luau_n,
            "compact_skills": len(compact),
            "raw_skills": len(skills_hub.list_raw(root)),
        },
        "run_status": st.get("status") or "idle",
    }
