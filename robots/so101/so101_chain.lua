-- so101: auto-generated from so101.urdf by onboard_robot.py
-- 6 DOF · workspace reach with auto rest-pose ~ 93%

M.SCALE = 33.0
M.CHAIN = {
  { name = 'shoulder_pan', pos = Vector3.new(1.2816, -0.0000, 2.0592), rpy = { 3.141590, 0.000000, -3.141590 }, axis = Vector3.new(0, 0, 1), lo = -110.0, hi = 110.0 },
  { name = 'shoulder_lift', pos = Vector3.new(-1.0032, -0.6032, -1.7886), rpy = { 1.570793, -1.570793, 3.141593 }, axis = Vector3.new(0, 0, 1), lo = -100.0, hi = 100.0 },
  { name = 'elbow_flex', pos = Vector3.new(-3.7148, -0.9240, 0.0000), rpy = { -0.000000, 0.000000, 1.570800 }, axis = Vector3.new(0, 0, 1), lo = -96.8, hi = 96.8 },
  { name = 'wrist_flex', pos = Vector3.new(-4.4517, 0.1716, 0.0000), rpy = { 0.000000, 0.000000, -1.570800 }, axis = Vector3.new(0, 0, 1), lo = -95.0, hi = 95.0 },
  { name = 'wrist_roll', pos = Vector3.new(0.0000, -2.0163, 0.5973), rpy = { 1.570800, 0.048680, 3.141590 }, axis = Vector3.new(0, 0, 1), lo = -157.2, hi = 162.8 },
  { name = 'gripper', pos = Vector3.new(0.6666, 0.6204, -0.7722), rpy = { 1.570800, -0.000000, -0.000000 }, axis = Vector3.new(0, 0, 1), lo = -10.0, hi = 100.0 },
}
M.REST = { 15.2, -14.0, 57.8, 54.8, 37.3 }