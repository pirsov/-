--!strict
-- system.coin_sync client HUD — A10.2 E2E
-- archetype: client_ui@v1
-- Listens CoinSync RemoteEvent only — NEVER DataStoreService.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local player = Players.LocalPlayer
local Remotes = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Gameplay"):WaitForChild("Remotes"))

local gui = Instance.new("ScreenGui")
gui.Name = "CoinHUD"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local label = Instance.new("TextLabel")
label.Name = "CoinsLabel"
label.Size = UDim2.new(0, 200, 0, 28)
label.Position = UDim2.new(0, 12, 0, 12)
label.BackgroundTransparency = 0.35
label.TextColor3 = Color3.new(1, 1, 1)
label.Text = "Coins: 0"
label.Parent = gui

local function paint(n: number)
	label.Text = string.format("Coins: %d", n)
end

Remotes.CoinSync.OnClientEvent:Connect(function(amount: number)
	if typeof(amount) == "number" then
		paint(amount)
	end
end)

-- Fallback paint from attr until first CoinSync
local v = player:GetAttribute("Coins")
if typeof(v) == "number" then
	paint(v :: number)
end
