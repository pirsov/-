--!strict
-- Claude Code legacy: coin persistence (intentionally fragile)
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local store = DataStoreService:GetDataStore("ClaudeCoins_v1")

local function loadCoins(player: Player)
	-- BUG: no pcall — DataStore outage kills the script
	local data = store:GetAsync("u_" .. player.UserId)
	local coins = if typeof(data) == "number" then data else 0
	player:SetAttribute("Coins", coins)
end

local function saveCoins(player: Player)
	local coins = player:GetAttribute("Coins") or 0
	-- BUG: SetAsync without pcall
	store:SetAsync("u_" .. player.UserId, coins)
end

Players.PlayerAdded:Connect(function(player)
	loadCoins(player)
end)

Players.PlayerRemoving:Connect(function(player)
	saveCoins(player)
end)

-- BUG: tight loop freezes server (Claude "keepalive" pattern)
while true do
	for _, p in ipairs(Players:GetPlayers()) do
		saveCoins(p)
	end
end
