--!strict
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

-- Neon styling
for _, label in ipairs({timeL, cpL, coinL, bestL}) do
	label.TextStrokeTransparency = 0
	label.TextStrokeColor3 = Color3.new(0, 1, 1) -- Neon blue
end

local t0 = os.clock()

local function paint()
	-- CRITICAL: attrs live on Player (set by Coins/Checkpoints servers), NOT on Character
	local coins = player:GetAttribute("Coins") or 0
	local cp = player:GetAttribute("Checkpoint") or 0
	local best = player:GetAttribute("BestTime")
	timeL.Text = string.format("Time: %.1f", os.clock() - t0)
	cpL.Text = "CP: " .. tostring(cp)
	coinL.Text = "Coins: " .. tostring(coins)
	bestL.Text = if typeof(best) == "number" and best < math.huge then string.format("Best: %.1f", best) else "Best: --"
end

RunService.RenderStepped:Connect(paint)
Remotes.CheckpointReached.OnClientEvent:Connect(function() paint() end)
Remotes.CoinCollected.OnClientEvent:Connect(function() paint() end)
player.CharacterAdded:Connect(function()
	t0 = os.clock()
	paint() -- do NOT zero Coins/Checkpoint locals; read player attrs
end)

paint()
-- NEVER character:GetAttribute("Coins") — that stays nil and wipes left HUD every frame
