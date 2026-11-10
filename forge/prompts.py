"""Prompt builder with context budget (fixes 39KB prompt blowups)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from .task_parser import Task, WriteMode

SKIP_NAMES = {"run.ps1", "run.py", "PROJECT_TZ.md", "AGENTS.md"}
SKIP_DIRS = {"logs", ".git", "forge", "build", ".forge", "__pycache__", "tests"}

_MODELS_PATH = Path(__file__).resolve().parent / "models.json"


def load_model_config() -> dict:
    if _MODELS_PATH.is_file():
        return json.loads(_MODELS_PATH.read_text(encoding="utf-8"))
    return {"agents": {}, "escalation": [], "fallback_any": True}


_CFG = load_model_config()

# Defaults match the user's original Ollama tags (7b-2k / 14b-4k / 3b-8k), NOT bare :7b/:14b
AGENT_MODELS: Dict[str, dict] = {
    name: dict(cfg)
    for name, cfg in (_CFG.get("agents") or {}).items()
}

# Ensure every known role has an entry even if JSON is trimmed
_FALLBACK_ROLE = {"model": "qwen2.5-coder:14b-4k", "ctx": 2048, "predict": 1024}
for _role in (
    "game_designer",
    "tech_architect",
    "gameplay_programmer",
    "client_programmer",
    "qa_engineer",
    "refactorer",
    "builder",
    "systems_designer",
    "content_author",
    "integrator",
):
    AGENT_MODELS.setdefault(_role, dict(_FALLBACK_ROLE))

ESCALATION: List[str] = list(_CFG.get("escalation") or [
    "qwen2.5-coder:14b-4k",
    "qwen2.5-coder:14b-2k",
    "qwen2.5-coder:14b",
])
FALLBACK_ANY = bool(_CFG.get("fallback_any", True))
WEEK_MODE: dict = dict(_CFG.get("week_mode") or {
    "disable_micro_split": True,
    "seed_first": True,
    "validate_every_n_steps": 5,
})
SPACEBUNNY_CFG: dict = dict(_CFG.get("spacebunny") or {})
OPENROUTER_CFG: dict = dict(_CFG.get("openrouter") or {})


def extract_agent_section(agents_md: str, owner: str) -> str:
    # Roles are "### @owner" (or "## @owner"); keep universal rules above first role.
    role_start = re.search(r"(?m)^#{2,3} @\w+", agents_md)
    universal = agents_md[: role_start.start() if role_start else len(agents_md)]
    m = re.search(
        rf"(?ms)^#{{2,3}} @{re.escape(owner)}\b.*?(?=^#{{2,3}} @|\Z)",
        agents_md,
    )
    section = m.group(0) if m else ""
    return universal + "\n" + section


def relevant_paths(root: Path, task: Task, owner: str = "") -> List[Path]:
    """Prefer files related to the task; QA/refactor always get all src/*.luau first."""
    picks: List[Path] = []
    seen: Set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve())
        if key in seen or not p.is_file():
            return
        seen.add(key)
        picks.append(p)

    # Roles that MUST see game code (P30.1 failed because only docs were included)
    needs_all_src = owner in {
        "qa_engineer",
        "refactorer",
        "integrator",
        "gameplay_programmer",
        "client_programmer",
    } or any(
        k in (task.description or "").lower()
        for k in ("qa", "static review", "fix", "integrity", "score")
    )

    src = root / "src"
    if needs_all_src and src.is_dir():
        for p in sorted(src.rglob("*.luau")):
            add(p)

    if task.target_path:
        add(root / task.target_path)
        # only add siblings for non-docs targets (docs/* siblings ate the budget)
        parent = (root / task.target_path).parent
        if parent.is_dir() and parent.name != "docs":
            for child in sorted(parent.glob("*")):
                add(child)

    for rel in (
        "default.project.json",
        "src/shared/Gameplay/Remotes.luau",
        "docs/ARCHITECTURE.md",
        "docs/GDD.md",
        "docs/QA_REPORT.md",
    ):
        add(root / rel)

    if len(picks) < 4 and src.is_dir():
        for p in sorted(src.rglob("*.luau")):
            add(p)

    return picks


def file_budget_chars() -> int:
    """Cloud 1M-ctx: large. Ollama A17 hard-fit: tiny file window inside 2k ctx."""
    try:
        from . import llm

        be = llm.backend_name()
        if be == "spacebunny":
            return int(SPACEBUNNY_CFG.get("file_budget") or 180_000)
        if be == "openrouter":
            return int(OPENROUTER_CFG.get("file_budget") or 180_000)
        ollama_cfg = dict(_CFG.get("ollama") or {})
        # A17: default 1800 chars — contracts/TZ/task must still fit ≤2000 tok / leave predict room
        return int(ollama_cfg.get("file_budget") or 1_800)
    except Exception:
        pass
    return 1_800


def compress_tz_for_prompt(tz: str, *, max_chars: int = 900) -> str:
    """
    A17: shrink PROJECT_TZ before Ollama — keep headers + open [ ] (+ sparse done markers).
    Done/failed lines collapse to a one-line count so open work stays visible.
    """
    lines = (tz or "").splitlines()
    keep: List[str] = []
    done_n = 0
    fail_n = 0
    header_n = 0
    for line in lines:
        s = line.strip()
        # Task markers always classified first (even in first lines)
        if "- [ ]" in line:
            keep.append(line)
            continue
        if "- [-]" in line:
            fail_n += 1
            m = re.search(r"\b([A-Z]\d+(?:\.\d+)?)\b", line)
            if m and len(keep) < 40:
                keep.append(f"- [-] {m.group(1)}")
            continue
        if "- [x]" in line:
            done_n += 1
            continue
        # Headers / preamble only (cap so done lists elsewhere don't sneak in)
        if s.startswith("#") or (header_n < 6 and not s.startswith("-")):
            keep.append(line)
            header_n += 1
            continue
    if done_n or fail_n:
        keep.append(f"(TZ compact: done={done_n} failed_repair={fail_n})")
    text = "\n".join(keep)
    if len(text) > max_chars:
        head = "\n".join(keep[:6])
        rest = "\n".join(keep[6:])
        room = max(0, max_chars - len(head) - 40)
        text = head + "\n...\n" + rest[-room:]
    return text[:max_chars]


def render_files(paths: Sequence[Path], root: Path, budget_chars: Optional[int] = None) -> str:
    if budget_chars is None:
        budget_chars = file_budget_chars()
    parts: List[str] = []
    used = 0
    for p in paths:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.name
        text = p.read_text(encoding="utf-8", errors="replace")
        chunk = f"=== {rel} ===\n{text}\n\n"
        if used + len(chunk) > budget_chars:
            remain = max(0, budget_chars - used - 80)
            if remain > 200:
                parts.append(f"=== {rel} ===\n{text[:remain]}\n...(truncated)\n\n")
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts) if parts else "(no files yet)"


def mode_instructions(task: Task, *, file_exists: bool = False, prefer_diff: bool = True) -> str:
    if task.mode == WriteMode.APPEND:
        return (
            "WRITE MODE = APPEND.\n"
            "- Return ONLY the new lines to append.\n"
            "- Do NOT repeat existing file content.\n"
            "- Do NOT rewrite the whole file.\n"
            f"- Target file: {task.target_path}\n"
        )
    if task.mode == WriteMode.REWRITE and file_exists and prefer_diff:
        return (
            "WRITE MODE = PATCH (file already exists — A15 diff economy).\n"
            "- Prefer SEARCH/REPLACE blocks inside <FILE> instead of rewriting the whole file.\n"
            "- Format exactly:\n"
            "<<<<<<< SEARCH\n"
            "exact old lines from the baseline\n"
            "=======\n"
            "new lines\n"
            ">>>>>>> REPLACE\n"
            "- Multiple blocks allowed. SEARCH must match the baseline exactly.\n"
            "- Full-file rewrite ONLY if >40% of the file must change.\n"
            f"- Target file: {task.target_path}\n"
        )
    if task.mode == WriteMode.REWRITE:
        return (
            "WRITE MODE = REWRITE.\n"
            "- Return the COMPLETE new file content.\n"
            f"- Target file: {task.target_path}\n"
        )
    if task.mode == WriteMode.CREATE:
        return (
            "WRITE MODE = CREATE.\n"
            "- Return the COMPLETE file content for a new/overwrite file.\n"
            f"- Target file: {task.target_path}\n"
        )
    if task.section:
        return (
            "WRITE MODE = SECTION APPEND.\n"
            f"- Append a markdown section to {task.target_path} (section #{task.section}).\n"
            "- Return only the new section body.\n"
        )
    return "WRITE MODE = NORMAL. Return complete file content for each <FILE>."


def format_validator_checklist(fails: Sequence[str]) -> str:
    """Numbered checklist for 7B repair — model must fix every bullet, nothing else."""
    items = [str(f).strip() for f in (fails or []) if str(f).strip()]
    if not items:
        items = ["(no structured validator_fails — re-read last VALIDATOR FAIL lines)"]
    lines = [f"{i}. {msg}" for i, msg in enumerate(items, 1)]
    return (
        "REPAIR CHECKLIST (validator_fails) — fix EVERY bullet, in order:\n"
        + "\n".join(lines)
        + "\nRules: surgical PATCH only; do not rewrite architecture; "
        "after edits the file must satisfy ALL bullets above."
    )


def build_prompt(
    root: Path,
    owner: str,
    task: Task,
    *,
    attempt: int = 1,
    validator_feedback: Optional[str] = None,
    prior_snapshot: Optional[str] = None,
    repair_draft: Optional[str] = None,
    is_7b: bool = False,
    prompt_budget_tokens: Optional[int] = None,
    num_ctx: Optional[int] = None,
    num_predict: Optional[int] = None,
) -> str:
    # A17: detect local Ollama so we hard-fit; cloud keeps larger prompts
    local_ollama = True
    try:
        from . import llm

        local_ollama = llm.backend_name() == "ollama"
    except Exception:
        local_ollama = True

    from . import llm_backends

    budget = prompt_budget_tokens
    if budget is None and local_ollama:
        budget = llm_backends.effective_prompt_token_budget(
            is_7b=is_7b,
            num_ctx=num_ctx,
            num_predict=num_predict,
            diff_mode=is_7b or attempt >= 2,
        )
    elif budget is None:
        budget = None  # cloud: no hard fit

    agents_raw = extract_agent_section((root / "AGENTS.md").read_text(encoding="utf-8"), owner)
    # A17: agents.md is huge — keep a stub for local ctx
    if local_ollama:
        agents = agents_raw[:500]
    else:
        agents = agents_raw

    tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
    if local_ollama:
        tz_compact = compress_tz_for_prompt(tz, max_chars=700 if is_7b else 900)
    else:
        tz_lines = tz.splitlines()
        compact: List[str] = []
        for i, line in enumerate(tz_lines):
            if i < 12 or line.startswith("#") or line.startswith("##") or "- [ ]" in line:
                compact.append(line)
            elif "- [x]" in line or "- [-]" in line:
                compact.append(line)
        tz_compact = "\n".join(compact)

    file_cap = 900 if is_7b else file_budget_chars()
    if local_ollama and not is_7b:
        file_cap = min(file_cap, 1_800)
    if local_ollama and is_7b:
        file_cap = min(file_cap, 700)
    files = render_files(relevant_paths(root, task, owner), root, budget_chars=file_cap)

    feedback = ""
    if validator_feedback:
        # Prefer short checklist; trim long freeform validator walls
        vf = validator_feedback.strip()
        if local_ollama and len(vf) > 600:
            vf = vf[:600] + "\n...(validator trimmed)..."
        feedback = f"\n=== VALIDATOR FEEDBACK (fix ONLY these issues) ===\n{vf}\n"
    if repair_draft:
        draft = repair_draft
        if local_ollama:
            # Keep surgical repair draft tiny so checklist + task still fit
            draft_cap = 1200 if is_7b else 1800
            if len(draft) > draft_cap:
                draft = draft[: draft_cap // 2] + "\n...(draft mid truncated)...\n" + draft[-draft_cap // 2 :]
        feedback += (
            "\n=== REPAIR MODE (A15 PATCH / 7B) ===\n"
            "Below is YOUR previous draft (almost done). Do NOT rewrite from scratch.\n"
            "Work the REPAIR CHECKLIST bullet-by-bullet "
            "(e.g. add Humanoid.Died + LoadCharacter; "
            'FindFirstChild("Checkpoint"..idx) for teleport; '
            "Checkpoint_ → Checkpoint..id).\n"
            "Prefer SEARCH/REPLACE blocks against this draft; full file only if required.\n"
            f"{draft}\n"
        )
    elif prior_snapshot and task.mode == WriteMode.APPEND:
        snap = prior_snapshot
        if local_ollama and len(snap) > 800:
            snap = snap[-800:]
        feedback += (
            f"\n=== CURRENT FILE CONTENT (append AFTER this, do not repeat) ===\n"
            f"{snap}\n"
        )
    elif prior_snapshot and task.mode in {WriteMode.REWRITE, WriteMode.CREATE}:
        snap = prior_snapshot
        if local_ollama:
            snap_cap = 900 if is_7b else 1400
            if len(snap) > snap_cap:
                snap = snap[: snap_cap // 2] + "\n...(baseline truncated)...\n" + snap[-snap_cap // 2 :]
        feedback += (
            "\n=== BASELINE FILE (PATCH from THIS — A15) ===\n"
            "Prefer SEARCH/REPLACE against this baseline. Do not invent a new architecture.\n"
            "Preserve: Map folder, Name=\"Path\" floor, SpawnPlaza, SpawnLocation, "
            'checkpoint Name = "Checkpoint" .. tostring(id) (NO underscore), coins, print section ids.\n'
            "Only apply the task delta (e.g. add Obstacle parts).\n"
            f"{snap}\n"
        )

    # Compact Roblox skills — A17: trim contracts hard before Ollama
    skills_block = ""
    try:
        from . import skills_hub
        from . import token_economy as te

        skill_ids = ["forge-player-attrs", "forge-luau-touch"]
        active = root / ".forge" / "active_project.json"
        if active.exists():
            import json as _json

            pid = (_json.loads(active.read_text(encoding="utf-8")) or {}).get("id")
            meta_p = root / "projects" / str(pid) / "meta.json"
            if meta_p.exists():
                meta = _json.loads(meta_p.read_text(encoding="utf-8"))
                skill_ids = list(meta.get("skills_compact") or skill_ids)[:3]
        focus = te.extract_focus_terms(task.raw or "", task.description or "", tz_compact[:800])
        max_skills = 1 if (local_ollama and is_7b) else (2 if local_ollama else 3)
        skills_block = skills_hub.bundle_for_14b(
            root,
            skill_ids[:max_skills],
            max_skills=max_skills,
            card_budget=220 if local_ollama else 350,
            rules_budget=180 if local_ollama else 400,
            focus_terms=focus,
            economy=True,
            prune=True,
            skeleton_budget=0,
        )
        skill_cap = 500 if is_7b else (900 if local_ollama else 3600)
        if len(skills_block) > skill_cap:
            skills_block = skills_block[:skill_cap]
        if skills_block:
            skills_block = "\n" + skills_block
    except Exception:
        skills_block = ""

    # A11.0: 3D asset catalog — skip or tiny on local hard-fit
    assets_block = ""
    if not local_ollama:
        try:
            from . import asset_hub

            assets_block = "\n=== " + asset_hub.catalog_for_prompt(root, max_chars=400) + " ===\n"
        except Exception:
            assets_block = ""
    else:
        try:
            from . import asset_hub

            assets_block = "\n=== " + asset_hub.catalog_for_prompt(root, max_chars=120) + " ===\n"
        except Exception:
            assets_block = ""

    retry_note = ""
    if attempt > 1:
        retry_note = (
            f"\nThis is attempt {attempt}. Previous output was rejected.\n"
            "If REPAIR MODE is present: patch that draft, do not start a new design.\n"
            "Follow the format EXACTLY. Begin with <DONE>. Include <FILE> tags.\n"
        )
    qa_template = ""
    if owner == "qa_engineer":
        qa_template = """
=== QA_REPORT TEMPLATE (copy structure; fill real bugs) ===
## BUGS
- [LOW] example only if real

## SUGGESTIONS
- one concrete suggestion

## TEST CASES
- one Studio test

## SCORE
- overall: 86
"""
    remotes_template = ""
    if task.target_path and task.target_path.replace("\\", "/").endswith("Remotes.luau"):
        remotes_template = """
=== REMOTES TEMPLATE (copy structure; do not return the Folder) ===
--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local folder = ReplicatedStorage:FindFirstChild("Remotes")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Remotes"
	folder.Parent = ReplicatedStorage
end

local function getOrCreate(name: string): RemoteEvent
	local r = folder:FindFirstChild(name)
	if not r then
		r = Instance.new("RemoteEvent")
		r.Name = name
		r.Parent = folder
	end
	return r :: RemoteEvent
end

local Remotes = {
	Checkpoint = getOrCreate("Checkpoint"),
	CheckpointReached = getOrCreate("CheckpointReached"),
	UpdateLeaderboard = getOrCreate("UpdateLeaderboard"),
	CoinCollected = getOrCreate("CoinCollected"),
}
return Remotes
"""
    checkpoints_template = ""
    if task.target_path and "Checkpoints.server.luau" in task.target_path.replace("\\", "/"):
        checkpoints_template = """
=== CHECKPOINTS TEMPLATE (Script — NO top-level return; NO coin logic) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local folder = workspace:FindFirstChild("Checkpoints")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Checkpoints"
	folder.Parent = workspace
end
local function hookPart(part: BasePart)
	local idx = tonumber(string.match(part.Name, "%d+"))
	if not idx then return end
	part.CanTouch = true
	part.Touched:Connect(function(hit: BasePart)
		local char = hit.Parent
		if not char then return end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then return end
		local current = plr:GetAttribute("Checkpoint") or 0
		if typeof(current) ~= "number" then current = 0 end
		if idx > (current :: number) then
			plr:SetAttribute("Checkpoint", idx)
			plr:SetAttribute("Score", idx * 100)
			Remotes.CheckpointReached:FireClient(plr, idx)
		end
	end)
end
for _, child in ipairs(folder:GetChildren()) do
	if child:IsA("BasePart") then hookPart(child) end
end
folder.ChildAdded:Connect(function(child)
	if child:IsA("BasePart") then hookPart(child) end
end)
local function teleportToCheckpoint(plr: Player, char: Model)
	local idx = plr:GetAttribute("Checkpoint") or 0
	if typeof(idx) ~= "number" or (idx :: number) < 1 then return end
	local cp = folder:FindFirstChild("Checkpoint" .. tostring(idx))
	if not cp or not cp:IsA("BasePart") then return end
	local hrp = char:FindFirstChild("HumanoidRootPart")
	if hrp and hrp:IsA("BasePart") then
		hrp.CFrame = CFrame.new(cp.Position + Vector3.new(0, 5, 0))
	end
end
local function hookCharacter(plr: Player, char: Model)
	task.defer(function() teleportToCheckpoint(plr, char) end)
	local hum = char:WaitForChild("Humanoid") :: Humanoid
	hum.Died:Connect(function()
		task.wait(0.1)
		plr:LoadCharacter()
	end)
end
Players.PlayerAdded:Connect(function(plr)
	plr.CharacterAdded:Connect(function(char) hookCharacter(plr, char) end)
	if plr.Character then hookCharacter(plr, plr.Character) end
end)
for _, plr in ipairs(Players:GetPlayers()) do
	plr.CharacterAdded:Connect(function(char) hookCharacter(plr, char) end)
	if plr.Character then hookCharacter(plr, plr.Character) end
end
-- NEVER Remotes.CoinsCollected (typo). NEVER destroy coins here.
"""
    effects_template = ""
    if task.target_path and "Effects.client.luau" in task.target_path.replace("\\", "/"):
        effects_template = """
=== EFFECTS TEMPLATE (LocalScript — NO top-level return) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local function play(soundId: string, volume: number)
	local ok, err = pcall(function()
		local s = Instance.new("Sound")
		s.SoundId = soundId
		s.Volume = volume
		s.Parent = SoundService
		s:Play()
		s.Ended:Connect(function() s:Destroy() end)
	end)
	if not ok then warn("[Effects] sound skip", err) end
end
local function flash(name: string)
	local gui = Players.LocalPlayer:FindFirstChild("PlayerGui")
	local hud = gui and gui:FindFirstChild("HUD")
	local label = hud and hud:FindFirstChild(name)
	if label and label:IsA("GuiObject") then
		local tw = TweenService:Create(label, TweenInfo.new(0.2), { BackgroundTransparency = 0.1 })
		tw:Play()
		tw.Completed:Connect(function()
			TweenService:Create(label, TweenInfo.new(0.3), { BackgroundTransparency = 0.5 }):Play()
		end)
	end
end
Remotes.CheckpointReached.OnClientEvent:Connect(function()
	play("rbxassetid://9112854440", 0.5)
	flash("CheckpointCount")
end)
if Remotes.CoinCollected then
	Remotes.CoinCollected.OnClientEvent:Connect(function()
		play("rbxassetid://9114224690", 0.4)
		flash("CoinCount")
	end)
end
"""
    generator_template = ""
    if task.target_path and "Generator.server.luau" in task.target_path.replace("\\", "/"):
        generator_template = """
=== GENERATOR RULES (must follow — validator will FAIL otherwise) ===
- ensureFolder(Workspace, "Map"), ensureFolder(Workspace, "Checkpoints"), ensureFolder(Workspace, "Coins")
  — the words Checkpoints and Coins MUST appear (folders created before spawning parts).
- Path Part Name="Path"; destroy Baseplate if present.
- Spawn MUST be exactly: Instance.new("SpawnLocation") — NEVER Instance.new("Part") with Name="SpawnLocation".
- Checkpoint parts Name="Checkpoint"..id under Checkpoints folder; Coin parts under Coins folder.
- Horror look OK (dark Path, neon CP) but folders+SpawnLocation rules are mandatory.
- print "[Generator] map floor ready"
"""
    coins_template = ""
    if task.target_path and "Coins.server.luau" in task.target_path.replace("\\", "/"):
        coins_template = """
=== COINS TEMPLATE (Script — NO top-level return) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local function hook(coin: BasePart)
	coin.CanTouch = true
	coin.Touched:Connect(function(hit: BasePart)
		local char = hit.Parent
		if not char then return end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then return end
		coin:Destroy()
		local n = (plr:GetAttribute("Coins") or 0) + 1
		plr:SetAttribute("Coins", n) -- PLAYER attrs, not character
		Remotes.CoinCollected:FireClient(plr, n)
		Remotes.UpdateLeaderboard:FireAllClients(plr.Name .. ": " .. tostring(n))
	end)
end
local function ensureCoinsFolder(): Folder
	local f = workspace:FindFirstChild("Coins")
	if f and f:IsA("Folder") then return f end
	local created = Instance.new("Folder")
	created.Name = "Coins"
	created.Parent = workspace
	return created
end
local coinsFolder = ensureCoinsFolder()
for _, child in ipairs(coinsFolder:GetChildren()) do
	if child:IsA("BasePart") then hook(child) end
end
coinsFolder.ChildAdded:Connect(function(child)
	if child:IsA("BasePart") then hook(child) end
end)
"""
    levelconfig_template = ""
    if task.target_path and "LevelConfig.luau" in task.target_path.replace("\\", "/"):
        levelconfig_template = """
=== LEVELCONFIG TEMPLATE (ModuleScript — Luau `=` NOT JS `:`) ===
--!strict
return {
	{ id = 1, gap = 50, coins = 5 },
	{ id = 2, gap = 70, coins = 5 },
	{ id = 3, gap = 90, coins = 5 },
	{ id = 4, gap = 110, coins = 5 },
	{ id = 5, gap = 130, coins = 8 },
}
-- Generator does: for i, section in ipairs(LevelConfig) do … section.gap / section.coins
-- NEVER write JavaScript: return { sections: { id: 0 } }
"""
    hud_template = ""
    if task.target_path and "HUD.client.luau" in task.target_path.replace("\\", "/"):
        hud_template = """
=== HUD TEMPLATE (LEFT UI — read PLAYER attrs, never Character attrs) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "HUD"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")
local function makeLabel(name: string, y: number): TextLabel
	local t = Instance.new("TextLabel")
	t.Name = name
	t.Size = UDim2.new(0, 220, 0, 24)
	t.Position = UDim2.new(0, 12, 0, y)
	t.BackgroundTransparency = 0.4
	t.TextColor3 = Color3.new(1, 1, 1)
	t.TextXAlignment = Enum.TextXAlignment.Left
	t.Parent = gui
	return t
end
local timeL = makeLabel("Time", 12)
local cpL = makeLabel("CheckpointCount", 40)
local coinL = makeLabel("CoinCount", 68)
local bestL = makeLabel("BestTime", 96)
local t0 = os.clock()
local function paint()
	-- CRITICAL: attrs live on Player (set by Coins/Checkpoints servers), NOT on Character
	local coins = player:GetAttribute("Coins") or 0
	local cp = player:GetAttribute("Checkpoint") or 0
	local best = player:GetAttribute("BestTime")
	timeL.Text = string.format("Time: %.1f", os.clock() - t0)
	cpL.Text = "CP: " .. tostring(cp)
	coinL.Text = "Coins: " .. tostring(coins)
	bestL.Text = if typeof(best) == "number" and best < math.huge then string.format("Best: %.1f", best) else "Best: --"
end
RunService.RenderStepped:Connect(paint)
Remotes.CheckpointReached.OnClientEvent:Connect(function() paint() end)
Remotes.CoinCollected.OnClientEvent:Connect(function() paint() end)
player.CharacterAdded:Connect(function()
	t0 = os.clock()
	paint() -- do NOT zero Coins/Checkpoint locals; read player attrs
end)
paint()
-- NEVER character:GetAttribute("Coins") — that stays nil and wipes left HUD every frame
"""
    leaderboard_template = ""
    if task.target_path and "Leaderboard.client.luau" in task.target_path.replace("\\", "/"):
        leaderboard_template = """
=== LEADERBOARD TEMPLATE (stub — create GUI; Remotes.UpdateLeaderboard only) ===
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "LeaderboardGui"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")
local label = Instance.new("TextLabel")
label.Name = "LeaderboardLabel"
label.Size = UDim2.new(0, 260, 0, 28)
label.Position = UDim2.new(1, -280, 0, 12)
label.BackgroundTransparency = 0.35
label.TextColor3 = Color3.new(1, 1, 1)
label.Text = "Leaderboard (waiting...)"
label.Parent = gui
if Remotes.UpdateLeaderboard then
	Remotes.UpdateLeaderboard.OnClientEvent:Connect(function(payload)
		label.Text = tostring(payload or "Leaderboard updated")
	end)
end
-- NEVER WaitForChild("LeaderboardFrame"); NEVER invent RequestLeaderboard / LeaderboardUpdated
"""
    void_template = ""
    if task.target_path and "Void.server.luau" in task.target_path.replace("\\", "/"):
        void_template = """
=== VOID RULES ===
Use RunService.Heartbeat: if HumanoidRootPart.Position.Y < -20 then Player:LoadCharacter().
Do NOT use Touched on HRP for void.
"""
    puzzles_template = ""
    if task.target_path and "Puzzles.server.luau" in task.target_path.replace("\\", "/"):
        puzzles_template = """
=== PUZZLES RULES ===
Create PressurePlate + Gate Parts if missing. Touched => open gate. TouchEnded => close.
Never use .Left. Prefer workspace.Puzzles folder.
"""

    # A17: on local Ollama, prefer one-line template hints over full Luau paste
    if local_ollama:
        def _short_tmpl(block: str, hint: str, cap: int = 280) -> str:
            if not block:
                return ""
            # Keep the === TITLE === line + short hint instead of full sample
            first = block.strip().splitlines()[0] if block.strip() else ""
            return f"\n{first}\n{hint}\n"

        remotes_template = _short_tmpl(
            remotes_template, "getOrCreate RemoteEvents; return Remotes table ModuleScript."
        )
        checkpoints_template = _short_tmpl(
            checkpoints_template,
            'Touched+SetAttribute; Died→LoadCharacter; FindFirstChild("Checkpoint"..idx).',
        )
        effects_template = _short_tmpl(effects_template, "LocalScript; OnClientEvent sounds; no top-level return.")
        generator_template = _short_tmpl(
            generator_template,
            'Map/Checkpoints/Coins folders; SpawnLocation; Name="Checkpoint"..id; print section ids.',
        )
        coins_template = _short_tmpl(
            coins_template, "Destroy coin; player attrs; FireClient; ChildAdded hook."
        )
        levelconfig_template = _short_tmpl(
            levelconfig_template, "return { { id = n, gap = g, coins = c }, ... } Luau `=` only."
        )
        hud_template = _short_tmpl(
            hud_template, "ScreenGui; read PLAYER attrs (not Character); CharacterAdded."
        )
        leaderboard_template = _short_tmpl(
            leaderboard_template, "create UI; UpdateLeaderboard only — no LeaderboardFrame."
        )
        qa_template = _short_tmpl(qa_template, "BUGS/SUGGESTIONS/TEST CASES/SCORE sections.") if qa_template else ""

    if local_ollama:
        strict_rules = f"""STRICT (ctx≤2k):
- ONLY this task. <DONE>{task.task_id}</DONE> + <FILE> required when → path.
- task.wait() not wait(); server/client: no top-level return; ModuleScript: return table.
- Checkpoint.."id" (no _); Remotes ModuleScript; LevelConfig Luau `=`; coins Destroy+FireClient.
- Compact code; SEARCH/REPLACE preferred on existing files."""
        token_econ = "TOKEN ECONOMY: minimal comments; only code for THIS task."
    else:
        strict_rules = f"""STRICT RULES:
- Do ONLY this one task. Do not touch other tasks.
- Do NOT block due to task ordering. Prerequisites are already done.
- If task says '-> path/file.md#section', '#' is a section name, NOT part of the filename.
- No stubs, no empty TODOs. Ship playable / readable content.
- NEVER use wait() — always task.wait().
- *.server.luau / *.client.luau MUST NOT end with return.
- *.luau ModuleScripts MUST end with return <table>.
- You MUST include at least one <FILE path="...">...</FILE> when the task has a → path.
- Reply MUST begin with <DONE>{task.task_id}</DONE>. Never output <BLOCKED>.
- NEVER list PlayerRespawn / PlayerRespawned as a BUG. That API is not in this project.
- For Checkpoints: Touched, SetAttribute, FireClient, Died/LoadCharacter — report only what you see.
- FILE path must be the real target (e.g. {task.target_path or "src/..."}), NEVER relative/path.ext.
- Generator: CREATE Map/Path/Spawn (Instance.new); never WaitForChild Map first.
- Generator checkpoint names: "Checkpoint" .. tostring(id) — NEVER "Checkpoint_".
- Remotes: require Gameplay.Remotes ModuleScript; never return a Folder.
- LevelConfig: Luau `id = n` only — NEVER JavaScript `id: n`. return array for ipairs.
- Coins: coin:Destroy(); FireClient(player); FindFirstChild Coins + ChildAdded.
- HUD: create ScreenGui; player.CharacterAdded — never bare characterAdded.
- Leaderboard: create UI; UpdateLeaderboard only — no LeaderboardFrame WaitForChild.
- Void: Heartbeat Y<-20 LoadCharacter. Puzzles: TouchEnded not .Left.
- TOKEN ECONOMY: Do not write excessive comments. Use concise local variable names. Output only the necessary code."""
        token_econ = """TOKEN ECONOMY (local 14B ctx≤4k):
- Do not write excessive comments. Critical one-liners only.
- Use concise local variable names; keep public/contract names stable.
- Output only the necessary code for THIS task.
- Prefer Luau-compact forms; no decorative blank lines."""

    prompt = f"""You are the agent @{owner} inside Quality Forge.
You WRITE the game (Luau / design docs). A human only playtests later.
Follow AGENTS.md. Do the task for real — do not reply NOTE-only when a FILE is required.
{retry_note}
=== AGENTS.md ===
{agents}

=== PROJECT_TZ.md (compact) ===
{tz_compact}

=== Existing project files (relevant) ===
{files}
{skills_block}{assets_block}{feedback}{qa_template}{remotes_template}{checkpoints_template}{effects_template}{generator_template}{coins_template}{levelconfig_template}{hud_template}{leaderboard_template}{void_template}{puzzles_template}
=== YOUR TASK ===
{task.raw.strip()}

{mode_instructions(task, file_exists=bool(prior_snapshot), prefer_diff=True)}

{strict_rules}

{token_econ}

Format:
<DONE>{task.task_id}</DONE>
<NOTE>one short sentence</NOTE>
<FILE path="{task.target_path or "src/server/Example.server.luau"}">
<<<<<<< SEARCH
old lines
=======
new lines
>>>>>>> REPLACE
</FILE>
(or full file content when CREATE / large rewrite)
"""
    # A17 hard fit — NEVER send oversized prompts to Ollama
    if budget is not None:
        prompt, meta = llm_backends.fit_prompt(prompt, int(budget))
        if not meta.get("ok") or llm_backends.estimate_tokens(prompt) > int(budget):
            prompt, meta = llm_backends.fit_prompt(prompt, int(budget))
        llm_backends.assert_prompt_fits(prompt, int(budget))
    return prompt

