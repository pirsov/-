--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

local function award(plr: Player, amount: number)
	local current = plr:GetAttribute("Coins") or 0
	if typeof(current) ~= "number" then
		current = 0
	end
	local nextVal = (current :: number) + amount
	plr:SetAttribute("Coins", nextVal)
	Remotes.CoinCollected:FireClient(plr, nextVal)
end

local function hookCoin(part: BasePart)
	local taken = false
	part.Touched:Connect(function(hit: BasePart)
		if taken then
			return
		end
		local char = hit.Parent
		if not char then
			return
		end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then
			return
		end
		taken = true
		award(plr, 1)
		part:Destroy()
	end)
end

local folder = workspace:FindFirstChild("Coins")
if folder then
	for _, child in ipairs(folder:GetChildren()) do
		if child:IsA("BasePart") then
			hookCoin(child)
		end
	end
	folder.ChildAdded:Connect(function(child)
		if child:IsA("BasePart") then
			hookCoin(child)
		end
	end)
end
