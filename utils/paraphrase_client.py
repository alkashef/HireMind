"""Paraphrase client (embeddings only) using sentence-transformers.

Design choices per TODO/user:
- Embedding-only client (no text generation).
- Uses sentence-transformers API (fast, local) to return floats.
- Model path is configurable via `PARAPHRASE_MODEL_DIR` and exposed in AppConfig.
- Loads onto GPU by default (PARAPHRASE_DEVICE=cuda) when available; falls back to CPU.

Usage:
    from config.settings import AppConfig
    from utils.paraphrase_client import ParaphraseClient

    cfg = AppConfig()
    client = ParaphraseClient(cfg=cfg)
    vec = client.text_to_embedding("hello world")

If the model artifacts are missing, the client raises RuntimeError with an
actionable message referencing `scripts/download_paraphrase.py`.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from config.settings import AppConfig

logger = logging.getLogger(__name__)


class ParaphraseClient:
    """Embedding-only client using sentence-transformers.

    - Lazy-loads the SentenceTransformer model on first use and caches it.
    - Exposes `text_to_embedding` and `embed_batch`.
    """

    def __init__(self, model_dir: Optional[str] = None, device: Optional[str] = None, cfg: Optional[AppConfig] = None):
        self.cfg = cfg or AppConfig()
        self.model_dir = model_dir or self.cfg.paraphrase_model_dir
        self.device = device or self.cfg.paraphrase_device
        self._model = None

    def _lazy_load(self):
        if self._model is not None:
            return

        try:
            # Import lazily; sentence-transformers is already in requirements.txt
            from sentence_transformers import SentenceTransformer
            import torch
        except Exception as exc:
            raise RuntimeError(
                "Missing dependency for paraphrase embeddings (sentence-transformers or torch). "
                "Install required packages or see scripts/download_paraphrase.py for model artifacts."
            ) from exc

        # Resolve device: prefer cuda when requested and available
        desired = (self.device or "cuda").lower()
        use_device = "cpu"
        if desired.startswith("cuda"):
            if torch.cuda.is_available():
                use_device = "cuda"
            else:
                logger.warning("PARAPHRASE_DEVICE=cuda requested but CUDA not available; falling back to CPU")

        try:
            # SentenceTransformer accepts a device argument
            self._model = SentenceTransformer(self.model_dir, device=use_device)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load paraphrase model from '{self.model_dir}': {exc}.\n"
                "If you don't have the model locally, run scripts/download_paraphrase.py to fetch the HF snapshot."
            ) from exc

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return embeddings for a list of texts as lists of floats.

        This method returns native Python lists for JSON-compatibility.
        """
        if not texts:
            return []
        self._lazy_load()

        # The SentenceTransformer model returns numpy arrays by default
        emb = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        if isinstance(emb, np.ndarray):
            # Ensure plain Python floats
            return emb.astype(float).tolist()
        # Fallback: ensure we return lists of floats
        return [list(map(float, e)) for e in emb]

    def text_to_embedding(self, text: str) -> List[float]:
        """Return the embedding for a single text as a list of floats."""
        res = self.embed_batch([text])
        return res[0] if res else []


__all__ = ["ParaphraseClient"]

# Convenience global client and functional API for backwards compatibility
_GLOBAL_PARAPHRASE_CLIENT: Optional[ParaphraseClient] = None


def get_global_paraphrase_client(cfg: Optional[AppConfig] = None) -> ParaphraseClient:
    global _GLOBAL_PARAPHRASE_CLIENT
    if _GLOBAL_PARAPHRASE_CLIENT is None:
        _GLOBAL_PARAPHRASE_CLIENT = ParaphraseClient(cfg=cfg)
    return _GLOBAL_PARAPHRASE_CLIENT


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Module-level convenience wrapper that returns embeddings for a list of texts."""
    client = get_global_paraphrase_client()
    return client.embed_batch(texts)


def text_to_embedding(text: str) -> List[float]:
    """Module-level convenience wrapper for single-text embedding."""
    client = get_global_paraphrase_client()
    return client.text_to_embedding(text)

