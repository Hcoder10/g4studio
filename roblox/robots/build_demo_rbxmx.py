"""Pack the SO-101 robot demo into ONE self-installing .rbxmx.

Insert it into Workspace ("Insert From File"), enable HTTP Requests, press Play. The DemoServer
script builds the arm + workcell, records traces to /api/trace, and clones the controller into
each player's PlayerGui (LocalScripts can't run from Workspace). Run:
    python roblox/robots/build_demo_rbxmx.py   ->   out/G4RobotDemo.rbxmx
"""
import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "out", "G4RobotDemo.rbxmx")
SERVER_URL = "http://127.0.0.1:8000"


def read(name: str) -> str:
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


SERVER_SRC = r'''--!strict
-- G4 Robot Demo (self-contained). Build the SO-101 + workcell, hand each player the controller,
-- and record manipulation episodes to /api/trace. Drop the G4RobotDemo folder in Workspace,
-- enable HTTP Requests (Game Settings -> Security), then Play.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local CollectionService = game:GetService("CollectionService")
local RunService = game:GetService("RunService")
local root = script.Parent
local SO101 = require(root:WaitForChild("SO101"))
local Trace = require(root:WaitForChild("Trace"))
local SERVER = (root:FindFirstChild("SERVER_URL") and root.SERVER_URL.Value) or "http://127.0.0.1:8000"
pcall(function() game:GetService("HttpService").HttpEnabled = true end)

local control = RS:FindFirstChild("G4Control") or Instance.new("RemoteEvent")
control.Name = "G4Control"; control.Parent = RS

-- hand each player the controller (a LocalScript only runs from PlayerGui, not Workspace)
local template = root:WaitForChild("ClientTemplate")
local function giveClient(plr)
	local pg = plr:WaitForChild("PlayerGui")
	if pg:FindFirstChild("G4RobotClient") then return end
	local c = template:Clone(); c.Name = "G4RobotClient"; c.Disabled = false; c.Parent = pg
end
Players.PlayerAdded:Connect(giveClient)
for _, p in ipairs(Players:GetPlayers()) do task.spawn(giveClient, p) end

-- workcell
local arm = SO101.new(workspace, CFrame.new(0, 2, 0))
local bin = Instance.new("Part")
bin.Name = "Bin"; bin.Size = Vector3.new(3, 1, 3); bin.Anchored = true
bin.Position = Vector3.new(-6, 0.5, 3); bin.Color = Color3.fromRGB(0, 170, 90); bin.Parent = workspace

local function spawnCube()
	local c = Instance.new("Part")
	c.Name = "Cube"; c.Size = Vector3.new(1, 1, 1); c.Anchored = false
	c.Color = Color3.fromRGB(255, 170, 0); c.Material = Enum.Material.SmoothPlastic
	c.Position = Vector3.new(math.random(-50, 50) / 10, 1, 6)
	c.Parent = workspace
	CollectionService:AddTag(c, "Graspable")
	return c
end
local cube = spawnCube()

local latest = { target = nil, grip = false }
control.OnServerEvent:Connect(function(_, t, grip)
	latest.target = t; latest.grip = grip and true or false
end)

local function newEpisode()
	return Trace.new("so101_pick_place", { robot = "SO101", action_space = "ee_target", reward = "dense" })
end
local ep = newEpisode()

RunService.Heartbeat:Connect(function(dt)
	if latest.target then arm:solveTo(latest.target) end
	arm:grip(latest.grip and 0 or 1)
	arm:step(dt)
	local obs = arm:getObs()
	local toCube = (cube.Position - arm.tip.Position).Magnitude
	local cubeToBin = (cube.Position - bin.Position).Magnitude
	local subgoal = obs.holding and (cubeToBin < 2.2 and "place" or "transport")
		or (toCube < 1.6 and "grasp" or "reach")
	local action = { target = latest.target and { latest.target.X, latest.target.Y, latest.target.Z } or nil,
		grip = latest.grip }
	ep:record(obs, action, -0.01 * toCube - (obs.holding and 0.02 * cubeToBin or 0), subgoal)
	if cubeToBin < 1.7 and cube.Position.Y < 2 and not obs.holding then
		ep:finish(true, 1, SERVER); cube:Destroy(); cube = spawnCube(); ep = newEpisode()
	elseif ep:length() > 1500 then
		ep:finish(false, 0, SERVER); cube:Destroy(); cube = spawnCube(); ep = newEpisode()
	end
end)
'''

CLIENT_SRC = r'''--!strict
-- G4 Robot controller (cloned into PlayerGui by the server). Aim the gripper with the mouse,
-- click to grab/release.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local UIS = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local player = Players.LocalPlayer
local control = RS:WaitForChild("G4Control")
local mouse = player:GetMouse()
local grip = false

local gui = Instance.new("ScreenGui"); gui.ResetOnSpawn = false; gui.Parent = player:WaitForChild("PlayerGui")
local lbl = Instance.new("TextLabel")
lbl.Size = UDim2.new(0, 380, 0, 40); lbl.Position = UDim2.new(0, 20, 0, 20)
lbl.BackgroundTransparency = 0.4; lbl.BackgroundColor3 = Color3.new(0, 0, 0)
lbl.TextColor3 = Color3.new(1, 1, 1); lbl.Font = Enum.Font.GothamBold; lbl.TextScaled = true
lbl.Text = "SO-101 · move mouse to aim · click to grab/release"; lbl.Parent = gui

UIS.InputBegan:Connect(function(i, gp)
	if gp then return end
	if i.UserInputType == Enum.UserInputType.MouseButton1 then
		grip = not grip
		lbl.Text = grip and "GRIPPER CLOSED — drop it in the green bin" or "GRIPPER OPEN — grab the cube"
	end
end)

local acc = 0
RunService.RenderStepped:Connect(function(dt)
	acc += dt; if acc < 0.03 then return end; acc = 0
	if mouse.Hit then control:FireServer(mouse.Hit.Position, grip) end
end)
'''


def _cdata(s: str) -> str:
    return "<![CDATA[" + s.replace("]]>", "]] >") + "]]>"


def _script(name, src, ref, cls="Script", disabled=False):
    return (f'<Item class="{cls}" referent="{ref}"><Properties>'
            f'<string name="Name">{name}</string>'
            f'<bool name="Disabled">{"true" if disabled else "false"}</bool>'
            f'<ProtectedString name="Source">{_cdata(src)}</ProtectedString></Properties></Item>')


def _module(name, src, ref):
    return (f'<Item class="ModuleScript" referent="{ref}"><Properties>'
            f'<string name="Name">{name}</string>'
            f'<ProtectedString name="Source">{_cdata(src)}</ProtectedString></Properties></Item>')


def _stringvalue(name, val, ref):
    return (f'<Item class="StringValue" referent="{ref}"><Properties>'
            f'<string name="Name">{name}</string>'
            f'<string name="Value">{html.escape(val)}</string></Properties></Item>')


def main():
    so101 = read("SO101.lua")
    trace = read("Trace.lua").replace("{{SERVER_URL}}", SERVER_URL)
    children = "\n".join([
        _module("SO101", so101, "g4_so101"),
        _module("Trace", trace, "g4_trace"),
        _stringvalue("SERVER_URL", SERVER_URL, "g4_url"),
        _script("ClientTemplate", CLIENT_SRC, "g4_client", cls="LocalScript", disabled=True),
        _script("DemoServer", SERVER_SRC, "g4_server", cls="Script", disabled=False),
    ])
    folder = (f'<Item class="Folder" referent="g4_root"><Properties>'
              f'<string name="Name">G4RobotDemo</string></Properties>\n{children}\n</Item>')
    xml = ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n'
           "<External>null</External>\n<External>nil</External>\n" + folder + "\n</roblox>\n")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"wrote {os.path.abspath(OUT)}  ({len(xml)} bytes)")


if __name__ == "__main__":
    main()
