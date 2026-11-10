--!strict
local Players = game:GetService("Players")
local player = Players.LocalPlayer

local gui = Instance.new("ScreenGui")
gui.Name = "CoinHUD"
gui.Parent = player:WaitForChild("PlayerGui")

local label = Instance.new("TextLabel")
label.Size = UDim2.fromScale(0.2, 0.05)
label.Parent = gui

player:GetAttributeChangedSignal("Coins"):Connect(function()
	label.Text = "Coins: " .. tostring(player:GetAttribute("Coins") or 0)
end)
