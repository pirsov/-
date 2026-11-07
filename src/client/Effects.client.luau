--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SoundService = game:GetService("SoundService")

local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

Remotes.CheckpointReached.OnClientEvent:Connect(function()
	local s = Instance.new("Sound")
	s.SoundId = "rbxassetid://9112854440"
	s.Volume = 0.5
	s.Parent = SoundService
	s:Play()
	s.Ended:Connect(function()
		s:Destroy()
	end)
end)
