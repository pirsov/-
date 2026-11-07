--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local gui = player:WaitForChild("PlayerGui")

local screen = Instance.new("ScreenGui")
screen.Name = "HUD"
screen.ResetOnSpawn = false
screen.Parent = gui

local timer = Instance.new("TextLabel")
timer.Name = "Timer"
timer.Text = "Time: 0s"
timer.Size = UDim2.new(0, 200, 0, 40)
timer.Position = UDim2.new(0.5, -100, 0, 10)
timer.BackgroundTransparency = 0.5
timer.BackgroundColor3 = Color3.fromRGB(20, 20, 20)
timer.TextColor3 = Color3.new(1, 1, 1)
timer.TextScaled = true
timer.Parent = screen

local cpLabel = Instance.new("TextLabel")
cpLabel.Name = "CheckpointCount"
cpLabel.Text = "CP: 0"
cpLabel.Size = UDim2.new(0, 200, 0, 40)
cpLabel.Position = UDim2.new(0.5, -100, 0, 60)
cpLabel.BackgroundTransparency = 0.5
cpLabel.BackgroundColor3 = Color3.fromRGB(20, 20, 20)
cpLabel.TextColor3 = Color3.new(1, 1, 1)
cpLabel.TextScaled = true
cpLabel.Parent = screen

task.spawn(function()
	local start = tick()
	while true do
		task.wait(1)
		timer.Text = string.format("Time: %ds", math.floor(tick() - start))
	end
end)

local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
Remotes.CheckpointReached.OnClientEvent:Connect(function(idx)
	cpLabel.Text = "CP: " .. tostring(idx)
end)
