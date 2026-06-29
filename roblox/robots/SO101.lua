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
-- Flip to true once the 7 BAKED link meshes are imported. Each link's URDF visuals are merged +
-- scaled to studs into ONE mesh, so Roblox's re-centering is harmless — the exact post-center
-- offset is baked in SO101.MESH_OFFSET below. No manual alignment.
SO101.USE_MESHES = true
SO101.MESHES = {  -- baked per-link meshes (roblox/robots/meshes/link_obj/<key>.obj)
    base = "rbxassetid://95596397903989",
    shoulder = "rbxassetid://100111761721607",
    upper = "rbxassetid://125188763339649",
    fore = "rbxassetid://111821043840824",
    wrist = "rbxassetid://133675858855321",
    gripperhub = "rbxassetid://94518968409146",
    jaw = "rbxassetid://81908923863369",
}

-- exact chain from the URDF (studs). Each entry: joint origin (pos + rpy) relative to the parent
-- link, rotation axis, limits (deg), and which mesh the child link wears.
SO101.CHAIN = {
    { name = "shoulder_pan", pos = Vector3.new(1.2816, -0.0000, 2.0592), rpy = { 3.141590, 0.000000, -3.141590 }, axis = Vector3.new(0, 0, 1), lo = -110.0, hi = 110.0, mesh = "shoulder" },
    { name = "shoulder_lift", pos = Vector3.new(-1.0032, -0.6032, -1.7886), rpy = { -1.570800, -1.570800, 0.000000 }, axis = Vector3.new(0, 0, 1), lo = -100.0, hi = 100.0, mesh = "upper" },
    { name = "elbow_flex", pos = Vector3.new(-3.7148, -0.9240, 0.0000), rpy = { -0.000000, 0.000000, 1.570800 }, axis = Vector3.new(0, 0, 1), lo = -96.8, hi = 96.8, mesh = "fore" },
    { name = "wrist_flex", pos = Vector3.new(-4.4517, 0.1716, 0.0000), rpy = { 0.000000, 0.000000, -1.570800 }, axis = Vector3.new(0, 0, 1), lo = -95.0, hi = 95.0, mesh = "wrist" },
    { name = "wrist_roll", pos = Vector3.new(0.0000, -2.0163, 0.5973), rpy = { 1.570800, 0.048680, 3.141590 }, axis = Vector3.new(0, 0, 1), lo = -157.2, hi = 162.8, mesh = "gripperhub" },
    { name = "gripper", pos = Vector3.new(0.6666, 0.6204, -0.7722), rpy = { 1.570800, -0.000000, -0.000000 }, axis = Vector3.new(0, 0, 1), lo = -10.0, hi = 100.0, mesh = "jaw" },
}
SO101.N = #SO101.CHAIN
SO101.SPEED_DEG = 200
SO101.GRIP_CLOSED, SO101.GRIP_OPEN = 0.0, 55.0  -- joint-6 deg for grip(0) .. grip(1)

local UPFIX = CFrame.Angles(-math.pi / 2, 0, 0)  -- URDF Z-up -> Roblox Y-up
local TIP_OFFSET = CFrame.new(-0.2607, -0.0072, -3.2380) * CFrame.Angles(0, math.pi, 0)  -- gripper_frame

-- exact post-recenter offset per baked link mesh (= bbox center of the baked geometry, in studs).
-- skin.CFrame = linkCF * MESH_OFFSET so geometry point q renders at linkCF*q. Computed, not guessed.
-- NOTE: this is purely cosmetic (mesh placement); the kinematics/IK/tip never read it.
SO101.MESH_OFFSET = {
    base = CFrame.new(0.5553, 0.0000, 1.1089) * CFrame.Angles(0, math.pi, 0),
    shoulder = CFrame.new(-0.6336, 0.0383, -0.3003) * CFrame.Angles(0, math.pi, 0),
    upper = CFrame.new(-1.9498, -0.4323, 0.6649) * CFrame.Angles(0, math.pi, 0),
    fore = CFrame.new(-2.1960, 0.1139, 0.6665) * CFrame.Angles(0, math.pi, 0),
    wrist = CFrame.new(-0.0716, -0.8882, 0.7309) * CFrame.Angles(0, math.pi, 0),
    gripperhub = CFrame.new(-0.0792, -0.0660, -1.7067) * CFrame.Angles(0, math.pi, 0),
    jaw = CFrame.new(-0.0380, -1.1881, 0.6237) * CFrame.Angles(0, math.pi, 0),
}

-- IK tuning (damped least squares + null-space posture)
local IK_ITERS = 6        -- DLS iterations per solve
local IK_TOL = 0.1        -- stop once the tip is within this many studs of the target
local IK_LAMBDA2 = 0.4    -- DLS damping^2 — singularity robustness (higher = smoother/slower)
local IK_STEP = 2.0       -- cap the tip error used per iteration (studs) -> bounded joint steps
local IK_POSTURE = 0.2    -- null-space pull toward the rest pose; lives in the REDUNDANT DOF only,
                          -- so it shapes posture WITHOUT moving the tip off target.
-- natural "elbow-up, gripper-down" pose the redundant freedom resolves toward (deg). If it favours
-- the wrong elbow, flip the sign of IK_REST[3].
local IK_REST = { 0, -50, 95, -45, 0 }

-- URDF rpy -> CFrame:  R = Rz(yaw) * Ry(pitch) * Rx(roll)
local function rpy(r: number, p: number, y: number): CFrame
    return CFrame.Angles(0, 0, y) * CFrame.Angles(0, p, 0) * CFrame.Angles(r, 0, 0)
end

-- pure FK (no instances touched): returns the link frames + tip position for a joint-angle array.
-- Used by the solver so it can evaluate trial poses without rendering 40x a frame.
local function fkFrames(base: CFrame, angles: { number }): ({ CFrame }, Vector3)
    local cf = base * UPFIX
    local F = table.create(SO101.N)
    for i = 1, SO101.N do
        local j = SO101.CHAIN[i]
        cf = cf * (CFrame.new(j.pos) * rpy(j.rpy[1], j.rpy[2], j.rpy[3])) * CFrame.fromAxisAngle(j.axis, math.rad(angles[i]))
        F[i] = cf
    end
    return F, (F[5] * TIP_OFFSET).Position
end

-- 3x3 inverse (row-major flat array of 9); nil if singular
local function inv3(m: { number }): { number }?
    local a, b, c, d, e, f, g, h, i = m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9]
    local A, B, C = e * i - f * h, f * g - d * i, d * h - e * g
    local det = a * A + b * B + c * C
    if math.abs(det) < 1e-9 then return nil end
    local id = 1 / det
    return {
        A * id, (c * h - b * i) * id, (b * f - c * e) * id,
        B * id, (a * i - c * g) * id, (c * d - a * f) * id,
        C * id, (b * g - a * h) * id, (a * e - b * d) * id,
    }
end

local function mul3(m: { number }, v: Vector3): Vector3  -- 3x3 (flat) * Vector3
    return Vector3.new(m[1] * v.X + m[2] * v.Y + m[3] * v.Z,
        m[4] * v.X + m[5] * v.Y + m[6] * v.Z, m[7] * v.X + m[8] * v.Y + m[9] * v.Z)
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
    local id = SO101.MESHES[key]
    if not SO101.USE_MESHES or not id or id == "" then return nil end
    local ok, mp = pcall(function()
        return AssetService:CreateMeshPartAsync(id,
            { CollisionFidelity = Enum.CollisionFidelity.Box, RenderFidelity = Enum.RenderFidelity.Precise })
    end)
    if not ok or not mp then warn("[SO101] mesh load failed for '" .. key .. "': " .. tostring(mp)); return nil end
    mp.Anchored = true; mp.CanCollide = false  -- imported pre-scaled to studs; keep native size
    mp.Material = Enum.Material.SmoothPlastic; mp.Color = Color3.fromRGB(226, 174, 64)  -- SO-101 yellow
    mp.Parent = parent
    return mp
end

function SO101.new(parent: Instance, baseCFrame: CFrame?)
    local self = setmetatable({}, SO101)
    self.base = baseCFrame or CFrame.new(0, 3, 0)
    -- start in the natural rest pose so it never opens in a folded configuration
    self.angles = { IK_REST[1], IK_REST[2], IK_REST[3], IK_REST[4], IK_REST[5], SO101.GRIP_OPEN }
    self.targets = { IK_REST[1], IK_REST[2], IK_REST[3], IK_REST[4], IK_REST[5], SO101.GRIP_OPEN }
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

-- Damped-least-squares IK with null-space posture: aim the tip at a world point using joints 1..4.
-- dq = J^T (J J^T + λ²I)^-1 e  drives the tip to the target (damped, so it's stable at singular/
-- extended poses); the null-space term (I - J⁺J)(q_rest - q) eases the redundant freedom toward a
-- natural elbow-up pose WITHOUT moving the tip — so it never folds into itself and never fights the
-- goal. Solves from the persistent TARGETS; step() then servo-limits the real motion. Generic over
-- any revolute chain (same method the SO-101's reference kinematics use).
function SO101:solveTo(worldTarget: Vector3)
    -- keep the goal inside the reachable shell around the shoulder
    local sh = (self.linkCF[2] or (self.base * UPFIX)).Position
    local d0 = worldTarget - sh
    local dist = d0.Magnitude
    if dist > 8.4 then worldTarget = sh + d0 * (8.4 / dist)
    elseif dist > 1e-3 and dist < 2.6 then worldTarget = sh + d0 * (2.6 / dist) end

    local q = { math.rad(self.targets[1]), math.rad(self.targets[2]), math.rad(self.targets[3]), math.rad(self.targets[4]) }
    for _ = 1, IK_ITERS do
        local a = { math.deg(q[1]), math.deg(q[2]), math.deg(q[3]), math.deg(q[4]), self.targets[5], self.angles[6] }
        local F, tip = fkFrames(self.base, a)
        local e = worldTarget - tip
        local em = e.Magnitude
        if em < IK_TOL then break end
        if em > IK_STEP then e = e * (IK_STEP / em) end

        -- Jacobian columns (per radian): Jc[c] = axis_c × (tip - pivot_c)
        local Jc = table.create(4)
        for c = 1, 4 do
            local fr = F[c]
            Jc[c] = fr:VectorToWorldSpace(SO101.CHAIN[c].axis):Cross(tip - fr.Position)
        end
        -- M = J Jᵀ + λ²I  (3x3, symmetric)
        local M = { IK_LAMBDA2, 0, 0, 0, IK_LAMBDA2, 0, 0, 0, IK_LAMBDA2 }
        for c = 1, 4 do
            local j = Jc[c]
            M[1] += j.X * j.X; M[2] += j.X * j.Y; M[3] += j.X * j.Z
            M[4] += j.X * j.Y; M[5] += j.Y * j.Y; M[6] += j.Y * j.Z
            M[7] += j.X * j.Z; M[8] += j.Y * j.Z; M[9] += j.Z * j.Z
        end
        local Minv = inv3(M)
        if not Minv then break end
        local y = mul3(Minv, e)                      -- (J Jᵀ + λ²I)^-1 e
        local dq = { Jc[1]:Dot(y), Jc[2]:Dot(y), Jc[3]:Dot(y), Jc[4]:Dot(y) }  -- Jᵀ y

        -- null-space posture: dq += POSTURE * (I - J⁺J)(q_rest - q)
        local z = {
            math.rad(IK_REST[1]) - q[1], math.rad(IK_REST[2]) - q[2],
            math.rad(IK_REST[3]) - q[3], math.rad(IK_REST[4]) - q[4],
        }
        local zc = Jc[1] * z[1] + Jc[2] * z[2] + Jc[3] * z[3] + Jc[4] * z[4]
        for c = 1, 4 do
            local Jpinv_c = mul3(Minv, Jc[c])        -- (J Jᵀ + λ²I)^-1 Jc  (M symmetric)
            dq[c] += IK_POSTURE * (z[c] - Jpinv_c:Dot(zc))
        end

        for c = 1, 4 do
            q[c] = math.clamp(q[c] + dq[c], math.rad(SO101.CHAIN[c].lo), math.rad(SO101.CHAIN[c].hi))
        end
    end
    for i = 1, 4 do self.targets[i] = math.deg(q[i]) end
end

function SO101:setTarget(i: number, deg: number)
    self.targets[i] = math.clamp(deg, SO101.CHAIN[i].lo, SO101.CHAIN[i].hi)
end

function SO101:grip(open01: number)
    self.gripperTarget = math.clamp(open01, 0, 1)
end

function SO101:step(dt: number)
    local maxStep = SO101.SPEED_DEG * dt
    -- servo-limit every arm joint toward its target -> smooth motion that filters any solver noise
    for i = 1, 5 do
        local err = self.targets[i] - self.angles[i]
        self.angles[i] += math.clamp(err, -maxStep, maxStep)
    end
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
