"""Multi-project registry (game1, game2, ...)."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def projects_root(root: Path) -> Path:
    return root / "projects"


def list_projects(root: Path) -> List[Dict[str, Any]]:
    base = projects_root(root)
    if not base.exists():
        return []
    out = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        meta_p = d / "meta.json"
        meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {"id": d.name}
        meta["path"] = str(d)
        luau = list(d.rglob("*.luau"))
        meta["luau_files"] = len(luau)
        out.append(meta)
    return out


def get_project(root: Path, project_id: str) -> Path:
    p = projects_root(root) / project_id
    if not p.exists():
        raise FileNotFoundError(project_id)
    return p


def activate_project(root: Path, project_id: str) -> Path:
    """Copy project src + TZ into workspace live tree for --week."""
    proj = get_project(root, project_id)
    src = proj / "src"
    if src.exists():
        live = root / "src"
        # clear luau only
        for f in live.rglob("*.luau"):
            f.unlink()
        for f in src.rglob("*.luau"):
            rel = f.relative_to(src)
            dest = live / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
    tz = proj / "PROJECT_TZ.md"
    if tz.exists():
        shutil.copy2(tz, root / "PROJECT_TZ.md")
    meta_p = proj / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    meta["activated_at"] = datetime.now(timezone.utc).isoformat()
    meta_p.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (root / ".forge").mkdir(exist_ok=True)
    (root / ".forge" / "active_project.json").write_text(
        json.dumps({"id": project_id}, indent=2), encoding="utf-8"
    )
    return proj


def save_smoke(root: Path, project_id: str, body: Dict[str, Any]) -> Path:
    """Persist smoke questionnaire. Accepts full UI body or bare answers map."""
    proj = get_project(root, project_id)
    smoke_dir = proj / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = smoke_dir / f"{stamp}.json"

    # UI sends { project, answers: {q1: {answer, prompt, detail}}, notes, overall_ok, ... }
    raw_answers = body.get("answers") if isinstance(body.get("answers"), dict) else body
    if not isinstance(raw_answers, dict):
        raw_answers = {}
    # Normalize each answer so "other" detail is never dropped
    answers: Dict[str, Any] = {}
    others: List[str] = []
    for qid, val in raw_answers.items():
        if not isinstance(val, dict):
            answers[str(qid)] = {"answer": str(val), "prompt": "", "detail": ""}
            continue
        ans = str(val.get("answer") or "").strip().lower()
        detail = str(val.get("detail") or "").strip()
        if ans in {"другое", "other", "o"}:
            ans = "other"
        entry = {
            "answer": ans,
            "prompt": str(val.get("prompt") or ""),
            "detail": detail if ans == "other" else "",
        }
        answers[str(qid)] = entry
        if ans == "other" and detail:
            others.append(f"{qid}: {detail}")

    notes = str(body.get("notes") or "").strip()
    if others:
        joined = " | ".join(others)
        notes = f"{notes} | {joined}".strip(" |") if notes else joined

    payload = {
        "when": datetime.now(timezone.utc).isoformat(),
        "project": project_id,
        "overall_ok": bool(body.get("overall_ok")),
        "notes": notes,
        "answers": answers,
        "others": others,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (smoke_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    meta_p = proj / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {"id": project_id}
    meta["smoke"] = {"pending": False, "latest": str(path), "others": others}
    promoted: List[str] = []
    skipped_missing: List[str] = []
    want = list(body.get("promote_skills") or [])
    if want:
        from . import skills_hub

        for sid in want:
            try:
                got = skills_hub.promote_compact(
                    sid,
                    root,
                    smoke_ok=True,
                    notes=f"promoted from {project_id} smoke {stamp}",
                    missing_ok=True,
                )
                if got is None:
                    skipped_missing.append(str(sid))
                else:
                    promoted.append(str(sid))
            except FileNotFoundError:
                skipped_missing.append(str(sid))
    meta["smoke"]["promoted"] = promoted
    meta["smoke"]["skipped_missing"] = skipped_missing
    # Keep on payload for API response consumers
    payload["promoted"] = promoted
    payload["skipped_missing"] = skipped_missing
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (smoke_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def snapshot_live_to_project(root: Path, project_id: str, *, title: str = "") -> Path:
    """Save current workspace src into projects/<id>."""
    proj = projects_root(root) / project_id
    proj.mkdir(parents=True, exist_ok=True)
    live_src = root / "src"
    dest_src = proj / "src"
    if dest_src.exists():
        shutil.rmtree(dest_src)
    if live_src.exists():
        shutil.copytree(live_src, dest_src)
    tz = root / "PROJECT_TZ.md"
    if tz.exists():
        shutil.copy2(tz, proj / "PROJECT_TZ.md")
    meta = {
        "id": project_id,
        "name": project_id,
        "title": title or project_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "backend_code": "ollama",
        "backend_prompt": "deepseek",
        "status": "snapshot",
        "skills_compact": [c["id"] for c in __import__("forge.skills_hub", fromlist=["list_compact"]).list_compact(root) if c.get("promoted") == "true"]
        or ["forge-player-attrs", "forge-luau-touch"],
        "smoke": {"pending": True},
    }
    (proj / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (proj / "smoke").mkdir(exist_ok=True)
    return proj
