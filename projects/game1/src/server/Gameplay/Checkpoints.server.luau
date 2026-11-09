--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local folder = workspace:FindFirstChild("Checkpoints")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Checkpoints"
	folder.Parent = workspace
end

local function hookPart(part: BasePart)
	local idx = tonumber(string.match(part.Name, "%d+"))
	if not idx then return end
	part.Touched:Connect(function(hit: BasePart)
		local char = hit.Parent
		if not char then return end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then return end
		local current = plr:GetAttribute("Checkpoint") or 0
		if typeof(current) ~= "number" then current = 0 end
		if idx > (current :: number) then
			local coinsFolder = workspace:FindFirstChild("Coins")
			if coinsFolder then
				for _, coin in ipairs(coinsFolder:GetChildren()) do
					if coin:IsA("BasePart") and coin.Position == part.Position then
						coin:Destroy()
						local currentCoins = plr:GetAttribute("Coins") or 0
						plr:SetAttribute("Coins", currentCoins + 1)
						Remotes.CoinsCollected:FireClient(plr, currentCoins + 1)
					end
				end
			end
			plr:SetAttribute("Checkpoint", idx)
			local score = idx * 100
			plr:SetAttribute("Score", score)
			Remotes.CheckpointReached:FireClient(plr, idx, score)
		end
	end)
end

for _, child in ipairs(folder:GetChildren()) do
	if child:IsA("BasePart") then hookPart(child) end
end

folder.ChildAdded:Connect(function(child)
	if child:IsA("BasePart") then hookPart(child) end
end)

local function teleportToCheckpoint(plr: Player, char: Model)
	local idx = plr:GetAttribute("Checkpoint") or 0
	if typeof(idx) ~= "number" or (idx :: number) < 1 then return end
	local cp = folder:FindFirstChild("Checkpoint" .. tostring(idx))
	if not cp or not cp:IsA("BasePart") then return end
	local hrp = char:FindFirstChild("HumanoidRootPart")
	if hrp and hrp:IsA("BasePart") then
		hrp.CFrame = CFrame.new(cp.Position + Vector3.new(0, 5, 0))
	end
end

local function hookCharacter(plr: Player, char: Model)
	task.defer(function() teleportToCheckpoint(plr, char) end)
	local hum = char:WaitForChild("Humanoid") :: Humanoid
	hum.Died:Connect(function()
		task.wait(0.1)
		plr:LoadCharacter()
	end)
end

Players.PlayerAdded:Connect(function(plr)
	plr.CharacterAdded:Connect(function(char) hookCharacter(plr, char) end)
	if plr.Character then hookCharacter(plr, plr.Character) end
end)

for _, plr in ipairs(Players:GetPlayers()) do
	plr.CharacterAdded:Connect(function(char) hookCharacter(plr, char) end)
	if plr.Character then hookCharacter(plr, plr.Character) end
end
