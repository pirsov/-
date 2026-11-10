--!strict
-- archetype: client_ui@v1.1 — UI + Remotes:FireServer ok; NEVER DataStore / RunStartedAt
local Players = game:GetService("Players")
local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")
-- Remotes.DonateRequest:FireServer(pack) — server owns DataStore
