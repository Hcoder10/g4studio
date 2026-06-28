"""Execute the model's world-building Luau in a stubbed Roblox sandbox (Lua 5.4 via
lupa) to recover the geometry — so the authored path can be RENDERED and shown to
Gemma-4 vision, and so runtime/syntax errors become validation signals.

Best-effort: a tiny Luau->Lua5.4 transpiler (compound assignment, `continue`) plus a
tolerant Roblox API stub. Gameplay (event handlers, task.spawn loops) is registered
but NOT run; only the synchronous world build executes. On any failure we return the
error (a useful signal) instead of raising.
"""
from __future__ import annotations

import re
from typing import Optional

# ---- tiny Luau -> Lua 5.4 transpiler ---------------------------------------
_COMPOUND = re.compile(r"^(\s*)([\w\.]+(?:\[[^\]]*\])?)\s*([+\-*/%]|\.\.)=\s*(.+?)\s*$")
_KW = re.compile(r"\b(function|if|for|while|do|repeat|end|until|elseif|else|then)\b")
_STR_COMMENT = re.compile(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|--\[\[.*?\]\]|--[^\n]*)', re.S)


def _compound(line: str) -> str:
    m = _COMPOUND.match(line)
    if not m:
        return line
    indent, lhs, op, rhs = m.groups()
    return f"{indent}{lhs} = {lhs} {op} {rhs}"


def _transpile(src: str) -> str:
    # compound assignment, line by line
    src = "\n".join(_compound(ln) for ln in src.split("\n"))
    # strip Luau type annotations on locals/params (best-effort, conservative)
    src = re.sub(r"(local\s+[\w\s,]+?)\s*:\s*[\w\.\{\}\[\]<>,\s\|\?]+?(\s*=)", r"\1\2", src)
    if "continue" not in src:
        return src

    # `continue` -> goto, with a unique label inserted at each loop's end.
    out, stack, counter = [], [], [0]

    def mask(line: str) -> str:
        return _STR_COMMENT.sub(lambda m: " " * len(m.group(0)), line)

    for line in src.split("\n"):
        masked = mask(line)
        new_line = line
        # handle continue first (belongs to nearest loop on the stack)
        if re.search(r"\bcontinue\b", masked):
            for fr in reversed(stack):
                if fr["loop"]:
                    fr["cont"] = True
                    new_line = re.sub(r"\bcontinue\b", f"goto __cont{fr['id']}", new_line)
                    break
        # track block open/close via keywords in the masked line
        for kw in _KW.findall(masked):
            if kw in ("function", "if", "while", "for", "do"):
                # `do` can be the body of for/while (already pushed) — only push standalone do
                if kw == "do" and stack and stack[-1].get("await_do"):
                    stack[-1]["await_do"] = False
                    continue
                is_loop = kw in ("for", "while")
                fr = {"loop": is_loop, "cont": False, "id": counter[0], "await_do": is_loop}
                counter[0] += 1
                stack.append(fr)
            elif kw == "repeat":
                stack.append({"loop": True, "cont": False, "id": counter[0], "await_do": False})
                counter[0] += 1
            elif kw in ("end", "until"):
                if stack:
                    fr = stack.pop()
                    if fr["loop"] and fr["cont"]:
                        new_line = re.sub(r"\b(end|until)\b", f"::__cont{fr['id']}:: \\1", new_line, count=1)
        out.append(new_line)
    return "\n".join(out)


# ---- Roblox API stub (Lua) -------------------------------------------------
_PRELUDE = r"""
__all = {}
TOLERANT = setmetatable({}, {
  __index = function() return TOLERANT end, __call = function() return TOLERANT end,
  __add=function() return 0 end, __sub=function() return 0 end, __mul=function() return 0 end,
  __div=function() return 0 end, __unm=function() return 0 end, __mod=function() return 0 end,
  __concat=function() return "" end, __tostring=function() return "" end, __len=function() return 0 end,
})

local VM = {}
function VM.__add(a,b) return Vector3.new(a.X+b.X,a.Y+b.Y,a.Z+b.Z) end
function VM.__sub(a,b) return Vector3.new(a.X-b.X,a.Y-b.Y,a.Z-b.Z) end
function VM.__mul(a,b)
  if type(a)=="number" then return Vector3.new(b.X*a,b.Y*a,b.Z*a) end
  if type(b)=="number" then return Vector3.new(a.X*b,a.Y*b,a.Z*b) end
  return Vector3.new(a.X*b.X,a.Y*b.Y,a.Z*b.Z)
end
VM.__index = function(v,k)
  if k=="Magnitude" then return math.sqrt(rawget(v,"X")^2+rawget(v,"Y")^2+rawget(v,"Z")^2) end
  if k=="Unit" then local m=v.Magnitude; if m==0 then m=1 end return Vector3.new(rawget(v,"X")/m,rawget(v,"Y")/m,rawget(v,"Z")/m) end
  if k=="x" then return rawget(v,"X") end
  if k=="y" then return rawget(v,"Y") end
  if k=="z" then return rawget(v,"Z") end
  return nil
end
Vector3 = { new=function(x,y,z) return setmetatable({X=x or 0,Y=y or 0,Z=z or 0}, VM) end }
Vector2 = { new=function(x,y) return Vector3.new(x or 0,y or 0,0) end }

local CM = {}
CM.__mul = function(a,b)
  local pa = rawget(a,"Position") or Vector3.new(0,0,0)
  local pb = (type(b)=="table" and rawget(b,"Position")) or Vector3.new(0,0,0)
  return CFrame.new(pa.X+pb.X, pa.Y+pb.Y, pa.Z+pb.Z)
end
CM.__index = function(c,k)
  if k=="Position" or k=="p" then return rawget(c,"Position") end
  if k=="X" then return rawget(c,"Position").X end
  if k=="Y" then return rawget(c,"Position").Y end
  if k=="Z" then return rawget(c,"Position").Z end
  return nil
end
CFrame = {
  new=function(x,y,z)
    if type(x)=="table" then return setmetatable({Position=x}, CM) end
    return setmetatable({Position=Vector3.new(x or 0,y or 0,z or 0)}, CM)
  end,
  Angles=function() return setmetatable({Position=Vector3.new(0,0,0)}, CM) end,
  fromEulerAnglesXYZ=function() return setmetatable({Position=Vector3.new(0,0,0)}, CM) end,
  lookAt=function(p) return setmetatable({Position=(type(p)=="table" and p) or Vector3.new(0,0,0)}, CM) end,
}

Color3 = {
  new=function(r,g,b) return {R=r or 0,G=g or 0,B=b or 0,_rgb={math.floor((r or 0)*255+0.5),math.floor((g or 0)*255+0.5),math.floor((b or 0)*255+0.5)}} end,
  fromRGB=function(r,g,b) return {R=(r or 0)/255,G=(g or 0)/255,B=(b or 0)/255,_rgb={r or 0,g or 0,b or 0}} end,
  fromHSV=function() return Color3.fromRGB(150,150,150) end,
}
local function tolctor() return TOLERANT end
UDim2 = { new=tolctor, fromScale=tolctor, fromOffset=tolctor }
UDim = { new=tolctor }
NumberSequence = { new=tolctor }
ColorSequence = { new=tolctor }
NumberRange = { new=tolctor }
TweenInfo = { new=tolctor }
Rect = { new=tolctor }
PhysicalProperties = { new=tolctor }
BrickColor = setmetatable({ new=function() return {Color=Color3.fromRGB(160,160,160)} end,
  Random=function() return {Color=Color3.fromRGB(160,160,160)} end },
  { __call=function() return {Color=Color3.fromRGB(160,160,160)} end })

local enumCat = setmetatable({}, { __index=function(_,name) return {Name=name, Value=0, EnumType=""} end })
Enum = setmetatable({}, { __index=function() return enumCat end })

local function newInstance(class)
  local props = {}
  local mt = {
    __index = function(_,k)
      if k=="_class" then return class end
      if k=="_props" then return props end
      if k=="ClassName" or k=="Name" then return props[k] or class end
      if props[k] ~= nil then return props[k] end
      return TOLERANT  -- methods / unset props -> tolerant
    end,
    __newindex = function(_,k,v) props[k]=v end,
  }
  local self = setmetatable({}, mt)
  table.insert(__all, self)
  return self
end
Instance = { new=function(class) return newInstance(class or "Part") end }

workspace = newInstance("Workspace")
Workspace = workspace
game = setmetatable({}, { __index=function(_,k)
  if k=="Workspace" then return workspace end
  if k=="GetService" then return function(_, name) return newInstance(name or "Service") end end
  if k=="FindService" then return function(_, name) return newInstance(name or "Service") end end
  return TOLERANT
end })

task = { spawn=function() return TOLERANT end, delay=function() return TOLERANT end,
         defer=function() return TOLERANT end, wait=function() return 0 end, cancel=function() end }
function wait() return 0 end
function spawn() return TOLERANT end
function delay() return TOLERANT end
function print() end
function warn() end
function tick() return 0 end
require = function() return TOLERANT end
os = os or {}; os.time = function() return 0 end; os.clock = function() return 0 end
setmetatable(_G, { __index = function() return TOLERANT end })

-- instruction-count guard: break runaway/infinite loops (world build is synchronous)
local __ic = 0
if debug and debug.sethook then
  debug.sethook(function() __ic = __ic + 1; if __ic > 600 then error("G4_TIMEOUT") end end, "", 100000)
end
"""

_BASEPARTS = {"Part", "SpawnLocation", "WedgePart", "CornerWedgePart", "MeshPart",
              "TrussPart", "Seat", "VehicleSeat", "Model"}
_MAT_NAMES = None  # resolved lazily


def run_world(luau_src: str, max_parts: int = 1200) -> tuple[dict, Optional[str]]:
    """Run the world-building portion -> {"parts": [...]}, error|None."""
    try:
        from lupa import LuaRuntime
    except Exception as e:  # lupa missing
        return {"parts": []}, f"lupa unavailable: {e}"

    code = _PRELUDE + "\n" + _transpile(luau_src)
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    err = None
    try:
        lua.execute(code)
    except Exception as e:
        err = str(e).splitlines()[-1][:300] if str(e) else "lua error"

    parts = []
    try:
        all_inst = lua.globals().__all
        if all_inst is not None:
            for inst in list(all_inst.values()):
                p = _extract_part(inst)
                if p:
                    parts.append(p)
                    if len(parts) >= max_parts:
                        break
    except Exception as e:
        if not err:
            err = f"extract: {e}"
    return {"parts": parts}, err


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _extract_part(inst):
    try:
        cls = inst._class
    except Exception:
        return None
    if cls not in _BASEPARTS or cls == "Model":
        return None
    props = inst._props
    if props is None:
        return None
    # position
    pos = props["Position"]
    if pos is None:
        cf = props["CFrame"]
        pos = cf["Position"] if cf is not None else None
    if pos is None:
        return None
    px, py, pz = _num(pos["X"]), _num(pos["Y"]), _num(pos["Z"])
    size = props["Size"]
    if size is not None:
        sx, sy, sz = _num(size["X"], 4), _num(size["Y"], 1), _num(size["Z"], 4)
    else:
        sx, sy, sz = (8, 1, 8) if cls == "SpawnLocation" else (4, 4, 4)
    col = props["Color"]
    rgb = [150, 150, 150]
    if col is not None:
        try:
            c = col._rgb
            if c is not None:
                rgb = [int(_num(c[1], 150)), int(_num(c[2], 150)), int(_num(c[3], 150))]
        except Exception:
            pass
    mat = props["Material"]
    material = "SmoothPlastic"
    if mat is not None:
        try:
            material = str(mat["Name"]) or "SmoothPlastic"
        except Exception:
            pass
    cc = props["CanCollide"]
    return {"name": str(props["Name"] or cls), "pos": [px, py, pz], "size": [sx, sy, sz],
            "color": rgb, "material": material, "cc": (cc if isinstance(cc, bool) else True)}
