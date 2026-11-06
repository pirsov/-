--!strict
local DataStoreService = game:GetService("DataStoreService")
local playerDataStore = DataStoreService:GetDataStore("PlayerData")

local function savePlayerData(player)
    local success, result = pcall(function()
        local score = player:GetAttribute("Score")
        playerDataStore:SetAsync(player.UserId, {Score = score})
    end)
    if not success then
        warn("Failed to save player data: " .. result)
    end
end

local function onPlayerAdded(player)
    local success, result = pcall(function()
        local data = playerDataStore:GetAsync(player.UserId)
        if data then
            player:SetAttribute("Score", data.Score)
        else
            player:SetAttribute("Score", 0)
        end
    end)
    if not success then
        warn("Failed to load player data: " .. result)
    end

    player.CharacterAdded:Connect(function(character)
        local humanoid = character:WaitForChild("Humanoid")
        humanoid.Died:Connect(function()
            savePlayerData(player)
        end)
    end)

    task.spawn(function()
        while true do
            wait(60)
            savePlayerData(player)
        end
    end)
end

local function onPlayerRemoving(player)
    savePlayerData(player)
end

game.Players.PlayerAdded:Connect(onPlayerAdded)
game.Players.PlayerRemoving:Connect(onPlayerRemoving)