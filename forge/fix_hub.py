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


def _task_for_issue(issue: Dict[str, Any], idx: int) -> str:
    """Map a smoke issue to one compact TZ task line."""
    prompt = (issue.get("prompt") or "").lower()
    detail = (issue.get("detail") or "").lower()
    blob = f"{prompt} {detail}"
    n = idx

    if "best" in blob:
        return (
            f"- [ ] F{n}a | REWRITE PlayerData BestTime=0 init; on leave/finish set BestTime from RunStartedAt if better; Studio only | "
            f"@gameplay_programmer | -> src/server/Data/PlayerData.server.luau\n"
            f"- [ ] F{n}b | REWRITE Checkpoints set RunStartedAt; update BestTime on last CP; attrs on Player | "
            f"@gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau\n"
            f"- [ ] F{n}c | REWRITE HUD Best from player:GetAttribute BestTime; -- only if nil/0 | "
            f"@client_programmer | -> src/client/HUD.client.luau"
        )
    if "спавн" in blob or "spawn" in blob or "загруз" in blob or "минут" in blob:
        return (
            f"- [ ] F{n}a | REWRITE Generator: lighter map build; fewer Parts; defer non-critical Instance.new; Path+SpawnLocation+CP+Coins only; no Baseplate | "
            f"@gameplay_programmer | -> src/server/Level/Generator.server.luau\n"
            f"- [ ] F{n}b | REWRITE PlayerData/InitRemotes: no blocking waits on join; SetAttribute defaults immediately | "
            f"@gameplay_programmer | -> src/server/Data/PlayerData.server.luau\n"
            f"- [ ] F{n}c | REWRITE InitRemotes getOrCreate remotes fast; no long WaitForChild loops | "
            f"@gameplay_programmer | -> src/server/InitRemotes.server.luau"
        )
    if "void" in blob or "паден" in blob:
        return (
            f"- [ ] F{n} | REWRITE Void: Y<-20 LoadCharacter; debounce; attrs on Player unchanged | "
            f"@gameplay_programmer | -> src/server/Gameplay/Void.server.luau"
        )
    if "монет" in blob or "coin" in blob:
        return (
            f"- [ ] F{n} | REWRITE Coins: CanTouch Destroy SetAttribute Coins FireClient CoinCollected FireAllClients UpdateLeaderboard | "
            f"@gameplay_programmer | -> src/server/Gameplay/Coins.server.luau"
        )
    if "checkpoint" in blob or "чек" in blob or "cp" in blob:
        return (
            f"- [ ] F{n} | REWRITE Checkpoints: Touched SetAttribute Checkpoint on Player FireClient CheckpointReached | "
            f"@gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau"
        )
    if "плит" in blob or "gate" in blob or "plate" in blob:
        return (
            f"- [ ] F{n} | REWRITE Puzzles: blue plate opens red gate; CanTouch; no invented remotes | "
            f"@gameplay_programmer | -> src/server/Gameplay/Puzzles.server.luau"
        )
    if "hud" in blob or "time" in blob or "худ" in blob:
        return (
            f"- [ ] F{n} | REWRITE HUD left labels via player:GetAttribute only never character | "
            f"@client_programmer | -> src/client/HUD.client.luau"
        )
    # generic
    note = issue.get("detail") or issue.get("prompt") or "smoke fail"
    note = str(note).replace("|", "/").replace("\n", " ")[:120]
    return (
        f"- [ ] F{n} | REWRITE fix smoke issue: {note} | "
        f"@gameplay_programmer | -> src/server/Level/Generator.server.luau"
    )


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

    blocks = []
    for i, issue in enumerate(issues, start=1):
        blocks.append(_task_for_issue(issue, i))

    issue_lines = []
    for issue in issues:
        d = issue.get("detail") or ""
        issue_lines.append(
            f"- {issue['id']}: [{issue['answer']}] {issue.get('prompt','')} {('— ' + d) if d else ''}".rstrip()
        )

    tz = (
        f"# LAST_UPDATE: FIX from smoke — {project_id}\n"
        f"# Auto from smoke N/Другое. Keep src. Run: python -u run.py --week --sleep 0\n\n"
        f"## SMOKE ISSUES\n"
        + "\n".join(issue_lines)
        + "\n\n## LEGEND\n- [ ] pending | [x] done | @human = Studio y/n\n\n"
        f"## DONE (keep)\n- [x] prior weeks / smoke captured | @integrator\n\n"
        f"## AGENT F — fixes from smoke\n"
        + "\n".join(blocks)
        + "\n\n## HUMAN GATES\n"
        f"- [ ] HF1 | Studio: re-check failed smoke items | @human\n"
        f"- [ ] HF2 | Final: python -u run.py --eval | @human\n"
    )

    # Prefer DeepSeek polish when available (shorten only; keep task lines)
    if deepseek.available():
        try:
            polished = deepseek.chat(
                f"Rewrite ONLY as PROJECT_TZ markdown with - [ ] F* task lines. "
                f"Keep all issues. Compact for 4k ctx. Input:\n{tz[:3500]}",
                system=(
                    "Return ONLY PROJECT_TZ markdown with checkbox tasks "
                    "`- [ ] F# | REWRITE ... | @role | -> path`. Russian/English OK. No prose."
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
