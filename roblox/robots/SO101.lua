--!strict
-- SO101: the Standard Open Arm 101 (6-DOF) for Roblox, reconstructed from the official URDF
-- (TheRobotStudio/SO-ARM100, Simulation/SO101/so101_new_calib.urdf). The kinematic chain — joint
-- origins, axes and limits — is exact; the real imported meshes are draped on the true link frames.
--
-- KINEMATIC arm (joint angles -> forward kinematics -> part CFrames): stable, exact joint traces.
-- Objects are physical; the gripper grasps by welding the nearest "Graspable" when it closes.
-- A general CCD solver (solveTo) aims the tip at any point, so this approach loads any URDF arm.
--
-- API: SO101.new(parent, baseCFrame) ; arm:solveTo(pos) ; arm:setTarget(i,deg) ; arm:grip(0..1) ;
--      arm:step(dt) ; arm:getObs() ; arm:getEEPose() ; arm.tip

local SO101 = {}
SO101.__index = SO101
local AssetService = game:GetService("AssetService")
local CollectionService = game:GetService("CollectionService")

-- Real geometry (imported MeshIds). USE_MESHES=false -> primitive blocks.
SO101.USE_MESHES = false  -- meshes need the one-time visual alignment; skeleton works now
SO101.MESH_SCALE = 0.033  -- studs per mm
SO101.MESHES = {
	base = "rbxassetid://83418669346877",       -- Base_SO101
	shoulder = "rbxassetid://130300121536438",  -- Rotation_Pitch
	upper = "rbxassetid://135195240065862",      -- Upper_arm
	fore = "rbxassetid://72714526696272",        -- Under_arm
	wrist = "rbxassetid://78151202619686",       -- Wrist_Roll_Pitch
	jaw = "rbxassetid://127752971220158",        -- Moving_Jaw
}
local MESH_MM = {
	base = Vector3.new(111, 72, 87), shoulder = Vector3.new(60, 84, 46),
	upper = Vector3.new(142, 25, 67), fore = Vector3.new(131, 24, 64),
	wrist = Vector3.new(62, 36, 78), jaw = Vector3.new(22, 92, 48),
}

-- exact chain from the URDF (studs). Each entry: joint origin (pos + rpy) relative to the parent
-- link, rotation axis, limits (deg), and which mesh the child link wears.
SO101.CHAIN = {
	{ name = "shoulder_pan", pos = Vector3.new(1.2816, -0.0000, 2.0592), rpy = { 3.141590, 0.000000, -3.141590 }, axis = Vector3.new(0, 0, 1), lo = -110.0, hi = 110.0, mesh = "shoulder" },
	{ name = "shoulder_lift", pos = Vector3.new(-1.0032, -0.6032, -1.7886), rpy = { -1.570800, -1.570800, 0.000000 }, axis = Vector3.new(0, 0, 1), lo = -100.0, hi = 100.0, mesh = "upper" },
	{ name = "elbow_flex", pos = Vector3.new(-3.7148, -0.9240, 0.0000), rpy = { -0.000000, 0.000000, 1.570800 }, axis = Vector3.new(0, 0, 1), lo = -96.8, hi = 96.8, mesh = "fore" },
	{ name = "wrist_flex", pos = Vector3.new(-4.4517, 0.1716, 0.0000), rpy = { 0.000000, 0.000000, -1.570800 }, axis = Vector3.new(0, 0, 1), lo = -95.0, hi = 95.0, mesh = "wrist" },
	{ name = "wrist_roll", pos = Vector3.new(0.0000, -2.0163, 0.5973), rpy = { 1.570800, 0.048680, 3.141590 }, axis = Vector3.new(0, 0, 1), lo = -157.2, hi = 162.8, mesh = nil },
	{ name = "gripper", pos = Vector3.new(0.6666, 0.6204, -0.7722), rpy = { 1.570800, -0.000000, -0.000000 }, axis = Vector3.new(0, 0, 1), lo = -10.0, hi = 100.0, mesh = "jaw" },
}
SO101.N = #SO101.CHAIN
SO101.SPEED_DEG = 200
SO101.GRIP_CLOSED, SO101.GRIP_OPEN = 0.0, 55.0  -- joint-6 deg for grip(0) .. grip(1)

local UPFIX = CFrame.Angles(-math.pi / 2, 0, 0)  -- URDF Z-up -> Roblox Y-up
local TIP_OFFSET = CFrame.new(-0.2607, -0.0072, -3.2380) * CFrame.Angles(0, math.pi, 0)  -- gripper_frame

-- per-link visual nudge for the re-centered imported meshes (tuned against a screenshot)
SO101.MESH_OFFSET = {
	base = CFrame.new(), shoulder = CFrame.new(), upper = CFrame.new(),
	fore = CFrame.new(), wrist = CFrame.new(), jaw = CFrame.new(),
}

-- URDF rpy -> CFrame:  R = Rz(yaw) * Ry(pitch) * Rx(roll)
local function rpy(r: number, p: number, y: number): CFrame
	return CFrame.Angles(0, 0, y) * CFrame.Angles(0, p, 0) * CFrame.Angles(r, 0, 0)
end

local function part(name, size, color, parent)
	local p = Instance.new("Part")
	p.Name = name; p.Size = size; p.Color = color
	p.Anchored = true; p.CanCollide = false; p.Material = Enum.Material.Metal
	p.TopSurface = Enum.SurfaceType.Smooth; p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

local function meshSkin(key, parent)
	if not SO101.USE_MESHES or not SO101.MESHES[key] then return nil end
	local ok, mp = pcall(function()
		return AssetService:CreateMeshPartAsync(SO101.MESHES[key],
			{ CollisionFidelity = Enum.CollisionFidelity.Box, RenderFidelity = Enum.RenderFidelity.Precise })
	end)
	if not ok or not mp then warn("[SO101] mesh load failed for '" .. key .. "': " .. tostring(mp)); return nil end
	mp.Size = MESH_MM[key] * SO101.MESH_SCALE
	mp.Anchored = true; mp.CanCollide = false
	mp.Material = Enum.Material.SmoothPlastic; mp.Color = Color3.fromRGB(48, 51, 58)
	mp.Parent = parent
	return mp
end

function SO101.new(parent: Instance, baseCFrame: CFrame?)
	local self = setmetatable({}, SO101)
	self.base = baseCFrame or CFrame.new(0, 3, 0)
	self.angles = { 0, 0, 0, 0, 0, SO101.GRIP_OPEN }   -- joint angles (deg); joint 6 = gripper
	self.targets = { 0, 0, 0, 0, 0, SO101.GRIP_OPEN }
	self.gripper = 1                                    -- 0 closed .. 1 open
	self.gripperTarget = 1
	self.grasped = nil
	self.linkCF = {}

	local model = Instance.new("Model"); model.Name = "SO101"; model.Parent = parent
	self.model = model
	local grey = Color3.fromRGB(60, 64, 70)

	-- geometry: real meshes (USE_MESHES) draped on the true link frames, else a clean skeleton
	self.skin, self.rods, self.balls = {}, {}, {}
	local steel, acc = Color3.fromRGB(74, 80, 92), Color3.fromRGB(86, 156, 255)
	if SO101.USE_MESHES then
		self.baseSkin = meshSkin("base", model)
		for i, j in ipairs(SO101.CHAIN) do
			if j.mesh then self.skin[i] = meshSkin(j.mesh, model) end
		end
	end
	if not self.baseSkin then  -- skeleton (rods between the URDF joints + a ball at each joint)
		for i = 0, SO101.N do
			local b = part("J" .. i, Vector3.new(0.95, 0.95, 0.95), acc, model); b.Shape = Enum.PartType.Ball
			self.balls[i] = b
			if i >= 1 then self.rods[i] = part("Rod" .. i, Vector3.new(0.5, 0.5, 1), steel, model) end
		end
	end
	self.tip = part("Tip", Vector3.new(0.3, 0.3, 0.3), Color3.fromRGB(255, 80, 80), model)
	self.tip.Transparency = 1

	self:_fk()
	return self
end

-- forward kinematics: walk the URDF chain, place link frames + meshes, compute the tip
function SO101:_fk()
	local root = self.base * UPFIX
	local cf = root
	if self.baseSkin then self.baseSkin.CFrame = root * SO101.MESH_OFFSET.base end
	for i, j in ipairs(SO101.CHAIN) do
		local origin = CFrame.new(j.pos) * rpy(j.rpy[1], j.rpy[2], j.rpy[3])
		cf = cf * origin * CFrame.fromAxisAngle(j.axis, math.rad(self.angles[i]))
		self.linkCF[i] = cf
		if self.skin[i] and j.mesh then
			self.skin[i].CFrame = cf * (SO101.MESH_OFFSET[j.mesh] or CFrame.identity)
		end
	end
	-- skeleton: a rod between consecutive joints + a ball at each joint
	if self.balls[0] then
		local prev = root.Position
		self.balls[0].CFrame = CFrame.new(prev)
		for i = 1, SO101.N do
			local p = self.linkCF[i].Position
			local len = (p - prev).Magnitude
			if self.rods[i] and len > 0.05 then
				self.rods[i].Size = Vector3.new(0.45, 0.45, len)
				self.rods[i].CFrame = CFrame.lookAt((prev + p) / 2, p)
			end
			self.balls[i].CFrame = CFrame.new(p)
			prev = p
		end
	end
	self.tip.CFrame = self.linkCF[5] * TIP_OFFSET  -- gripper_frame TCP (after wrist_roll)
	self.ee = self.tip.CFrame
end

-- CCD inverse kinematics: aim the tip at a world point using joints 1..4
function SO101:solveTo(worldTarget: Vector3)
	for _ = 1, 10 do
		for i = 4, 1, -1 do
			local pivot = self.linkCF[i].Position
			local axisW = self.linkCF[i]:VectorToWorldSpace(SO101.CHAIN[i].axis).Unit
			local toTip = self.tip.Position - pivot
			local toTgt = worldTarget - pivot
			toTip = toTip - axisW * toTip:Dot(axisW)
			toTgt = toTgt - axisW * toTgt:Dot(axisW)
			if toTip.Magnitude > 0.05 and toTgt.Magnitude > 0.05 then
				local ang = math.atan2(toTip:Cross(toTgt):Dot(axisW), toTip:Dot(toTgt))
				local nl = math.clamp(self.angles[i] + math.deg(ang), SO101.CHAIN[i].lo, SO101.CHAIN[i].hi)
				self.angles[i] = nl; self.targets[i] = nl
				self:_fk()
			end
		end
	end
end

function SO101:setTarget(i: number, deg: number)
	self.targets[i] = math.clamp(deg, SO101.CHAIN[i].lo, SO101.CHAIN[i].hi)
end

function SO101:grip(open01: number)
	self.gripperTarget = math.clamp(open01, 0, 1)
end

function SO101:step(dt: number)
	local maxStep = SO101.SPEED_DEG * dt
	-- joints 1..4 are set directly by solveTo; smooth wrist_roll (5) toward its target
	local err = self.targets[5] - self.angles[5]
	self.angles[5] += math.clamp(err, -maxStep, maxStep)
	-- gripper
	self.gripper += math.clamp(self.gripperTarget - self.gripper, -3 * dt, 3 * dt)
	self.angles[6] = SO101.GRIP_CLOSED + (SO101.GRIP_OPEN - SO101.GRIP_CLOSED) * self.gripper
	self:_fk()
	self:_updateGrasp()
end

function SO101:_updateGrasp()
	if self.gripper < 0.35 and not self.grasped then
		local best, bd = nil, 2.0
		for _, obj in ipairs(CollectionService:GetTagged("Graspable")) do
			if obj:IsA("BasePart") then
				local d = (obj.Position - self.tip.Position).Magnitude
				if d < bd then bd = d; best = obj end
			end
		end
		if best then best.Anchored = true; self.grasped = best end
	elseif self.gripper > 0.6 and self.grasped then
		self.grasped.Anchored = false
		self.grasped = nil
	end
	if self.grasped then self.grasped.CFrame = self.tip.CFrame end
end

function SO101:getObs()
	return {
		joints = { self.angles[1], self.angles[2], self.angles[3], self.angles[4], self.angles[5] },
		gripper = self.gripper,
		ee = { self.ee.Position.X, self.ee.Position.Y, self.ee.Position.Z },
		holding = self.grasped ~= nil,
	}
end

function SO101:getEEPose(): CFrame
	return self.ee
end

return SO101
