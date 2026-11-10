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
    timeout: float = 180,
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    try:
        from . import asset_hub

        assets_line = asset_hub.catalog_for_prompt()
    except Exception:
        assets_line = "Available 3D assets: (catalog unavailable)."
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
        "- When spawning collectibles, ONLY use asset ids from the Available 3D assets list "
        "(never invent Apple/Banana/Coin if missing). Mention proposed_assets in task text.\n"
        f"- {assets_line}\n"
    )
    prompt = (
        f"Project: {project_id}\nGoal:\n{goal}\n\n"
        f"{assets_line}\n\n"
        f"Compact skills:\n- " + "\n- ".join(compact_skills or ["forge-player-attrs"]) + "\n"
        f"Existing files:\n- " + "\n- ".join(existing_files[:40] or ["(empty)"]) + "\n"
        "Return the PROJECT_TZ.md now."
    )
    if not available():
        raise llm.AuthError(
            "DEEPSEEK_API_KEY unset - cannot generate PROJECT_TZ. "
            "Set DEEPSEEK_API_KEY (https://platform.deepseek.com/) and retry. "
            "Refusing silent fallback to stale horror-coins TZ."
        )
    out = chat(prompt, system=system, max_tokens=2200, temperature=0.15)
    out = out.strip()
    if out.startswith("```"):
        out = re.sub(r"^```(?:markdown|md)?\n?", "", out)
        out = re.sub(r"\n?```$", "", out)
    if count_tz_tasks(out) < 5:
        # one strict retry — still no silent horror-coins fallback
        out2 = chat(
            prompt + "\n\nPREVIOUS OUTPUT INVALID (not enough '- [ ] T' lines). Rewrite as tasks only.",
            system=system,
            max_tokens=2200,
            temperature=0.05,
        )
        out2 = out2.strip()
        if count_tz_tasks(out2) >= 5:
            return out2
        raise RuntimeError(
            f"DeepSeek TZ invalid: expected >=5 checkbox tasks, got {count_tz_tasks(out2)}. "
            "Fix the goal/skills and retry - refusing stale horror-coins fallback."
        )
    return out


_TASK_LINE_RE = re.compile(
    r"(?m)^\s*- \[ \] ((?:[PW]\d+(?:\.\d+)*(?:\.[a-z])?)|(?:[ABHZGFRT]\d+[a-z]?))\s*\|.+$"
)


def next_tz_task_number(done_tasks_summary: str, existing_files: Optional[List[str]] = None) -> int:
    """Next T# after highest T/F/R/P/G/A agent id seen in summary text."""
    nums = [int(n) for n in re.findall(r"(?i)\b[TFRPGA]\s*(\d+)\b", done_tasks_summary or "")]
    if existing_files:
        # unused; kept for API symmetry with callers that pass both
        pass
    return (max(nums) + 1) if nums else 13


def extract_tz_task_lines(text: str) -> List[str]:
    """Pull PROJECT_TZ checkbox agent lines from model output."""
    out: List[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s.startswith("- [ ] "):
            continue
        if _TASK_LINE_RE.match(s) or re.match(r"^- \[ \] [A-Z]?\d+", s):
            # Prefer AGENT tasks (T/F/R/P/G/A); skip bare H* human gates
            m = re.match(r"^- \[ \] ([A-Z]?\d+[a-z]?)", s)
            if m and m.group(1).upper().startswith("H"):
                continue
            out.append(s)
    return out


def generate_more_tasks(
    project_id: str,
    goal: str,
    existing_files: List[str],
    done_tasks_summary: str,
) -> List[str]:
    """Ask DeepSeek for 3-5 NEW polish/sound/opt/feature tasks (Live Ops).

    Returns PROJECT_TZ checkbox lines with IDs continuing (T13, T14...).
    Empty list when unavailable / invalid / too few unique tasks.
    """
    start_n = next_tz_task_number(done_tasks_summary)
    id_hint = ", ".join(f"T{start_n + i}" for i in range(5))
    try:
        from . import asset_hub

        assets_line = asset_hub.catalog_for_prompt()
    except Exception:
        assets_line = "Available 3D assets: (catalog unavailable)."

    system = (
        "You extend a Quality Forge PROJECT_TZ.md AGENT task list for Live Ops. "
        "Return ONLY 3 to 5 new checkbox lines (no headers, no HUMAN, no fences). "
        "EVERY line MUST match exactly:\n"
        "- [ ] T13 | REWRITE ... | @gameplay_programmer | -> src/path/File.luau\n"
        "Rules:\n"
        "- ASCII arrow -> only (never unicode)\n"
        "- ALWAYS start description with REWRITE or APPEND or CREATE\n"
        "- Focus polish / sound / optimization / small feature gaps — NOT redo of done work\n"
        "- HUD / Effects / Leaderboard => @client_programmer\n"
        "- LevelConfig / Generator / Coins / Checkpoints / Void / Puzzles => @gameplay_programmer\n"
        "- Keep each description under 180 chars\n"
        f"- Use NEW ids starting at T{start_n} (suggested: {id_hint})\n"
        "- Do NOT repeat done task ids or near-duplicate descriptions\n"
        f"- {assets_line}\n"
    )
    prompt = (
        f"Project: {project_id}\nGoal:\n{(goal or '')[:900]}\n\n"
        f"Done / existing tasks summary:\n{(done_tasks_summary or '(none)')[:3500]}\n\n"
        f"Existing files:\n- " + "\n- ".join((existing_files or [])[:40] or ["(empty)"]) + "\n\n"
        f"{assets_line}\n"
        f"Invent 3-5 NEW AGENT tasks with ids from T{start_n} upward."
    )
    if not available():
        return []
    try:
        raw = chat(prompt, system=system, max_tokens=1200, temperature=0.35)
    except Exception:
        return []
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:markdown|md)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    lines = extract_tz_task_lines(raw)
    # Drop lines that reuse ids already in the summary
    known_ids = {
        m.group(1)
        for m in re.finditer(
            r"(?m)^\s*- \[[ xX-]\] ((?:[PW]\d+(?:\.\d+)*(?:\.[a-z])?)|(?:[ABHZGFRT]\d+[a-z]?))\b",
            done_tasks_summary or "",
        )
    }
    # also catch bare id mentions like "T3 done"
    known_ids |= set(re.findall(r"\b([TFRPGA]\d+[a-z]?)\b", done_tasks_summary or ""))
    fresh: List[str] = []
    seen_desc: set = set()
    for line in lines:
        m = re.match(r"^- \[ \] ([A-Za-z0-9.]+)\s*\|\s*(.+?)\s*\|\s*@", line)
        if not m:
            continue
        tid, desc = m.group(1), m.group(2).strip().lower()
        if tid in known_ids:
            continue
        # near-duplicate: same normalized description
        norm = re.sub(r"\s+", " ", desc)[:120]
        if norm in seen_desc:
            continue
        seen_desc.add(norm)
        fresh.append(line)
        known_ids.add(tid)
    if len(fresh) < 3:
        return []
    return fresh[:5]


def horror_coins_tz_fallback(*, project_id: str, goal: str) -> str:
    """Legacy fixture TZ for unit tests only — not used when API key is missing."""
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


_DEFAULT_COMPACT = [
    "forge-player-attrs",
    "forge-luau-touch",
    "forge-ui-modern",
    "forge-ui-animation",
]

_CONTRACT_RU = (
    "Контракт: attrs Score/Checkpoint/Coins/BestTime только на Player "
    "(GetAttribute/SetAttribute); НЕ Character. Remotes whitelist: "
    "Checkpoint, CheckpointReached, UpdateLeaderboard, CoinCollected."
)
_CONTRACT_EN = (
    "Contract: Score/Checkpoint/Coins/BestTime attrs on Player only "
    "(never Character). Remotes whitelist: Checkpoint, CheckpointReached, "
    "UpdateLeaderboard, CoinCollected."
)


def pick_skill_hints(goal: str, compact_skills: Optional[List[str]] = None) -> List[str]:
    """Heuristic skill ids from goal keywords (2-4)."""
    allowed = list(compact_skills or _DEFAULT_COMPACT)
    g = (goal or "").lower()
    scored: List[tuple] = []
    rules = [
        ("forge-player-attrs", ("hud", "attr", "best", "coin", "checkpoint", "score", "худ", "монет", "чек")),
        ("forge-luau-touch", ("touch", "coin", "checkpoint", "void", "plate", "каса", "монет", "плит")),
        ("forge-ui-modern", ("ui", "hud", "button", "menu", "интерф", "кноп", "меню")),
        ("forge-ui-animation", ("anim", "tween", "juice", "анима", "эффект")),
    ]
    for sid, keys in rules:
        if sid not in allowed:
            continue
        hits = sum(1 for k in keys if k in g)
        if hits:
            scored.append((hits, sid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out = [sid for _, sid in scored[:4]]
    if len(out) < 2:
        for sid in allowed:
            if sid not in out:
                out.append(sid)
            if len(out) >= 3:
                break
    return out[:4]


def extract_skill_hints(text: str, compact_skills: Optional[List[str]] = None) -> List[str]:
    """Parse 'Skills needed:' line or fall back to keyword pick."""
    allowed = list(compact_skills or _DEFAULT_COMPACT)
    m = re.search(r"Skills needed:\s*(.+)$", text or "", re.I | re.M)
    if m:
        parts = re.split(r"[,;\s]+", m.group(1).strip())
        found = [p for p in parts if p in allowed]
        if found:
            return found[:4]
    return pick_skill_hints(text, allowed)


def _looks_russian(text: str) -> bool:
    return sum(1 for c in text if "а" <= c.lower() <= "я" or c in "ёЁ") >= 3


def _quality_gate(text: str, *, russian: bool, skills: List[str]) -> str:
    """Ensure systems + contract + skills line are present; clamp to ~900 chars."""
    t = (text or "").strip()
    systems = ("HUD", "Coin", "Checkpoint", "Spawn", "Void", "Best", "монет", "чек", "худ")
    if not any(s.lower() in t.lower() for s in systems):
        extra = (
            "Системы: HUD, Coins, Checkpoints, SpawnLocation, Void, BestTime."
            if russian
            else "Systems: HUD, Coins, Checkpoints, SpawnLocation, Void, BestTime."
        )
        t = f"{t}\n{extra}".strip()
    contract = _CONTRACT_RU if russian else _CONTRACT_EN
    if "Remotes" not in t and "remotes" not in t.lower() and "whitelist" not in t.lower():
        t = f"{t}\n{contract}"
    if "Skills needed:" not in t:
        t = f"{t}\nSkills needed: {', '.join(skills[:3])}"
    return _clamp_goal(t, limit=900)


def _clamp_goal(text: str, *, limit: int = 900) -> str:
    if len(text) <= limit:
        return text
    # Keep tail blocks: Contract/Контракт + Skills needed
    skills_m = re.search(r"(Skills needed:\s*.+)$", text, re.I | re.M)
    contract_m = re.search(r"((?:Контракт|Contract):.+?)(?=\nSkills needed:|\Z)", text, re.I | re.S)
    tail_parts = []
    if contract_m:
        tail_parts.append(contract_m.group(1).strip())
    if skills_m:
        tail_parts.append(skills_m.group(1).strip())
    tail = ("\n" + "\n".join(tail_parts)) if tail_parts else ""
    head_budget = max(120, limit - len(tail) - 1)
    head = text[:head_budget].rstrip()
    if tail and head.endswith(tail.strip()):
        return head[:limit]
    out = (head + tail).strip()
    return out[:limit]


def improve_goal(
    goal: str,
    *,
    project_id: str = "game1",
    compact_skills: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Rewrite user goal so Ollama agent + skill picker understand intent.

    Returns {goal, skills_hint}. Local template if no DeepSeek key / timeout.
    """
    raw_goal = (goal or "").strip()
    if not raw_goal:
        raise ValueError("goal empty")

    compact_ids = list(compact_skills or _DEFAULT_COMPACT)
    hints = pick_skill_hints(raw_goal, compact_ids)
    russian = _looks_russian(raw_goal)

    try:
        from . import asset_hub

        assets_line = asset_hub.catalog_for_prompt()
    except Exception:
        assets_line = "Available 3D assets: (none)."
    system = (
        "You improve Roblox game goals for Quality Forge. "
        "Return ONLY the improved goal text (no markdown fences). "
        "Keep user intent. Make it concrete for a local coding agent. "
        "Russian if input is Russian else English. 500-900 chars. "
        "Include systems (HUD/Coins/CP/BestTime/Spawn/Void) and a Contract line. "
        "If the goal mentions 3D props/fruits, name ONLY assets from the catalog. "
        "End with: Skills needed: id1, id2, id3"
    )
    prompt = (
        f"Project {project_id}. Raw goal:\n{raw_goal}\n\n"
        f"{assets_line}\n"
        "Rewrite so the agent knows genre + systems + hard rules "
        "(Player attrs not Character; remotes whitelist "
        "Checkpoint,CheckpointReached,UpdateLeaderboard,CoinCollected). "
        f"Prefer skills from: {', '.join(compact_ids)}. "
        f"Suggested skills: {', '.join(hints)}."
    )

    if not available():
        improved = _fallback_improve_goal(raw_goal, hints, russian=russian)
        improved = _quality_gate(improved, russian=russian, skills=hints)
        return {"goal": improved, "skills_hint": extract_skill_hints(improved, compact_ids)}

    try:
        text = chat(
            prompt,
            system=system,
            max_tokens=900,
            temperature=0.2,
            timeout=30,
        ).strip()
    except Exception:
        text = _fallback_improve_goal(raw_goal, hints, russian=russian)

    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    if len(text) < 40:
        text = _fallback_improve_goal(raw_goal, hints, russian=russian)
    text = _quality_gate(text, russian=russian, skills=hints)
    return {"goal": text, "skills_hint": extract_skill_hints(text, compact_ids)}


def _fallback_improve_goal(goal: str, skills: List[str], *, russian: bool) -> str:
    short = goal[:180].rstrip(".")
    if russian:
        return (
            f"Цель ({short}): сделать играбельный Roblox-уровень. "
            "Системы: Path + SpawnLocation, Neon Checkpoints, золотые Coins, "
            "левый HUD Time/CP/Coins/Best через player:GetAttribute (НЕ Character), "
            "Void Y<-20 LoadCharacter, PressurePlate→gate. "
            f"{_CONTRACT_RU} "
            f"Skills needed: {', '.join(skills[:3])}"
        )
    return (
        f"Goal ({short}): ship a playable Roblox level. "
        "Systems: Path + SpawnLocation, Neon Checkpoints, gold Coins, "
        "left HUD Time/CP/Coins/Best via player:GetAttribute (NOT Character), "
        "Void Y<-20 LoadCharacter, PressurePlate→gate. "
        f"{_CONTRACT_EN} "
        f"Skills needed: {', '.join(skills[:3])}"
    )


def smoke_questionnaire(*, project_id: str, focus: str = "gameplay HUD coins CP") -> Dict[str, Any]:
    """Ask structured smoke questions after a week run (human answers in UI)."""
    system = (
        "Return ONLY valid JSON with key questions: array of "
        "{id, prompt, expect_yes_means}. 6-10 short Studio smoke questions. "
        "ALL prompt strings MUST be in Russian."
    )
    prompt = (
        f"Project {project_id}. Focus: {focus}. "
        "Cover left HUD, coins, checkpoints, BestTime, spawn, void, puzzles, Output errors. "
        "Write every prompt in Russian."
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
            # If model returned English, fall back to Russian defaults.
            prompts = " ".join(str(q.get("prompt") or "") for q in data["questions"])
            cyr = sum(1 for c in prompts if "а" <= c.lower() <= "я" or c in "ёЁ")
            if cyr < 8:
                return _default_smoke()
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


def _default_hitl_pack(*, cycle: int = 0, focus: str = "") -> Dict[str, Any]:
    from .planner_schema import normalize_hitl_pack

    pack = {
        "kind": "hitl_pack",
        "cycle": cycle,
        "questions": [
            {
                "id": "Q1",
                "topic": "next_priority",
                "ask": "Что важнее сейчас для агента?",
                "options": [
                    {"key": "A", "label": "Стабильность BestTime / PlayerData"},
                    {"key": "B", "label": "Скорость join / Generator"},
                    {"key": "C", "label": "Полировка HUD / VFX"},
                ],
                "other": {"key": "other", "label": "Другое", "allows_text": True},
                "default_if_timeout": "A",
                "related_plugin": "game1.player_data",
            },
            {
                "id": "Q2",
                "topic": "verify_mode",
                "ask": "Как принимать следующий плагин после validator PASS?",
                "options": [
                    {"key": "A", "label": "Сразу closed (без Studio)"},
                    {"key": "B", "label": "HITL Да/Нет после Studio smoke"},
                    {"key": "C", "label": "Только auto + golden regression"},
                ],
                "other": {"key": "other", "label": "Другое", "allows_text": True},
                "default_if_timeout": "B",
            },
        ],
    }
    if focus:
        pack["questions"][0]["ask"] = f"Фокус «{focus[:60]}»: что важнее сейчас?"
    return normalize_hitl_pack(pack, cycle=cycle)


def ask_hitl_pack(
    *,
    cycle: int = 0,
    focus: str = "",
    open_topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """DeepSeek returns strict A/B/C/Другое pack (≤2 questions). Falls back to default."""
    from .planner_schema import normalize_hitl_pack, parse_json_object, validate_hitl_pack

    topics = ", ".join(open_topics or []) or "gameplay priority"
    try:
        from . import asset_hub

        assets_line = asset_hub.catalog_for_prompt()
    except Exception:
        assets_line = "Available 3D assets: (none)."
    system = (
        "Return ONLY valid JSON for kind=hitl_pack. "
        "questions: 1 or 2 items. Each question MUST have id, ask, "
        "options exactly [{key:A,label},{key:B,label},{key:C,label}], "
        "other:{key:other,label:Другое,allows_text:true}, default_if_timeout A|B|C. "
        "No open-ended questions. Prefer Russian ask/labels. "
        "If asking about props/collectibles, options may reference catalog asset ids only."
    )
    prompt = (
        f"Cycle {cycle}. Focus: {focus or 'agent core'}. Topics: {topics}. "
        f"{assets_line} "
        "Ask the human what to do next with A/B/C/Другое only."
    )
    if not available():
        return _default_hitl_pack(cycle=cycle, focus=focus)
    try:
        raw = chat(prompt, system=system, max_tokens=900, temperature=0.15)
        data = parse_json_object(raw)
        if not data:
            return _default_hitl_pack(cycle=cycle, focus=focus)
        data["cycle"] = cycle
        ok, errs = validate_hitl_pack(data)
        if not ok:
            return _default_hitl_pack(cycle=cycle, focus=focus)
        return normalize_hitl_pack(data, cycle=cycle)
    except Exception:
        return _default_hitl_pack(cycle=cycle, focus=focus)


def clarify_other(
    *,
    question: Dict[str, Any],
    other_text: str,
    cycle: int = 0,
) -> Dict[str, Any]:
    """
    User chose Другое + free text.
    Returns either a new 1-question hitl_pack OR {resolved:{key,label,from_other:true}}.
    """
    from .planner_schema import normalize_hitl_pack, parse_json_object, validate_hitl_pack

    text = (other_text or "").strip()
    system = (
        "Return ONLY JSON. Either "
        '{"resolved":{"key":"A|B|C","label":"...","from_other":true}} '
        "mapping the free text onto A/B/C, OR a hitl_pack with exactly 1 clarifying "
        "question (same A/B/C/other schema). Prefer resolved when text clearly matches."
    )
    prompt = (
        f"Original ask: {question.get('ask')}\n"
        f"Options: {json.dumps(question.get('options') or [], ensure_ascii=False)}\n"
        f"User other text: {text}\n"
    )
    if not available():
        # heuristic: if text mentions option label keywords, map; else new pack
        low = text.lower()
        for opt in question.get("options") or []:
            lab = str(opt.get("label") or "").lower()
            if lab and (lab in low or lab.split()[0] in low):
                return {
                    "resolved": {
                        "key": str(opt.get("key") or "B").upper(),
                        "label": opt.get("label"),
                        "from_other": True,
                        "note": text[:200],
                    }
                }
        return normalize_hitl_pack(
            {
                "kind": "hitl_pack",
                "cycle": cycle,
                "questions": [
                    {
                        "id": f"{question.get('id') or 'Q1'}b",
                        "topic": question.get("topic") or "clarify",
                        "ask": f"Уточните: «{text[:80]}». Ближе к чему?",
                        "options": question.get("options")
                        or [
                            {"key": "A", "label": "Вариант A"},
                            {"key": "B", "label": "Вариант B"},
                            {"key": "C", "label": "Вариант C"},
                        ],
                        "other": {"key": "other", "label": "Другое", "allows_text": True},
                        "default_if_timeout": question.get("default_if_timeout") or "B",
                    }
                ],
            },
            cycle=cycle,
        )
    try:
        raw = chat(prompt, system=system, max_tokens=700, temperature=0.1)
        data = parse_json_object(raw) or {}
        if isinstance(data.get("resolved"), dict):
            key = str(data["resolved"].get("key") or "").upper()
            if key in {"A", "B", "C"}:
                data["resolved"]["key"] = key
                data["resolved"]["from_other"] = True
                return data
        ok, _ = validate_hitl_pack(data)
        if ok:
            return normalize_hitl_pack(data, cycle=cycle)
    except Exception:
        pass
    return _fallback_clarify(question, text, cycle)


def _fallback_clarify(question: Dict[str, Any], text: str, cycle: int) -> Dict[str, Any]:
    from .planner_schema import normalize_hitl_pack

    return normalize_hitl_pack(
        {
            "kind": "hitl_pack",
            "cycle": cycle,
            "questions": [
                {
                    "id": f"{question.get('id') or 'Q1'}b",
                    "topic": "clarify",
                    "ask": f"Уточните «{text[:80]}». Какой вариант ближе?",
                    "options": question.get("options")
                    or [
                        {"key": "A", "label": "A"},
                        {"key": "B", "label": "B"},
                        {"key": "C", "label": "C"},
                    ],
                    "other": {"key": "other", "label": "Другое", "allows_text": True},
                    "default_if_timeout": "B",
                }
            ],
        },
        cycle=cycle,
    )


def compress_skill_card(raw_md: str, *, name: str, max_chars: int = 350) -> Dict[str, Any]:
    """Compress skill into typed contract card JSON (≤ max_chars)."""
    from .planner_schema import CARD_MAX_CHARS, clamp_skill_card, parse_json_object, validate_skill_card

    budget = min(max_chars, CARD_MAX_CHARS)
    system = (
        "Return ONLY JSON skill card: "
        '{"id","exports":[\"fn(a:type)->t\"],"attrs":[],"forbid":[],"files":[]}. '
        f"Hard max JSON length {budget} chars. Keep arg types. No prose."
    )
    if not available():
        return _heuristic_skill_card(raw_md, name=name, max_chars=budget)
    try:
        raw = chat(
            f"Skill: {name}\n===\n{raw_md[:12000]}\n===",
            system=system,
            max_tokens=400,
            temperature=0.1,
        )
        data = parse_json_object(raw) or {}
        data["id"] = data.get("id") or name
        card = clamp_skill_card(data, max_chars=budget)
        ok, _ = validate_skill_card(card, max_chars=budget)
        if ok:
            return card
    except Exception:
        pass
    return _heuristic_skill_card(raw_md, name=name, max_chars=budget)


def _heuristic_skill_card(raw_md: str, *, name: str, max_chars: int = 350) -> Dict[str, Any]:
    from .planner_schema import clamp_skill_card

    exports = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*\([^`]{0,60}\))`", raw_md)[:6]
    if not exports:
        exports = re.findall(r"\b([a-z_][a-z0-9_]{3,}\([^)]{0,40}\))", raw_md, re.I)[:4]
    forbid = []
    for ln in raw_md.splitlines():
        if re.search(r"forbid|never|NEVER|запрет", ln, re.I):
            forbid.append(ln.strip()[:60])
    attrs = re.findall(r"\b(BestTime|Checkpoint|Coins|Score|RunStartedAt)\b", raw_md)
    files = re.findall(r"[\w./]+\.luau", raw_md)[:4]
    card = {
        "id": name,
        "exports": exports or [f"{name.replace('-', '_')}()"],
        "attrs": sorted(set(attrs))[:8],
        "forbid": forbid[:4],
        "files": files,
    }
    return clamp_skill_card(card, max_chars=max_chars)
