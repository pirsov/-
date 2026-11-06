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