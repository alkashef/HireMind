"""Embedding adapter: local paraphrase model with GPU support when available.

This module exposes a simple `text_to_embedding(text: str) -> list[float]`
function that loads the `paraphrase-MiniLM-L12-v2` model from the local
`models/` directory when available, and otherwise falls back to the
sentence-transformers hub name. It prefers CUDA when PyTorch reports an
available GPU.

The loader is lazy and caches the model in module scope.
"""
from __future__ import annotations

from typing import List, Optional
import logging
import threading

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_model = None
_device = "cpu"


def _init_model(local_model_path: Optional[str] = None):
    """Lazy-load the sentence-transformers model and pick device (cuda if available).

    If the local model path exists we try to load from it; otherwise we
    fall back to the HF model id "paraphrase-MiniLM-L12-v2" which will
    download if needed (user should run `scripts/download_paraphrase.py` in
    production to avoid runtime downloads).
    """
    global _model, _device
    if _model is not None:
        return

    try:
        # Prefer torch device selection
        import torch
    except Exception:
        torch = None

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        logger.exception("sentence-transformers not available")
        raise RuntimeError("sentence-transformers is required for embeddings. Install with 'pip install sentence-transformers'") from exc

    # pick device
    if torch is not None and torch.cuda.is_available():
        _device = "cuda"
    else:
        _device = "cpu"

    model_name = local_model_path or "paraphrase-MiniLM-L12-v2"
    try:
        # SentenceTransformer accepts device argument
        _model = SentenceTransformer(model_name, device=_device)
        logger.info("Loaded paraphrase model '%s' on device=%s", model_name, _device)
    except Exception as exc:
        logger.exception("Failed to load SentenceTransformer model '%s'", model_name)
        raise


def text_to_embedding(text: str, local_model_path: Optional[str] = None) -> List[float]:
    """Return an embedding vector (list of floats) for the input text.

    Args:
        text: input string
        local_model_path: optional path to local model folder under `models/`.

    Returns:
        list[float] embedding

    Raises:
        RuntimeError if sentence-transformers isn't installed or loading fails.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    if _model is None:
        with _model_lock:
            if _model is None:
                _init_model(local_model_path)

    # encode returns numpy array or list depending on backend; convert to list
    vec = _model.encode([text], show_progress_bar=False)[0]
    # convert to plain python list of floats
    try:
        return [float(x) for x in vec.tolist()]
    except Exception:
        # if vec is already a list-like
        return [float(x) for x in vec]


__all__ = ["text_to_embedding"]
