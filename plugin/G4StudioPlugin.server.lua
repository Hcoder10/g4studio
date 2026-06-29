--!nonstrict
-- G4 Studio — Roblox Studio plugin (streaming).
-- Type a prompt; a Gemma-4 swarm on Cerebras designs + builds a playable obby
-- LIVE in your Workspace, stage by stage, with a per-agent activity feed.

local HttpService = game:GetService("HttpService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")

local DEFAULT_SERVER = "http://localhost:8000"
local SERVER_SETTING = "G4Studio_ServerURL"

local function serverUrl()
	local saved = plugin:GetSetting(SERVER_SETTING)
	if type(saved) == "string" and #saved > 0 then return saved end
	return DEFAULT_SERVER
end

local MAT = {
	Plastic = Enum.Material.Plastic, SmoothPlastic = Enum.Material.SmoothPlastic,
	Neon = Enum.Material.Neon, Wood = Enum.Material.Wood, WoodPlanks = Enum.Material.WoodPlanks,
	Marble = Enum.Material.Marble, Slate = Enum.Material.Slate, Concrete = Enum.Material.Concrete,
	Granite = Enum.Material.Granite, Brick = Enum.Material.Brick, Pebble = Enum.Material.Pebble,
	Cobblestone = Enum.Material.Cobblestone, Metal = Enum.Material.Metal,
	DiamondPlate = Enum.Material.DiamondPlate, Grass = Enum.Material.Grass, Sand = Enum.Material.Sand,
	Fabric = Enum.Material.Fabric, Ice = Enum.Material.Ice, Glass = Enum.Material.Glass, Foil = Enum.Material.Foil,
}

local SHAPES = {
	Ball = Enum.PartType.Ball, Cylinder = Enum.PartType.Cylinder, Block = Enum.PartType.Block,
}

-- ============================ UI ============================================
local toolbar = plugin:CreateToolbar("G4 Studio")
local button = toolbar:CreateButton("G4 Studio",
	"Generate a playable obby with Gemma-4 on Cerebras", "rbxassetid://4458901886")

local info = DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, true, false, 360, 440, 320, 360)
local widget = plugin:CreateDockWidgetPluginGui("G4StudioWidget", info)
widget.Title = "G4 Studio"

local bg = Instance.new("Frame")
bg.Size = UDim2.fromScale(1, 1)
bg.BackgroundColor3 = Color3.fromRGB(13, 19, 29)
bg.BorderSizePixel = 0
bg.Parent = widget
local pad = Instance.new("UIPadding")
pad.PaddingTop = UDim.new(0, 12); pad.PaddingBottom = UDim.new(0, 12)
pad.PaddingLeft = UDim.new(0, 12); pad.PaddingRight = UDim.new(0, 12)
pad.Parent = bg
local layout = Instance.new("UIListLayout")
layout.Padding = UDim.new(0, 8); layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Parent = bg

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, 0, 0, 22); title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold; title.TextSize = 16
title.TextXAlignment = Enum.TextXAlignment.Left
title.TextColor3 = Color3.fromRGB(29, 233, 182)
title.Text = "G4 STUDIO  ·  Gemma-4 on Cerebras"
title.LayoutOrder = 1; title.Parent = bg

local promptBox = Instance.new("TextBox")
promptBox.Size = UDim2.new(1, 0, 0, 56); promptBox.BackgroundColor3 = Color3.fromRGB(18, 26, 38)
promptBox.BorderSizePixel = 0; promptBox.Font = Enum.Font.Gotham; promptBox.TextSize = 14
promptBox.TextColor3 = Color3.fromRGB(230, 237, 243)
promptBox.PlaceholderText = "Describe an obby…"
promptBox.Text = "neon lava parkour with moving platforms, spinning blades and 2 checkpoints"
promptBox.TextWrapped = true; promptBox.TextXAlignment = Enum.TextXAlignment.Left
promptBox.TextYAlignment = Enum.TextYAlignment.Top; promptBox.ClearTextOnFocus = false
promptBox.MultiLine = true; promptBox.LayoutOrder = 2; promptBox.Parent = bg
local pbpad = Instance.new("UIPadding"); pbpad.PaddingLeft = UDim.new(0, 8); pbpad.PaddingTop = UDim.new(0, 6); pbpad.Parent = promptBox
local pbc = Instance.new("UICorner"); pbc.CornerRadius = UDim.new(0, 8); pbc.Parent = promptBox

local buildBtn = Instance.new("TextButton")
buildBtn.Size = UDim2.new(1, 0, 0, 38); buildBtn.BackgroundColor3 = Color3.fromRGB(29, 233, 182)
buildBtn.BorderSizePixel = 0; buildBtn.Font = Enum.Font.GothamBold; buildBtn.TextSize = 15
buildBtn.TextColor3 = Color3.fromRGB(4, 18, 26); buildBtn.Text = "Build ⚡"
buildBtn.LayoutOrder = 3; buildBtn.Parent = bg
local btc = Instance.new("UICorner"); btc.CornerRadius = UDim.new(0, 8); btc.Parent = buildBtn

local playBtn = Instance.new("TextButton")
playBtn.Size = UDim2.new(1, 0, 0, 32); playBtn.BackgroundColor3 = Color3.fromRGB(74, 163, 255)
playBtn.BorderSizePixel = 0; playBtn.Font = Enum.Font.GothamBold; playBtn.TextSize = 14
playBtn.TextColor3 = Color3.fromRGB(4, 18, 26); playBtn.Text = "🤖 Agent Playtest"
playBtn.LayoutOrder = 3; playBtn.Parent = bg
local ptc = Instance.new("UICorner"); ptc.CornerRadius = UDim.new(0, 8); ptc.Parent = playBtn

local agentList = Instance.new("ScrollingFrame")
agentList.Size = UDim2.new(1, 0, 1, -150); agentList.BackgroundColor3 = Color3.fromRGB(10, 15, 23)
agentList.BorderSizePixel = 0; agentList.ScrollBarThickness = 4
agentList.AutomaticCanvasSize = Enum.AutomaticSize.Y; agentList.CanvasSize = UDim2.new()
agentList.LayoutOrder = 4; agentList.Parent = bg
local alc = Instance.new("UICorner"); alc.CornerRadius = UDim.new(0, 8); alc.Parent = agentList
local alLayout = Instance.new("UIListLayout"); alLayout.Padding = UDim.new(0, 6)
alLayout.SortOrder = Enum.SortOrder.LayoutOrder; alLayout.Parent = agentList
local alPad = Instance.new("UIPadding")
alPad.PaddingTop = UDim.new(0, 8); alPad.PaddingBottom = UDim.new(0, 8)
alPad.PaddingLeft = UDim.new(0, 8); alPad.PaddingRight = UDim.new(0, 8); alPad.Parent = agentList

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, 0, 0, 30); status.BackgroundTransparency = 1
status.Font = Enum.Font.Gotham; status.TextSize = 13; status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left; status.TextYAlignment = Enum.TextYAlignment.Top
status.TextColor3 = Color3.fromRGB(125, 141, 163)
status.Text = "Ready · " .. serverUrl()
status.LayoutOrder = 5; status.Parent = bg

button.Click:Connect(function() widget.Enabled = not widget.Enabled end)

-- ============================ Agent cards ==================================
local cards = {}
local cardOrder = 0

local function clearAgents()
	for _, c in pairs(cards) do c:Destroy() end
	cards = {}; cardOrder = 0
end

local function upsertAgent(id, name, role)
	local card = cards[id]
	if not card then
		cardOrder += 1
		card = Instance.new("Frame")
		card.Name = id; card.Size = UDim2.new(1, -2, 0, 44)
		card.BackgroundColor3 = Color3.fromRGB(18, 26, 38); card.BorderSizePixel = 0
		card.LayoutOrder = cardOrder; card.Parent = agentList
		local cc = Instance.new("UICorner"); cc.CornerRadius = UDim.new(0, 6); cc.Parent = card
		local bar = Instance.new("Frame"); bar.Name = "Bar"; bar.Size = UDim2.new(0, 3, 1, 0)
		bar.BorderSizePixel = 0; bar.BackgroundColor3 = Color3.fromRGB(74, 163, 255); bar.Parent = card
		local nm = Instance.new("TextLabel"); nm.Name = "NameL"; nm.BackgroundTransparency = 1
		nm.Position = UDim2.new(0, 10, 0, 5); nm.Size = UDim2.new(1, -14, 0, 16)
		nm.Font = Enum.Font.GothamBold; nm.TextSize = 13; nm.TextXAlignment = Enum.TextXAlignment.Left
		nm.TextColor3 = Color3.fromRGB(230, 237, 243); nm.Parent = card
		local st = Instance.new("TextLabel"); st.Name = "StatL"; st.BackgroundTransparency = 1
		st.Position = UDim2.new(0, 10, 0, 22); st.Size = UDim2.new(1, -14, 0, 16)
		st.Font = Enum.Font.Gotham; st.TextSize = 12; st.TextXAlignment = Enum.TextXAlignment.Left
		st.TextColor3 = Color3.fromRGB(125, 141, 163); st.Parent = card
		cards[id] = card
	end
	card.NameL.Text = (role and ("[" .. role .. "] ") or "") .. (name or id)
	return card
end

local function setWorking(id)
	local card = cards[id]; if not card then return end
	card.Bar.BackgroundColor3 = Color3.fromRGB(74, 163, 255)
	card.StatL.Text = "● working…"
end

local function setDone(id, detail, isDirector)
	local card = cards[id]; if not card then return end
	card.Bar.BackgroundColor3 = isDirector and Color3.fromRGB(255, 212, 0) or Color3.fromRGB(29, 233, 182)
	card.StatL.Text = "✓ " .. (detail or "done")
end

-- ============================ Building =====================================
local buildRoot, buildFolders

local function ensureRoot(rootName)
	rootName = rootName or "G4Game"
	local ws = workspace
	for _, n in ipairs({ "G4Obby", "G4Game", rootName }) do
		local o = ws:FindFirstChild(n); if o then o:Destroy() end
	end
	buildRoot = Instance.new("Folder"); buildRoot.Name = rootName; buildRoot.Parent = ws
	buildFolders = { _root = buildRoot }
end

-- folders are created on demand so any genre's folder set works
local function getFolder(name)
	if name == nil or name == "_root" then return buildRoot end
	local f = buildFolders[name]
	if not f then
		f = Instance.new("Folder"); f.Name = name; f.Parent = buildRoot; buildFolders[name] = f
	end
	return f
end

local function applyOps(ops)
	if not ops then return end
	for i, p in ipairs(ops) do
		local ok = pcall(function()
			local inst = Instance.new(p.class)
			inst.Name = p.name
			inst.Anchored = true
			inst.CanCollide = (p.cc ~= false)
			inst.Size = Vector3.new(p.size[1], p.size[2], p.size[3])
			if p.rot then
				inst.CFrame = CFrame.new(p.pos[1], p.pos[2], p.pos[3]) * CFrame.Angles(0, math.rad(p.rot), 0)
			else
				inst.CFrame = CFrame.new(p.pos[1], p.pos[2], p.pos[3])
			end
			inst.Color = Color3.fromRGB(p.color[1], p.color[2], p.color[3])
			inst.Material = MAT[p.material] or Enum.Material.SmoothPlastic
			if p.shape and inst:IsA("Part") and SHAPES[p.shape] then inst.Shape = SHAPES[p.shape] end
			if p.light then
				local L = Instance.new("PointLight")
				L.Color = Color3.fromRGB(p.light.color[1], p.light.color[2], p.light.color[3])
				L.Brightness = p.light.brightness
				L.Range = p.light.range
				L.Parent = inst
			end
			inst.Parent = getFolder(p.folder)
		end)
		if ok and i % 5 == 0 then task.wait() end
	end
end

-- ===== Authored games: build in REAL Studio + vision loop =====
-- Place gameplay as real Scripts that run at game RUNTIME (not in the plugin/edit runtime).
local function placeScripts(server, client)
	local SSS = game:GetService("ServerScriptService")
	local oldS = SSS:FindFirstChild("G4Server"); if oldS then oldS:Destroy() end
	if server and #server > 0 then
		local sc = Instance.new("Script"); sc.Name = "G4Server"; sc.Source = server; sc.Parent = SSS
	end
	local SP = game:GetService("StarterPlayer")
	local SPS = SP:FindFirstChild("StarterPlayerScripts")
	if not SPS then SPS = Instance.new("StarterPlayerScripts"); SPS.Parent = SP end
	local oldC = SPS:FindFirstChild("G4Client"); if oldC then oldC:Destroy() end
	if client and #client > 0 then
		local lc = Instance.new("LocalScript"); lc.Name = "G4Client"; lc.Source = client; lc.Parent = SPS
	end
end

-- ===== AI playtest: a real Play Solo session via StudioTestService =====
local TEST_SERVER_SRC = [==[
local StudioTestService = game:GetService("StudioTestService")
local RunService = game:GetService("RunService")
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local HttpService = game:GetService("HttpService")
local SERVER = "{{SERVER_URL}}"
if not RunService:IsRunning() then return end
if StudioTestService:GetTestArgs() ~= "G4PLAYTEST" then return end

local camRemote = Instance.new("RemoteEvent"); camRemote.Name = "G4CamRemote"; camRemote.Parent = RS
local camCF = nil
camRemote.OnServerEvent:Connect(function(_, cf) camCF = cf end)

task.spawn(function()
	local plr = Players:GetPlayers()[1] or Players.PlayerAdded:Wait()
	local char = plr.Character or plr.CharacterAdded:Wait()
	local hum = char:WaitForChild("Humanoid")
	local hrp = char:WaitForChild("HumanoidRootPart")
	pcall(function() hrp:SetNetworkOwner(nil) end)
	task.wait(1.5)
	local function readState()
		local ls = {}
		local lsf = plr:FindFirstChild("leaderstats")
		if lsf then for _, v in ipairs(lsf:GetChildren()) do ls[v.Name] = v.Value end end
		return { pos = { math.floor(hrp.Position.X), math.floor(hrp.Position.Y), math.floor(hrp.Position.Z) },
			health = hum.Health, leaderstats = ls }
	end
	local verdict, score = "playtest ended", 5
	for step = 0, 40 do
		local ok, res = pcall(function()
			return HttpService:RequestAsync({ Url = SERVER .. "/api/playbot", Method = "POST",
				Headers = { ["Content-Type"] = "application/json" },
				Body = HttpService:JSONEncode({ state = readState(), step = step }) })
		end)
		if not ok or not res.Success then break end
		local data = HttpService:JSONDecode(res.Body)
		local dir = Vector3.zero
		if camCF then
			local look = camCF.LookVector; look = Vector3.new(look.X, 0, look.Z); if look.Magnitude > 0 then look = look.Unit end
			local rt = camCF.RightVector; rt = Vector3.new(rt.X, 0, rt.Z); if rt.Magnitude > 0 then rt = rt.Unit end
			local a = data.action
			if a == "forward" then dir = look elseif a == "back" then dir = -look
			elseif a == "left" then dir = -rt elseif a == "right" then dir = rt end
		end
		hum:Move(dir, false)
		if data.action == "jump" then hum.Jump = true end
		if data.done then verdict = data.verdict or verdict; score = data.score or score; break end
		task.wait(0.35)
	end
	pcall(function() hum:Move(Vector3.zero) end)
	StudioTestService:EndTest({ verdict = verdict, score = score })
end)
]==]

local TEST_CLIENT_SRC = [==[
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local camRemote = RS:WaitForChild("G4CamRemote", 8)
if not camRemote then return end
local cam = workspace.CurrentCamera
while camRemote and camRemote.Parent do
	task.wait(0.2)
	if cam then camRemote:FireServer(cam.CFrame) end
end
]==]

local function placeTestScripts()
	local SSS = game:GetService("ServerScriptService")
	local SP = game:GetService("StarterPlayer")
	local SPS = SP:FindFirstChild("StarterPlayerScripts") or Instance.new("StarterPlayerScripts", SP)
	local oldS = SSS:FindFirstChild("G4TestServer"); if oldS then oldS:Destroy() end
	local s = Instance.new("Script"); s.Name = "G4TestServer"
	s.Source = TEST_SERVER_SRC:gsub("{{SERVER_URL}}", function() return serverUrl() end)
	s.Parent = SSS
	local oldC = SPS:FindFirstChild("G4TestClient"); if oldC then oldC:Destroy() end
	local c = Instance.new("LocalScript"); c.Name = "G4TestClient"; c.Source = TEST_CLIENT_SRC; c.Parent = SPS
end

local function removeTestScripts()
	for _, where in ipairs({ game:GetService("ServerScriptService"):FindFirstChild("G4TestServer"),
		game:GetService("StarterPlayer"):FindFirstChild("StarterPlayerScripts") and
		game:GetService("StarterPlayer").StarterPlayerScripts:FindFirstChild("G4TestClient"),
		game:GetService("ReplicatedStorage"):FindFirstChild("G4CamRemote") }) do
		if where then where:Destroy() end
	end
end

-- Run the BUILD code in EDIT mode (plugin runtime) to construct the static world.
local function buildInStudio(buildSrc)
	if not loadstring then return false, "loadstring unavailable" end
	local old = workspace:FindFirstChild("G4Game"); if old then old:Destroy() end
	local fn, lerr = loadstring(buildSrc)
	if not fn then return false, "compile: " .. tostring(lerr) end
	local ok, rerr = pcall(fn)
	if not ok then return false, "runtime: " .. tostring(rerr) end
	return true
end

local function frameCamera()
	local root = workspace:FindFirstChild("G4Game")
	if not root then return end
	local minv, maxv
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("BasePart") then
			local p = d.Position
			if not minv then minv = p; maxv = p
			else
				minv = Vector3.new(math.min(minv.X, p.X), math.min(minv.Y, p.Y), math.min(minv.Z, p.Z))
				maxv = Vector3.new(math.max(maxv.X, p.X), math.max(maxv.Y, p.Y), math.max(maxv.Z, p.Z))
			end
		end
	end
	if not minv then return end
	local center = (minv + maxv) / 2
	local dist = math.max((maxv - minv).Magnitude * 0.65, 45)
	local cam = workspace.CurrentCamera
	if cam then
		pcall(function()
			cam.CFrame = CFrame.lookAt(center + Vector3.new(0, dist * 0.95, dist * 0.95), center)
		end)
	end
end

local function runStudioVision(build, server, client)
	task.spawn(function()
		local current = build
		for attempt = 0, 2 do
			task.wait(0.6)
			local ok, res = pcall(function()
				return HttpService:RequestAsync({
					Url = serverUrl() .. "/api/vision", Method = "POST",
					Headers = { ["Content-Type"] = "application/json" },
					Body = HttpService:JSONEncode({ build = current, attempt = attempt }),
				})
			end)
			if not ok or not res.Success then break end
			local data = HttpService:JSONDecode(res.Body)
			if data.error then status.Text = "Playtester: " .. tostring(data.error); break end
			upsertAgent("playtester", "Playtester", "QA")
			setDone("playtester", "Studio render " .. tostring(data.score) .. "/10")
			status.Text = string.format("Playtester (Studio): %s/10 — %s",
				tostring(data.score), tostring(data.verdict or ""))
			if data.revised_build and #data.revised_build > 80 then
				upsertAgent("reviser", "Reviser", "Coder"); setWorking("reviser")
				current = data.revised_build
				local b2 = buildInStudio(current)
				setDone("reviser", "rebuilt the world")
				if not b2 then break end
				frameCamera()
			else
				break
			end
		end
		-- gameplay runs at game runtime, not in the plugin: place Server + Client scripts
		placeScripts(server, client)
		status.Text = "✅ World built + Server/Client scripts placed. Press PLAY."
	end)
end

local function handleEvent(ev)
	if ev.type == "genre" then
		status.Text = "Genre: " .. tostring(ev.genre) .. " — building live…"
	elseif ev.type == "redesign" then
		status.Text = "Playtester rejected (" .. tostring(ev.score) .. "/10) — Designer redesigning…"
	elseif ev.type == "reset" then
		ensureRoot(buildRoot and buildRoot.Name or "G4Game")
	elseif ev.type == "agent" then
		upsertAgent(ev.id, ev.name, ev.role)
		if ev.status == "done" then
			setDone(ev.id, ev.detail or ev.name, ev.id == "director")
		else
			setWorking(ev.id)
		end
	elseif ev.type == "agent_build" then
		setDone(ev.id, ev.detail)
		applyOps(ev.ops)
	elseif ev.type == "stage" then
		applyOps(ev.ops)
	elseif ev.type == "done" then
		local m = ev.metrics or {}
		if ev.authored and ev.build then
			-- BUILD the static world in REAL Studio (edit/plugin runtime); gameplay scripts
			-- are placed to run at game runtime, not in the plugin.
			status.Text = "Building '" .. tostring(ev.name or "game") .. "' in Studio…"
			local built, berr = buildInStudio(ev.build)
			if built then
				frameCamera()
				runStudioVision(ev.build, ev.server, ev.client)
			else
				placeScripts((ev.build or "") .. "\n\n" .. (ev.server or ""), ev.client)
				status.Text = "Live preview off (" .. tostring(berr) .. "). Scripts placed. Press PLAY."
			end
		else
			if ev.mechanics and buildRoot then
				local sc = Instance.new("Script"); sc.Name = "G4Mechanics"
				sc.Source = ev.mechanics; sc.Parent = buildRoot
			end
			status.Text = string.format("✅ '%s' · %d parts · %d agents · %d ms · Play to test",
				tostring(ev.name or "game"), tonumber(m.parts) or 0, tonumber(m.agents) or 0, tonumber(m.wall_ms) or 0)
		end
		return true
	elseif ev.type == "error" then
		status.Text = "Error: " .. tostring(ev.error)
		return true
	end
	return false
end

-- ============================ Run ==========================================
local busy = false
local function build()
	if busy then return end
	local prompt = promptBox.Text
	if prompt == "" then return end
	busy = true
	buildBtn.Text = "Building…"; buildBtn.BackgroundColor3 = Color3.fromRGB(74, 163, 255)
	clearAgents()
	status.Text = "Starting swarm on Cerebras…"

	task.spawn(function()
		local function done()
			busy = false
			buildBtn.Text = "Build ⚡"; buildBtn.BackgroundColor3 = Color3.fromRGB(29, 233, 182)
		end

		local startOk, startRes = pcall(function()
			return HttpService:RequestAsync({
				Url = serverUrl() .. "/api/generate/start", Method = "POST",
				Headers = { ["Content-Type"] = "application/json" },
				Body = HttpService:JSONEncode({ prompt = prompt }),
			})
		end)
		if not startOk then status.Text = "Server unreachable (is it running?):\n" .. tostring(startRes); done(); return end
		if not startRes.Success then status.Text = "HTTP " .. tostring(startRes.StatusCode); done(); return end
		local startData = HttpService:JSONDecode(startRes.Body)
		if not startData.job_id then status.Text = "No job id (" .. tostring(startData.error) .. ")"; done(); return end
		local job = startData.job_id

		ensureRoot(startData.root)
		local recording = nil
		pcall(function() recording = ChangeHistoryService:TryBeginRecording("G4 Studio build") end)

		local cursor, finished, guard = 0, false, 0
		while not finished and guard < 600 do
			guard += 1
			local ok, res = pcall(function()
				return HttpService:RequestAsync({
					Url = serverUrl() .. "/api/generate/poll?job=" .. job .. "&cursor=" .. cursor,
					Method = "GET",
				})
			end)
			if ok and res.Success then
				local data = HttpService:JSONDecode(res.Body)
				for _, ev in ipairs(data.events or {}) do
					if handleEvent(ev) then finished = true end
				end
				cursor = data.cursor or cursor
				if data.done then finished = true end
			end
			if not finished then task.wait(0.1) end
		end

		if recording then
			pcall(function()
				ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
			end)
		end
		done()
	end)
end
buildBtn.MouseButton1Click:Connect(build)

local function agentPlaytest()
	if busy then return end
	busy = true
	status.Text = "Placing test bot + starting Play Solo…"
	pcall(function() game:GetService("HttpService").HttpEnabled = true end)
	placeTestScripts()
	task.spawn(function()
		local sok, sts = pcall(function() return game:GetService("StudioTestService") end)
		if not sok or not sts then
			status.Text = "StudioTestService unavailable (update Studio)."
			removeTestScripts(); busy = false; return
		end
		local rok, result = pcall(function() return sts:ExecutePlayModeAsync("G4PLAYTEST") end)
		removeTestScripts()
		if rok and type(result) == "table" then
			status.Text = string.format("🤖 Playtest: %s/10 — %s", tostring(result.score), tostring(result.verdict))
		elseif rok then
			status.Text = "🤖 Playtest finished."
		else
			status.Text = "Playtest error: " .. tostring(result)
		end
		busy = false
	end)
end
playBtn.MouseButton1Click:Connect(agentPlaytest)

print("[G4Studio] plugin loaded. Server: " .. serverUrl())
