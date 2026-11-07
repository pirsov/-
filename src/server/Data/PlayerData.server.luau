--!strict
local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")

local playerDataStore = DataStoreService:GetDataStore("PlayerData_v2")

local function savePlayerData(player: Player)
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
	local success, result = pcall(function()
		return playerDataStore:GetAsync(player.UserId)
	end)
	if success and typeof(result) == "table" then
		player:SetAttribute("Score", result.Score or 0)
		player:SetAttribute("Checkpoint", result.Checkpoint or 0)
		player:SetAttribute("Coins", result.Coins or 0)
		player:SetAttribute("BestTime", result.BestTime or 0)
	else
		if not success then
			warn("Failed to load player data: " .. tostring(result))
		end
		player:SetAttribute("Score", 0)
		player:SetAttribute("Checkpoint", 0)
		player:SetAttribute("Coins", 0)
		player:SetAttribute("BestTime", 0)
	end
	player:SetAttribute("RunStartedAt", os.clock())

	task.spawn(function()
		while player.Parent do
			task.wait(60)
			savePlayerData(player)
		end
	end)
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
