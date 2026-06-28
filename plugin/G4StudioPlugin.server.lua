--!nonstrict
-- G4 Studio — Roblox Studio plugin.
-- Type a prompt, and a Gemma-4 swarm on Cerebras designs + builds a playable
-- obby LIVE in your Workspace in seconds.

local HttpService = game:GetService("HttpService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")

local DEFAULT_SERVER = "http://localhost:8000"
local SERVER_SETTING = "G4Studio_ServerURL"

local function serverUrl()
	local saved = plugin:GetSetting(SERVER_SETTING)
	if type(saved) == "string" and #saved > 0 then return saved end
	return DEFAULT_SERVER
end

-- ---- Material map (op name -> Enum.Material) -------------------------------
local MAT = {
	Plastic = Enum.Material.Plastic, SmoothPlastic = Enum.Material.SmoothPlastic,
	Neon = Enum.Material.Neon, Wood = Enum.Material.Wood, WoodPlanks = Enum.Material.WoodPlanks,
	Marble = Enum.Material.Marble, Slate = Enum.Material.Slate, Concrete = Enum.Material.Concrete,
	Granite = Enum.Material.Granite, Brick = Enum.Material.Brick, Pebble = Enum.Material.Pebble,
	Cobblestone = Enum.Material.Cobblestone, Metal = Enum.Material.Metal,
	DiamondPlate = Enum.Material.DiamondPlate, Grass = Enum.Material.Grass, Sand = Enum.Material.Sand,
	Fabric = Enum.Material.Fabric, Ice = Enum.Material.Ice, Glass = Enum.Material.Glass, Foil = Enum.Material.Foil,
}

-- ---- Build the obby from a build-op payload --------------------------------
local function applyBuild(build)
	local ws = workspace
	local old = ws:FindFirstChild(build.root)
	if old then old:Destroy() end

	local rootFolder = Instance.new("Folder")
	rootFolder.Name = build.root
	rootFolder.Parent = ws

	local folders = { _root = rootFolder }
	for _, fname in ipairs(build.folders) do
		local f = Instance.new("Folder")
		f.Name = fname
		f.Parent = rootFolder
		folders[fname] = f
	end

	local count = 0
	for i, p in ipairs(build.parts) do
		local inst = Instance.new(p.class)
		inst.Name = p.name
		inst.Anchored = true
		inst.Size = Vector3.new(p.size[1], p.size[2], p.size[3])
		inst.CFrame = CFrame.new(p.pos[1], p.pos[2], p.pos[3])
		inst.Color = Color3.fromRGB(p.color[1], p.color[2], p.color[3])
		inst.Material = MAT[p.material] or Enum.Material.SmoothPlastic
		inst.Parent = folders[p.folder] or rootFolder
		count += 1
		if i % 4 == 0 then task.wait() end -- let parts visibly pop in
	end

	for _, s in ipairs(build.scripts or {}) do
		local sc = Instance.new("Script")
		sc.Name = s.name
		sc.Source = s.source
		sc.Parent = folders[s.folder] or rootFolder
	end
	return count
end

-- ---- UI --------------------------------------------------------------------
local toolbar = plugin:CreateToolbar("G4 Studio")
local button = toolbar:CreateButton("G4 Studio",
	"Generate a playable obby with Gemma-4 on Cerebras", "rbxassetid://4458901886")

local info = DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, true, false, 340, 230, 300, 200)
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
layout.FillDirection = Enum.FillDirection.Vertical
layout.Padding = UDim.new(0, 8)
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Parent = bg

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, 0, 0, 22)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.TextSize = 16
title.TextXAlignment = Enum.TextXAlignment.Left
title.TextColor3 = Color3.fromRGB(29, 233, 182)
title.Text = "G4 STUDIO  ·  Gemma-4 on Cerebras"
title.LayoutOrder = 1
title.Parent = bg

local promptBox = Instance.new("TextBox")
promptBox.Size = UDim2.new(1, 0, 0, 64)
promptBox.BackgroundColor3 = Color3.fromRGB(18, 26, 38)
promptBox.BorderSizePixel = 0
promptBox.Font = Enum.Font.Gotham
promptBox.TextSize = 14
promptBox.TextColor3 = Color3.fromRGB(230, 237, 243)
promptBox.PlaceholderText = "Describe an obby…"
promptBox.Text = "neon lava parkour with moving platforms and 2 checkpoints"
promptBox.TextWrapped = true
promptBox.TextXAlignment = Enum.TextXAlignment.Left
promptBox.TextYAlignment = Enum.TextYAlignment.Top
promptBox.ClearTextOnFocus = false
promptBox.MultiLine = true
promptBox.LayoutOrder = 2
promptBox.Parent = bg
local pbpad = Instance.new("UIPadding"); pbpad.PaddingLeft = UDim.new(0, 8); pbpad.PaddingTop = UDim.new(0, 6); pbpad.Parent = promptBox
local pbcorner = Instance.new("UICorner"); pbcorner.CornerRadius = UDim.new(0, 8); pbcorner.Parent = promptBox

local buildBtn = Instance.new("TextButton")
buildBtn.Size = UDim2.new(1, 0, 0, 38)
buildBtn.BackgroundColor3 = Color3.fromRGB(29, 233, 182)
buildBtn.BorderSizePixel = 0
buildBtn.Font = Enum.Font.GothamBold
buildBtn.TextSize = 15
buildBtn.TextColor3 = Color3.fromRGB(4, 18, 26)
buildBtn.Text = "Build ⚡"
buildBtn.LayoutOrder = 3
buildBtn.Parent = bg
local btcorner = Instance.new("UICorner"); btcorner.CornerRadius = UDim.new(0, 8); btcorner.Parent = buildBtn

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, 0, 0, 44)
status.BackgroundTransparency = 1
status.Font = Enum.Font.Gotham
status.TextSize = 13
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.TextYAlignment = Enum.TextYAlignment.Top
status.TextColor3 = Color3.fromRGB(125, 141, 163)
status.Text = "Server: " .. serverUrl()
status.LayoutOrder = 4
status.Parent = bg

button.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

local busy = false
local function build()
	if busy then return end
	local prompt = promptBox.Text
	if prompt == "" then return end
	busy = true
	buildBtn.Text = "Building…"
	buildBtn.BackgroundColor3 = Color3.fromRGB(74, 163, 255)
	status.Text = "Designing + building on Cerebras…"

	task.spawn(function()
		local t0 = os.clock()
		local ok, res = pcall(function()
			return HttpService:RequestAsync({
				Url = serverUrl() .. "/api/generate",
				Method = "POST",
				Headers = { ["Content-Type"] = "application/json" },
				Body = HttpService:JSONEncode({ prompt = prompt }),
			})
		end)
		local function finish()
			busy = false
			buildBtn.Text = "Build ⚡"
			buildBtn.BackgroundColor3 = Color3.fromRGB(29, 233, 182)
		end

		if not ok then
			status.Text = "Request error (is the server running?):\n" .. tostring(res)
			finish(); return
		end
		if not res.Success then
			status.Text = "HTTP " .. tostring(res.StatusCode) .. ": " .. tostring(res.Body):sub(1, 200)
			finish(); return
		end
		local okd, data = pcall(function() return HttpService:JSONDecode(res.Body) end)
		if not okd or not data then status.Text = "Bad response"; finish(); return end
		if data.error then status.Text = "Error: " .. tostring(data.error); finish(); return end

		local recording = nil
		pcall(function() recording = ChangeHistoryService:TryBeginRecording("G4 Studio build") end)
		local count = applyBuild(data.build)
		if recording then
			pcall(function()
				ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
			end)
		end

		local totalMs = math.floor((os.clock() - t0) * 1000)
		local m = data.metrics or {}
		status.Text = string.format(
			"✅ '%s'\n%d parts · %d agents · swarm %d ms · total %d ms",
			tostring(data.name or "obby"), count, tonumber(m.agents) or 0,
			tonumber(m.wall_ms) or 0, totalMs
		)
		finish()
	end)
end
buildBtn.MouseButton1Click:Connect(build)

print("[G4Studio] plugin loaded. Server: " .. serverUrl())
