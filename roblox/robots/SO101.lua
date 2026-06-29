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
	self.p_hand = part("Hand", Vector3.new(1.2, 0.6, L.hand), grey, model)
	self.fingerL = part("FingerL", Vector3.new(0.25, 0.25, 1.4), accent, model)
	self.fingerR = part("FingerR", Vector3.new(0.25, 0.25, 1.4), accent, model)
	self.tip = part("Tip", Vector3.new(0.4, 0.4, 0.4), Color3.fromRGB(255, 80, 80), model)
	self.tip.Transparency = 1

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
	-- hand points outward (+Y of the chain becomes the approach axis)
	local hand = c * CFrame.new(0, L.hand / 2, 0) * CFrame.Angles(-math.pi / 2, 0, 0)
	self.p_hand.CFrame = hand
	local spread = (SO101.GRIPPER_OPEN_DEG * self.gripper) / 60  -- studs each side
	self.fingerL.CFrame = hand * CFrame.new(-0.35 - spread, 0, -L.hand / 2)
	self.fingerR.CFrame = hand * CFrame.new(0.35 + spread, 0, -L.hand / 2)
	self.tip.CFrame = hand * CFrame.new(0, 0, -L.hand)
	self.ee = self.tip.CFrame
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
