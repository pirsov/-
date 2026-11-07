--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local gui = player:WaitForChild("PlayerGui")

local screen = Instance.new("ScreenGui")
screen.Name = "HUD"
screen.ResetOnSpawn = false
screen.Parent = gui

local function makeLabel(name: string, text: string, y: number): TextLabel
	local label = Instance.new("TextLabel")
	label.Name = name
	label.Text = text
	label.Size = UDim2.new(0, 200, 0, 40)
	label.Position = UDim2.new(0.5, -100, 0, y)
	label.BackgroundTransparency = 0.5
	label.BackgroundColor3 = Color3.fromRGB(20, 20, 20)
	label.TextColor3 = Color3.new(1, 1, 1)
	label.TextScaled = true
	label.Parent = screen
	return label
end

local timer = makeLabel("Timer", "Time: 0s", 10)
local cpLabel = makeLabel("CheckpointCount", "CP: 0", 60)
local coinLabel = makeLabel("CoinCount", "Coins: 0", 110)
local bestLabel = makeLabel("BestTime", "Best: --", 160)

task.spawn(function()
	local start = tick()
	while true do
		task.wait(1)
		timer.Text = string.format("Time: %ds", math.floor(tick() - start))
		local best = player:GetAttribute("BestTime")
		if typeof(best) == "number" and (best :: number) > 0 then
			bestLabel.Text = string.format("Best: %ds", math.floor(best :: number))
		end
	end
end)

local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
Remotes.CheckpointReached.OnClientEvent:Connect(function(idx)
	cpLabel.Text = "CP: " .. tostring(idx)
end)
if Remotes.CoinCollected then
	Remotes.CoinCollected.OnClientEvent:Connect(function(total)
		coinLabel.Text = "Coins: " .. tostring(total)
	end)
end
