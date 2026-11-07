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

	task.spawn(function()
		while player.Parent do
			task.wait(60)
			savePlayerData(player)
		end
	end)
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(savePlayerData)

for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(onPlayerAdded, player)
end
