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


def generate_project_tz(
    *,
    project_id: str,
    goal: str,
    compact_skills: List[str],
    existing_files: List[str],
) -> str:
    """DeepSeek drafts PROJECT_TZ.md tasks (agent still executes via Ollama)."""
    system = (
        "You write PROJECT_TZ.md for Quality Forge. "
        "Tasks use lines: - [ ] ID | DESCRIPTION | @role | -> path\n"
        "Roles: @gameplay_programmer @client_programmer @integrator @qa_engineer "
        "@game_designer @content_author @human\n"
        "IDs like T1 T2... then H1 human gates. ASCII arrows -> only. "
        "Do not write Luau. Do not mark tasks done."
    )
    prompt = (
        f"Project: {project_id}\nGoal: {goal}\n"
        f"Compact skills available:\n- " + "\n- ".join(compact_skills) + "\n"
        f"Existing files:\n- " + "\n- ".join(existing_files[:40]) + "\n"
        "Emit a full PROJECT_TZ.md body."
    )
    return chat(prompt, system=system, max_tokens=2500, temperature=0.2)


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
                "prompt": "Left HUD shows Time/CP/Coins updating?",
                "expect_yes_means": "HUD player attrs OK",
            },
            {
                "id": "q2",
                "prompt": "Picking a gold coin increments left Coins and right leaderboard?",
                "expect_yes_means": "Coins remotes OK",
            },
            {
                "id": "q3",
                "prompt": "Green neon checkpoint updates CP without Output errors?",
                "expect_yes_means": "Checkpoints OK",
            },
            {
                "id": "q4",
                "prompt": "Real SpawnLocation; no Baseplate; Path walkable?",
                "expect_yes_means": "Generator OK",
            },
            {
                "id": "q5",
                "prompt": "Fall below map respawns (void)?",
                "expect_yes_means": "Void OK",
            },
            {
                "id": "q6",
                "prompt": "Blue plate opens red gate on Path?",
                "expect_yes_means": "Puzzles OK",
            },
        ]
    }
