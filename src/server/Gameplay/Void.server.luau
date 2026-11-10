--!strict
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local function onCharacterAdded(plr: Player, char: Model)
	local hrp = char:WaitForChild("HumanoidRootPart")
	hrp:GetPropertyChangedSignal("Position"):Connect(function()
		if hrp.Position.Y < -20 then
			task.wait(0.1)
			plr:LoadCharacter()
		end
	end)
end

Players.PlayerAdded:Connect(function(plr)
	plr.CharacterAdded:Connect(function(char) onCharacterAdded(plr, char) end)
	if plr.Character then onCharacterAdded(plr, plr.Character) end
end)

for _, plr in ipairs(Players:GetPlayers()) do
	plr.CharacterAdded:Connect(function(char) onCharacterAdded(plr, char) end)
	if plr.Character then onCharacterAdded(plr, plr.Character) end
end
