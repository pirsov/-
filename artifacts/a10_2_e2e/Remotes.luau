--!strict
-- system.coin_sync Remotes — A10.2 E2E
-- archetype: network_remote@v1.1
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local folder = ReplicatedStorage:FindFirstChild("Remotes") or Instance.new("Folder")
folder.Name = "Remotes"
folder.Parent = ReplicatedStorage

local function getOrCreate(name: string): RemoteEvent
	local r = folder:FindFirstChild(name)
	if not r then
		r = Instance.new("RemoteEvent")
		r.Name = name
		r.Parent = folder
	end
	return r :: RemoteEvent
end

local Remotes = {
	CheckpointReached = getOrCreate("CheckpointReached"),
	CoinCollected = getOrCreate("CoinCollected"),
	CoinSync = getOrCreate("CoinSync"),
	DonateRequest = getOrCreate("DonateRequest"),
	SaveAck = getOrCreate("SaveAck"),
}
return Remotes
