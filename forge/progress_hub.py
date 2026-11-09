"""Progressive UI stages 1..5 for Quality Forge control panel."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from . import deepseek, run_hub, skills_hub


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


def snapshot(root: Path) -> Dict[str, Any]:
    data = load(root)
    # derive from disk too (resilient if flags missing)
    active = root / ".forge" / "active_project.json"
    if active.exists():
        data["activated"] = True
    compact = skills_hub.list_compact(root)
    if len(compact) >= 2:
        data["skills_done"] = True
    tz = root / "PROJECT_TZ.md"
    if tz.exists() and deepseek.count_tz_tasks(tz.read_text(encoding="utf-8", errors="replace")) >= 5:
        data["tz_done"] = True
    st = run_hub.status()
    if st.get("status") == "done" and (st.get("exit_code") == 0 or (st.get("report") or {}).get("quality")):
        data["run_done"] = True
    smoke = root / "projects" / "game1" / "smoke" / "latest.json"
    if smoke.exists():
        data["smoke_done"] = True

    # stage = highest unlocked (1..5)
    stage = 1
    if data.get("activated"):
        stage = 2
    if data.get("skills_done"):
        stage = 3
    if data.get("tz_done"):
        stage = 4
    if data.get("run_done"):
        stage = 5
    unlocked = {
        "1": True,
        "2": stage >= 2,
        "3": stage >= 3,
        "4": stage >= 4,
        "5": stage >= 5,
    }
    return {
        "flags": data,
        "stage": stage,
        "unlocked": unlocked,
        "labels": {
            "1": "Проект",
            "2": "Цель + skills",
            "3": "TZ",
            "4": "Генерация",
            "5": "Smoke",
        },
    }
