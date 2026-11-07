--!strict
-- Ensure Remotes folder + events exist before any client WaitForChild("Remotes").
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
print("[InitRemotes] ready:", Remotes.CheckpointReached ~= nil, Remotes.CoinCollected ~= nil)
