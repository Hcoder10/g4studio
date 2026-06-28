"""Templated, model-agnostic Luau mechanics for generated obbies.

This single server Script (placed inside the G4Obby folder so it runs from
Workspace) reads the folder structure the emitters produce and wires up:
  - checkpoints (respawn at last touched flag)
  - hazards (touch = death)
  - win pad (finish detection)
  - moving platforms (params encoded in the part name: Move_<axis>_<dist>_<speed>)

Keeping the engineering in a proven template is what makes LLM-generated games
reliable: the model only has to place parts well, not write correct game code.
"""

MECHANICS_LUAU = r"""--!nonstrict
-- G4Studio obby mechanics (templated)
local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")

local root = script.Parent
local function folder(name)
    return root:FindFirstChild(name)
end

-- ===== Checkpoints =====
local checkpoints = {}
local cpFolder = folder("Checkpoints")
if cpFolder then
    for _, p in ipairs(cpFolder:GetChildren()) do
        if p:IsA("BasePart") then
            local idx = tonumber(tostring(p.Name):match("(%d+)$")) or 0
            checkpoints[idx] = p
        end
    end
end

local lastCp = {}

local function placeAtCheckpoint(plr, char)
    local hrp = char:WaitForChild("HumanoidRootPart", 5)
    if not hrp then return end
    local cp = checkpoints[lastCp[plr] or 0]
    if cp then
        hrp.CFrame = cp.CFrame + Vector3.new(0, 4, 0)
    end
end

Players.PlayerAdded:Connect(function(plr)
    lastCp[plr] = 0
    plr.CharacterAdded:Connect(function(char)
        task.wait(0.1)
        placeAtCheckpoint(plr, char)
    end)
end)
Players.PlayerRemoving:Connect(function(plr)
    lastCp[plr] = nil
end)

for idx, cp in pairs(checkpoints) do
    cp.Touched:Connect(function(hit)
        local plr = Players:GetPlayerFromCharacter(hit.Parent)
        if plr and (lastCp[plr] or 0) < idx then
            lastCp[plr] = idx
        end
    end)
end

-- ===== Hazards (kill) =====
local hazFolder = folder("Hazards")
if hazFolder then
    for _, h in ipairs(hazFolder:GetChildren()) do
        if h:IsA("BasePart") then
            h.Touched:Connect(function(hit)
                local hum = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
                if hum and hum.Health > 0 then
                    hum.Health = 0
                end
            end)
        end
    end
end

-- ===== Win pad =====
local win = root:FindFirstChild("Win")
if win and win:IsA("BasePart") then
    win.Touched:Connect(function(hit)
        local plr = Players:GetPlayerFromCharacter(hit.Parent)
        if plr then
            print("[G4Studio] " .. plr.Name .. " finished the obby!")
        end
    end)
end

-- ===== Moving platforms =====
local movFolder = folder("Moving")
if movFolder then
    for _, m in ipairs(movFolder:GetChildren()) do
        if m:IsA("BasePart") then
            local axis, dist, speed = tostring(m.Name):match("Move_(%a)_([%d%.]+)_([%d%.]+)")
            axis = axis or "x"
            dist = tonumber(dist) or 16
            speed = tonumber(speed) or 8
            local dir = Vector3.new(
                axis == "x" and 1 or 0,
                axis == "y" and 1 or 0,
                axis == "z" and 1 or 0
            )
            m.Anchored = true
            local startPos = m.Position
            local goalPos = startPos + dir * dist
            local secs = math.max(dist / math.max(speed, 0.1), 0.1)
            local info = TweenInfo.new(secs, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true)
            TweenService:Create(m, info, { Position = goalPos }):Play()
        end
    end
end

-- ===== Spinners (rotating kill-bars) =====
local spinFolder = folder("Spinners")
if spinFolder then
    local spinners = {}
    for _, s in ipairs(spinFolder:GetChildren()) do
        if s:IsA("BasePart") then
            local axis, speed = tostring(s.Name):match("Spin_(%a)_([%d%.]+)")
            s.Anchored = true
            table.insert(spinners, {
                part = s, axis = axis or "y",
                speed = tonumber(speed) or 90, base = s.CFrame,
            })
            s.Touched:Connect(function(hit)
                local hum = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
                if hum and hum.Health > 0 then hum.Health = 0 end
            end)
        end
    end
    if #spinners > 0 then
        local t = 0
        RunService.Heartbeat:Connect(function(dt)
            t += dt
            for _, sp in ipairs(spinners) do
                local ang = math.rad(sp.speed) * t
                local rot
                if sp.axis == "x" then rot = CFrame.Angles(ang, 0, 0)
                elseif sp.axis == "z" then rot = CFrame.Angles(0, 0, ang)
                else rot = CFrame.Angles(0, ang, 0) end
                sp.part.CFrame = sp.base * rot
            end
        end)
    end
end

print("[G4Studio] mechanics online")
"""


def get_mechanics_luau() -> str:
    return MECHANICS_LUAU
