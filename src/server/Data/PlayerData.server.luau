--!strict
-- Studio playtests: never call GetDataStore (unpublished places hard-error in Output).
-- Live servers: pcall + persist Score/Checkpoint/Coins/BestTime.
local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local playerDataStore: DataStore? = nil
local allowStudioStore = game:GetAttribute("EnableStudioDataStore") == true

if (not RunService:IsStudio()) or allowStudioStore then
	local ok, store = pcall(function()
		return DataStoreService:GetDataStore("PlayerData_v2")
	end)
	if ok then
		playerDataStore = store
	else
		warn("[PlayerData] DataStore unavailable — session attributes only. " .. tostring(store))
	end
else
	print("[PlayerData] Studio offline mode — no DataStore calls (playtest OK without publish).")
end

local function savePlayerData(player: Player)
	if not playerDataStore then
		return
	end
	local success, result = pcall(function()
		playerDataStore:SetAsync(player.UserId, {
			Score = player:GetAttribute("Score"),
			Checkpoint = player:GetAttribute("Checkpoint"),
			Coins = player:GetAttribute("Coins"),
			BestTime = player:GetAttribute("BestTime"),
		})
	end)
	if not success then
		warn("Failed to save player data: " .. tostring(result))
	end
end

local function updateBestTime(player: Player)
	local started = player:GetAttribute("RunStartedAt")
	if typeof(started) ~= "number" then
		return
	end
	local elapsed = os.clock() - (started :: number)
	if elapsed < 0 then
		return
	end
	local best = player:GetAttribute("BestTime")
	if typeof(best) ~= "number" then
		best = 0
	end
	if (best :: number) == 0 or elapsed < (best :: number) then
		player:SetAttribute("BestTime", elapsed)
	end
end

local function onPlayerAdded(player: Player)
	local loaded = false
	if playerDataStore then
		local success, result = pcall(function()
			return playerDataStore:GetAsync(player.UserId)
		end)
		if success and typeof(result) == "table" then
			player:SetAttribute("Score", result.Score or 0)
			player:SetAttribute("Checkpoint", result.Checkpoint or 0)
			player:SetAttribute("Coins", result.Coins or 0)
			player:SetAttribute("BestTime", result.BestTime or 0)
			loaded = true
		elseif not success then
			warn("Failed to load player data: " .. tostring(result))
		end
	end
	if not loaded then
		player:SetAttribute("Score", 0)
		player:SetAttribute("Checkpoint", 0)
		player:SetAttribute("Coins", 0)
		player:SetAttribute("BestTime", 0)
	end
	player:SetAttribute("RunStartedAt", os.clock())

	if playerDataStore then
		task.spawn(function()
			while player.Parent do
				task.wait(60)
				savePlayerData(player)
			end
		end)
	end
end

local function onPlayerRemoving(player: Player)
	updateBestTime(player)
	savePlayerData(player)
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(onPlayerRemoving)

for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(onPlayerAdded, player)
end
