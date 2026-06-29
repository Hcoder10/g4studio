--!strict
-- DEMO (server): SO-101 pick-and-place that collects traces naturally. Drop SO101 + Trace as
-- ModuleScripts under ReplicatedStorage.G4Robots, put this Script in ServerScriptService and the
-- matching LocalScript in StarterPlayerScripts, set G4Robots.SERVER_URL, then Play.
-- The player moves the mouse to aim the gripper (IK) and clicks to grab/release. Every tick is
-- logged; dropping the cube in the bin = a successful episode shipped to /api/trace.

local RS = game:GetService("ReplicatedStorage")
local CollectionService = game:GetService("CollectionService")
local RunService = game:GetService("RunService")

local SO101 = require(RS:WaitForChild("G4Robots"):WaitForChild("SO101"))
local Trace = require(RS.G4Robots:WaitForChild("Trace"))
local SERVER = (RS.G4Robots:FindFirstChild("SERVER_URL") and RS.G4Robots.SERVER_URL.Value) or "http://127.0.0.1:8000"

local control = RS:FindFirstChild("G4Control") or Instance.new("RemoteEvent")
control.Name = "G4Control"; control.Parent = RS

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

local latest = { target = nil :: Vector3?, grip = false }
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
	local reward = -0.01 * toCube - (obs.holding and 0.02 * cubeToBin or 0)
	local action = { target = latest.target and { latest.target.X, latest.target.Y, latest.target.Z } or nil,
		grip = latest.grip }
	ep:record(obs, action, reward, subgoal)

	if cubeToBin < 1.7 and cube.Position.Y < 2 and not obs.holding then
		ep:finish(true, 1, SERVER)
		cube:Destroy(); cube = spawnCube(); ep = newEpisode()
	elseif ep:length() > 1500 then
		ep:finish(false, 0, SERVER)
		cube:Destroy(); cube = spawnCube(); ep = newEpisode()
	end
end)
