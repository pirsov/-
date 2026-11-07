--!strict
local folder = workspace:FindFirstChild("Checkpoints")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Checkpoints"
	folder.Parent = workspace
end

-- Clear previous generated parts (safe re-run)
for _, child in ipairs(folder:GetChildren()) do
	if child:IsA("BasePart") and string.match(child.Name, "^Checkpoint%d+$") then
		child:Destroy()
	end
end

for i = 1, 10 do
	local p = Instance.new("Part")
	p.Name = "Checkpoint" .. i
	p.Size = Vector3.new(10, 1, 10)
	p.Position = Vector3.new(0, 5, -i * 50)
	p.Anchored = true
	p.Material = Enum.Material.Neon
	p.Color = Color3.fromRGB(0, 200, 0)
	p.Parent = folder
end

print("[Generator] spawned 10 checkpoints")
