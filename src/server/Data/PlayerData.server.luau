--!strict
local Players = game:GetService("Players")

local function loadPlayerData(player: Player): { Score: number, Checkpoint: number, Coins: number, BestTime: number }
    local data = {
        Score = 0,
        Checkpoint = 0,
        Coins = 0,
        BestTime = math.huge
    }

    -- Simulate loading from DataStore in Studio
    if game:GetService("RunService"):IsStudio() then
        local attributes = player:GetAttributes()
        if attributes.Score then
            data.Score = attributes.Score
        end
        if attributes.Checkpoint then
            data.Checkpoint = attributes.Checkpoint
        end
        if attributes.Coins then
            data.Coins = attributes.Coins
        end
        if attributes.BestTime then
            data.BestTime = attributes.BestTime
        end
    end

    return data
end

local function savePlayerData(player: Player, data: { Score: number, Checkpoint: number, Coins: number, BestTime: number })
    -- Simulate saving to DataStore in Studio
    if game:GetService("RunService"):IsStudio() then
        player:SetAttribute("Score", data.Score)
        player:SetAttribute("Checkpoint", data.Checkpoint)
        player:SetAttribute("Coins", data.Coins)
        player:SetAttribute("BestTime", data.BestTime)
    end
end

local function onPlayerAdded(player: Player)
    local data = loadPlayerData(player)
    player:SetAttribute("Score", data.Score)
    player:SetAttribute("Checkpoint", data.Checkpoint)
    player:SetAttribute("Coins", data.Coins or 0) -- Ensure Coins is initialized
    player:SetAttribute("BestTime", data.BestTime)
end

local function onCharacterAdded(character: Model)
    local player = Players:GetPlayerFromCharacter(character)
    if player then
        local coins = player:GetAttribute("Coins") or 0
        player:SetAttribute("Coins", coins) -- Ensure Coins are not wiped
    end
end

local function onPlayerRemoving(player: Player)
    local data = {
        Score = player:GetAttribute("Score") or 0,
        Checkpoint = player:GetAttribute("Checkpoint") or 0,
        Coins = player:GetAttribute("Coins") or 0,
        BestTime = player:GetAttribute("BestTime") or math.huge
    }
    savePlayerData(player, data)
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(onPlayerRemoving)

for _, player in ipairs(Players:GetPlayers()) do
    player.CharacterAdded:Connect(onCharacterAdded)
end
