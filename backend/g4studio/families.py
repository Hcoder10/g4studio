"""Structured TASK FAMILIES for robot data collection — the opposite of free-text "prompt-and-hope".

Each family pins a robot SKILL, the action space, and the VARIATION AXES the generator should sweep,
so a family produces a diverse, deduped *curriculum* of games (not random one-offs). A persistent
registry tracks what's been generated per family for diversity + coverage.
"""
import difflib
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(REPO, "datasets", "families_registry.json")

FAMILIES = {
    "pick_place": {
        "skill": "reach, grasp, and place objects at target zones",
        "summary": "Move objects from where they are to where they belong.",
        "axes": ["object count (1-6)", "target type (bin / pad / slot / shelf)", "distractor objects",
                 "time pressure", "placement order constraint"],
    },
    "sorting": {
        "skill": "classify, then place objects by an attribute",
        "summary": "Sort a mixed pile into the right destinations by color / size / shape.",
        "axes": ["attribute (color / size / shape)", "number of categories (2-4)", "pile size",
                 "combo / streak scoring", "moving deadline"],
    },
    "stacking": {
        "skill": "precise vertical placement and gentle release (balance + center of mass)",
        "summary": "Build a stable tower where precision and center-of-mass decide success.",
        "axes": ["target height", "block size variance", "order (large->small)", "wobble / nudge",
                 "placement tolerance"],
    },
    "insertion": {
        "skill": "tight-tolerance alignment and insertion (peg-in-hole)",
        "summary": "Fit objects into sockets/holes that demand orientation and precision.",
        "axes": ["clearance (loose / tight)", "orientation requirement", "number of sockets",
                 "insertion depth", "fragility / penalty"],
    },
    "kitting": {
        "skill": "sequenced multi-object assembly following a recipe / layout",
        "summary": "Assemble a kit by placing parts in the right order and layout.",
        "axes": ["number of parts", "sequence strictness", "layout (grid / tray / pattern)",
                 "last-second swap-ins", "timer"],
    },
}


def load_registry() -> dict:
    if os.path.isfile(REGISTRY):
        try:
            return json.load(open(REGISTRY, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_design(family: str, design: dict) -> None:
    reg = load_registry()
    reg.setdefault(family, []).append({"name": design.get("name"), "task": design.get("task"),
                                       "pitch": design.get("pitch")})
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), indent=2)


def is_duplicate(design: dict, prior: list) -> bool:
    """True if this design is too close to one already generated (name or task id)."""
    def norm(s):
        return "".join(c for c in (s or "").lower() if c.isalnum())
    n, t = norm(design.get("name")), norm(design.get("task"))
    for p in prior:
        if difflib.SequenceMatcher(None, n, norm(p.get("name"))).ratio() > 0.8:
            return True
        if t and t == norm(p.get("task")):
            return True
    return False


def family_context(family: str, prior: list) -> str:
    fam = FAMILIES[family]
    ctx = (f"\n\nThis game MUST belong to the '{family}' skill FAMILY: {fam['skill']}. "
           f"{fam['summary']} Pick a FRESH point in the family by varying these axes: "
           f"{', '.join(fam['axes'])}.")
    if prior:
        recent = "; ".join(f"\"{p['name']}\"" for p in prior[-8:])
        ctx += (f"\n\nAlready generated in this family (yours must be clearly DIFFERENT — different "
                f"objects, axis values, twist and scoring): {recent}.")
    return ctx
