--!strict
-- SO101: a faithful Standard Open Arm 101 (6-DOF) for Roblox, built for DATA COLLECTION.
--
-- The arm is KINEMATIC (joint angles -> forward kinematics -> part CFrames each step): stable,
-- exactly controllable, and it yields clean joint trajectories. The OBJECTS it manipulates are
-- physical (unanchored), and the gripper grasps by welding the nearest object when it closes.
-- This mirrors a position-controlled real arm (STS3215 servos) in a physical world.
--
-- DOF (matches the real SO-101): 1 base-yaw, 2 shoulder-pitch, 3 elbow-pitch, 4 wrist-pitch,
-- 5 wrist-roll, 6 gripper. All angles are DEGREES.
--
-- API:
--   local arm = SO101.new(parent, baseCFrame)
--   arm:setTargets({j1,j2,j3,j4,j5}, gripper01)   -- command joint targets (smoothed toward)
--   arm:setTarget(i, deg)                          -- one joint
--   arm:solveTo(worldPos)                          -- simple IK: aim the gripper at a world point
--   arm:step(dt)                                   -- advance toward targets + update FK + grasp
--   arm:getObs()  -> { joints={...}, gripper=n, ee=CFrame, tip=Vector3 }   -- for traces
--   arm:getEEPose() -> CFrame
--   arm.tip : Part   -- the gripper tip (for proximity/contact)

local SO101 = {}
SO101.__index = SO101

-- Link lengths in studs (scaled-up SO-101 proportions; 1 stud ~ 0.18 m here for playability).
local L = { base = 2.0, shoulder = 1.2, upper = 4.6, fore = 4.6, wrist = 1.6, hand = 1.8 }

-- Joint limits (degrees), in chain order j1..j5 (+ gripper handled separately).
SO101.LIMITS = {
	{ -180, 180 }, -- base yaw
	{ -100, 100 }, -- shoulder pitch
	{ -150, 150 }, -- elbow pitch
	{ -100, 100 }, -- wrist pitch
	{ -180, 180 }, -- wrist roll
}
SO101.GRIPPER_OPEN_DEG = 32   -- finger spread when fully open
SO101.SPEED_DEG = 160         -- max joint speed (deg/s), ~ STS3215 at 12V

-- Real SO-101 geometry (imported MeshIds). The kinematics are unchanged — these render the
-- actual parts as skins on each link. Set USE_MESHES=false to fall back to primitive blocks.
SO101.USE_MESHES = true
SO101.MESH_SCALE = 0.033       -- studs per mm (so the ~350mm arm is ~12 studs)
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
-- per-link visual offset for alignment (tuned against a screenshot). UPFIX = CAD Z-up -> Roblox Y-up.
local UPFIX = CFrame.Angles(-math.pi / 2, 0, 0)
SO101.MESH_OFFSET = {
	base = UPFIX, shoulder = UPFIX, upper = UPFIX, fore = UPFIX, wrist = UPFIX, jaw = UPFIX,
}

local function clampDeg(i, deg)
	local lim = SO101.LIMITS[i]
	return math.clamp(deg, lim[1], lim[2])
end

local function part(name, size, color, parent)
	local p = Instance.new("Part")
	p.Name = name; p.Size = size; p.Color = color
	p.Anchored = true; p.CanCollide = false; p.Material = Enum.Material.Metal
	p.TopSurface = Enum.SurfaceType.Smooth; p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

local function meshSkin(key: string, parent: Instance)
	if not SO101.USE_MESHES or not SO101.MESHES[key] then return nil end
	local mp = Instance.new("MeshPart")
	local ok = pcall(function() mp.MeshId = SO101.MESHES[key] end)
	if not ok then mp:Destroy(); return nil end  -- MeshId not assignable -> keep the primitive
	mp.Size = MESH_MM[key] * SO101.MESH_SCALE
	mp.Anchored = true; mp.CanCollide = false
	mp.Material = Enum.Material.SmoothPlastic; mp.Color = Color3.fromRGB(48, 51, 58)
	mp.Parent = parent
	return mp
end

function SO101.new(parent: Instance, baseCFrame: CFrame)
	local self = setmetatable({}, SO101)
	self.base = baseCFrame or CFrame.new(0, L.base, 0)
	self.angles = { 0, 0, 0, 0, 0 }   -- current joint angles (deg)
	self.targets = { 0, 0, 0, 0, 0 }  -- commanded targets (deg)
	self.gripper = 1                  -- 0 closed .. 1 open
	self.gripperTarget = 1
	self.grasped = nil                -- the welded object, if any

	local model = Instance.new("Model"); model.Name = "SO101"; model.Parent = parent
	self.model = model
	local grey = Color3.fromRGB(60, 64, 70)
	local accent = Color3.fromRGB(70, 163, 255)

	-- pedestal / base (yaw housing)
	self.p_base = part("Base", Vector3.new(2.4, L.base, 2.4), grey, model)
	self.p_yaw = part("Yaw", Vector3.new(1.6, L.shoulder, 1.6), accent, model)
	self.p_upper = part("UpperArm", Vector3.new(1.0, L.upper, 1.0), grey, model)
	self.p_fore = part("Forearm", Vector3.new(0.9, L.fore, 0.9), grey, model)
	self.p_wrist = part("Wrist", Vector3.new(0.8, L.wrist, 0.8), accent, model)
	self.p_hand = part("Hand", Vector3.new(1.3, 1.0, L.hand), grey, model)         -- wrist/palm
	self.fixedJaw = part("FixedJaw", Vector3.new(0.9, 0.3, 1.7), grey, model)      -- static lower jaw
	self.movingJaw = part("MovingJaw", Vector3.new(0.9, 0.3, 1.7), accent, model)  -- pivoting upper jaw
	self.tip = part("Tip", Vector3.new(0.3, 0.3, 0.3), Color3.fromRGB(255, 80, 80), model)
	self.tip.Transparency = 1

	-- real SO-101 geometry as skins on the kinematic links (falls back to the blocks above)
	self.skins = {
		base = meshSkin("base", model), shoulder = meshSkin("shoulder", model),
		upper = meshSkin("upper", model), fore = meshSkin("fore", model),
		wrist = meshSkin("wrist", model), jaw = meshSkin("jaw", model),
	}
	if self.skins.base then self.p_base.Transparency = 1 end
	if self.skins.shoulder then self.p_yaw.Transparency = 1 end
	if self.skins.upper then self.p_upper.Transparency = 1 end
	if self.skins.fore then self.p_fore.Transparency = 1 end
	if self.skins.wrist then self.p_wrist.Transparency = 1; self.p_hand.Transparency = 1 end
	if self.skins.jaw then self.movingJaw.Transparency = 1; self.fixedJaw.Transparency = 1 end

	self:_fk()
	return self
end

-- Forward kinematics: place every link from the current joint angles.
function SO101:_fk()
	local a = self.angles
	local r = math.rad
	-- base pedestal sits at the mount
	self.p_base.CFrame = self.base
	-- yaw about world up
	local c = self.base * CFrame.Angles(0, r(a[1]), 0)
	self.p_yaw.CFrame = c * CFrame.new(0, L.shoulder / 2, 0)
	-- shoulder pitch (about local X), then go up the upper arm
	c = c * CFrame.new(0, L.shoulder, 0) * CFrame.Angles(r(a[2]), 0, 0)
	self.p_upper.CFrame = c * CFrame.new(0, L.upper / 2, 0)
	-- elbow pitch
	c = c * CFrame.new(0, L.upper, 0) * CFrame.Angles(r(a[3]), 0, 0)
	self.p_fore.CFrame = c * CFrame.new(0, L.fore / 2, 0)
	-- wrist pitch
	c = c * CFrame.new(0, L.fore, 0) * CFrame.Angles(r(a[4]), 0, 0)
	self.p_wrist.CFrame = c * CFrame.new(0, L.wrist / 2, 0)
	-- wrist roll (about the arm axis)
	c = c * CFrame.new(0, L.wrist, 0) * CFrame.Angles(0, r(a[5]), 0)
	-- hand points outward (the chain's +Y becomes the approach axis -Z of the palm)
	local hand = c * CFrame.new(0, L.hand / 2, 0) * CFrame.Angles(-math.pi / 2, 0, 0)
	self.p_hand.CFrame = hand
	-- gripper: a FIXED lower jaw + a MOVING upper jaw that PIVOTS open about the palm hinge
	-- (like the real SO-101 Moving_Jaw), instead of two sliding fingers.
	local openRad = math.rad(SO101.GRIPPER_OPEN_DEG * self.gripper)
	local hinge = hand * CFrame.new(0, 0, -L.hand * 0.5)
	self.fixedJaw.CFrame = hinge * CFrame.new(0, -0.45, -0.85)
	self.movingJaw.CFrame = hinge * CFrame.Angles(openRad, 0, 0) * CFrame.new(0, 0.45, -0.85)
	self.tip.CFrame = hinge * CFrame.new(0, -0.1, -1.6)
	self.ee = self.tip.CFrame

	-- drape the real meshes over the kinematic links (offsets tunable via SO101.MESH_OFFSET)
	if self.skins then
		local O = SO101.MESH_OFFSET
		local function place(s, base, off) if s and off then s.CFrame = base * off end end
		place(self.skins.base, self.p_base.CFrame, O.base)
		place(self.skins.shoulder, self.p_yaw.CFrame, O.shoulder)
		place(self.skins.upper, self.p_upper.CFrame, O.upper)
		place(self.skins.fore, self.p_fore.CFrame, O.fore)
		place(self.skins.wrist, self.p_wrist.CFrame, O.wrist)
		place(self.skins.jaw, self.movingJaw.CFrame, O.jaw)
	end
end

function SO101:setTarget(i: number, deg: number)
	self.targets[i] = clampDeg(i, deg)
end

function SO101:setTargets(joints, gripper01)
	for i = 1, 5 do
		if joints[i] then self.targets[i] = clampDeg(i, joints[i]) end
	end
	if gripper01 ~= nil then self.gripperTarget = math.clamp(gripper01, 0, 1) end
end

-- Simple planar IK: aim shoulder+elbow+wrist so the tip reaches toward `worldPos`.
-- (2-link analytic for reach in the yaw plane; good enough to drag the gripper around.)
function SO101:solveTo(worldPos: Vector3)
	local rel = self.base:PointToObjectSpace(worldPos)
	local yaw = math.deg(math.atan2(rel.X, rel.Z))
	self.targets[1] = clampDeg(1, yaw)
	local planar = math.sqrt(rel.X * rel.X + rel.Z * rel.Z)
	local height = rel.Y - L.shoulder
	local d = math.clamp(math.sqrt(planar * planar + height * height), 0.1, L.upper + L.fore - 0.2)
	local a1, a2 = L.upper, L.fore
	local cosE = math.clamp((d * d - a1 * a1 - a2 * a2) / (-2 * a1 * a2), -1, 1)
	local elbow = math.pi - math.acos(cosE)
	local base = math.atan2(height, planar) + math.acos(math.clamp((d * d + a1 * a1 - a2 * a2) / (2 * a1 * d), -1, 1))
	self.targets[2] = clampDeg(2, 90 - math.deg(base))
	self.targets[3] = clampDeg(3, -math.deg(elbow))
	self.targets[4] = clampDeg(4, -(self.targets[2] + self.targets[3]))  -- keep hand level-ish
end

function SO101:grip(open01: number)
	self.gripperTarget = math.clamp(open01, 0, 1)
end

-- advance the joints toward their targets at servo speed, refresh FK, handle grasp/release
function SO101:step(dt: number)
	local maxStep = SO101.SPEED_DEG * dt
	for i = 1, 5 do
		local err = self.targets[i] - self.angles[i]
		self.angles[i] += math.clamp(err, -maxStep, maxStep)
	end
	local gerr = self.gripperTarget - self.gripper
	self.gripper += math.clamp(gerr, -2 * dt, 2 * dt)
	self:_fk()
	self:_updateGrasp()
end

-- grasp the nearest small physical part when the gripper closes; release when it opens
function SO101:_updateGrasp()
	local CollectionService = game:GetService("CollectionService")
	if self.gripper < 0.35 and not self.grasped then
		local best, bd = nil, 1.8
		for _, obj in ipairs(CollectionService:GetTagged("Graspable")) do
			if obj:IsA("BasePart") then
				local d = (obj.Position - self.tip.Position).Magnitude
				if d < bd then bd = d; best = obj end
			end
		end
		if best then
			best.Anchored = false
			local weld = Instance.new("WeldConstraint")
			weld.Name = "G4Grasp"; weld.Part0 = self.p_hand; weld.Part1 = best
			weld.Parent = self.p_hand
			best.Anchored = true  -- ride with the kinematic hand
			self.grasped = best
		end
	elseif self.gripper > 0.6 and self.grasped then
		local w = self.p_hand:FindFirstChild("G4Grasp")
		if w then w:Destroy() end
		self.grasped.Anchored = false  -- drop it into physics
		self.grasped = nil
	end
	if self.grasped then  -- carry the grasped object with the hand
		self.grasped.CFrame = self.p_hand.CFrame * CFrame.new(0, -L.hand, 0)
	end
end

-- observation for traces: joint angles, gripper, end-effector pose, tip position
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
