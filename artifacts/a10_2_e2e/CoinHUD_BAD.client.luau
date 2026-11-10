--!strict
-- NEGATIVE A10.2 — client must not touch DataStore; must use CoinSync remotes
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local player = Players.LocalPlayer
local store = DataStoreService:GetDataStore("PlayerSave_v1")
local gui = Instance.new("ScreenGui")
gui.Parent = player:WaitForChild("PlayerGui")
pcall(function()
	store:GetAsync("p_" .. player.UserId)
end)
