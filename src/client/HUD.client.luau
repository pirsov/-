local cpLabel = Instance.new("TextLabel")
cpLabel.Name = "CheckpointCount"
cpLabel.Text = "CP: 0"
cpLabel.Size = UDim2.new(0, 200, 0, 40)
cpLabel.Position = UDim2.new(0.5, -100, 0, 60)
cpLabel.BackgroundTransparency = 0.5
cpLabel.TextColor3 = Color3.new(1, 1, 1)
cpLabel.TextScaled = true
cpLabel.Parent = screen

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

Remotes.CheckpointReached.OnClientEvent:Connect(function(idx)
    cpLabel.Text = "CP: " .. idx
end)