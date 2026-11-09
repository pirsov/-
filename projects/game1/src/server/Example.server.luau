--!strict
local RunService = game:GetService("RunService")

local function onHeartbeat()
    for _, player in pairs(game.Players:GetPlayers()) do
        local character = player.Character
        if character then
            local humanoidRootPart = character:FindFirstChild("HumanoidRootPart")
            if humanoidRootPart and humanoidRootPart.Position.Y < -20 then
                player:LoadCharacter()
            end
        end
    end
end

RunService.Heartbeat:Connect(onHeartbeat)
