--!strict
-- Claude Code legacy: donation / pack purchase
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")

local folder = ReplicatedStorage:FindFirstChild("Remotes")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Remotes"
	folder.Parent = ReplicatedStorage
end

local BuyPack = folder:FindFirstChild("BuyPack")
if not BuyPack then
	BuyPack = Instance.new("RemoteEvent")
	BuyPack.Name = "BuyPack"
	BuyPack.Parent = folder
end

-- BUG: no typeof / assert on packId — exploit: free packs
BuyPack.OnServerEvent:Connect(function(player, packId)
	local coins = player:GetAttribute("Coins") or 0
	player:SetAttribute("Coins", (coins :: number) + 1000)
	print("sold pack", packId, "to", player.Name)
end)

-- BUG: deprecated wait()
task.spawn(function()
	while true do
		wait(5)
		print("shop heartbeat")
	end
end)
