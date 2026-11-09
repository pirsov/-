"""Progressive UI stages 1..5 with focus, skip, and next_action."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from . import deepseek, run_hub, skills_hub

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
            data = json.loads(p.read_text(encoding="utf-8"))
            if "skipped" not in data or not isinstance(data.get("skipped"), list):
                data["skipped"] = []
            return data
        except json.JSONDecodeError:
            pass
    return {
        "activated": False,
        "skills_done": False,
        "tz_done": False,
        "run_done": False,
        "smoke_done": False,
        "skipped": [],
    }


def save(root: Path, data: Dict[str, Any]) -> None:
    if "skipped" not in data:
        data["skipped"] = []
    _progress_path(root).write_text(json.dumps(data, indent=2), encoding="utf-8")


def mark(root: Path, **flags: bool) -> Dict[str, Any]:
    data = load(root)
    data.update({k: bool(v) for k, v in flags.items() if k != "skipped"})
    # Drop skipped flags for stages that became done
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
    """Mark stage (or range stage..through) as skipped, or undo skip."""
    data = load(root)
    skipped: Set[int] = {int(x) for x in data.get("skipped") or []}
    start = max(1, min(5, int(stage)))
    end = start if through is None else max(start, min(5, int(through)))
    for n in range(start, end + 1):
        if n == 5:
            continue  # never skip smoke itself via bulk
        if undo:
            skipped.discard(n)
        else:
            skipped.add(n)
    data["skipped"] = sorted(skipped)
    save(root, data)
    return snapshot(root)


def _derive_flags(root: Path, data: Dict[str, Any]) -> Any:
    flags = {k: data.get(k, False) for k in (
        "activated", "skills_done", "tz_done", "run_done", "smoke_done"
    )}
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
    snap = list((root / "projects" / "game1" / "src").rglob("*.luau"))
    luau_n = max(len(luau), len(snap))
    report = root / "docs" / "AGENT_RUN_REPORT.md"
    if luau_n >= 8 and (report.exists() or flags.get("tz_done")):
        flags["run_done"] = True
    smoke = root / "projects" / "game1" / "smoke" / "latest.json"
    if smoke.exists():
        flags["smoke_done"] = True

    if flags.get("smoke_done"):
        flags["run_done"] = True
    if flags.get("run_done"):
        flags["tz_done"] = True
    if flags.get("tz_done"):
        flags["skills_done"] = True
    if flags.get("skills_done"):
        flags["activated"] = True
    return flags, tz_tasks, compact, luau_n, st


def _effective_done(flags: Dict[str, Any], skipped: Set[int], stage_id: int, key: str) -> bool:
    return bool(flags.get(key)) or stage_id in skipped


def snapshot(root: Path, *, smoke_loaded: bool = False, focus: Optional[int] = None) -> Dict[str, Any]:
    data = load(root)
    flags, tz_tasks, compact, luau_n, st = _derive_flags(root, data)
    skipped: Set[int] = {int(x) for x in data.get("skipped") or []}
    # Auto-drop skipped once truly done
    cleaned = {n for n in skipped if not flags.get(STAGE_META[n - 1]["key"])}
    if cleaned != skipped:
        data["skipped"] = sorted(cleaned)
        save(root, data)
        skipped = cleaned

    # First incomplete (not done and not skipped)
    current = 5
    for meta in STAGE_META:
        if not _effective_done(flags, skipped, meta["id"], meta["key"]):
            current = meta["id"]
            break

    focus_stage = int(focus) if focus else current
    focus_stage = max(1, min(5, focus_stage))

    stages: List[Dict[str, Any]] = []
    unlocked: Dict[str, bool] = {}
    labels: Dict[str, str] = {}
    for meta in STAGE_META:
        n = meta["id"]
        done = bool(flags.get(meta["key"]))
        is_skipped = n in skipped and not done
        if done:
            state = "done"
        elif is_skipped:
            state = "skipped"
        elif n == current:
            state = "current"
        else:
            state = "locked"

        unlocked[str(n)] = True  # focus switch allowed; UI dims non-focus
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
                "can_skip": n < 5 and not done,
            }
        )

    if flags.get("smoke_done"):
        next_action = NEXT_ACTIONS["done"]
    elif current == 5 and smoke_loaded:
        next_action = NEXT_ACTIONS["smoke_submit"]
    else:
        next_action = NEXT_ACTIONS[current]

    return {
        "flags": flags,
        "stage": current,
        "focus_stage": focus_stage,
        "unlocked": unlocked,
        "labels": labels,
        "stages": stages,
        "next_action": next_action,
        "can_skip": current < 5 and not flags.get(STAGE_META[current - 1]["key"]),
        "skipped": sorted(skipped),
        "lock_hints": {str(m["id"]): m["hint"] for m in STAGE_META if m["id"] > 1},
        "counts": {
            "tz_tasks": tz_tasks,
            "luau_files": luau_n,
            "compact_skills": len(compact),
            "raw_skills": len(skills_hub.list_raw(root)),
        },
        "run_status": st.get("status") or "idle",
    }
