--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

local function hook(coin: BasePart)
	coin.CanTouch = true
	coin.Touched:Connect(function(hit: BasePart)
		local char = hit.Parent
		if not char then return end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then return end
		coin:Destroy()
		local n = (plr:GetAttribute("Coins") or 0) + 1
		plr:SetAttribute("Coins", n) -- PLAYER attrs, not character
		Remotes.CoinCollected:FireClient(plr, n)
		Remotes.UpdateLeaderboard:FireAllClients(plr.Name .. ": " .. tostring(n))
	end)
end

local function ensureCoinsFolder(): Folder
	local f = workspace:FindFirstChild("Coins")
	if f and f:IsA("Folder") then return f end
	local created = Instance.new("Folder")
	created.Name = "Coins"
	created.Parent = workspace
	return created
end

local coinsFolder = ensureCoinsFolder()
for _, child in ipairs(coinsFolder:GetChildren()) do
	if child:IsA("BasePart") then hook(child) end
end

coinsFolder.ChildAdded:Connect(function(child)
	if child:IsA("BasePart") then hook(child) end
end)
