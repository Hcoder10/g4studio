"""Local open-source MULTIMODAL embedder (text + image in one space) for asset RAG.

Default: jina-clip-v2 (recent multimodal model) via sentence-transformers, on GPU if
available. Override with G4_EMBED_MODEL. Because it's multimodal, we can embed an
asset's THUMBNAIL image and its text into the same space and search either way.
"""
from __future__ import annotations

import os

import numpy as np

_MODEL_NAME = os.environ.get("G4_EMBED_MODEL", "jinaai/jina-clip-v2")
_model = None


def _load():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = SentenceTransformer(_MODEL_NAME, trust_remote_code=True, device=device)
    return _model


def embed_texts(texts, batch_size: int = 64) -> np.ndarray:
    m = _load()
    embs = m.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                    convert_to_numpy=True, show_progress_bar=False)
    return np.asarray(embs, dtype="float32")


def embed_images(images, batch_size: int = 16) -> np.ndarray:
    """images: list of PIL.Image or file paths (jina-clip-v2 handles both)."""
    m = _load()
    embs = m.encode(list(images), batch_size=batch_size, normalize_embeddings=True,
                    convert_to_numpy=True, show_progress_bar=False)
    return np.asarray(embs, dtype="float32")


def embed_one(text: str) -> np.ndarray:
    return embed_texts([text])[0]
