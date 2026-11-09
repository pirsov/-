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
    gate.Position = Vector3.new(position.X, position.Y + 3, position.Z)
    gate.Anchored = true
    gate.CanCollide = true
    gate.Color = Color3.new(1, 0, 0) -- Red
    gate.Parent = Puzzles

    local function openGate()
        gate.Size = Vector3.new(10, 0.1, 1)
    end

    local function closeGate()
        gate.Size = Vector3.new(10, 5, 1)
    end

    pressurePlate.Touched:Connect(function(hit)
        local character = hit.Parent
        if character and character:FindFirstChild("Humanoid") then
            openGate()
        end
    end)

    pressurePlate.TouchEnded:Connect(function(hit)
        local character = hit.Parent
        if character and character:FindFirstChild("Humanoid") then
            closeGate()
        end
    end)
end

-- Example usage: Create a pressure plate and gate at a specific position
createPressurePlateAndGate(Vector3.new(8, 5.5, 40))
