--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local gui = player:WaitForChild("PlayerGui")

local screen = Instance.new("ScreenGui")
screen.Name = "LeaderboardGui"
screen.ResetOnSpawn = false
screen.Parent = gui

local label = Instance.new("TextLabel")
label.Name = "Leaderboard"
label.Size = UDim2.new(0, 220, 0, 120)
label.Position = UDim2.new(0, 10, 0.5, -60)
label.BackgroundTransparency = 0.4
label.BackgroundColor3 = Color3.fromRGB(15, 15, 15)
label.TextColor3 = Color3.new(1, 1, 1)
label.TextXAlignment = Enum.TextXAlignment.Left
label.TextYAlignment = Enum.TextYAlignment.Top
label.TextScaled = false
label.TextSize = 16
label.Text = "Leaderboard\n(waiting...)"
label.Parent = screen

local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
if Remotes.UpdateLeaderboard then
	Remotes.UpdateLeaderboard.OnClientEvent:Connect(function(payload)
		if typeof(payload) == "string" then
			label.Text = "Leaderboard\n" .. payload
		elseif typeof(payload) == "table" then
			local lines = { "Leaderboard" }
			for i, row in ipairs(payload) do
				table.insert(lines, string.format("%d. %s", i, tostring(row)))
			end
			label.Text = table.concat(lines, "\n")
		end
	end)
end
