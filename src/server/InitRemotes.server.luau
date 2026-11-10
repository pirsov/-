--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

print("[InitRemotes] ready")

-- Register remotes for coins and leaderboard updates
Remotes.CoinCollected = Instance.new("RemoteEvent")
Remotes.CoinCollected.Name = "CoinCollected"
Remotes.CoinCollected.Parent = Remotes

Remotes.UpdateLeaderboard = Instance.new("RemoteEvent")
Remotes.UpdateLeaderboard.Name = "UpdateLeaderboard"
Remotes.UpdateLeaderboard.Parent = Remotes
