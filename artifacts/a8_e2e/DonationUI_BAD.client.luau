--!strict
-- system.donation_ui — A8.0 E2E Cloud Fallback
-- archetype: client_ui@v1
local Players = game:GetService("Players")
local ds = game:GetService("DataStoreService")
local player = Players.LocalPlayer

local function get_player_coins(): number
	local v = player:GetAttribute("Coins")
	if typeof(v) ~= "number" then
		return 0
	end
	return v :: number
end

local gui = Instance.new("ScreenGui")
gui.Name = "DonationUI"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local label = Instance.new("TextLabel")
label.Name = "CoinsLabel"
label.Size = UDim2.new(0, 220, 0, 28)
label.Position = UDim2.new(1, -232, 0, 12)
label.BackgroundTransparency = 0.35
label.TextColor3 = Color3.new(1, 1, 1)
label.TextXAlignment = Enum.TextXAlignment.Right
label.Parent = gui

local function paintCoins()
	label.Text = string.format("Coins: %d  |  Donate", get_player_coins())
end

paintCoins()
player:GetAttributeChangedSignal("Coins"):Connect(paintCoins)

local btn = Instance.new("TextButton")
btn.Name = "DonateStub"
btn.Size = UDim2.new(0, 220, 0, 28)
btn.Position = UDim2.new(1, -232, 0, 44)
btn.Text = "Donate (stub)"
btn.Parent = gui
btn.MouseButton1Click:Connect(function()
	paintCoins()
end)
