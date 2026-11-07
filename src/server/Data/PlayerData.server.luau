--!strict
local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")

local playerDataStore = DataStoreService:GetDataStore("PlayerData")

local function savePlayerData(player: Player)
	local success, result = pcall(function()
		local score = player:GetAttribute("Score")
		local checkpoint = player:GetAttribute("Checkpoint")
		playerDataStore:SetAsync(player.UserId, {
			Score = score,
			Checkpoint = checkpoint,
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
	else
		if not success then
			warn("Failed to load player data: " .. tostring(result))
		end
		player:SetAttribute("Score", 0)
		player:SetAttribute("Checkpoint", 0)
	end

	task.spawn(function()
		while player.Parent do
			task.wait(60)
			savePlayerData(player)
		end
	end)
end

local function onPlayerRemoving(player: Player)
	savePlayerData(player)
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(onPlayerRemoving)

for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(onPlayerAdded, player)
end
