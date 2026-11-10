--!strict
-- system.player_save — A10.1 E2E
-- archetype: datastore_service@v1
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local store = DataStoreService:GetDataStore("PlayerSave_v1")

local function keyFor(player: Player): string
	return "p_" .. tostring(player.UserId)
end

local function get_player_coins(player: Player): number
	local v = player:GetAttribute("Coins")
	if typeof(v) ~= "number" then
		return 0
	end
	return v :: number
end

local function loadPlayer(player: Player)
	local ok, data = pcall(function()
		return store:GetAsync(keyFor(player))
	end)
	local coins = 0
	if ok and typeof(data) == "table" and typeof((data :: any).Coins) == "number" then
		coins = (data :: any).Coins
	end
	player:SetAttribute("Coins", coins)
end

local function savePlayer(player: Player)
	local coins = get_player_coins(player)
	pcall(function()
		store:SetAsync(keyFor(player), { Coins = coins })
	end)
end

Players.PlayerAdded:Connect(function(player)
	loadPlayer(player)
end)

Players.PlayerRemoving:Connect(function(player)
	savePlayer(player)
end)
