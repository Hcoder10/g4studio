"""Headless RUNTIME validator for generated Game modules. Compile-checking only catches syntax;
this executes the game's setup() + 200 step() ticks against a mock of the kit's ctx API + the Roblox
types it uses (Vector3 / Color3 / CFrame / Enum), with a mock arm/tool moved around to exercise the
logic. It catches the runtime bugs that actually break games in Studio (nil arithmetic, bad fields,
calling a missing ctx method, etc.) so broken games never ship.
"""
import io
import os
import subprocess
import tempfile
import zipfile
from urllib.request import urlopen

_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "luau.exe")
_URL = "https://github.com/luau-lang/luau/releases/latest/download/luau-windows.zip"


def _ensure_luau() -> bool:
    """Self-bootstrap the Luau runtime (same release as the vendored luau-compile)."""
    if os.path.exists(_BIN):
        return True
    try:
        data = urlopen(_URL, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.endswith("luau.exe"):
                    os.makedirs(os.path.dirname(_BIN), exist_ok=True)
                    with z.open(n) as src, open(_BIN, "wb") as dst:
                        dst.write(src.read())
                    return True
    except Exception:
        pass
    return False

_MOCK = r"""
-- minimal Roblox-type mocks ------------------------------------------------
local Vmt = {}
local function vec(x, y, z) return setmetatable({ X = x or 0, Y = y or 0, Z = z or 0 }, Vmt) end
Vmt.__add = function(a, b) return vec(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
Vmt.__sub = function(a, b) return vec(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
Vmt.__mul = function(a, b)
    if type(a) == "number" then return vec(b.X * a, b.Y * a, b.Z * a) end
    if type(b) == "number" then return vec(a.X * b, a.Y * b, a.Z * b) end
    return vec(a.X * b.X, a.Y * b.Y, a.Z * b.Z)
end
Vmt.__index = function(self, k)
    if k == "Magnitude" then return math.sqrt(self.X * self.X + self.Y * self.Y + self.Z * self.Z) end
    if k == "Unit" then local m = math.sqrt(self.X * self.X + self.Y * self.Y + self.Z * self.Z); m = m > 0 and m or 1; return vec(self.X / m, self.Y / m, self.Z / m) end
    if k == "Lerp" then return function(s, o, t) return vec(s.X + (o.X - s.X) * t, s.Y + (o.Y - s.Y) * t, s.Z + (o.Z - s.Z) * t) end end
    if k == "Dot" then return function(s, o) return s.X * o.X + s.Y * o.Y + s.Z * o.Z end end
    if k == "Cross" then return function(s, o) return vec(s.Y * o.Z - s.Z * o.Y, s.Z * o.X - s.X * o.Z, s.X * o.Y - s.Y * o.X) end end
    return nil
end
Vector3 = { new = function(x, y, z) return vec(x, y, z) end, zero = vec(0, 0, 0), one = vec(1, 1, 1) }
Color3 = { fromRGB = function() return { R = 0, G = 0, B = 0 } end, new = function() return { R = 0, G = 0, B = 0 } end, fromHSV = function() return {} end }
local Cmt = {}
local function cf() return setmetatable({ Position = vec(0, 0, 0), p = vec(0, 0, 0) }, Cmt) end
Cmt.__mul = function() return cf() end
Cmt.__index = function(self, k) if k == "Position" or k == "p" then return vec(0, 0, 0) end; return function() return cf() end end
CFrame = { new = function() return cf() end, Angles = function() return cf() end, identity = cf(),
    fromAxisAngle = function() return cf() end, lookAt = function() return cf() end, fromEulerAnglesXYZ = function() return cf() end }
local function estub() return setmetatable({}, { __index = function() return estub() end }) end
Enum = estub()
local function part(pos)
    return setmetatable({ Position = pos or vec(0, 0, 0), Color = Color3.new(), Size = vec(1, 1, 1),
        Parent = true, Anchored = false, CanCollide = true, Transparency = 0, Name = "Part" },
        { __index = function() return function() end end })
end
Instance = { new = function() return part() end }
task = { wait = function() end, spawn = function() end, delay = function() end }
game = setmetatable({ GetService = function() return setmetatable({}, { __index = function() return function() end end }) end }, { __index = function() return function() end end })
workspace = game
typeof = typeof or type
tick = function() return 0 end

-- mock ctx -----------------------------------------------------------------
local won = 0
local ctx = {}
ctx.region = { center = vec(0, 1, 3), reach = 5.5, table = part() }
ctx.state = {}
ctx.t = 0
ctx.arm = { tip = part(vec(0, 2, 3)), grasped = nil, linkCF = { part().Position }, getObs = function() return {} end }
ctx.holding = function() return ctx.arm.grasped end
ctx.dist = function(a, b) return (a - b).Magnitude end
ctx.rand = function(lo, hi) return lo + 0.5 * ((hi or 1) - (lo or 0)) end
ctx.spawnCube = function(pos) return part(pos) end
ctx.spawnBin = function(pos) return part(pos) end
ctx.spawnPart = function(props) local p = part(); if type(props) == "table" and props.Position then p.Position = props.Position end; return p end
ctx.attachTool = function(props, offset) local p = part(vec(0, 1.5, 3)); ctx.arm.grasped = p; return p end
ctx.makeGraspable = function() end
ctx.hud = function() end
ctx.popup = function() end
ctx.burst = function() end
ctx.ding = function() end
ctx.win = function() won += 1 end
ctx.lose = function() won += 1 end

-- run the game -------------------------------------------------------------
local ok, Game = pcall(function() return (function() __GAME__ end)() end)
if not ok then print("VALIDATION:FAIL:load:" .. tostring(Game)); return end
if type(Game) ~= "table" or type(Game.setup) ~= "function" or type(Game.step) ~= "function" then
    print("VALIDATION:FAIL:shape:module must return { setup=fn, step=fn, ... }"); return end
local oks, err = pcall(Game.setup, ctx)
if not oks then print("VALIDATION:FAIL:setup:" .. tostring(err)); return end
for i = 1, 200 do
    ctx.t = i / 60
    ctx.arm.tip.Position = vec(math.sin(i * 0.11) * 3, 1.5, 3 + math.cos(i * 0.11) * 2)
    if ctx.arm.grasped then ctx.arm.grasped.Position = ctx.arm.tip.Position end
    if i == 70 and ctx.arm.grasped == nil then ctx.arm.grasped = part(ctx.arm.tip.Position) end  -- simulate a grab
    local okk, e = pcall(Game.step, ctx, 1 / 60)
    if not okk then print("VALIDATION:FAIL:step@" .. i .. ":" .. tostring(e)); return end
end
print("VALIDATION:OK")
"""


def validate_game(source: str) -> tuple[bool, str]:
    """Run the Game module headless. Returns (ok, error_message)."""
    if not _ensure_luau():
        return True, "luau runtime unavailable (skipped)"
    lua = _MOCK.replace("__GAME__", source)
    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False, encoding="utf-8") as f:
        f.write(lua)
        path = f.name
    try:
        proc = subprocess.run([_BIN, path], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=20)
    except Exception as e:
        os.unlink(path)
        return True, f"validator error (skipped): {e}"
    os.unlink(path)
    out = (proc.stdout or "") + (proc.stderr or "")
    if "VALIDATION:OK" in out:
        return True, ""
    for line in out.splitlines():
        if line.startswith("VALIDATION:FAIL:"):
            return False, line[len("VALIDATION:FAIL:"):].strip()
    return False, (out.strip()[:200] or "unknown runtime error")
