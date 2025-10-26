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

import numpy as np
import pytest

from config.settings import AppConfig


cfg = AppConfig()


def _load_sentence_transformer(model_path: Optional[pathlib.Path] = None, device: str = "cuda"):
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise RuntimeError("sentence-transformers package is required; run scripts/download_paraphrase.py to fetch the model and `pip install sentence-transformers`") from exc

    if model_path:
        return SentenceTransformer(str(model_path), device=device)
    return SentenceTransformer("paraphrase-MiniLM-L12-v2", device=device)


def test_paraphrase_embedding_gpu_consistency():
    """GPU-only: load configured paraphrase model and assert numeric consistency.

    Requirements enforced (test will be skipped if any missing):
      - PyTorch installed with CUDA available
      - sentence-transformers package installed
      - model artifacts present at AppConfig().paraphrase_model_dir

    Assertions (fail the test if either fails):
      - embedding length equals the model's reported embedding dimension
      - repeated encode() calls produce the same numeric output (deterministic)
    """
    # Require torch + CUDA
    try:
        import torch
    except Exception:
        pytest.fail("PyTorch not installed; GPU is required for this test")

    if not torch.cuda.is_available():
        pytest.fail("CUDA not available; GPU is required for this test")

    model_dir = pathlib.Path(cfg.paraphrase_model_dir)
    if not model_dir.exists():
        pytest.fail(f"Local paraphrase model not found at {model_dir}; run scripts/download_paraphrase.py to install it")

    try:
        model = _load_sentence_transformer(model_dir, device=cfg.paraphrase_device)
    except RuntimeError as exc:
        pytest.fail(str(exc))

    # Ensure model is on CUDA
    reported_device = getattr(model, "device", None) or getattr(model, "_target_device", None)
    assert reported_device is not None and "cuda" in str(reported_device).lower(), f"Model not on CUDA: {reported_device}"

    # Load sample prompt via AppConfig prompt filename
    prompt_name = cfg.prompt_sample_short_hello
    prompt_path = PROJECT_ROOT / "prompts" / prompt_name
    if not prompt_path.exists():
        pytest.fail(f"Prompt file {prompt_path} not found; set PROMPT_SAMPLE_SHORT_HELLO in config or add the file to prompts/")

    sample_text = prompt_path.read_text(encoding="utf-8").strip()
    if not sample_text:
        pytest.fail(f"Prompt file {prompt_path} is empty")

    # Encode twice and check numeric consistency
    try:
        # seed for determinism where applicable
        torch.manual_seed(0)
        vec1 = model.encode([sample_text], show_progress_bar=False)[0]
        torch.manual_seed(0)
        vec2 = model.encode([sample_text], show_progress_bar=False)[0]
    except Exception as exc:
        pytest.fail(f"Failed to compute embeddings on GPU: {exc}")

    # Convert to numpy arrays
    a1 = np.asarray(vec1)
    a2 = np.asarray(vec2)

    # Embedding dimension consistency
    try:
        expected_dim = model.get_sentence_embedding_dimension()
    except Exception:
        expected_dim = a1.shape[0]

    assert a1.shape[0] == expected_dim, f"Embedding length {a1.shape[0]} != expected {expected_dim}"
    assert a2.shape[0] == expected_dim

    # Determinism: repeated calls must match numerically
    assert a1.shape == a2.shape, "Embedding shapes differ between runs"
    if not np.allclose(a1, a2, atol=1e-6):
        # Fail the test when numeric outputs are not consistent
        pytest.fail("Embedding outputs differ between repeated encode() calls (not deterministic)")


def main() -> int:
    """Standalone runner for local model verification (returns exit codes)."""
    try:
        import torch
    except Exception:
        print("PyTorch not installed; run in an environment with CUDA and torch installed")
        return 3

    if not torch.cuda.is_available():
        print("CUDA not available; this test requires GPU")
        return 2

    model_dir = pathlib.Path(cfg.paraphrase_model_dir)
    if not model_dir.exists():
        print(f"Model directory not found: {model_dir}\nRun: python scripts/download_paraphrase.py")
        return 2

    try:
        model = _load_sentence_transformer(model_dir, device=cfg.paraphrase_device)
    except RuntimeError as exc:
        print(str(exc))
        return 3
    except Exception as exc:
        print("Unexpected error loading model:", repr(exc))
        return 4

    prompt_name = cfg.prompt_sample_short_hello
    prompt_path = PROJECT_ROOT / "prompts" / prompt_name
    if not prompt_path.exists():
        print(f"Prompt file not found: {prompt_path}")
        return 2

    sample_text = prompt_path.read_text(encoding="utf-8").strip()
    try:
        import numpy as _np
        import torch as _torch
        _torch.manual_seed(0)
        vec1 = model.encode([sample_text], show_progress_bar=False)[0]
        _torch.manual_seed(0)
        vec2 = model.encode([sample_text], show_progress_bar=False)[0]
        a1 = _np.asarray(vec1)
        a2 = _np.asarray(vec2)
        expected_dim = model.get_sentence_embedding_dimension()
        print(f"Embedding length: {a1.shape[0]} (expected {expected_dim})")
        print("Deterministic match:", bool(_np.allclose(a1, a2, atol=1e-6)))
        return 0 if (a1.shape[0] == expected_dim and _np.allclose(a1, a2, atol=1e-6)) else 4
    except Exception as exc:
        print("Failed to compute/check embeddings:", repr(exc))
        return 4


if __name__ == "__main__":
    rc = main()
    raise SystemExit(rc)
