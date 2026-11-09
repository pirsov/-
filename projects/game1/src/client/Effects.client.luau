--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")
local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes"))

local function play(soundId: string, volume: number)
	local ok, err = pcall(function()
		local s = Instance.new("Sound")
		s.SoundId = soundId
		s.Volume = volume
		s.Parent = SoundService
		s:Play()
		s.Ended:Connect(function() s:Destroy() end)
	end)
	if not ok then warn("[Effects] sound skip", err) end
end

local function flash(name: string)
	local gui = Players.LocalPlayer:FindFirstChild("PlayerGui")
	local hud = gui and gui:FindFirstChild("HUD")
	local label = hud and hud:FindFirstChild(name)
	if label and label:IsA("GuiObject") then
		local tw = TweenService:Create(label, TweenInfo.new(0.2), { BackgroundTransparency = 0.1 })
		tw:Play()
		tw.Completed:Connect(function()
			TweenService:Create(label, TweenInfo.new(0.3), { BackgroundTransparency = 0.5 }):Play()
		end)
	end
end

Remotes.CheckpointReached.OnClientEvent:Connect(function()
	play("rbxassetid://9112854440", 0.5)
	flash("CheckpointCount")
end)

if Remotes.CoinCollected then
	Remotes.CoinCollected.OnClientEvent:Connect(function()
		play("rbxassetid://9114224690", 0.4)
		flash("CoinCount")
	end)
end
