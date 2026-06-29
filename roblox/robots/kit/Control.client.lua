--!strict
-- Hover controller + game HUD (cloned into each player's PlayerGui by the harness). The gripper
-- follows the point under the mouse at an adjustable height. mouse = move, R/F = up/down,
-- click = grab/release, Q/E = roll wrist.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local UIS = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local player = Players.LocalPlayer
local control = RS:WaitForChild("G4Control")
local hudRemote = RS:WaitForChild("G4HUD")
local camera = workspace.CurrentCamera

local TweenService = game:GetService("TweenService")
local CAM_CFRAME = CFrame.lookAt(Vector3.new(0, 13, 27), Vector3.new(0, 3, 4))  -- locked front-on view
local function lockCamera()
	camera.CameraType = Enum.CameraType.Scriptable
	camera.CFrame = CAM_CFRAME
	camera.FieldOfView = 55
end
local function lockChar(c)
	pcall(function()
		local h = c:FindFirstChildOfClass("Humanoid") or c:WaitForChild("Humanoid", 5)
		if h then h.WalkSpeed = 0; h.JumpPower = 0; pcall(function() h.JumpHeight = 0 end) end
		local hrp = c:FindFirstChild("HumanoidRootPart") or c:WaitForChild("HumanoidRootPart", 5)
		if hrp then hrp.Anchored = true; hrp.CFrame = CFrame.new(0, 200, 0) end  -- pin the avatar out of view
		for _, p in ipairs(c:GetDescendants()) do
			if p:IsA("BasePart") then p.Transparency = 1; p.CanCollide = false
			elseif p:IsA("Decal") then p.Transparency = 1 end
		end
	end)
	lockCamera()
end
if player.Character then task.spawn(lockChar, player.Character) end
player.CharacterAdded:Connect(function(c) task.wait(0.15); lockChar(c) end)
lockCamera()

local grip, wristRoll, hover = false, 0, 1.2  -- hover = gripper height above the table point
local TABLE_TOP = 0.5                          -- table surface y (matches the harness table)
local marker = Instance.new("Part")
marker.Shape = Enum.PartType.Ball; marker.Size = Vector3.new(0.7, 0.7, 0.7)
marker.Color = Color3.fromRGB(0, 255, 150); marker.Material = Enum.Material.Neon
marker.Anchored = true; marker.CanCollide = false; marker.Transparency = 0.25; marker.Parent = workspace

-- sleek UI ------------------------------------------------------------------
local gui = Instance.new("ScreenGui"); gui.ResetOnSpawn = false; gui.IgnoreGuiInset = true
gui.Parent = player:WaitForChild("PlayerGui")
local function panel(size, pos, anchor)
	local f = Instance.new("Frame"); f.Size = size; f.Position = pos; f.AnchorPoint = anchor or Vector2.new(0, 0)
	f.BackgroundColor3 = Color3.fromRGB(15, 17, 24); f.BackgroundTransparency = 0.12; f.BorderSizePixel = 0
	f.Parent = gui
	local c = Instance.new("UICorner"); c.CornerRadius = UDim.new(0, 12); c.Parent = f
	local s = Instance.new("UIStroke"); s.Color = Color3.fromRGB(70, 150, 255); s.Thickness = 1.5; s.Transparency = 0.35; s.Parent = f
	return f
end
local topP = panel(UDim2.new(0, 580, 0, 62), UDim2.new(0.5, 0, 0, 18), Vector2.new(0.5, 0))
local accent = Instance.new("Frame"); accent.Size = UDim2.new(0, 6, 1, -18); accent.Position = UDim2.new(0, 11, 0, 9)
accent.BackgroundColor3 = Color3.fromRGB(70, 150, 255); accent.BorderSizePixel = 0; accent.Parent = topP
Instance.new("UICorner", accent).CornerRadius = UDim.new(0, 3)
local top = Instance.new("TextLabel"); top.BackgroundTransparency = 1; top.Size = UDim2.new(1, -34, 1, -16)
top.Position = UDim2.new(0, 26, 0, 8); top.TextColor3 = Color3.fromRGB(236, 241, 255); top.Font = Enum.Font.GothamBold
top.TextScaled = true; top.TextXAlignment = Enum.TextXAlignment.Left; top.Text = "Get ready…"; top.Parent = topP
local hintP = panel(UDim2.new(0, 540, 0, 34), UDim2.new(0.5, 0, 1, -18), Vector2.new(0.5, 1))
local hint = Instance.new("TextLabel"); hint.BackgroundTransparency = 1; hint.Size = UDim2.new(1, -20, 1, 0)
hint.Position = UDim2.new(0, 10, 0, 0); hint.TextColor3 = Color3.fromRGB(168, 184, 214); hint.Font = Enum.Font.GothamMedium
hint.TextScaled = true; hint.Text = "move mouse over the table  ·  click GRAB / DROP  ·  F/R height  ·  Q/E wrist"; hint.Parent = hintP
local count = Instance.new("TextLabel"); count.AnchorPoint = Vector2.new(0.5, 0.5); count.Size = UDim2.new(0, 320, 0, 320)
count.Position = UDim2.new(0.5, 0, 0.42, 0); count.BackgroundTransparency = 1; count.Text = ""
count.TextColor3 = Color3.fromRGB(255, 255, 255); count.Font = Enum.Font.GothamBlack; count.TextScaled = true; count.Parent = gui
local cstroke = Instance.new("UIStroke"); cstroke.Color = Color3.fromRGB(70, 150, 255); cstroke.Thickness = 3; cstroke.Parent = count

hudRemote.OnClientEvent:Connect(function(kind, text)
	if kind == "hud" then
		top.Text = text
	elseif kind == "count" then
		count.Text = text
		if text ~= "" then
			count.TextColor3 = (text == "GO!") and Color3.fromRGB(120, 255, 160) or Color3.fromRGB(255, 255, 255)
			count.TextTransparency = 0; cstroke.Transparency = 0; count.Size = UDim2.new(0, 170, 0, 170)
			TweenService:Create(count, TweenInfo.new(0.55, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
				{ Size = UDim2.new(0, 340, 0, 340), TextTransparency = 0.2 }):Play()
		end
	end
end)

UIS.InputBegan:Connect(function(i, gp)
	if gp then return end
	if i.UserInputType == Enum.UserInputType.MouseButton1 then grip = not grip end
end)

local acc = 0
RunService.RenderStepped:Connect(function(dt)
	lockCamera()  -- re-assert every frame so a (re)spawn can't snap the camera back to the avatar
	if UIS:IsKeyDown(Enum.KeyCode.R) then hover = math.min(hover + 5 * dt, 6) end
	if UIS:IsKeyDown(Enum.KeyCode.F) then hover = math.max(hover - 5 * dt, 0.2) end
	if UIS:IsKeyDown(Enum.KeyCode.Q) then wristRoll = math.clamp(wristRoll - 120 * dt, -180, 180) end
	if UIS:IsKeyDown(Enum.KeyCode.E) then wristRoll = math.clamp(wristRoll + 120 * dt, -180, 180) end
	-- aim at the point on the TABLE under the mouse; the gripper hovers `hover` studs above it,
	-- so you just point where you want and click — no separate height axis to manage.
	local mp = UIS:GetMouseLocation()
	local ray = camera:ViewportPointToRay(mp.X, mp.Y)
	if ray.Direction.Y < -1e-3 then
		local tp = (TABLE_TOP - ray.Origin.Y) / ray.Direction.Y
		if tp > 0 then
			local onTable = ray.Origin + ray.Direction * tp
			local target = onTable + Vector3.new(0, hover, 0)
			marker.Position = target
			marker.Color = grip and Color3.fromRGB(255, 80, 80) or Color3.fromRGB(0, 255, 150)
			acc += dt; if acc >= 0.03 then acc = 0; control:FireServer(target, grip, wristRoll) end
		end
	end
end)
