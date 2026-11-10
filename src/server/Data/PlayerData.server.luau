--!strict
-- PlayerData: attrs on Player only. BestTime = float seconds (0 = none).
-- Cloud Fallback rewrite (F3). Studio only — no DataStore.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local function get_best_time(player: Player): number
	local v = player:GetAttribute("BestTime")
	if typeof(v) ~= "number" then
		return 0
	end
	return v :: number
end

-- Only write when new is a positive finish time better than current (or first record).
local function set_best_time(player: Player, val: number)
	if typeof(val) ~= "number" or val <= 0 then
		return
	end
	local current = get_best_time(player)
	if current == 0 or val < current then
		player:SetAttribute("BestTime", val)
	end
end

local function initAttrs(player: Player)
	if player:GetAttribute("Score") == nil then
		player:SetAttribute("Score", 0)
	end
	if player:GetAttribute("Checkpoint") == nil then
		player:SetAttribute("Checkpoint", 0)
	end
	if player:GetAttribute("Coins") == nil then
		player:SetAttribute("Coins", 0)
	end
	-- BestTime default 0 (NOT math.huge) so HUD shows Best: --
	local best = player:GetAttribute("BestTime")
	if typeof(best) ~= "number" or (best :: number) < 0 or (best :: number) == math.huge then
		player:SetAttribute("BestTime", 0)
	end
end

local function onPlayerAdded(player: Player)
	if not RunService:IsStudio() then
		-- Live DataStore path deferred; Studio contract only for now
		initAttrs(player)
		return
	end
	initAttrs(player)
end

local function onPlayerRemoving(player: Player)
	if not RunService:IsStudio() then
		return
	end
	local started = player:GetAttribute("RunStartedAt")
	if typeof(started) == "number" then
		local elapsed = os.clock() - (started :: number)
		set_best_time(player, elapsed)
	end
	-- Persist attrs already live on Player in Studio
	player:SetAttribute("Score", player:GetAttribute("Score") or 0)
	player:SetAttribute("Checkpoint", player:GetAttribute("Checkpoint") or 0)
	player:SetAttribute("Coins", player:GetAttribute("Coins") or 0)
	player:SetAttribute("BestTime", get_best_time(player))
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(onPlayerRemoving)

for _, player in ipairs(Players:GetPlayers()) do
	task.defer(onPlayerAdded, player)
end
