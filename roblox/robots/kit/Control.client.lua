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

local function lockChar(c)
	local h = c:FindFirstChildOfClass("Humanoid") or c:WaitForChild("Humanoid")
	h.WalkSpeed = 0; h.JumpPower = 0; pcall(function() h.JumpHeight = 0 end)
	for _, p in ipairs(c:GetDescendants()) do
		if p:IsA("BasePart") or p:IsA("Decal") then p.Transparency = 1 end
	end
end
if player.Character then lockChar(player.Character) end
player.CharacterAdded:Connect(lockChar)
task.wait(0.2)
camera.CameraType = Enum.CameraType.Scriptable
camera.CFrame = CFrame.lookAt(Vector3.new(10, 9.5, 12), Vector3.new(-1, 1.5, 3))

local grip, wristRoll, height = false, 0, 3.0
local marker = Instance.new("Part")
marker.Shape = Enum.PartType.Ball; marker.Size = Vector3.new(0.7, 0.7, 0.7)
marker.Color = Color3.fromRGB(0, 255, 150); marker.Material = Enum.Material.Neon
marker.Anchored = true; marker.CanCollide = false; marker.Transparency = 0.25; marker.Parent = workspace

local gui = Instance.new("ScreenGui"); gui.ResetOnSpawn = false; gui.Parent = player:WaitForChild("PlayerGui")
local top = Instance.new("TextLabel")
top.Size = UDim2.new(0, 520, 0, 56); top.Position = UDim2.new(0.5, -260, 0, 14); top.AnchorPoint = Vector2.new(0, 0)
top.BackgroundTransparency = 0.35; top.BackgroundColor3 = Color3.new(0, 0, 0)
top.TextColor3 = Color3.fromRGB(120, 255, 180); top.Font = Enum.Font.GothamBlack; top.TextScaled = true
top.Text = "Loading game…"; top.Parent = gui
local hint = Instance.new("TextLabel")
hint.Size = UDim2.new(0, 470, 0, 30); hint.Position = UDim2.new(0, 16, 1, -42)
hint.BackgroundTransparency = 0.45; hint.BackgroundColor3 = Color3.new(0, 0, 0)
hint.TextColor3 = Color3.new(1, 1, 1); hint.Font = Enum.Font.GothamMedium; hint.TextScaled = true
hint.Text = "mouse: move  ·  R/F: up-down  ·  click: grab  ·  Q/E: wrist"; hint.Parent = gui

hudRemote.OnClientEvent:Connect(function(kind, text)
	if kind == "hud" then top.Text = text end
end)

UIS.InputBegan:Connect(function(i, gp)
	if gp then return end
	if i.UserInputType == Enum.UserInputType.MouseButton1 then grip = not grip end
end)

local acc = 0
RunService.RenderStepped:Connect(function(dt)
	if UIS:IsKeyDown(Enum.KeyCode.R) then height = math.min(height + 7 * dt, 9) end
	if UIS:IsKeyDown(Enum.KeyCode.F) then height = math.max(height - 7 * dt, 0.4) end
	if UIS:IsKeyDown(Enum.KeyCode.Q) then wristRoll = math.clamp(wristRoll - 120 * dt, -180, 180) end
	if UIS:IsKeyDown(Enum.KeyCode.E) then wristRoll = math.clamp(wristRoll + 120 * dt, -180, 180) end
	local mp = UIS:GetMouseLocation()
	local ray = camera:ViewportPointToRay(mp.X, mp.Y)
	if math.abs(ray.Direction.Y) > 1e-3 then
		local tp = (height - ray.Origin.Y) / ray.Direction.Y
		if tp > 0 then
			local target = ray.Origin + ray.Direction * tp
			marker.Position = target; marker.Color = grip and Color3.fromRGB(255, 80, 80) or Color3.fromRGB(0, 255, 150)
			acc += dt; if acc >= 0.03 then acc = 0; control:FireServer(target, grip, wristRoll) end
		end
	end
end)
