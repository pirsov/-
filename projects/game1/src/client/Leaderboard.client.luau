--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "LeaderboardGui"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")
local label = Instance.new("TextLabel")
label.Name = "LeaderboardLabel"
label.Size = UDim2.new(0, 260, 0, 28)
label.Position = UDim2.new(1, -280, 0, 12)
label.BackgroundTransparency = 0.35
label.TextColor3 = Color3.new(1, 1, 1)
label.Text = "Leaderboard (waiting...)"
label.Parent = gui

if Remotes.UpdateLeaderboard then
	Remotes.UpdateLeaderboard.OnClientEvent:Connect(function(payload)
		label.Text = tostring(payload or "Leaderboard updated")
	end)
end
