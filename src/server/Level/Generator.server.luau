--!strict
-- Spawns checkpoints + coins from LevelConfig. No death logic here.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local LevelConfig = require(ReplicatedStorage:WaitForChild("Content"):WaitForChild("LevelConfig"))

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

local cpFolder = ensureFolder("Checkpoints")
local coinFolder = ensureFolder("Coins")

for _, child in ipairs(cpFolder:GetChildren()) do
	child:Destroy()
end
for _, child in ipairs(coinFolder:GetChildren()) do
	child:Destroy()
end

local z = 0
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

for _, section in ipairs(sections) do
	local gap = section.gap or 50
	local coinCount = section.coins or 3
	local id = section.id or 1
	z -= gap

	local p = Instance.new("Part")
	p.Name = "Checkpoint" .. tostring(id)
	p.Size = Vector3.new(10, 1, 10)
	p.Position = Vector3.new(0, 5, z)
	p.Anchored = true
	p.Material = Enum.Material.Neon
	p.Color = Color3.fromRGB(0, 200, 0)
	p.Parent = cpFolder

	for c = 1, math.min(coinCount, 8) do
		local coin = Instance.new("Part")
		coin.Name = "Coin_" .. tostring(id) .. "_" .. tostring(c)
		coin.Shape = Enum.PartType.Cylinder
		coin.Size = Vector3.new(0.4, 2, 2)
		coin.Position = Vector3.new((c - (coinCount + 1) / 2) * 3, 7, z + 15)
		coin.Anchored = true
		coin.Material = Enum.Material.Neon
		coin.Color = Color3.fromRGB(255, 215, 0)
		coin.Parent = coinFolder
	end
end

local ids = {}
for _, section in ipairs(sections) do
	table.insert(ids, tostring(section.id or "?"))
end
print("[Generator] section ids:", table.concat(ids, ","))
print("[Generator] spawned", #cpFolder:GetChildren(), "checkpoints and", #coinFolder:GetChildren(), "coins")
