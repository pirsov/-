local folder = workspace:WaitForChild("Checkpoints")

for _, part in ipairs(folder:GetChildren()) do
    if part:IsA("BasePart") then
        local idx = tonumber(string.match(part.Name, "%d+"))
        if idx then
            part.Touched:Connect(function(hit)
                local char = hit.Parent
                local plr = Players:GetPlayerFromCharacter(char)
                if plr then
                    local current = plr:GetAttribute("Checkpoint") or 0
                    if idx > current then
                        plr:SetAttribute("Checkpoint", idx)
                        Remotes.CheckpointReached:FireClient(plr, idx)
                    end
                end
            end)
        end
    end
end