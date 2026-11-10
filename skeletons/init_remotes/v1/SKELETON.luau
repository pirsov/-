--!strict
-- archetype: init_remotes@v1 — bootstrap Remotes only (no Player/Workspace mandate)
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
-- TODO: ensure RemoteEvents exist via getOrCreate / Instance.new; print ready; no top-level return
print("[InitRemotes] ready")
local _ = Remotes
