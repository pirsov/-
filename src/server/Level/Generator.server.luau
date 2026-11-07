--!strict
-- Builds walkable map floor + checkpoints + coins from LevelConfig.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local LevelConfig = require(ReplicatedStorage:WaitForChild("Content"):WaitForChild("LevelConfig"))

local FLOOR_TOP_Y = 5
local FLOOR_THICK = 2
local PATH_WIDTH = 28
local SPAWN_Z = 20

local function ensureFolder(name: string): Folder
	local f = workspace:FindFirstChild(name)
	if f and f:IsA("Folder") then
		return f
	end
	if f then
		f:Destroy()
	end
	local folder = Instance.new("Folder")
	folder.Name = name
	folder.Parent = workspace
	return folder
end

local function clearFolder(folder: Folder)
	for _, child in ipairs(folder:GetChildren()) do
		child:Destroy()
	end
end

-- Remove default empty-place Baseplate so players don't spawn miles away.
local baseplate = workspace:FindFirstChild("Baseplate")
if baseplate then
	baseplate:Destroy()
end

local mapFolder = ensureFolder("Map")
local cpFolder = ensureFolder("Checkpoints")
local coinFolder = ensureFolder("Coins")
clearFolder(mapFolder)
clearFolder(cpFolder)
clearFolder(coinFolder)

local sections = LevelConfig.sections
if typeof(sections) ~= "table" then
	sections = {
		{ id = 1, gap = 50, coins = 3 },
		{ id = 2, gap = 70, coins = 3 },
		{ id = 3, gap = 90, coins = 3 },
		{ id = 4, gap = 110, coins = 3 },
		{ id = 5, gap = 130, coins = 3 },
	}
end

-- Precompute checkpoint Z along −Z from spawn.
local cpZs: { number } = {}
local z = 0
for _, section in ipairs(sections) do
	local gap = section.gap or 50
	z -= gap
	table.insert(cpZs, z)
end
local endZ = if #cpZs > 0 then cpZs[#cpZs] else -50

local floorY = FLOOR_TOP_Y - FLOOR_THICK / 2
local pathLen = (SPAWN_Z - endZ) + 40
local pathCenterZ = (SPAWN_Z + endZ) / 2

local floor = Instance.new("Part")
floor.Name = "Path"
floor.Size = Vector3.new(PATH_WIDTH, FLOOR_THICK, pathLen)
floor.Position = Vector3.new(0, floorY, pathCenterZ)
floor.Anchored = true
floor.Material = Enum.Material.Slate
floor.Color = Color3.fromRGB(70, 78, 90)
floor.Parent = mapFolder

-- Spawn plaza (wider pad so first join is safe).
local plaza = Instance.new("Part")
plaza.Name = "SpawnPlaza"
plaza.Size = Vector3.new(40, FLOOR_THICK, 36)
plaza.Position = Vector3.new(0, floorY, SPAWN_Z)
plaza.Anchored = true
plaza.Material = Enum.Material.Concrete
plaza.Color = Color3.fromRGB(95, 105, 120)
plaza.Parent = mapFolder

local spawn = Instance.new("SpawnLocation")
spawn.Name = "Spawn"
spawn.Size = Vector3.new(12, 1, 12)
spawn.Position = Vector3.new(0, FLOOR_TOP_Y + 0.5, SPAWN_Z)
spawn.Anchored = true
spawn.Duration = 0
spawn.Neutral = true
spawn.Material = Enum.Material.Neon
spawn.Color = Color3.fromRGB(60, 140, 255)
spawn.Parent = mapFolder

-- Soft side rails so players don't walk off immediately.
for _, side in ipairs({ -1, 1 }) do
	local rail = Instance.new("Part")
	rail.Name = if side < 0 then "RailLeft" else "RailRight"
	rail.Size = Vector3.new(1.5, 3, pathLen)
	rail.Position = Vector3.new(side * (PATH_WIDTH / 2 + 0.75), FLOOR_TOP_Y + 1.5, pathCenterZ)
	rail.Anchored = true
	rail.CanCollide = true
	rail.Transparency = 0.35
	rail.Material = Enum.Material.SmoothPlastic
	rail.Color = Color3.fromRGB(40, 40, 50)
	rail.Parent = mapFolder
end

for i, section in ipairs(sections) do
	local coinCount = section.coins or 3
	local id = section.id or i
	local cpZ = cpZs[i]

	local p = Instance.new("Part")
	p.Name = "Checkpoint" .. tostring(id)
	p.Size = Vector3.new(12, 1, 12)
	p.Position = Vector3.new(0, FLOOR_TOP_Y + 0.5, cpZ)
	p.Anchored = true
	p.Material = Enum.Material.Neon
	p.Color = Color3.fromRGB(0, 200, 0)
	p.Parent = cpFolder

	-- Short connector stripe between previous and this CP (visual section mark).
	local prevZ = if i == 1 then SPAWN_Z else cpZs[i - 1]
	local midZ = (prevZ + cpZ) / 2
	local stripe = Instance.new("Part")
	stripe.Name = "SectionStripe" .. tostring(id)
	stripe.Size = Vector3.new(PATH_WIDTH - 2, 0.2, 4)
	stripe.Position = Vector3.new(0, FLOOR_TOP_Y + 0.15, midZ)
	stripe.Anchored = true
	stripe.CanCollide = false
	stripe.Material = Enum.Material.Neon
	stripe.Color = Color3.fromRGB(120, 180, 255)
	stripe.Transparency = 0.4
	stripe.Parent = mapFolder

	for c = 1, math.min(coinCount, 8) do
		local coin = Instance.new("Part")
		coin.Name = "Coin_" .. tostring(id) .. "_" .. tostring(c)
		coin.Shape = Enum.PartType.Cylinder
		coin.Size = Vector3.new(0.4, 2, 2)
		-- Between previous landmark and this checkpoint, on the path.
		local coinZ = cpZ + 15 + (c - 1) * 3
		if coinZ > prevZ - 5 then
			coinZ = midZ + (c - (coinCount + 1) / 2) * 3
		end
		coin.Position = Vector3.new((c - (coinCount + 1) / 2) * 3, FLOOR_TOP_Y + 2.5, coinZ)
		coin.Anchored = true
		coin.Material = Enum.Material.Neon
		coin.Color = Color3.fromRGB(255, 215, 0)
		coin.Parent = coinFolder
	end
end

-- Align pressure-plate lane onto the map (same floor height).
local puzzles = workspace:FindFirstChild("Puzzles")
if puzzles then
	local plate = puzzles:FindFirstChild("PressurePlate")
	if plate and plate:IsA("BasePart") then
		plate.Position = Vector3.new(8, FLOOR_TOP_Y + 0.5, -30)
	end
	local gate = puzzles:FindFirstChild("Gate")
	if gate and gate:IsA("BasePart") then
		gate.Position = Vector3.new(8, FLOOR_TOP_Y + 6, -40)
	end
end

local ids = {}
for _, section in ipairs(sections) do
	table.insert(ids, tostring(section.id or "?"))
end
print("[Generator] map floor ready | spawn Z=", SPAWN_Z, "end Z=", endZ)
print("[Generator] section ids:", table.concat(ids, ","))
print("[Generator] spawned", #cpFolder:GetChildren(), "checkpoints and", #coinFolder:GetChildren(), "coins")
