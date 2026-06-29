"""Asset store: load a corpus of Roblox assets (jsonl), embed them once (cached to .npy),
and semantically search. Multimodal: if an asset has a local thumbnail we blend its image
embedding with its text embedding so visual similarity counts too.

Asset record (one JSON object per line):
  {"id": "rbxassetid://123", "name": "...", "description": "...",
   "type": "mesh|model|decal|audio|vfx", "tags": ["..."], "thumb": "optional/local.png"}
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

from .embedder import embed_texts


def _text_of(a: dict) -> str:
    tags = " ".join(a.get("tags", []) or [])
    return f"{a.get('name', '')}. {a.get('description', '')}. type:{a.get('type', '')} {tags}".strip()


class AssetStore:
    def __init__(self, path: str):
        self.path = path
        self.assets: list[dict] = []
        self.mat: Optional[np.ndarray] = None
        if os.path.exists(path):
            self.load()

    def load(self) -> None:
        with open(self.path, encoding="utf-8") as f:
            self.assets = [json.loads(ln) for ln in f if ln.strip()]
        emb_path = self.path + ".npy"
        if os.path.exists(emb_path):
            mat = np.load(emb_path)
            if mat.shape[0] == len(self.assets):
                self.mat = mat
                return
        self.build()

    def build(self) -> None:
        """Embed every asset (text, blended with thumbnail image when present) and cache."""
        texts = [_text_of(a) for a in self.assets]
        tmat = embed_texts(texts)
        # blend in thumbnail image embeddings where we have a local file
        thumbs, idxs = [], []
        for i, a in enumerate(self.assets):
            tp = a.get("thumb")
            if tp and os.path.exists(tp):
                thumbs.append(tp)
                idxs.append(i)
        if thumbs:
            from .embedder import embed_images
            imat = embed_images(thumbs)
            for j, i in enumerate(idxs):
                blended = tmat[i] + imat[j]
                tmat[i] = blended / (np.linalg.norm(blended) + 1e-8)
        self.mat = tmat.astype("float32")
        np.save(self.path + ".npy", self.mat)

    def search(self, query: str, type: Optional[str] = None, k: int = 6) -> list[dict]:
        if self.mat is None or not self.assets:
            return []
        q = embed_texts([query])[0]
        sims = self.mat @ q
        out = []
        for i in np.argsort(-sims):
            a = self.assets[int(i)]
            if type and a.get("type") != type:
                continue
            out.append({**a, "score": round(float(sims[int(i)]), 3)})
            if len(out) >= k:
                break
        return out


_STORE: Optional[AssetStore] = None


def get_store() -> AssetStore:
    global _STORE
    if _STORE is None:
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _STORE = AssetStore(os.path.join(here, "assets", "corpus.jsonl"))
    return _STORE
