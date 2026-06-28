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

local function ensureRoot()
	local ws = workspace
	local old = ws:FindFirstChild("G4Obby"); if old then old:Destroy() end
	buildRoot = Instance.new("Folder"); buildRoot.Name = "G4Obby"; buildRoot.Parent = ws
	buildFolders = { _root = buildRoot }
	for _, fn in ipairs({ "Platforms", "Hazards", "Checkpoints", "Moving", "Spinners", "Decor" }) do
		local f = Instance.new("Folder"); f.Name = fn; f.Parent = buildRoot; buildFolders[fn] = f
	end
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
			inst.CFrame = CFrame.new(p.pos[1], p.pos[2], p.pos[3])
			inst.Color = Color3.fromRGB(p.color[1], p.color[2], p.color[3])
			inst.Material = MAT[p.material] or Enum.Material.SmoothPlastic
			inst.Parent = buildFolders[p.folder] or buildRoot
		end)
		if ok and i % 5 == 0 then task.wait() end
	end
end

local function handleEvent(ev)
	if ev.type == "agent" then
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
		if ev.mechanics and buildRoot then
			local sc = Instance.new("Script"); sc.Name = "G4Mechanics"
			sc.Source = ev.mechanics; sc.Parent = buildRoot
		end
		local m = ev.metrics or {}
		status.Text = string.format("✅ '%s' · %d parts · %d agents · swarm %d ms · Play to test",
			tostring(ev.name or "obby"), tonumber(m.parts) or 0, tonumber(m.agents) or 0, tonumber(m.wall_ms) or 0)
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

		ensureRoot()
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

print("[G4Studio] plugin loaded. Server: " .. serverUrl())
