"""Emit a GameSpec as an insertable Roblox model (.rbxmx XML).

Why a model (not a place): you right-click Workspace -> Insert From File -> select
the .rbxmx -> press Play. Works in any place, no full-place structure needed. The
mechanics Script lives inside the folder (runs from Workspace), so it "just works".

We deliberately avoid CollectionService tags and Attributes (both serialize as
binary blobs in XML). Instead we organize parts into named folders and encode
moving-platform params in the part name (Move_<axis>_<dist>_<speed>).
"""
from __future__ import annotations

from ..mechanics import get_mechanics_luau
from ..ops import GameSpec
from .common import color3uint8, material_token, xml_escape


class _Ref:
    def __init__(self) -> None:
        self.n = 0

    def next(self) -> str:
        self.n += 1
        return f"G4REF{self.n:08d}"


def _part(ref: _Ref, class_name: str, name: str, pos, size,
          color: str, material: str, anchored: bool = True,
          can_collide: bool = True, transparency: float = 0.0) -> str:
    return f"""<Item class="{class_name}" referent="{ref.next()}">
<Properties>
<string name="Name">{xml_escape(name)}</string>
<bool name="Anchored">{str(anchored).lower()}</bool>
<bool name="CanCollide">{str(can_collide).lower()}</bool>
<Color3uint8 name="Color">{color3uint8(color)}</Color3uint8>
<token name="Material">{material_token(material)}</token>
<float name="Transparency">{transparency}</float>
<Vector3 name="size"><X>{size[0]}</X><Y>{size[1]}</Y><Z>{size[2]}</Z></Vector3>
<CoordinateFrame name="CFrame"><X>{pos[0]}</X><Y>{pos[1]}</Y><Z>{pos[2]}</Z><R00>1</R00><R01>0</R01><R02>0</R02><R10>0</R10><R11>1</R11><R12>0</R12><R20>0</R20><R21>0</R21><R22>1</R22></CoordinateFrame>
</Properties>
</Item>"""


def _script(ref: _Ref, name: str, source: str) -> str:
    # Source is a ProtectedString in CDATA. Guard against the only illegal token.
    safe = source.replace("]]>", "]] >")
    return f"""<Item class="Script" referent="{ref.next()}">
<Properties>
<string name="Name">{xml_escape(name)}</string>
<bool name="Disabled">false</bool>
<ProtectedString name="Source"><![CDATA[{safe}]]></ProtectedString>
</Properties>
</Item>"""


def _folder(ref: _Ref, name: str, children: str) -> str:
    return f"""<Item class="Folder" referent="{ref.next()}">
<Properties><string name="Name">{xml_escape(name)}</string></Properties>
{children}
</Item>"""


def to_rbxmx(spec: GameSpec) -> str:
    ref = _Ref()

    platforms = "\n".join(
        _part(ref, "Part", f"Platform{i + 1}", p.pos, p.size, p.color, p.material)
        for i, p in enumerate(spec.platforms)
    )
    hazards = "\n".join(
        _part(ref, "Part", f"Hazard{i + 1}", h.pos, h.size, h.color, h.material)
        for i, h in enumerate(spec.hazards)
    )
    checkpoints = "\n".join(
        _part(ref, "Part", f"Checkpoint{c.index}", c.pos, c.size, c.color, c.material)
        for c in spec.checkpoints
    )
    moving = "\n".join(
        _part(ref, "Part", f"Move_{m.axis}_{m.distance}_{m.speed}", m.pos, m.size, m.color, m.material)
        for m in spec.moving
    )
    spinners = "\n".join(
        _part(ref, "Part", f"Spin_{s.axis}_{s.speed}", s.pos, s.size, s.color, s.material)
        for s in spec.spinners
    )
    decor = "\n".join(
        _part(ref, "Part", f"Decor{i + 1}", d.pos, d.size, d.color, d.material, can_collide=False)
        for i, d in enumerate(spec.decor)
    )

    spawn = _part(ref, "SpawnLocation", "Spawn", spec.spawn.pos, (8.0, 1.0, 8.0),
                  "#cfd8dc", "SmoothPlastic")
    win = _part(ref, "Part", "Win", spec.win.pos, spec.win.size, spec.win.color, spec.win.material)
    mechanics = _script(ref, "G4Mechanics", get_mechanics_luau())

    children = "\n".join([
        _folder(ref, "Platforms", platforms),
        _folder(ref, "Hazards", hazards),
        _folder(ref, "Checkpoints", checkpoints),
        _folder(ref, "Moving", moving),
        _folder(ref, "Spinners", spinners),
        _folder(ref, "Decor", decor),
        spawn,
        win,
        mechanics,
    ])
    root = _folder(ref, "G4Obby", children)

    return f"""<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">
<Meta name="ExplicitAutoJoints">true</Meta>
<External>null</External>
<External>nil</External>
{root}
</roblox>
"""
