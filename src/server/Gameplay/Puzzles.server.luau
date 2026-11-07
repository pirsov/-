--!strict
-- MVP pressure plate: stand on Plate opens Gate (Transparency + CanCollide).
local Players = game:GetService("Players")

local folder = workspace:FindFirstChild("Puzzles")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Puzzles"
	folder.Parent = workspace
end

local plate = folder:FindFirstChild("PressurePlate")
if not plate then
	plate = Instance.new("Part")
	plate.Name = "PressurePlate"
	plate.Size = Vector3.new(6, 1, 6)
	plate.Position = Vector3.new(12, 5, -30)
	plate.Anchored = true
	plate.Color = Color3.fromRGB(80, 80, 200)
	plate.Parent = folder
end

local gate = folder:FindFirstChild("Gate")
if not gate then
	gate = Instance.new("Part")
	gate.Name = "Gate"
	gate.Size = Vector3.new(10, 12, 1)
	gate.Position = Vector3.new(12, 11, -40)
	gate.Anchored = true
	gate.Color = Color3.fromRGB(180, 60, 60)
	gate.Parent = folder
end

assert(plate:IsA("BasePart") and gate:IsA("BasePart"))

local standing = 0
local lastTouch = 0.0

local function setOpen(open: boolean)
	gate.CanCollide = not open
	gate.Transparency = if open then 0.7 else 0
end

plate.Touched:Connect(function(hit: BasePart)
	local char = hit.Parent
	if not char then
		return
	end
	local plr = Players:GetPlayerFromCharacter(char)
	if not plr then
		return
	end
	local now = os.clock()
	if now - lastTouch < 0.05 then
		return
	end
	lastTouch = now
	standing += 1
	setOpen(true)
end)

plate.TouchEnded:Connect(function(hit: BasePart)
	local char = hit.Parent
	if not char then
		return
	end
	if not Players:GetPlayerFromCharacter(char) then
		return
	end
	standing = math.max(0, standing - 1)
	if standing == 0 then
		setOpen(false)
	end
end)

print("[Puzzles] pressure plate ready")
