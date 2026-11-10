local ds=game:GetService("DataStoreService"):GetDataStore("x")
ds:SetAsync("k",1)
r.OnServerEvent:Connect(function(p,a) end)
while true do print(1) end
