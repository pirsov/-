--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local Effects = {}

function Effects.PlaySound(soundId)
    local sound = Instance.new("Sound")
    sound.SoundId = soundId
    sound.Parent = ReplicatedStorage
    sound:Play()
    sound.Ended:Connect(function()
        sound:Destroy()
    end)
end

function Effects.UpdateHUD(player, checkpointCount, timeLeft)
    local playerGui = player:FindFirstChild("PlayerGui")
    if playerGui then
        local HUD = playerGui:FindFirstChild("HUD")
        if HUD then
            HUD.CheckpointCount.Text = "Checkpoints: " .. checkpointCount
            HUD.Timer.Text = "Time: " .. string.format("%.2f", timeLeft) .. "s"

            local tweenInfo = TweenInfo.new(0.5, Enum.EasingStyle.Quint, Enum.EasingDirection.Out)
            local tween = TweenService:Create(HUD, tweenInfo, {Position = HUD.Position + Vector2.new(0, 10)})
            tween:Play()
        end
    end
end

return Effects
