--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Remotes = require(ReplicatedStorage.Gameplay.Remotes)

local function ensureFolder(folderName: string): Folder
    local folder = Workspace:FindFirstChild(folderName)
    if folder and folder:IsA("Folder") then
        return folder
    else
        local newFolder = Instance.new("Folder")
        newFolder.Name = folderName
        newFolder.Parent = Workspace
        return newFolder
    end
end

local Puzzles = ensureFolder("Puzzles")

local function createPressurePlateAndGate(position: Vector3)
    local pressurePlate = Instance.new("Part")
    pressurePlate.Name = "PressurePlate"
    pressurePlate.Size = Vector3.new(6, 1, 6)
    pressurePlate.Position = position
    pressurePlate.Anchored = true
    pressurePlate.CanCollide = true
    pressurePlate.Color = Color3.new(0, 0, 1) -- Blue
    pressurePlate.Parent = Puzzles

    local gate = Instance.new("Part")
    gate.Name = "Gate"
    gate.Size = Vector3.new(10, 5, 1)
    gate.Position = position + Vector3.new(0, 3, 0)
    gate.Anchored = true
    gate.CanCollide = true
    gate.Color = Color3.new(1, 0, 0) -- Red
    gate.Parent = Puzzles

    local sound = Instance.new("Sound")
    sound.Name = "GateSound"
    sound.SoundId = "rbxassetid://123456789" -- Replace with actual sound ID
    sound.Parent = gate

    pressurePlate.Touched:Connect(function(hit: BasePart)
        local char = hit.Parent
        if char and char:IsA("Model") then
            gate.CanCollide = false
            sound:Play()
        end
    end)

    pressurePlate.TouchEnded:Connect(function(hit: BasePart)
        local char = hit.Parent
        if char and char:IsA("Model") then
            gate.CanCollide = true
        end
    end)
end

-- Example usage: create a pressure plate and gate at a specific position
createPressurePlateAndGate(Vector3.new(0, 0, 0))
