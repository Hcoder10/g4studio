"""Build a REAL asset corpus from Roblox's Creator Store via the public toolbox-service
search (no API key needed). Pulls free, game-relevant meshes / models / decals / audio,
writes assets/corpus.jsonl. Run: python g4studio/rag/fetch.py
"""
from __future__ import annotations

import json
import os
import time

import httpx

SEARCH = "https://apis.roblox.com/toolbox-service/v2/assets:search"

KEYWORDS = {
    "Model": ["tower", "turret", "cannon", "archer tower", "wizard tower", "knight", "zombie",
              "goblin", "orc", "skeleton", "dragon", "slime monster", "robot", "alien", "spaceship",
              "race car", "tank", "tree", "rock", "castle", "medieval house", "crate", "barrel",
              "treasure chest", "crystal", "torch", "fence", "bridge", "sword", "shield", "laser gun",
              "spawn pad", "checkpoint", "coin pickup", "boss monster", "enemy", "npc character"],
    "Decal": ["grass texture", "lava texture", "brick wall", "wood plank", "metal panel", "water",
              "sand", "snow", "stone floor", "target", "arrow", "ui button", "health bar",
              "explosion", "smoke"],
    "Audio": ["explosion", "coin pickup", "button click", "sword hit", "gun shot", "magic spell",
              "jump", "footstep", "victory fanfare", "game over", "epic battle music",
              "ambient music", "menu music loop", "laser", "powerup", "damage hit", "heal",
              "wave horn", "bell", "whoosh", "cannon fire", "enemy death"],
}
CAT_TYPE = {"Model": "model", "Decal": "decal", "Audio": "audio"}


def _is_free(item: dict) -> bool:
    cp = item.get("creatorStoreProduct") or {}
    q = (cp.get("purchasePrice") or {}).get("quantity") or {}
    return bool(cp.get("purchasable")) and q.get("significand", 1) == 0


def fetch_kw(client: httpx.Client, category: str, keyword: str, want: int = 12) -> list[dict]:
    try:
        r = client.get(SEARCH, params={"searchCategoryType": category, "query": keyword, "limit": 40})
    except Exception:
        return []
    if r.status_code != 200:
        return []
    out = []
    for item in r.json().get("creatorStoreAssets", []) or []:
        if not _is_free(item):
            continue
        a = item.get("asset") or {}
        aid = a.get("id")
        if not aid:
            continue
        name = (a.get("name") or "").strip()
        desc = (a.get("description") or "").strip().replace("\r", " ").replace("\n", " ")[:220]
        tags = [keyword]
        if category == "Audio":
            for k in ("audioType", "genre"):
                if a.get(k):
                    tags.append(str(a[k]).lower())
        out.append({
            "id": f"rbxassetid://{aid}",
            "name": name or keyword,
            "description": desc or f"{keyword} {CAT_TYPE[category]}",
            "type": CAT_TYPE[category],
            "tags": tags,
        })
        if len(out) >= want:
            break
    return out


def build_corpus(out_path: str, want: int = 12) -> int:
    seen: set[str] = set()
    rows: list[dict] = []
    headers = {"User-Agent": "g4studio-asset-rag/1.0"}
    with httpx.Client(timeout=25.0, headers=headers) as client:
        for cat, kws in KEYWORDS.items():
            got = 0
            for kw in kws:
                for row in fetch_kw(client, cat, kw, want):
                    if row["id"] in seen:
                        continue
                    seen.add(row["id"])
                    rows.append(row)
                    got += 1
                time.sleep(0.12)
            print(f"  {cat}: {got} assets")
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
    path = os.path.join(here, "assets", "corpus.jsonl")
    print("fetching Roblox Creator Store assets (no key)…")
    n = build_corpus(path)
    cache = path + ".npy"
    if os.path.exists(cache):
        os.remove(cache)  # force re-embed on next load
    print(f"wrote {n} assets -> {path} (embeddings will rebuild on next use)")
