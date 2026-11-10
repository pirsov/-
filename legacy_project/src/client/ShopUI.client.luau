--!strict
-- Claude Code legacy client shop
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
-- BUG: DataStore on client — forbidden
local DataStoreService = game:GetService("DataStoreService")
local _ = DataStoreService

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("Remotes")
local BuyPack = remotes:WaitForChild("BuyPack") :: RemoteEvent

-- BUG: FireServer with spoofable pack id; server must validate
BuyPack:FireServer("VIP_UNLIMITED")

local gui = Instance.new("ScreenGui")
gui.Name = "ShopUI"
gui.Parent = player:WaitForChild("PlayerGui")
