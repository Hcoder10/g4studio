--!strict
-- G4 Robot-Game Harness (PROVIDED, fixed). It owns the robot: builds the SO-101, hands players the
-- hover controller, runs the arm, and records EVERY step as a manipulation trace. A Gemma-authored
-- Game module only supplies the fun (scene + rules + scoring + juice + per-step skill labels), so
-- generated games can't break the robot, the IK, or the data pipeline. Playing the game IS labeling
-- training data.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local CollectionService = game:GetService("CollectionService")
local Debris = game:GetService("Debris")

local kit = script.Parent  -- the G4RobotGame folder holds SO101, Trace, Game, ControlClient, SERVER_URL
local SO101 = require(kit:WaitForChild("SO101"))
local Trace = require(kit:WaitForChild("Trace"))
local SERVER = (kit:FindFirstChild("SERVER_URL") and kit.SERVER_URL.Value) or "http://127.0.0.1:8000"
pcall(function() game:GetService("HttpService").HttpEnabled = true end)

-- control + HUD remotes; hand each player the hover controller
local control = RS:FindFirstChild("G4Control") or Instance.new("RemoteEvent")
control.Name = "G4Control"; control.Parent = RS
local hud = RS:FindFirstChild("G4HUD") or Instance.new("RemoteEvent")
hud.Name = "G4HUD"; hud.Parent = RS
local clientTpl = kit:WaitForChild("ControlClient")
local function giveClient(plr)
	local pg = plr:WaitForChild("PlayerGui")
	if pg:FindFirstChild("G4Control") then return end
	local c = clientTpl:Clone(); c.Name = "G4Control"; c.Disabled = false; c.Parent = pg
end
Players.PlayerAdded:Connect(giveClient)
for _, p in ipairs(Players:GetPlayers()) do task.spawn(giveClient, p) end

-- a sleek work surface + an enclosed arena (open toward the camera) so it reads as a separate stage
local arena = Instance.new("Folder"); arena.Name = "Arena"; arena.Parent = workspace
local tablePart = Instance.new("Part")
tablePart.Name = "Table"; tablePart.Anchored = true; tablePart.Size = Vector3.new(15, 1, 14)
tablePart.Position = Vector3.new(0, 0, 2.5); tablePart.Color = Color3.fromRGB(38, 41, 52)
tablePart.Material = Enum.Material.SmoothPlastic; tablePart.Parent = arena
local function neon(size, pos, color)
	local p = Instance.new("Part"); p.Anchored = true; p.CanCollide = false; p.Size = size
	p.Position = pos; p.Color = color or Color3.fromRGB(90, 170, 255); p.Material = Enum.Material.Neon
	p.Parent = arena
end
neon(Vector3.new(15.4, 0.25, 14.4), Vector3.new(0, 0.6, 2.5), Color3.fromRGB(70, 150, 255))  -- table edge glow
local function wall(size, pos)
	local w = Instance.new("Part"); w.Anchored = true; w.Size = size; w.Position = pos
	w.Color = Color3.fromRGB(24, 26, 34); w.Material = Enum.Material.SmoothPlastic; w.Parent = arena
	neon(Vector3.new(size.X, 0.3, size.Z), pos + Vector3.new(0, size.Y / 2, 0))  -- top trim
end
wall(Vector3.new(16, 8, 1), Vector3.new(0, 4.5, -4.5))     -- back (far from camera)
wall(Vector3.new(1, 8, 13), Vector3.new(-7.5, 4.5, 2.5))   -- left
wall(Vector3.new(1, 8, 13), Vector3.new(7.5, 4.5, 2.5))    -- right
local arm = SO101.new(workspace, CFrame.new(0, 1.5, -1))

local latest = { target = nil :: Vector3?, grip = false, wristRoll = 0 }
control.OnServerEvent:Connect(function(_, t, grip, wr)
	latest.target = t; latest.grip = grip and true or false; latest.wristRoll = wr or 0
end)

-- the reachable forward workcell (where games place objects)
local SH = arm.linkCF[2].Position
local REGION = { center = Vector3.new(SH.X, 1.2, SH.Z + 4.2), reach = 5.5, table = tablePart }

-- juice + scene helpers exposed to the game ----------------------------------
local sceneFolder = Instance.new("Folder"); sceneFolder.Name = "GameScene"; sceneFolder.Parent = workspace
local function clearScene()
	sceneFolder:ClearAllChildren()
	if arm.grasped then arm.grasped = nil end
end
-- safety net: any unanchored object the game spawns is a manipulable, so make it graspable even if
-- the game forgot to tag it. (Bins/zones are anchored, so they're left alone.)
local function autoTagGraspables()
	for _, c in ipairs(sceneFolder:GetChildren()) do
		if c:IsA("BasePart") and not c.Anchored and not CollectionService:HasTag(c, "Graspable") then
			CollectionService:AddTag(c, "Graspable")
		end
	end
end
local function popup(pos: Vector3, text: string, color: Color3?)
	local p = Instance.new("Part"); p.Anchored = true; p.CanCollide = false; p.Transparency = 1
	p.Size = Vector3.new(1, 1, 1); p.Position = pos; p.Parent = workspace
	local bb = Instance.new("BillboardGui"); bb.Size = UDim2.new(0, 200, 0, 50); bb.AlwaysOnTop = true
	bb.StudsOffset = Vector3.new(0, 2, 0); bb.Parent = p
	local tl = Instance.new("TextLabel"); tl.Size = UDim2.new(1, 0, 1, 0); tl.BackgroundTransparency = 1
	tl.Text = text; tl.TextColor3 = color or Color3.new(1, 1, 1); tl.Font = Enum.Font.GothamBlack
	tl.TextScaled = true; tl.Parent = bb
	task.spawn(function()
		for i = 1, 30 do p.Position += Vector3.new(0, 0.06, 0); tl.TextTransparency = i / 30; task.wait(0.03) end
	end)
	Debris:AddItem(p, 1.2)
end
local function burst(pos: Vector3, color: Color3?)
	local p = Instance.new("Part"); p.Anchored = true; p.CanCollide = false; p.Transparency = 1
	p.Position = pos; p.Size = Vector3.new(1, 1, 1); p.Parent = workspace
	local e = Instance.new("ParticleEmitter"); e.Color = ColorSequence.new(color or Color3.new(1, 0.9, 0.2))
	e.Lifetime = NumberRange.new(0.4, 0.7); e.Speed = NumberRange.new(8, 14); e.Rate = 0
	e.SpreadAngle = Vector2.new(180, 180); e.Parent = p; e:Emit(40)
	Debris:AddItem(p, 1)
end
local function ding(good: boolean)
	local s = Instance.new("Sound"); s.SoundId = good and "rbxassetid://9114128602" or "rbxassetid://9114134790"
	s.Volume = 0.5; s.Parent = workspace; s:Play(); Debris:AddItem(s, 2)
end

-- episode + ctx --------------------------------------------------------------
local HttpService = game:GetService("HttpService")
local Game = require(kit:WaitForChild("Game"))
local episode, epStart, ended
local MASTER_AT = 2                   -- consecutive wins before Gemma forges a harder challenge
local mastered, totalWins, winTimes = 0, 0, {}
local live = false                       -- true only after the GO countdown (gates scoring/recording)
local extendGame, safeSetup, startRound  -- forward decls (defined after ctx)
local function newEpisode()
	episode = Trace.new(Game.task or "so101_game", {
		robot = "SO101", game = Game.name or "game", fps = 60,
		action_space = "joint_position",  -- LeRobot-native: state = joint angles, action = joint targets
		state_names = SO101.STATE_NAMES, action_names = SO101.STATE_NAMES,
	})
	epStart = os.clock(); ended = false
end

local ctx = {}
ctx.arm = arm
ctx.region = REGION
ctx.state = {}
function ctx.holding() return arm.grasped end
function ctx.dist(a, b) return (a - b).Magnitude end
function ctx.rand(lo, hi) return lo + math.random() * (hi - lo) end
function ctx.spawnCube(pos: Vector3, color: Color3?, size: number?)
	local s = size or 1
	local c = Instance.new("Part"); c.Name = "Cube"; c.Size = Vector3.new(s, s, s); c.Anchored = false
	c.Color = color or Color3.fromRGB(255, 170, 0); c.Material = Enum.Material.SmoothPlastic
	c.Position = pos; c.Parent = sceneFolder; CollectionService:AddTag(c, "Graspable")
	return c
end
function ctx.spawnBin(pos: Vector3, color: Color3?, size: Vector3?)
	local b = Instance.new("Part"); b.Name = "Bin"; b.Anchored = true
	b.Size = size or Vector3.new(2.5, 1, 2.5); b.Position = pos
	b.Color = color or Color3.fromRGB(0, 170, 90); b.Material = Enum.Material.SmoothPlastic; b.Parent = sceneFolder
	return b
end
function ctx.spawnPart(props)
	local p = Instance.new("Part"); p.Anchored = true; p.Parent = sceneFolder
	for k, v in pairs(props) do
		if k == "Color3" then k = "Color" end            -- common slip: the property is Color
		pcall(function() (p :: any)[k] = v end)          -- ignore unknown props, never crash the round
	end
	return p
end
function ctx.makeGraspable(p: BasePart) CollectionService:AddTag(p, "Graspable") end
-- give the arm a tool to hold FROM THE START (bucket / wand / sponge) — makes easy "use the tool"
-- games. props = Part props; offset = CFrame of the tool relative to the gripper tip.
function ctx.attachTool(props, offset)
	local p = Instance.new("Part"); p.Anchored = true; p.CanCollide = false; p.Parent = sceneFolder
	for k, v in pairs(props or {}) do
		if k == "Color3" then k = "Color" end
		pcall(function() (p :: any)[k] = v end)
	end
	arm:setTool(p, offset)
	return p
end
function ctx.hud(text: string) hud:FireAllClients("hud", text) end
function ctx.popup(pos, text, color) popup(pos, text, color) end
function ctx.burst(pos, color) burst(pos, color) end
function ctx.ding(good) ding(good and true or false) end
function ctx.win(score: number?)
	if ended then return end
	ended = true; ding(true); ctx.hud("✅ +" .. tostring(score or 0))
	episode:finish(true, score or 1, SERVER)
	totalWins += 1; mastered += 1; table.insert(winTimes, os.clock() - epStart)
	task.delay(0.7, function()
		if mastered >= MASTER_AT then mastered = 0; task.spawn(extendGame)
		else task.spawn(startRound) end
	end)
end
function ctx.lose()
	if ended then return end
	ended = true; ding(false); mastered = 0  -- a loss breaks the mastery streak
	episode:finish(false, 0, SERVER)
	task.delay(0.7, function() task.spawn(startRound) end)
end

-- Gemma extends the curriculum: once a player MASTERS the current game, fetch a harder one and
-- hot-swap it in (needs HTTP + LoadStringEnabled). Falls back to replaying the current game.
local function fetchExtension()
	local ok, res = pcall(function()
		return HttpService:RequestAsync({
			Url = SERVER .. "/api/robotgame/extend", Method = "POST",
			Headers = { ["Content-Type"] = "application/json" },
			Body = HttpService:JSONEncode({
				name = Game.name, task = Game.task, skill = Game.skill,
				wins = totalWins, avg_seconds = winTimes[#winTimes],
			}),
		})
	end)
	if not ok or not res or not res.Success then return nil end
	local good, data = pcall(function() return HttpService:JSONDecode(res.Body) end)
	if not good or not data.source then return nil end
	if not loadstring then return nil, "loadstring" end
	local chunk = loadstring(data.source)
	if not chunk then return nil end
	local okg, g = pcall(chunk)
	if okg and type(g) == "table" and type(g.setup) == "function" and type(g.step) == "function" then
		return g
	end
	return nil
end
function extendGame()
	live = false
	ctx.hud("🔥 MASTERED! Gemma is forging a harder challenge…")
	local g, why = fetchExtension()
	if g then Game = g; ctx.hud("⚡ NEW CHALLENGE — " .. tostring(Game.name or "")); task.wait(0.8)
	elseif why == "loadstring" then ctx.hud("Enable LoadStringEnabled (Game Settings ▸ Security) to evolve games"); task.wait(1) end
	startRound()
end

-- run the game's setup safely: a buggy generated setup must not crash the robot/controls
function safeSetup()
	local ok, err = pcall(Game.setup, ctx)
	if not ok then
		warn("[G4Game] setup error: " .. tostring(err))
		ctx.hud("⚠ game setup error (see Output) — the arm still works")
	end
end

-- start a round: build the scene, run a 3-2-1-GO countdown, THEN go live (scoring + recording)
function startRound()
	live = false
	clearScene(); ctx.state = {}
	safeSetup()
	for _, n in ipairs({ "3", "2", "1", "GO!" }) do
		hud:FireAllClients("count", n); task.wait(0.7)
	end
	hud:FireAllClients("count", "")
	newEpisode()
	live = true
end

-- boot
task.spawn(startRound)

local smoothT = nil  -- low-passed IK goal: filters mouse noise so the arm doesn't jitter
RunService.Heartbeat:Connect(function(dt)
	autoTagGraspables()
	if latest.target then
		smoothT = smoothT and smoothT:Lerp(latest.target, 0.4) or latest.target
		arm:solveTo(smoothT)
	end
	arm:setTarget(5, latest.wristRoll)
	arm:grip(latest.grip and 0 or 1)
	arm:step(dt)            -- the arm is always controllable (you can pre-aim during the countdown)
	if ended or not live then return end   -- but no scoring/recording until GO
	ctx.t = os.clock() - epStart
	local reward, subgoal = 0, "idle"
	local ok, r, s = pcall(Game.step, ctx, dt)
	if ok then reward = tonumber(r) or 0; subgoal = (typeof(s) == "string" and s) or subgoal
	else warn("[G4Game] step error: " .. tostring(r)) end
	episode:record(arm:getObs(), arm:getAction(), reward, subgoal)  -- joint-space obs + action
end)
