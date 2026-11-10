--!strict
-- HUD + I012: on death/respawn reset Time only; Best/Coins/CP stay on player attrs.
-- NEVER character:GetAttribute. Best: -- if nil/<=0 else %.1f.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "HUD"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local function makeLabel(name: string, y: number): TextLabel
	local t = Instance.new("TextLabel")
	t.Name = name
	t.Size = UDim2.new(0, 220, 0, 24)
	t.Position = UDim2.new(0, 12, 0, y)
	t.BackgroundTransparency = 0.4
	t.TextColor3 = Color3.new(1, 1, 1)
	t.TextXAlignment = Enum.TextXAlignment.Left
	t.Parent = gui
	return t
end

local timeL = makeLabel("Time", 12)
local cpL = makeLabel("CheckpointCount", 40)
local coinL = makeLabel("CoinCount", 68)
local bestL = makeLabel("BestTime", 96)

for _, label in ipairs({ timeL, cpL, coinL, bestL }) do
	label.TextStrokeTransparency = 0
	label.TextStrokeColor3 = Color3.new(0, 1, 1)
end

-- Local run clock (client os.clock ≠ server; never assign RunStartedAt absolute)
local t0 = os.clock()

local function resetRunClock()
	t0 = os.clock()
end

local function formatBest(best: any): string
	if typeof(best) ~= "number" then
		return "Best: --"
	end
	local n = best :: number
	if n <= 0 or n == math.huge then
		return "Best: --"
	end
	return string.format("Best: %.1f", n)
end

local function paint()
	-- Stable labels: Coins/CP/Best from Player attrs (survive death)
	local coins = player:GetAttribute("Coins") or 0
	local cp = player:GetAttribute("Checkpoint") or 0
	local best = player:GetAttribute("BestTime")
	timeL.Text = string.format("Time: %.1f", os.clock() - t0)
	cpL.Text = "CP: " .. tostring(cp)
	coinL.Text = "Coins: " .. tostring(coins)
	bestL.Text = formatBest(best)
end

RunService.RenderStepped:Connect(paint)
Remotes.CheckpointReached.OnClientEvent:Connect(function()
	paint()
end)
Remotes.CoinCollected.OnClientEvent:Connect(function()
	paint()
end)

-- I012: death/respawn → new run Time; do NOT zero Coins/Checkpoint/Best
player.CharacterAdded:Connect(function()
	resetRunClock()
	paint()
end)

-- Server also stamps RunStartedAt on respawn — sync display clock without mixing clocks
player:GetAttributeChangedSignal("RunStartedAt"):Connect(function()
	resetRunClock()
	paint()
end)

paint()
