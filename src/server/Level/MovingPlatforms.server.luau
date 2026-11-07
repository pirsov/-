--!strict
-- One anchored platform tweening along Z between -20 and -80.
local TweenService = game:GetService("TweenService")

local folder = workspace:FindFirstChild("Moving")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Moving"
	folder.Parent = workspace
end

local platform = folder:FindFirstChild("Mover1")
if not platform then
	platform = Instance.new("Part")
	platform.Name = "Mover1"
	platform.Size = Vector3.new(12, 1, 8)
	platform.Position = Vector3.new(-15, 5, -20)
	platform.Anchored = true
	platform.Color = Color3.fromRGB(120, 120, 120)
	platform.Parent = folder
end

assert(platform:IsA("BasePart"))

local function loop()
	while platform.Parent do
		local toFar = TweenService:Create(
			platform,
			TweenInfo.new(4, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut),
			{ Position = Vector3.new(platform.Position.X, platform.Position.Y, -80) }
		)
		toFar:Play()
		toFar.Completed:Wait()
		local toNear = TweenService:Create(
			platform,
			TweenInfo.new(4, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut),
			{ Position = Vector3.new(platform.Position.X, platform.Position.Y, -20) }
		)
		toNear:Play()
		toNear.Completed:Wait()
	end
end

task.spawn(loop)
print("[MovingPlatforms] Mover1 looping")
