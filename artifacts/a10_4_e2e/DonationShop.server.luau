--!strict
-- system.donation_shop server save — A10.4
-- archetype: datastore_service@v1
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local store = DataStoreService:GetDataStore("DonationShop_v1")
local Remotes = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Gameplay"):WaitForChild("Remotes"))

local PACKS = { [10] = 100, [50] = 600, [100] = 1500 } -- Robux stub → coins

local function keyFor(player: Player): string
	return "donate_" .. tostring(player.UserId)
end

local function coinsOf(player: Player): number
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
	Remotes.CoinSync:FireClient(player, coins)
end

local function savePlayer(player: Player)
	local coins = coinsOf(player)
	pcall(function()
		store:SetAsync(keyFor(player), { Coins = coins })
	end)
	Remotes.SaveAck:FireClient(player, true)
end

Remotes.DonateRequest.OnServerEvent:Connect(function(player: Player, pack: number)
	if typeof(pack) ~= "number" then
		return
	end
	local add = PACKS[pack]
	if not add then
		return
	end
	player:SetAttribute("Coins", coinsOf(player) + add)
	Remotes.CoinSync:FireClient(player, coinsOf(player))
	savePlayer(player)
end)

Players.PlayerAdded:Connect(loadPlayer)
Players.PlayerRemoving:Connect(savePlayer)
