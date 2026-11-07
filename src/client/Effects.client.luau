--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")

local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

local function play(soundId: string, volume: number)
	local s = Instance.new("Sound")
	s.SoundId = soundId
	s.Volume = volume
	s.Parent = SoundService
	s:Play()
	s.Ended:Connect(function()
		s:Destroy()
	end)
end

Remotes.CheckpointReached.OnClientEvent:Connect(function()
	play("rbxassetid://9112854440", 0.5)
	local gui = game:GetService("Players").LocalPlayer:FindFirstChild("PlayerGui")
	if not gui then
		return
	end
	local hud = gui:FindFirstChild("HUD")
	if not hud then
		return
	end
	local cp = hud:FindFirstChild("CheckpointCount")
	if cp and cp:IsA("GuiObject") then
		local tween = TweenService:Create(
			cp,
			TweenInfo.new(0.2, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
			{ BackgroundTransparency = 0.1 }
		)
		tween:Play()
		tween.Completed:Connect(function()
			TweenService:Create(
				cp,
				TweenInfo.new(0.3),
				{ BackgroundTransparency = 0.5 }
			):Play()
		end)
	end
end)

if Remotes.CoinCollected then
	Remotes.CoinCollected.OnClientEvent:Connect(function()
		play("rbxassetid://9114224690", 0.4)
	end)
end
