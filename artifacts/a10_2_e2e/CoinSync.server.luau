--!strict
-- system.coin_sync server — A10.2 E2E
-- archetype: server_script@v1
-- Pushes player Coins attr to client via CoinSync (no DataStore here).
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Gameplay"):WaitForChild("Remotes"))

local function coinsOf(player: Player): number
	local v = player:GetAttribute("Coins")
	if typeof(v) ~= "number" then
		return 0
	end
	return v :: number
end

local function pushCoins(player: Player)
	Remotes.CoinSync:FireClient(player, coinsOf(player))
end

Players.PlayerAdded:Connect(function(player)
	if player:GetAttribute("Coins") == nil then
		player:SetAttribute("Coins", 0)
	end
	pushCoins(player)
	player:GetAttributeChangedSignal("Coins"):Connect(function()
		pushCoins(player)
	end)
end)

for _, player in Players:GetPlayers() do
	pushCoins(player)
end
