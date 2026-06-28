"""Wrap the plugin Luau into an installable .rbxmx (a Script that Studio loads as
a plugin). Run:  python plugin/build_plugin.py  ->  out/G4StudioPlugin.rbxmx

Install: Studio -> Plugins tab -> "Plugins Folder", drop the .rbxmx in, restart Studio.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, "G4StudioPlugin.server.lua")
OUT = os.path.join(HERE, "..", "out", "G4StudioPlugin.rbxmx")


def main() -> None:
    with open(LUA, "r", encoding="utf-8") as f:
        src = f.read()
    safe = src.replace("]]>", "]] >")  # only illegal sequence inside CDATA
    xml = (
        '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n'
        "<External>null</External>\n<External>nil</External>\n"
        '<Item class="Script" referent="G4PLUGIN1">\n'
        "<Properties>\n"
        '<string name="Name">G4StudioPlugin</string>\n'
        '<bool name="Disabled">false</bool>\n'
        '<ProtectedString name="Source"><![CDATA[' + safe + "]]></ProtectedString>\n"
        "</Properties>\n</Item>\n</roblox>\n"
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"wrote {os.path.abspath(OUT)}  ({len(xml)} bytes)")
    print("Install: Studio -> Plugins -> Plugins Folder -> drop this file in -> restart Studio")


if __name__ == "__main__":
    main()
