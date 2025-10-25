"""Standalone and pytest-compatible checks for local paraphrase embedding model.

This test verifies that the local `paraphrase-MiniLM-L12-v2` model exists under
`models/` and that it can produce an embedding for a short sample string.

Usage (standalone):
    python tests/test_paraphrase_local.py

Usage (pytest):
    pytest -q tests/test_paraphrase_local.py
"""
from __future__ import annotations

import sys
import pathlib
from typing import Optional

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest


MODEL_DIR = PROJECT_ROOT / "models" / "paraphrase-MiniLM-L12-v2"


def _load_sentence_transformer(model_path: Optional[pathlib.Path] = None):
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise RuntimeError("sentence-transformers package is required; run scripts/download_paraphrase.py to fetch the model and `pip install sentence-transformers`") from exc

    if model_path:
        return SentenceTransformer(str(model_path))
    return SentenceTransformer("paraphrase-MiniLM-L12-v2")


def test_model_folder_exists():
    if not MODEL_DIR.exists():
        pytest.skip(f"Local paraphrase model not found at {MODEL_DIR}; run scripts/download_paraphrase.py to install it")


def test_paraphrase_embedding_local():
    """Load the local model and compute a small embedding.

    Skips when the model folder is missing or the sentence-transformers
    package is not installed.
    """
    # Require CUDA for this test
    try:
        import torch
    except Exception:
        pytest.skip("PyTorch not installed; skipping GPU paraphrase test")

    if not torch.cuda.is_available():
        pytest.skip("CUDA not available; skipping GPU paraphrase test")

    if not MODEL_DIR.exists():
        pytest.skip(f"Local paraphrase model not found at {MODEL_DIR}; run scripts/download_paraphrase.py to install it")

    try:
        model = _load_sentence_transformer(MODEL_DIR)
    except RuntimeError as exc:
        pytest.skip(str(exc))

    # Force encode on GPU by ensuring model was initialized with CUDA device
    reported_device = getattr(model, "device", None) or getattr(model, "_target_device", None)
    assert reported_device is not None and "cuda" in str(reported_device).lower(), f"Model not on CUDA: {reported_device}"

    vecs = model.encode(["hello world"], show_progress_bar=False)
    assert hasattr(vecs, "__len__")
    first = vecs[0]
    length = len(first) if hasattr(first, "__len__") else getattr(first, "shape")[0]
    assert length > 0


def main() -> int:
    """Standalone runner for local model verification.

    Exit codes:
      0 - success
      2 - model directory missing
      3 - missing dependency (sentence-transformers)
      4 - unexpected exception
    """
    if not MODEL_DIR.exists():
        print(f"Model directory not found: {MODEL_DIR}\nRun: python scripts/download_paraphrase.py")
        return 2

    try:
        model = _load_sentence_transformer(MODEL_DIR)
    except RuntimeError as exc:
        print(str(exc))
        return 3
    except Exception as exc:
        print("Unexpected error loading model:", repr(exc))
        return 4

    try:
        vecs = model.encode(["hello world"], show_progress_bar=False)
        first = vecs[0]
        length = len(first) if hasattr(first, "__len__") else getattr(first, "shape")[0]
        print(f"Embedding length: {length}; sample values: {first[:6] if hasattr(first, '__len__') else first}")
        return 0
    except Exception as exc:
        print("Failed to compute embedding:", repr(exc))
        return 4


if __name__ == "__main__":
    rc = main()
    raise SystemExit(rc)
