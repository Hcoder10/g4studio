-- so100: auto-generated from _so100.urdf by onboard_robot.py
-- 6 DOF · workspace reach with auto rest-pose ~ 100%

M.SCALE = 33.0
M.CHAIN = {
  { name = 'shoulder_pan', pos = Vector3.new(0.0000, -1.4916, 0.5445), rpy = { 1.570790, -0.000000, 0.000000 }, axis = Vector3.new(0, 1, 0), lo = -114.6, hi = 114.6 },
  { name = 'shoulder_lift', pos = Vector3.new(0.0000, 3.3825, 1.0098), rpy = { -1.800000, -0.000000, 0.000000 }, axis = Vector3.new(1, 0, 0), lo = 0.0, hi = 200.5 },
  { name = 'elbow_flex', pos = Vector3.new(0.0000, 3.7148, 0.9240), rpy = { 1.570790, -0.000000, 0.000000 }, axis = Vector3.new(1, 0, 0), lo = -180.0, hi = 0.0 },
  { name = 'wrist_flex', pos = Vector3.new(0.0000, 0.1716, 4.4517), rpy = { -1.000000, -0.000000, 0.000000 }, axis = Vector3.new(1, 0, 0), lo = -143.2, hi = 68.8 },
  { name = 'wrist_roll', pos = Vector3.new(0.0000, -1.9833, 0.0000), rpy = { 0.000000, 1.570790, 0.000000 }, axis = Vector3.new(0, 1, 0), lo = -180.0, hi = 180.0 },
  { name = 'gripper', pos = Vector3.new(-0.6666, -0.8052, 0.0000), rpy = { 3.141593, 0.000013, 3.141593 }, axis = Vector3.new(0, 0, 1), lo = -11.5, hi = 114.6 },
}
M.REST = { 0.0, 0.0, 0.0, 0.0, 0.0 }