--!strict
-- Trace: records a manipulation episode (per-step obs/action/reward + high-level sub-goal tags)
-- and ships it to the G4 server, where it's stored as a dataset for training. Runs SERVER-side
-- (HttpService is server-only) — the client sends control inputs, the server applies + records,
-- exactly like a real teleop follower arm.

local Trace = {}
Trace.__index = Trace

local HttpService = game:GetService("HttpService")
local DEFAULT_SERVER = "{{SERVER_URL}}"  -- injected by the plugin; or pass one to :finish()

-- task: e.g. "so101_pick_place"; meta: { robot="SO101", action_space="joint_delta", ... }
function Trace.new(task: string, meta)
	return setmetatable({
		task = task, meta = meta or {}, steps = {}, t = 0, started = os.clock(),
	}, Trace)
end

-- obs: SO101:getObs() + any task state; action: what the player commanded this tick;
-- reward: dense or sparse; subgoal: high-level skill label ("reach"|"grasp"|"transport"|"place"|...)
function Trace:record(obs, action, reward: number?, subgoal: string?)
	self.t += 1
	table.insert(self.steps, {
		t = self.t, obs = obs, action = action, reward = reward or 0, subgoal = subgoal,
	})
end

function Trace:length(): number
	return self.t
end

-- ship the episode (success + final score), then reset
function Trace:finish(success: boolean, score: number?, server: string?)
	local payload = {
		task = self.task, meta = self.meta,
		success = success and true or false, score = score or 0,
		length = self.t, duration = os.clock() - self.started, steps = self.steps,
	}
	local url = (server or DEFAULT_SERVER) .. "/api/trace"
	pcall(function()
		HttpService:RequestAsync({
			Url = url, Method = "POST",
			Headers = { ["Content-Type"] = "application/json" },
			Body = HttpService:JSONEncode(payload),
		})
	end)
	self.steps = {}; self.t = 0
end

return Trace
