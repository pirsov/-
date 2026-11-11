--!strict
-- archetype: network_remote@v1.1 — whitelist only; no DataStore/UI
-- Folder stays in `folder`; Remotes is ALWAYS a TABLE of RemoteEvent refs.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local folder = ReplicatedStorage:FindFirstChild("Remotes")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Remotes"
	folder.Parent = ReplicatedStorage
end
local function getOrCreate(name: string): RemoteEvent
	local r = folder:FindFirstChild(name)
	if not r then
		r = Instance.new("RemoteEvent")
		r.Name = name
		r.Parent = folder
	end
	return r :: RemoteEvent
end
-- CoinSync = Server→Client coins; DonateRequest = Client→Server; SaveAck = save ok
local Remotes = {
	Checkpoint = getOrCreate("Checkpoint"),
	CheckpointReached = getOrCreate("CheckpointReached"),
	UpdateLeaderboard = getOrCreate("UpdateLeaderboard"),
	CoinCollected = getOrCreate("CoinCollected"),
	CoinSync = getOrCreate("CoinSync"),
	DonateRequest = getOrCreate("DonateRequest"),
	SaveAck = getOrCreate("SaveAck"),
}
return Remotes
