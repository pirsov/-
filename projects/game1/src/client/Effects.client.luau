--!strict
-- Effects + I010: Checkpoint touch VFX pulse (world flash + HUD flash).
-- I009 coin sound asset hunt deferred — keep existing guarded play.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

local player = Players.LocalPlayer

local function play(soundId: string, volume: number)
	local ok, err = pcall(function()
		local s = Instance.new("Sound")
		s.SoundId = soundId
		s.Volume = volume
		s.Parent = SoundService
		s:Play()
		s.Ended:Connect(function()
			s:Destroy()
		end)
	end)
	if not ok then
		warn("[Effects] sound skip", err)
	end
end

local function flashHud(name: string)
	local gui = player:FindFirstChild("PlayerGui")
	local hud = gui and gui:FindFirstChild("HUD")
	local label = hud and hud:FindFirstChild(name)
	if label and label:IsA("GuiObject") then
		local tw = TweenService:Create(label, TweenInfo.new(0.2), { BackgroundTransparency = 0.1 })
		tw:Play()
		tw.Completed:Connect(function()
			TweenService:Create(label, TweenInfo.new(0.3), { BackgroundTransparency = 0.4 }):Play()
		end)
	end
end

-- I010: brief neon pulse on the touched Checkpoint part (local visual only)
local function pulseCheckpoint(idx: number?)
	if typeof(idx) ~= "number" then
		return
	end
	local folder = workspace:FindFirstChild("Checkpoints")
	if not folder then
		return
	end
	local part = folder:FindFirstChild("Checkpoint" .. tostring(idx))
	if not part or not part:IsA("BasePart") then
		return
	end

	local originalColor = part.Color
	local originalMaterial = part.Material
	part.Material = Enum.Material.Neon
	part.Color = Color3.new(0.6, 1, 0.85)

	local light = part:FindFirstChild("CPPulseLight")
	if not light then
		light = Instance.new("PointLight")
		light.Name = "CPPulseLight"
		light.Parent = part
	end
	if light:IsA("PointLight") then
		light.Color = Color3.new(0.5, 1, 0.9)
		light.Range = 18
		light.Brightness = 4
		TweenService:Create(light, TweenInfo.new(0.45), { Brightness = 0, Range = 6 }):Play()
	end

	local emitter = part:FindFirstChild("CPPulseParticles")
	if not emitter then
		emitter = Instance.new("ParticleEmitter")
		emitter.Name = "CPPulseParticles"
		emitter.Texture = "rbxasset://textures/particles/sparkles_main.dds"
		emitter.Lifetime = NumberSequence.new(0.35)
		emitter.Lifetime = NumberRange.new(0.4, 0.7)
		emitter.Speed = NumberRange.new(2, 6)
		emitter.SpreadAngle = Vector2.new(40, 40)
		emitter.LightEmission = 0.8
		emitter.Color = ColorSequence.new(Color3.new(0.5, 1, 0.85))
		emitter.Enabled = false
		emitter.Parent = part
	end
	if emitter:IsA("ParticleEmitter") then
		emitter:Emit(18)
	end

	TweenService:Create(part, TweenInfo.new(0.35), { Color = Color3.new(0.2, 1, 0.35) }):Play()
	task.delay(0.4, function()
		if part.Parent then
			TweenService:Create(part, TweenInfo.new(0.35), { Color = originalColor }):Play()
			part.Material = originalMaterial
		end
	end)
end

Remotes.CheckpointReached.OnClientEvent:Connect(function(idx: number?)
	play("rbxassetid://9112854440", 0.5)
	flashHud("CheckpointCount")
	pulseCheckpoint(idx)
end)

Remotes.CoinCollected.OnClientEvent:Connect(function()
	play("rbxassetid://9114224690", 0.4)
	flashHud("CoinCount")
end)
