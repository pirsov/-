"""Build repair TZ tasks from smoke questionnaire (N / Другое)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import deepseek


def latest_smoke(root: Path, project_id: str = "game1") -> Optional[Dict[str, Any]]:
    p = root / "projects" / project_id / "smoke" / "latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def extract_issues(smoke: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return list of failed/partial smoke items (answer n or other)."""
    if not smoke:
        return []
    answers = smoke.get("answers") or {}
    out: List[Dict[str, Any]] = []
    for qid, val in answers.items():
        if not isinstance(val, dict):
            continue
        ans = str(val.get("answer") or "").lower()
        if ans not in {"n", "other", "нет"}:
            continue
        out.append(
            {
                "id": str(qid),
                "answer": "other" if ans in {"other", "другое"} else "n",
                "prompt": str(val.get("prompt") or ""),
                "detail": str(val.get("detail") or "").strip(),
            }
        )
    return out


def _tasks_for_issue(issue: Dict[str, Any], start_id: int) -> List[str]:
    """Map a smoke issue to one or more compact TZ task lines. Returns (lines, next_id)."""
    prompt = (issue.get("prompt") or "").lower()
    detail = (issue.get("detail") or "").lower()
    blob = f"{prompt} {detail}"
    n = start_id
    lines: List[str] = []

    def add(desc: str, role: str, path: str) -> None:
        nonlocal n
        lines.append(
            f"- [ ] F{n} | REWRITE {desc} | @{role} | -> {path}"
        )
        n += 1

    if "best" in blob:
        add(
            "PlayerData BestTime=0 init; on leave/finish set BestTime from RunStartedAt if better; Studio only no DataStore",
            "gameplay_programmer",
            "src/server/Data/PlayerData.server.luau",
        )
        add(
            "Checkpoints set RunStartedAt if nil; update BestTime on last CP; attrs only on Player; NEVER Remotes.CoinsCollected",
            "gameplay_programmer",
            "src/server/Gameplay/Checkpoints.server.luau",
        )
        add(
            "HUD Best via player:GetAttribute BestTime; show -- only if nil/0; NEVER character:GetAttribute",
            "client_programmer",
            "src/client/HUD.client.luau",
        )
    elif "спавн" in blob or "spawn" in blob or "загруз" in blob or "минут" in blob:
        add(
            "Generator lighter map; Instance.new(\"SpawnLocation\") real class; Path+CP+Coins; no Baseplate; join under ~10s",
            "gameplay_programmer",
            "src/server/Level/Generator.server.luau",
        )
        add(
            "PlayerData init attrs immediately on join; no blocking DataStore in Studio",
            "gameplay_programmer",
            "src/server/Data/PlayerData.server.luau",
        )
        add(
            "InitRemotes getOrCreate remotes fast; no long WaitForChild loops",
            "gameplay_programmer",
            "src/server/InitRemotes.server.luau",
        )
    elif "void" in blob or "паден" in blob:
        add(
            "Void Y<-20 LoadCharacter debounce; keep Player attrs",
            "gameplay_programmer",
            "src/server/Gameplay/Void.server.luau",
        )
    elif "монет" in blob or "coin" in blob:
        add(
            "Coins CanTouch Destroy SetAttribute Coins FireClient CoinCollected FireAllClients UpdateLeaderboard",
            "gameplay_programmer",
            "src/server/Gameplay/Coins.server.luau",
        )
    elif "checkpoint" in blob or "чек" in blob or "cp" in blob:
        add(
            "Checkpoints Touched SetAttribute Checkpoint on Player FireClient CheckpointReached; NEVER CoinsCollected",
            "gameplay_programmer",
            "src/server/Gameplay/Checkpoints.server.luau",
        )
    elif "плит" in blob or "gate" in blob or "plate" in blob:
        add(
            "Puzzles blue plate opens red gate CanTouch; no invented remotes",
            "gameplay_programmer",
            "src/server/Gameplay/Puzzles.server.luau",
        )
    elif "hud" in blob or "худ" in blob:
        add(
            "HUD left labels via player:GetAttribute only never character",
            "client_programmer",
            "src/client/HUD.client.luau",
        )
    else:
        note = issue.get("detail") or issue.get("prompt") or "smoke fail"
        note = str(note).replace("|", "/").replace("\n", " ")[:100]
        add(
            f"fix smoke issue: {note}",
            "gameplay_programmer",
            "src/server/Level/Generator.server.luau",
        )
    return lines, n


def build_fix_tz(
    root: Path,
    *,
    project_id: str = "game1",
    issues: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    smoke = latest_smoke(root, project_id)
    issues = issues if issues is not None else extract_issues(smoke)
    if not issues:
        return {
            "ok": True,
            "issues": [],
            "task_lines": 0,
            "tz": "",
            "message": "Нет ошибок smoke (всё Y) — блок фиксов не нужен",
        }

    blocks: List[str] = []
    next_id = 1
    for issue in issues:
        lines, next_id = _tasks_for_issue(issue, next_id)
        blocks.extend(lines)

    issue_lines = []
    for issue in issues:
        d = issue.get("detail") or ""
        issue_lines.append(
            f"- {issue['id']}: [{issue['answer']}] {issue.get('prompt','')}{(' — ' + d) if d else ''}".rstrip()
        )

    tz = (
        f"# LAST_UPDATE: FIX from smoke — {project_id}\n"
        f"# Auto from smoke N/Другое. Keep src. Activate project first if src empty.\n"
        f"#   python -u run.py --week --sleep 0\n\n"
        f"## SMOKE ISSUES\n"
        + "\n".join(issue_lines)
        + "\n\n## LEGEND\n- [ ] pending | [x] done | @human = Studio y/n\n\n"
        f"## DONE (keep)\n- [x] prior weeks / smoke captured | @integrator\n\n"
        f"## AGENT F — fixes from smoke\n"
        + "\n".join(blocks)
        + "\n\n## HUMAN GATES\n"
        f"- [ ] H11 | Studio: re-check failed smoke items (Best + spawn load) | @human\n"
        f"- [ ] H12 | Final: python -u run.py --eval | @human\n"
    )

    if deepseek.available():
        try:
            polished = deepseek.chat(
                f"Rewrite ONLY as PROJECT_TZ markdown with - [ ] F# task lines "
                f"(F1 F2 F3 ids, NO F1a). Keep all issues. Compact for 4k ctx.\n{tz[:3500]}",
                system=(
                    "Return ONLY PROJECT_TZ markdown with checkbox tasks "
                    "`- [ ] F1 | REWRITE ... | @role | -> path`. "
                    "Use F1 F2 F3 (digits only, optional single letter ok). No prose."
                ),
                max_tokens=1800,
                temperature=0.1,
                timeout=30,
            )
            if deepseek.count_tz_tasks(polished) >= 1:
                tz = polished.strip()
        except Exception:
            pass

    out_proj = root / "projects" / project_id / "PROJECT_TZ.md"
    out_live = root / "PROJECT_TZ.md"
    out_gen = root / "projects" / project_id / "PROJECT_TZ.fix.md"
    for p in (out_proj, out_live, out_gen):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tz, encoding="utf-8")

    return {
        "ok": True,
        "issues": issues,
        "task_lines": deepseek.count_tz_tasks(tz),
        "tz": tz,
        "preview": tz[:2000],
        "paths": {
            "live": "PROJECT_TZ.md",
            "project": str(out_proj),
            "generated": str(out_gen),
        },
    }
