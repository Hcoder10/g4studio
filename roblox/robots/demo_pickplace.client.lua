--!strict
-- DEMO (client): aim the SO-101 gripper with the mouse, click to grab/release. A tiny HUD shows
-- the current sub-goal the data is labeling. Put this LocalScript in StarterPlayerScripts.

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
lbl.Size = UDim2.new(0, 360, 0, 40); lbl.Position = UDim2.new(0, 20, 0, 20)
lbl.BackgroundTransparency = 0.4; lbl.BackgroundColor3 = Color3.new(0, 0, 0)
lbl.TextColor3 = Color3.new(1, 1, 1); lbl.Font = Enum.Font.GothamBold; lbl.TextScaled = true
lbl.Text = "Move mouse to aim · click to grab/release"; lbl.Parent = gui

UIS.InputBegan:Connect(function(i, gp)
	if gp then return end
	if i.UserInputType == Enum.UserInputType.MouseButton1 then
		grip = not grip
		lbl.Text = grip and "GRIPPER CLOSED — drop it in the green bin" or "GRIPPER OPEN — go grab the cube"
	end
end)

local acc = 0
RunService.RenderStepped:Connect(function(dt)
	acc += dt
	if acc < 0.03 then return end  -- ~30 Hz control stream
	acc = 0
	if mouse.Hit then control:FireServer(mouse.Hit.Position, grip) end
end)
