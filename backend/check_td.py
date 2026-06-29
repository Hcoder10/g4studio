import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g4studio.verify import verify
from g4studio.syntax import check
d = "out/td"; mods = []
for f in sorted(os.listdir(d)):
    if not f.endswith(".lua") or "Bootstrap" in f: continue
    src = open(os.path.join(d, f), encoding="utf-8").read()
    if f.startswith("SHARED_"): kind, nm = "shared", f[7:-4]
    elif f.startswith("SYS_server_"): kind, nm = "server", f[11:-4]
    elif f.startswith("SYS_client_"): kind, nm = "client", f[11:-4]
    else: continue
    mods.append({"name": nm, "kind": kind, "source": src})
issues, _ = verify({"shared_remotes": []}, mods)
comp = [(m["name"], check(m["source"])) for m in mods]; comp = [(n, e) for n, e in comp if e]
allsrc = "\n".join(m["source"] for m in mods)
serv = "\n".join(m["source"] for m in mods if m["kind"] == "server")
def c(p, s=allsrc): return len(re.findall(p, s))
print(f"VERIFY mismatches: {len(issues)} | COMPILE errors: {len(comp)}")
for n, e in comp: print("   compile:", n, e)
print(f"JUICE -> Sound:{c(r'Sound')} Particle:{c(r'ParticleEmitter')} Tween:{c(r'TweenService|:Tween')} Billboard:{c(r'BillboardGui')}")
print(f"FOOTGUNS -> bare wait(:{c(chr(92)+'bwait'+chr(92)+'(')-c(r'task.wait'+chr(92)+'(')-c(r':[Ww]ait'+chr(92)+'(')} | LocalPlayer in server:{c(r'LocalPlayer', serv)} | SetPrimaryPartCFrame:{c('SetPrimaryPartCFrame')}")
print("modules:", [(m['name'], m['kind']) for m in mods])
