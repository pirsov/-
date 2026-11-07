--!strict
-- Soft void: if HRP falls below Y=-20, LoadCharacter (respawn uses Checkpoints hooks).
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local VOID_Y = -20

local function watch(plr: Player, char: Model)
	local hrp = char:WaitForChild("HumanoidRootPart", 5)
	if not hrp or not hrp:IsA("BasePart") then
		return
	end
	local conn: RBXScriptConnection? = nil
	conn = RunService.Heartbeat:Connect(function()
		if not plr.Parent or not char.Parent then
			if conn then
				conn:Disconnect()
			end
			return
		end
		if hrp.Position.Y < VOID_Y then
			if conn then
				conn:Disconnect()
			end
			plr:LoadCharacter()
		end
	end)
end

local function hook(plr: Player)
	plr.CharacterAdded:Connect(function(char)
		watch(plr, char)
	end)
	if plr.Character then
		watch(plr, plr.Character)
	end
end

Players.PlayerAdded:Connect(hook)
for _, plr in ipairs(Players:GetPlayers()) do
	hook(plr)
end
