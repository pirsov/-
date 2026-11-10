--!strict
-- archetype: datastore_service@v1
-- Server-only PlayerSave: pcall around GetAsync/SetAsync; attrs on Player; never UI.
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local store = DataStoreService:GetDataStore("PlayerSave_v1")

local function key(player: Player): string
	return "p_" .. tostring(player.UserId)
end

local function loadPlayer(player: Player)
	local ok, data = pcall(function()
		return store:GetAsync(key(player))
	end)
	local coins = 0
	if ok and typeof(data) == "table" and typeof(data.Coins) == "number" then
		coins = data.Coins
	end
	player:SetAttribute("Coins", coins)
end

local function savePlayer(player: Player)
	local coins = player:GetAttribute("Coins")
	if typeof(coins) ~= "number" then
		coins = 0
	end
	pcall(function()
		store:SetAsync(key(player), { Coins = coins :: number })
	end)
end

Players.PlayerAdded:Connect(loadPlayer)
Players.PlayerRemoving:Connect(savePlayer)
