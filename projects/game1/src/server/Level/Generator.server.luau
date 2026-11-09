--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")
local Workspace = game:GetService("Workspace")

local LevelConfig = require(ReplicatedStorage:WaitForChild("Content"):WaitForChild("LevelConfig"))

local function ensureFolder(parent: Instance, folderName: string): Instance
    local folder = parent:FindFirstChild(folderName)
    if not folder then
        folder = Instance.new("Folder")
        folder.Name = folderName
        folder.Parent = parent
    end
    return folder
end

local function createPath(pathLength: number): Instance
    local path = Instance.new("Part")
    path.Name = "Path"
    path.Size = Vector3.new(28, 1, pathLength)
    path.Position = Vector3.new(0, 5, pathLength / 2)
    path.Anchored = true
    path.CanCollide = true
    path.BrickColor = BrickColor.new("Medium stone grey")
    path.Parent = ensureFolder(Workspace, "Map")
    return path
end

local function createSpawnPlaza(): Instance
    local spawnPlaza = Instance.new("Part")
    spawnPlaza.Name = "SpawnPlaza"
    spawnPlaza.Size = Vector3.new(28, 1, 10)
    spawnPlaza.Position = Vector3.new(0, 5, 20)
    spawnPlaza.Anchored = true
    spawnPlaza.CanCollide = true
    spawnPlaza.Parent = ensureFolder(Workspace, "Map")
    return spawnPlaza
end

local function createSpawnLocation(): Instance
    local spawnLocation = Instance.new("Part")
    spawnLocation.Name = "SpawnLocation"
    spawnLocation.Size = Vector3.new(2, 2, 2)
    spawnLocation.Position = Vector3.new(0, 6, 20)
    spawnLocation.Anchored = true
    spawnLocation.CanCollide = false
    spawnLocation.Parent = ensureFolder(Workspace, "Map")
    return spawnLocation
end

local function createCheckpoint(id: number, position: Vector3): Instance
    local checkpoint = Instance.new("Part")
    checkpoint.Name = "Checkpoint" .. tostring(id)
    checkpoint.Size = Vector3.new(2, 2, 2)
    checkpoint.Position = position
    checkpoint.Anchored = true
    checkpoint.CanCollide = false
    checkpoint.Color = Color3.new(0, 1, 0) -- Green
    checkpoint.Material = Enum.Material.Neon
    checkpoint.Parent = ensureFolder(Workspace, "Checkpoints")
    return checkpoint
end

local function createCoin(position: Vector3): Instance
    local coin = Instance.new("Part")
    coin.Name = "Coin"
    coin.Size = Vector3.new(1, 1, 1)
    coin.Position = position
    coin.Anchored = true
    coin.CanCollide = false
    coin.Color = Color3.new(1, 0.84, 0) -- Gold/Yellow
    coin.Parent = ensureFolder(Workspace, "Coins")
    return coin
end

local function createObstacle(position: Vector3): Instance
    local obstacle = Instance.new("Part")
    obstacle.Name = "Obstacle"
    obstacle.Size = Vector3.new(5, 2, 5)
    obstacle.Position = position
    obstacle.Anchored = true
    obstacle.CanCollide = true
    obstacle.Parent = ensureFolder(Workspace, "Obstacles")
    return obstacle
end

local function generateLevel()
    -- Destroy the Baseplate
    local baseplate = Workspace:FindFirstChild("Baseplate")
    if baseplate then
        baseplate:Destroy()
    end

    local totalLength = 0
    for i, section in ipairs(LevelConfig) do
        totalLength = totalLength + section.gap
    end

    createPath(totalLength)
    createSpawnPlaza()
    createSpawnLocation()

    local currentZ = 20
    for i, section in ipairs(LevelConfig) do
        local checkpointPosition = Vector3.new(0, 5, currentZ + section.gap / 2)
        createCheckpoint(i, checkpointPosition)

        for _ = 1, section.coins do
            local coinPosition = Vector3.new(math.random(-12, 12), 7, currentZ + math.random(-section.gap / 2, section.gap / 2))
            createCoin(coinPosition)
        end

        for _ = 1, 3 do
            local obstaclePosition = Vector3.new(math.random(-12, 12), 1, currentZ + math.random(-section.gap / 2, section.gap / 2))
            createObstacle(obstaclePosition)
        end

        currentZ = currentZ + section.gap
    end

    print("[Generator] map floor ready")
end

generateLevel()
