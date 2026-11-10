--!strict
-- I013: Horror fog density preset — Lighting + Atmosphere for mood (no extra map props).
local Lighting = game:GetService("Lighting")

local function ensureAtmosphere(): Atmosphere
	local atm = Lighting:FindFirstChildOfClass("Atmosphere")
	if atm then
		return atm
	end
	local created = Instance.new("Atmosphere")
	created.Name = "HorrorAtmosphere"
	created.Parent = Lighting
	return created
end

local function ensureColorCorrection(): ColorCorrectionEffect
	local fx = Lighting:FindFirstChild("HorrorColorCorrection")
	if fx and fx:IsA("ColorCorrectionEffect") then
		return fx
	end
	local created = Instance.new("ColorCorrectionEffect")
	created.Name = "HorrorColorCorrection"
	created.Parent = Lighting
	return created
end

local function applyHorrorFog()
	-- Dense low fog, cool desaturated horror look
	Lighting.FogEnd = 90
	Lighting.FogStart = 12
	Lighting.FogColor = Color3.fromRGB(18, 22, 28)
	Lighting.Ambient = Color3.fromRGB(35, 38, 48)
	Lighting.OutdoorAmbient = Color3.fromRGB(28, 30, 40)
	Lighting.Brightness = 1.1
	Lighting.ClockTime = 0.5 -- near midnight
	Lighting.GlobalShadows = true

	local atm = ensureAtmosphere()
	atm.Density = 0.45
	atm.Offset = 0.15
	atm.Color = Color3.fromRGB(40, 48, 58)
	atm.Decay = Color3.fromRGB(20, 22, 30)
	atm.Glare = 0.1
	atm.Haze = 1.8

	local cc = ensureColorCorrection()
	cc.Enabled = true
	cc.Saturation = -0.25
	cc.Contrast = 0.12
	cc.TintColor = Color3.fromRGB(200, 210, 230)

	print("[HorrorFog] preset applied")
end

applyHorrorFog()
