"""DeepSeek cloud helper: compress skills, draft TZ prompts, smoke questionnaires.

Uses OpenAI-compatible API (api.deepseek.com). Does NOT write game Luau —
Ollama/local models still write src/. DeepSeek only plans / shortens text.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from . import llm


# OpenAI chat path: deepseek-chat (legacy) or deepseek-flash / deepseek-v4-pro.
# Claude Code Anthropic path is separate — see scripts/start-claude-deepseek.*.
DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"


def available() -> bool:
    return bool(llm._clean_key(os.environ.get("DEEPSEEK_API_KEY")))


def chat(
    prompt: str,
    *,
    system: str,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    model: Optional[str] = None,
) -> str:
    key = llm._clean_key(os.environ.get("DEEPSEEK_API_KEY"))
    if not key:
        raise llm.AuthError(
            "DEEPSEEK_API_KEY unset. Get a key at https://platform.deepseek.com/"
        )
    url = BASE_URL.rstrip("/") + "/chat/completions"
    body = {
        "model": model or DEFAULT_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        if e.code in (401, 403):
            raise llm.AuthError(f"DeepSeek auth failed HTTP {e.code}: {detail}") from e
        raise RuntimeError(f"DeepSeek HTTP {e.code}: {detail}") from e
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"DeepSeek empty choices: {payload!r}")
    msg = choices[0].get("message") or {}
    return str(msg.get("content") or "")


def select_skills(
    *,
    goal: str,
    catalog: List[Dict[str, str]],
    max_pick: int = 3,
) -> List[str]:
    """Pick raw skill ids for the goal. Returns ids like ash__roblox-luau-architecture."""
    lines = []
    for c in catalog:
        lines.append(f"- {c['id']} | {c.get('name','')} | src={c.get('source','')}")
    catalog_txt = "\n".join(lines)
    if not available():
        return _heuristic_select(goal, catalog, max_pick=max_pick)
    system = (
        "You pick Roblox agent skills for a local Ollama coder with 4k context. "
        f"Return ONLY JSON: {{\"ids\": [\"...\"]}} with at most {max_pick} ids "
        "copied exactly from the catalog. Prefer code/ui/architecture/debug over marketing."
    )
    prompt = (
        f"Goal:\n{goal}\n\nCatalog:\n{catalog_txt}\n\n"
        "Pick the best skills for this goal."
    )
    raw = chat(prompt, system=system, max_tokens=400, temperature=0.1)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        data = json.loads(raw)
        ids = [str(x) for x in (data.get("ids") or []) if x]
    except json.JSONDecodeError:
        ids = []
    allowed = {c["id"] for c in catalog}
    ids = [i for i in ids if i in allowed][:max_pick]
    if not ids:
        return _heuristic_select(goal, catalog, max_pick=max_pick)
    return ids


def _heuristic_select(goal: str, catalog: List[Dict[str, str]], *, max_pick: int = 3) -> List[str]:
    g = goal.lower()
    prefer = []
    keywords = [
        ("hud", ("ui", "ux", "client")),
        ("ui", ("ui", "ux")),
        ("coin", ("code", "economy", "debug")),
        ("checkpoint", ("code", "architecture")),
        ("spawn", ("map", "architecture", "code")),
        ("map", ("map", "world", "level")),
        ("plugin", ("studio", "ui", "code")),
        ("debug", ("debug", "triage", "bug")),
        ("attr", ("code", "architecture", "datastore")),
    ]
    buckets: List[str] = []
    for key, tags in keywords:
        if key in g:
            buckets.extend(tags)
    if not buckets:
        buckets = ["code", "architecture", "ui", "debug", "map"]
    scored: List[tuple] = []
    for c in catalog:
        name = (c.get("name") or c.get("id") or "").lower()
        score = 0
        for t in buckets:
            if t in name:
                score += 2
        if c.get("source") == "sypho" and any(t in name for t in ("code", "ui", "map")):
            score += 1
        if c.get("source") == "ash" and "architecture" in name:
            score += 1
        if score:
            scored.append((score, c["id"]))
    scored.sort(reverse=True)
    ids = [i for _, i in scored[:max_pick]]
    if ids:
        return ids
    # fallback first useful sypho/ash
    for needle in ("roblox-code", "roblox-luau-architecture", "roblox-ui", "roblox-debugging"):
        for c in catalog:
            if needle in c["id"]:
                ids.append(c["id"])
                if len(ids) >= max_pick:
                    return ids
    return [c["id"] for c in catalog[:max_pick]]


def compress_skill(raw_md: str, *, name: str, max_chars: int = 1200) -> str:
    """Shorten a raw SKILL.md for Ollama 4k ctx injection."""
    system = (
        "You compress Roblox agent skills for a 4096-token local coder model. "
        "Output ONLY markdown. Keep hard rules, forbidden patterns, and copy-paste "
        "Luau snippets. Drop MCP tool lists, marketing, long examples, and fluff. "
        f"Hard limit: {max_chars} characters."
    )
    prompt = (
        f"Skill name: {name}\n"
        f"Max chars: {max_chars}\n\n"
        f"=== RAW SKILL ===\n{raw_md[:24000]}\n=== END ===\n"
        "Return compact SKILL.md starting with YAML frontmatter name/source/max_chars."
    )
    out = chat(prompt, system=system, max_tokens=900, temperature=0.1)
    out = out.strip()
    if out.startswith("```"):
        out = re.sub(r"^```(?:markdown|md)?\n?", "", out)
        out = re.sub(r"\n?```$", "", out)
    if len(out) > max_chars + 200:
        out = out[: max_chars + 200]
    return out


def count_tz_tasks(tz_text: str) -> int:
    return len(re.findall(r"(?m)^\s*- \[ \] [A-Z]?\d+", tz_text))


def generate_project_tz(
    *,
    project_id: str,
    goal: str,
    compact_skills: List[str],
    existing_files: List[str],
) -> str:
    """DeepSeek drafts PROJECT_TZ.md as checkbox tasks only (for --week)."""
    system = (
        "You write ONLY a Quality Forge PROJECT_TZ.md task list. "
        "EVERY actionable line MUST match exactly:\n"
        "- [ ] T1 | REWRITE ... | @gameplay_programmer | -> src/path/File.luau\n"
        "Rules:\n"
        "- Start with a 2-line # comment header, then ## AGENT, then ## HUMAN\n"
        "- Use IDs T1..T12 then H1..H3\n"
        "- ASCII arrow -> only (never unicode)\n"
        "- ALWAYS start description with REWRITE or APPEND or CREATE\n"
        "- Generator task MUST contain these exact words: Checkpoints Coins "
        "Instance.new(\"SpawnLocation\") ensureFolder\n"
        "- LevelConfig / Generator / Coins / Checkpoints / Void / Puzzles => "
        "@gameplay_programmer (NOT @content_author)\n"
        "- HUD / Effects / Leaderboard => @client_programmer\n"
        "- H1 H2 H3 lines MUST use @human and MUST NOT have -> path\n"
        "- NO prose sections, NO design essays, NO code fences, NO Luau bodies\n"
        "- Keep each description under 180 chars so Ollama 4k ctx fits\n"
        "- Include: HUD player:GetAttribute; Coins Destroy+UpdateLeaderboard; "
        "Checkpoints; Void; Puzzles; Effects sounds; LevelConfig Luau id=\n"
    )
    prompt = (
        f"Project: {project_id}\nGoal:\n{goal}\n\n"
        f"Compact skills:\n- " + "\n- ".join(compact_skills or ["forge-player-attrs"]) + "\n"
        f"Existing files:\n- " + "\n- ".join(existing_files[:40] or ["(empty)"]) + "\n"
        "Return the PROJECT_TZ.md now."
    )
    if not available():
        return horror_coins_tz_fallback(project_id=project_id, goal=goal)
    out = chat(prompt, system=system, max_tokens=2200, temperature=0.15)
    out = out.strip()
    if out.startswith("```"):
        out = re.sub(r"^```(?:markdown|md)?\n?", "", out)
        out = re.sub(r"\n?```$", "", out)
    if count_tz_tasks(out) < 5:
        # one strict retry
        out2 = chat(
            prompt + "\n\nPREVIOUS OUTPUT INVALID (not enough '- [ ] T' lines). Rewrite as tasks only.",
            system=system,
            max_tokens=2200,
            temperature=0.05,
        )
        out2 = out2.strip()
        if count_tz_tasks(out2) >= 5:
            return out2
        return horror_coins_tz_fallback(project_id=project_id, goal=goal)
    return out


def horror_coins_tz_fallback(*, project_id: str, goal: str) -> str:
    """Compact task list that always parses; keeps Ollama ctx small."""
    return f"""# LAST_UPDATE: {project_id} horror coins obstacle
# Goal: {goal[:240]}

## AGENT
- [ ] T1 | REWRITE LevelConfig array id= gap= coins= Luau = only never JS colon | @gameplay_programmer | -> src/shared/Content/LevelConfig.luau
- [ ] T2 | REWRITE Generator ensureFolder Map Checkpoints Coins; Instance.new(\"SpawnLocation\"); dark Path; Neon CP; gold coins; destroy Baseplate | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [ ] T3 | REWRITE Checkpoints Player SetAttribute Checkpoint+Score; FireClient CheckpointReached; CanTouch; no CoinsCollected; no destroy coins | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] T4 | REWRITE Coins CanTouch coin:Destroy plr:SetAttribute Coins FireClient CoinCollected FireAllClients UpdateLeaderboard | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
- [ ] T5 | REWRITE Void Heartbeat HRP.Y<-20 LoadCharacter | @gameplay_programmer | -> src/server/Gameplay/Void.server.luau
- [ ] T6 | REWRITE Puzzles ensureFolder once PressurePlate+Gate on Path Z~40 Touched/TouchEnded | @gameplay_programmer | -> src/server/Gameplay/Puzzles.server.luau
- [ ] T7 | REWRITE PlayerData init Player attrs Score Checkpoint Coins BestTime Studio only | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] T8 | REWRITE HUD left labels Time CP Coins Best via player:GetAttribute only never character attrs | @client_programmer | -> src/client/HUD.client.luau
- [ ] T9 | REWRITE Effects pcall Sound coin+checkpoint+quiet ambience ids 9114224690 9112854440 | @client_programmer | -> src/client/Effects.client.luau
- [ ] T10 | REWRITE Leaderboard ScreenGui UpdateLeaderboard text only | @client_programmer | -> src/client/Leaderboard.client.luau
- [ ] T11 | APPEND GDD #horror-coins atmosphere notes | @game_designer | -> docs/GDD.md#horror-coins
- [ ] T12 | REWRITE QA_REPORT ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE overall NN | @qa_engineer | -> docs/QA_REPORT.md

## HUMAN
- [ ] H1 | Studio: dark Path SpawnLocation gold coins neon CP; left HUD updates | @human
- [ ] H2 | Studio: plate/gate void; scary coin sound; no CoinsCollected errors | @human
- [ ] H3 | Final python -u run.py --eval | @human
"""


def smoke_questionnaire(*, project_id: str, focus: str = "gameplay HUD coins CP") -> Dict[str, Any]:
    """Ask structured smoke questions after a week run (human answers in UI)."""
    system = (
        "Return ONLY valid JSON with key questions: array of "
        "{id, prompt, expect_yes_means}. 6-10 short Studio smoke questions."
    )
    prompt = (
        f"Project {project_id}. Focus: {focus}. "
        "Cover left HUD, coins, checkpoints, spawn, void, puzzles, Output errors."
    )
    if not available():
        return _default_smoke()
    raw = chat(prompt, system=system, max_tokens=1200, temperature=0.2)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("questions"):
            return data
    except json.JSONDecodeError:
        pass
    return _default_smoke()


def _default_smoke() -> Dict[str, Any]:
    return {
        "questions": [
            {
                "id": "q1",
                "prompt": "Левый HUD: Time / CP / Coins обновляются?",
                "expect_yes_means": "HUD player attrs OK",
            },
            {
                "id": "q2",
                "prompt": "Золотая монета: Coins слева + лидерборд справа растут?",
                "expect_yes_means": "Coins remotes OK",
            },
            {
                "id": "q3",
                "prompt": "Зелёный neon CP обновляет Checkpoint без ошибок Output?",
                "expect_yes_means": "Checkpoints OK",
            },
            {
                "id": "q4",
                "prompt": "Настоящий SpawnLocation; нет Baseplate; Path проходим?",
                "expect_yes_means": "Generator OK",
            },
            {
                "id": "q5",
                "prompt": "Падение в void (Y < -20) респавнит персонажа?",
                "expect_yes_means": "Void OK",
            },
            {
                "id": "q6",
                "prompt": "Синяя плита открывает красный gate на Path?",
                "expect_yes_means": "Puzzles OK",
            },
            {
                "id": "q7",
                "prompt": "Best в HUD показывает число (не --) после финиша/респавна?",
                "expect_yes_means": "BestTime written on Player",
            },
        ]
    }
