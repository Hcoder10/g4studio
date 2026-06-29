"""Pack the robot-game KIT + a Gemma-authored Game module into ONE self-installing .rbxmx.

Insert the G4RobotGame folder into Workspace, enable HTTP, Play: the Harness builds the SO-101 +
table, hands you the hover controller, runs the game, and ships a manipulation trace every round.

    python roblox/robots/build_game_rbxmx.py <game.lua>   ->   out/G4RobotGame.rbxmx
or import build() and pass the Game source directly.
"""
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "out", "G4RobotGame.rbxmx")
SERVER_URL = "https://g4studio-backend-production.up.railway.app"


def _read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def _cdata(s):
    return "<![CDATA[" + s.replace("]]>", "]] >") + "]]>"


def _script(name, src, ref, cls="Script", disabled=False):
    return (f'<Item class="{cls}" referent="{ref}"><Properties>'
            f'<string name="Name">{name}</string>'
            f'<bool name="Disabled">{"true" if disabled else "false"}</bool>'
            f'<ProtectedString name="Source">{_cdata(src)}</ProtectedString></Properties></Item>')


def _module(name, src, ref):
    return (f'<Item class="ModuleScript" referent="{ref}"><Properties>'
            f'<string name="Name">{name}</string>'
            f'<ProtectedString name="Source">{_cdata(src)}</ProtectedString></Properties></Item>')


def _stringvalue(name, val, ref):
    return (f'<Item class="StringValue" referent="{ref}"><Properties>'
            f'<string name="Name">{name}</string>'
            f'<string name="Value">{html.escape(val)}</string></Properties></Item>')


def build(game_source: str, out_path: str = OUT) -> str:
    so101 = _read("SO101.lua")
    trace = _read("Trace.lua").replace("{{SERVER_URL}}", SERVER_URL)
    harness = _read(os.path.join("kit", "Harness.server.lua"))
    control = _read(os.path.join("kit", "Control.client.lua"))
    children = "\n".join([
        _module("SO101", so101, "g_so101"),
        _module("Trace", trace, "g_trace"),
        _module("Game", game_source, "g_game"),
        _stringvalue("SERVER_URL", SERVER_URL, "g_url"),
        _script("ControlClient", control, "g_client", cls="LocalScript", disabled=True),
        _script("Harness", harness, "g_harness", cls="Script", disabled=False),
    ])
    folder = ('<Item class="Folder" referent="g_root"><Properties>'
              '<string name="Name">G4RobotGame</string></Properties>\n' + children + "\n</Item>")
    xml = ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n'
           "<External>null</External>\n<External>nil</External>\n" + folder + "\n</roblox>\n")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    return os.path.abspath(out_path)


def main():
    src = _read(sys.argv[1]) if len(sys.argv) > 1 else _read(os.path.join("kit", "sample_game.lua"))
    path = build(src)
    print(f"wrote {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
