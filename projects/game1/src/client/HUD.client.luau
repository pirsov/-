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

local coins = 0
local cp = 0
local t0 = os.clock()
local best = math.huge

local function paint()
    timeL.Text = string.format("Time: %.1f", os.clock() - t0)
    cpL.Text = "CP: " .. tostring(cp)
    coinL.Text = "Coins: " .. tostring(coins)
    bestL.Text = if best < math.huge then string.format("Best: %.1f", best) else "Best: --"
end

local function updateAttributes()
    local char = player.Character
    if char then
        coins = char:GetAttribute("Coins") or 0
        cp = char:GetAttribute("Checkpoint") or 0
    end
    paint()
end

RunService.RenderStepped:Connect(updateAttributes)

Remotes.CheckpointReached.OnClientEvent:Connect(function(idx)
    cp = tonumber(idx) or cp
    paint()
end)

Remotes.CoinCollected.OnClientEvent:Connect(function()
    coins += 1
    paint()
end)

player.CharacterAdded:Connect(function()
    t0 = os.clock()
    coins = 0
    cp = 0
    updateAttributes()
end)

paint()
