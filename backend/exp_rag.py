"""Smoke test for the asset RAG: embed the corpus + run semantic queries."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from g4studio.rag.store import get_store

store = get_store()
dim = store.mat.shape if store.mat is not None else None
print(f"loaded {len(store.assets)} assets | embedding matrix {dim}")

queries = [
    ("a turret to defend my base", None),
    ("an undead monster that walks at the castle", "model"),
    ("background music for an intense fight", "audio"),
    ("particle effect when an enemy blows up", "vfx"),
    ("coins and money for the player economy", None),
    ("a fast vehicle for a racing game", None),
    ("ground texture for grassy terrain", "decal"),
]
for q, t in queries:
    print(f"\nQ: {q!r}  (type={t})")
    for r in store.search(q, type=t, k=4):
        print(f"  {r['score']:+.3f}  [{r['type']:5}] {r['name']}")
