--!strict
local Workspace = game:GetService("Workspace")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))
local _ = Remotes

local function ensureFolder(folderName: string): Folder
	local folder = Workspace:FindFirstChild(folderName)
	if folder and folder:IsA("Folder") then
		return folder
	end
	local created = Instance.new("Folder")
	created.Name = folderName
	created.Parent = Workspace
	return created
end

local puzzles = ensureFolder("Puzzles")

local plate = puzzles:FindFirstChild("PressurePlate")
if not (plate and plate:IsA("BasePart")) then
	local p = Instance.new("Part")
	p.Name = "PressurePlate"
	p.Size = Vector3.new(6, 1, 6)
	p.Position = Vector3.new(0, 1, 40)
	p.Anchored = true
	p.CanCollide = true
	p.CanTouch = true
	p.Parent = puzzles
	plate = p
end

local gate = puzzles:FindFirstChild("Gate")
if not (gate and gate:IsA("BasePart")) then
	local g = Instance.new("Part")
	g.Name = "Gate"
	g.Size = Vector3.new(8, 10, 1)
	g.Position = Vector3.new(0, 6, 48)
	g.Anchored = true
	g.CanCollide = true
	g.Parent = puzzles
	gate = g
end

local pressurePlate = plate :: BasePart
local gatePart = gate :: BasePart

pressurePlate.Touched:Connect(function(_hit: BasePart)
	gatePart.CanCollide = false
	gatePart.Transparency = 0.5
end)

pressurePlate.TouchEnded:Connect(function(_hit: BasePart)
	gatePart.CanCollide = true
	gatePart.Transparency = 0
end)
