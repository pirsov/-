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
_FALLBACK_ROLE = {"model": "qwen2.5-coder:14b-4k", "ctx": 4096, "predict": 4096}
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
    """Cloud 1M-ctx: large. Ollama on 6GB VRAM: keep prompt small so 4k ctx has room to write."""
    try:
        from . import llm

        be = llm.backend_name()
        if be == "spacebunny":
            return int(SPACEBUNNY_CFG.get("file_budget") or 180_000)
        if be == "openrouter":
            return int(OPENROUTER_CFG.get("file_budget") or 180_000)
        ollama_cfg = dict(_CFG.get("ollama") or {})
        return int(ollama_cfg.get("file_budget") or 12_000)
    except Exception:
        pass
    return 12_000


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


def mode_instructions(task: Task) -> str:
    if task.mode == WriteMode.APPEND:
        return (
            "WRITE MODE = APPEND.\n"
            "- Return ONLY the new lines to append.\n"
            "- Do NOT repeat existing file content.\n"
            "- Do NOT rewrite the whole file.\n"
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


def build_prompt(
    root: Path,
    owner: str,
    task: Task,
    *,
    attempt: int = 1,
    validator_feedback: Optional[str] = None,
    prior_snapshot: Optional[str] = None,
    repair_draft: Optional[str] = None,
) -> str:
    agents = extract_agent_section((root / "AGENTS.md").read_text(encoding="utf-8"), owner)
    tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
    tz_lines = tz.splitlines()
    compact: List[str] = []
    for i, line in enumerate(tz_lines):
        if i < 12 or line.startswith("#") or line.startswith("##") or "- [ ]" in line:
            compact.append(line)
        elif "- [x]" in line or "- [-]" in line:
            compact.append(line)
    tz_compact = "\n".join(compact)
    files = render_files(relevant_paths(root, task, owner), root)

    feedback = ""
    if validator_feedback:
        feedback = f"\n=== VALIDATOR FEEDBACK (fix ONLY these issues) ===\n{validator_feedback}\n"
    if repair_draft:
        feedback += (
            "\n=== REPAIR MODE ===\n"
            "Below is YOUR previous draft (almost done). Do NOT rewrite from scratch.\n"
            "Change the minimum lines needed to fix the validator errors "
            "(e.g. one wrong Roblox API call, a missing Name=\"Path\", Checkpoint_ → Checkpoint..id).\n"
            "Return the FULL file with those small fixes applied.\n"
            f"{repair_draft}\n"
        )
    elif prior_snapshot and task.mode == WriteMode.APPEND:
        feedback += (
            f"\n=== CURRENT FILE CONTENT (append AFTER this, do not repeat) ===\n"
            f"{prior_snapshot}\n"
        )
    elif prior_snapshot and task.mode in {WriteMode.REWRITE, WriteMode.CREATE}:
        feedback += (
            "\n=== BASELINE FILE (REWRITE from THIS — do not invent a new architecture) ===\n"
            "Preserve: Map folder, Name=\"Path\" floor, SpawnPlaza, SpawnLocation, "
            'checkpoint Name = "Checkpoint" .. tostring(id) (NO underscore), coins, print section ids.\n'
            "Only apply the task delta (e.g. add Obstacle parts).\n"
            f"{prior_snapshot}\n"
        )

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
=== GENERATOR RULES (must follow) ===
- CREATE folders with Instance.new — never WaitForChild("Map") before creating it.
- ensureFolder("Map"), ensureFolder("Checkpoints"), ensureFolder("Coins").
- Path Part Name="Path"; destroy Baseplate.
- Spawn MUST be: local s = Instance.new("SpawnLocation") — NOT Instance.new("Part") renamed.
- Checkpoints green Neon; Coins gold; obstacles Y on Path (~6); print "[Generator] map floor ready".
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

    return f"""You are the agent @{owner} inside Quality Forge.
You WRITE the game (Luau / design docs). A human only playtests later.
Follow AGENTS.md. Do the task for real — do not reply NOTE-only when a FILE is required.
{retry_note}
=== AGENTS.md ===
{agents}

=== PROJECT_TZ.md (compact) ===
{tz_compact}

=== Existing project files (relevant) ===
{files}
{feedback}{qa_template}{remotes_template}{checkpoints_template}{effects_template}{generator_template}{coins_template}{levelconfig_template}{hud_template}{leaderboard_template}{void_template}{puzzles_template}
=== YOUR TASK ===
{task.raw.strip()}

{mode_instructions(task)}

STRICT RULES:
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

Format:
<DONE>{task.task_id}</DONE>
<NOTE>one short sentence</NOTE>
<FILE path="{task.target_path or "src/server/Example.server.luau"}">
file content
</FILE>
"""
