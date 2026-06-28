"""Generic emitter: render ANY genre's build dict to artifacts.

A build dict is genre-agnostic:
    {
      "root": "G4Game",
      "folders": ["Platforms", "Orbs", ...],
      "parts":  [{folder, class, name, pos[3], size[3], color[3], material, cc}, ...],
      "scripts":[{folder, name, source}, ...],   # mechanics, baked per-game
    }
Both obby and the new genres produce this shape, so emitters + plugin are shared.
"""
from __future__ import annotations

from .common import material_token, xml_escape, hex_to_rgb  # noqa: F401


def _packed(color) -> int:
    r, g, b = int(color[0]), int(color[1]), int(color[2])
    return 4278190080 + (r << 16) + (g << 8) + b


class _Ref:
    def __init__(self) -> None:
        self.n = 0

    def next(self) -> str:
        self.n += 1
        return f"G4REF{self.n:08d}"


def _part_xml(ref: _Ref, op: dict) -> str:
    pos, size = op["pos"], op["size"]
    cc = "true" if op.get("cc", True) else "false"
    return (
        f'<Item class="{op.get("class", "Part")}" referent="{ref.next()}"><Properties>'
        f'<string name="Name">{xml_escape(op["name"])}</string>'
        f'<bool name="Anchored">true</bool>'
        f'<bool name="CanCollide">{cc}</bool>'
        f'<Color3uint8 name="Color">{_packed(op["color"])}</Color3uint8>'
        f'<token name="Material">{material_token(op.get("material", "SmoothPlastic"))}</token>'
        f'<Vector3 name="size"><X>{size[0]}</X><Y>{size[1]}</Y><Z>{size[2]}</Z></Vector3>'
        f'<CoordinateFrame name="CFrame"><X>{pos[0]}</X><Y>{pos[1]}</Y><Z>{pos[2]}</Z>'
        "<R00>1</R00><R01>0</R01><R02>0</R02><R10>0</R10><R11>1</R11><R12>0</R12>"
        "<R20>0</R20><R21>0</R21><R22>1</R22></CoordinateFrame>"
        "</Properties></Item>"
    )


def _script_xml(ref: _Ref, name: str, source: str) -> str:
    safe = source.replace("]]>", "]] >")
    return (
        f'<Item class="Script" referent="{ref.next()}"><Properties>'
        f'<string name="Name">{xml_escape(name)}</string>'
        f'<bool name="Disabled">false</bool>'
        f'<ProtectedString name="Source"><![CDATA[{safe}]]></ProtectedString>'
        "</Properties></Item>"
    )


def _folder_xml(ref: _Ref, name: str, inner: str) -> str:
    return (f'<Item class="Folder" referent="{ref.next()}">'
            f'<Properties><string name="Name">{xml_escape(name)}</string></Properties>{inner}</Item>')


def build_to_rbxmx(build: dict) -> str:
    ref = _Ref()
    root = build.get("root", "G4Game")
    by_folder: dict = {}
    for op in build.get("parts", []):
        by_folder.setdefault(op.get("folder", "_root"), []).append(op)

    children = []
    for fname in build.get("folders", []):
        inner = "".join(_part_xml(ref, op) for op in by_folder.get(fname, []))
        children.append(_folder_xml(ref, fname, inner))
    for op in by_folder.get("_root", []):
        children.append(_part_xml(ref, op))
    for s in build.get("scripts", []):
        children.append(_script_xml(ref, s["name"], s["source"]))

    root_xml = _folder_xml(ref, root, "".join(children))
    return (
        '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n'
        '<Meta name="ExplicitAutoJoints">true</Meta>\n<External>null</External>\n<External>nil</External>\n'
        f"{root_xml}\n</roblox>\n"
    )


def build_to_luau(build: dict) -> str:
    root = build.get("root", "G4Game")
    L = [f"-- G4Studio generated game", "local WS = workspace",
         f'local old = WS:FindFirstChild("{root}"); if old then old:Destroy() end',
         f'local root = Instance.new("Folder"); root.Name = "{root}"; root.Parent = WS',
         "local folders = {_root = root}"]
    for fname in build.get("folders", []):
        L.append(f'do local f=Instance.new("Folder");f.Name="{fname}";f.Parent=root;folders["{fname}"]=f end')
    for op in build.get("parts", []):
        c = op["color"]
        cc = "true" if op.get("cc", True) else "false"
        L.append(
            f'do local p=Instance.new("{op.get("class", "Part")}");p.Name="{op["name"]}";'
            f'p.Anchored=true;p.CanCollide={cc};'
            f'p.Size=Vector3.new({op["size"][0]},{op["size"][1]},{op["size"][2]});'
            f'p.CFrame=CFrame.new({op["pos"][0]},{op["pos"][1]},{op["pos"][2]});'
            f'p.Color=Color3.fromRGB({c[0]},{c[1]},{c[2]});p.Material=Enum.Material.{op.get("material", "SmoothPlastic")};'
            f'p.Parent=folders["{op.get("folder", "_root")}"] or root end'
        )
    for s in build.get("scripts", []):
        src = s["source"].replace("]==]", "]= =]")
        L.append(f'do local sc=Instance.new("Script");sc.Name="{s["name"]}";sc.Source=[==[\n{src}\n]==];sc.Parent=root end')
    L.append('print("[G4Studio] built " .. root.Name)')
    return "\n".join(L)
