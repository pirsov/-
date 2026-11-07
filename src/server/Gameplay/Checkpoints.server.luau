--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local folder = workspace:WaitForChild("Checkpoints")

local DEBOUNCE: { [number]: number } = {}

local function hookPart(part: BasePart)
	local idx = tonumber(string.match(part.Name, "%d+"))
	if not idx then
		return
	end
	part.Touched:Connect(function(hit: BasePart)
		local char = hit.Parent
		if not char then
			return
		end
		local plr = Players:GetPlayerFromCharacter(char)
		if not plr then
			return
		end
		local now = os.clock()
		local last = DEBOUNCE[plr.UserId]
		if last and now - last < 0.35 then
			return
		end
		local current = plr:GetAttribute("Checkpoint") or 0
		if typeof(current) ~= "number" then
			current = 0
		end
		if idx > (current :: number) then
			DEBOUNCE[plr.UserId] = now
			plr:SetAttribute("Checkpoint", idx)
			Remotes.CheckpointReached:FireClient(plr, idx)
		end
	end)
end

for _, part in ipairs(folder:GetChildren()) do
	if part:IsA("BasePart") then
		hookPart(part)
	end
end

folder.ChildAdded:Connect(function(child)
	if child:IsA("BasePart") then
		hookPart(child)
	end
end)

local function teleportToCheckpoint(plr: Player, char: Model)
	local idx = plr:GetAttribute("Checkpoint") or 0
	if typeof(idx) ~= "number" or (idx :: number) < 1 then
		return
	end
	local cp = folder:FindFirstChild("Checkpoint" .. tostring(idx))
	if not cp or not cp:IsA("BasePart") then
		return
	end
	local hrp = char:FindFirstChild("HumanoidRootPart")
	if hrp and hrp:IsA("BasePart") then
		hrp.CFrame = CFrame.new(cp.Position + Vector3.new(0, 5, 0))
	end
end

local function hookCharacter(plr: Player, char: Model)
	-- Place at last checkpoint on (re)spawn
	task.defer(function()
		teleportToCheckpoint(plr, char)
	end)
	local hum = char:WaitForChild("Humanoid") :: Humanoid
	hum.Died:Connect(function()
		task.wait(0.1)
		plr:LoadCharacter()
	end)
end

local function hookPlayer(plr: Player)
	plr.CharacterAdded:Connect(function(char)
		hookCharacter(plr, char)
	end)
	if plr.Character then
		hookCharacter(plr, plr.Character)
	end
end

Players.PlayerAdded:Connect(hookPlayer)
for _, plr in ipairs(Players:GetPlayers()) do
	hookPlayer(plr)
end
