--!strict
-- NEGATIVE A10.1 — DataStore on client must FAIL validator
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local player = Players.LocalPlayer
local store = DataStoreService:GetDataStore("PlayerSave_v1")
local gui = Instance.new("ScreenGui")
gui.Parent = player:WaitForChild("PlayerGui")
pcall(function()
	store:SetAsync("hack", { Coins = 999 })
end)
