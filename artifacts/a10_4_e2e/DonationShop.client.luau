--!strict
-- system.donation_shop client UI — A10.4
-- archetype: client_ui@v1
-- FireServer DonateRequest only — NEVER DataStore / RunStartedAt
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local player = Players.LocalPlayer
local Remotes = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Gameplay"):WaitForChild("Remotes"))

local gui = Instance.new("ScreenGui")
gui.Name = "DonationShop"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local label = Instance.new("TextLabel")
label.Name = "CoinsLabel"
label.Size = UDim2.new(0, 220, 0, 28)
label.Position = UDim2.new(1, -232, 0, 12)
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

local packs = { 10, 50, 100 }
for i, pack in ipairs(packs) do
	local btn = Instance.new("TextButton")
	btn.Name = "Buy" .. tostring(pack)
	btn.Size = UDim2.new(0, 220, 0, 28)
	btn.Position = UDim2.new(1, -232, 0, 12 + i * 32)
	btn.Text = string.format("Donate %d", pack)
	btn.Parent = gui
	btn.MouseButton1Click:Connect(function()
		Remotes.DonateRequest:FireServer(pack)
	end)
end

local v = player:GetAttribute("Coins")
if typeof(v) == "number" then
	paint(v :: number)
end
