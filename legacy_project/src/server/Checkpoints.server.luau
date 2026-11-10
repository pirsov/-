--!strict
local Players = game:GetService("Players")

local folder = workspace:FindFirstChild("Checkpoints")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Checkpoints"
	folder.Parent = workspace
end

local function onTouched(hit: BasePart)
	local char = hit.Parent
	if not char then
		return
	end
	-- BUG: GetPlayerFromCharacter without nil guard before use
	local plr = Players:GetPlayerFromCharacter(char)
	plr:SetAttribute("Checkpoint", 1)
end

for _, child in ipairs(folder:GetChildren()) do
	if child:IsA("BasePart") then
		child.Touched:Connect(onTouched)
	end
end
