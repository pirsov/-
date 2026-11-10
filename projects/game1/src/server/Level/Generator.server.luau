--!strict
-- Generator (F4 Cloud Fallback): SpawnLocation class, Path, Checkpoints/Coins folders,
-- destroy Baseplate, lighter map. Join readiness: async poll up to 60s (non-blocking).
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local LevelConfig = require(ReplicatedStorage:WaitForChild("Content"):WaitForChild("LevelConfig"))

local JOIN_POLL_BUDGET_S = 60

local function ensureFolder(parent: Instance, folderName: string): Folder
	local folder = parent:FindFirstChild(folderName)
	if folder and folder:IsA("Folder") then
		return folder
	end
	local created = Instance.new("Folder")
	created.Name = folderName
	created.Parent = parent
	return created
end

local function createPath(pathLength: number): Part
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

local function createSpawnPlaza(): Part
	local spawnPlaza = Instance.new("Part")
	spawnPlaza.Name = "SpawnPlaza"
	spawnPlaza.Size = Vector3.new(28, 1, 10)
	spawnPlaza.Position = Vector3.new(0, 5, 20)
	spawnPlaza.Anchored = true
	spawnPlaza.CanCollide = true
	spawnPlaza.Parent = ensureFolder(Workspace, "Map")
	return spawnPlaza
end

local function createSpawnLocation(): SpawnLocation
	-- Must be real SpawnLocation class (validator forbids Part renamed SpawnLocation)
	local spawnLocation = Instance.new("SpawnLocation")
	spawnLocation.Name = "SpawnLocation"
	spawnLocation.Size = Vector3.new(6, 1, 6)
	spawnLocation.Position = Vector3.new(0, 6, 20)
	spawnLocation.Anchored = true
	spawnLocation.CanCollide = true
	spawnLocation.Neutral = true
	spawnLocation.Duration = 0
	spawnLocation.Parent = ensureFolder(Workspace, "Map")
	return spawnLocation
end

local function createCheckpoint(id: number, position: Vector3): Part
	local checkpoint = Instance.new("Part")
	checkpoint.Name = "Checkpoint" .. tostring(id)
	checkpoint.Size = Vector3.new(2, 2, 2)
	checkpoint.Position = position
	checkpoint.Anchored = true
	checkpoint.CanCollide = false
	checkpoint.CanTouch = true
	checkpoint.Color = Color3.new(0, 1, 0)
	checkpoint.Material = Enum.Material.Neon
	checkpoint.Parent = ensureFolder(Workspace, "Checkpoints")
	return checkpoint
end

local function createCoin(position: Vector3): Part
	local coin = Instance.new("Part")
	coin.Name = "Coin"
	coin.Size = Vector3.new(1, 1, 1)
	coin.Position = position
	coin.Anchored = true
	coin.CanCollide = false
	coin.CanTouch = true
	coin.Color = Color3.new(1, 0.84, 0)
	coin.Parent = ensureFolder(Workspace, "Coins")
	return coin
end

local function createObstacle(position: Vector3): Part
	local obstacle = Instance.new("Part")
	obstacle.Name = "Obstacle"
	obstacle.Size = Vector3.new(4, 2, 4)
	obstacle.Position = position
	obstacle.Anchored = true
	obstacle.CanCollide = true
	obstacle.Parent = ensureFolder(Workspace, "Obstacles")
	return obstacle
end

local function generateLevel()
	local baseplate = Workspace:FindFirstChild("Baseplate")
	if baseplate then
		baseplate:Destroy()
	end

	-- Ensure folders exist even before parts (Coins/Checkpoints ChildAdded hooks)
	ensureFolder(Workspace, "Checkpoints")
	ensureFolder(Workspace, "Coins")
	ensureFolder(Workspace, "Map")

	local totalLength = 40
	for _, section in ipairs(LevelConfig) do
		totalLength = totalLength + section.gap
	end

	createPath(totalLength)
	createSpawnPlaza()
	createSpawnLocation()

	local currentZ = 20
	for i, section in ipairs(LevelConfig) do
		local checkpointPosition = Vector3.new(0, 6, currentZ + section.gap / 2)
		createCheckpoint(i, checkpointPosition)

		for _ = 1, section.coins do
			local coinPosition = Vector3.new(
				math.random(-10, 10),
				7,
				currentZ + math.random(0, math.max(1, section.gap - 1))
			)
			createCoin(coinPosition)
		end

		-- Lighter: 1 obstacle per section (was 3)
		local obstaclePosition = Vector3.new(
			math.random(-8, 8),
			6,
			currentZ + math.floor(section.gap / 2)
		)
		createObstacle(obstaclePosition)

		currentZ = currentZ + section.gap
	end

	print("[Generator] map floor ready")
end

generateLevel()

-- Light async join/spawn readiness poll (Q2: 60s budget, never blocks main thread)
task.spawn(function()
	local deadline = os.clock() + JOIN_POLL_BUDGET_S
	while os.clock() < deadline do
		local map = Workspace:FindFirstChild("Map")
		local spawn = map and map:FindFirstChild("SpawnLocation")
		if spawn and spawn:IsA("SpawnLocation") then
			print("[Generator] spawn ready")
			return
		end
		task.wait(0.25)
	end
	warn("[Generator] spawn not ready within " .. tostring(JOIN_POLL_BUDGET_S) .. "s")
end)
