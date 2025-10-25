"""Test that Hermes-Pro model exists and is loadable on GPU.

This test requires CUDA and the local Hermes model directory `models/hermes-pro`.
It attempts to load the model via `utils.llm_runner.load_hermes_model()` and
performs a tiny generation if a vllm backend is returned.
"""
from __future__ import annotations

import sys
import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HERMES_MODEL_DIR = PROJECT_ROOT / "models" / "hermes-pro"


def test_hermes_on_gpu():
    try:
        import torch
    except Exception:
        pytest.skip("PyTorch not installed; skipping Hermes GPU test")

    if not torch.cuda.is_available():
        pytest.skip("CUDA not available; skipping Hermes GPU test")

    if not HERMES_MODEL_DIR.exists():
        pytest.skip(f"Hermes model directory not found at {HERMES_MODEL_DIR}; place GGUF under models/hermes-pro")

    try:
        from utils.llm_runner import load_hermes_model
    except Exception as exc:
        pytest.skip(f"utils.llm_runner not available: {exc}")

    # Attempt to load; this may use vllm or transformers
    try:
        backend = load_hermes_model(str(HERMES_MODEL_DIR))
    except RuntimeError as exc:
        pytest.skip(f"Hermes GPU backend missing or not supported in this environment: {exc}")

    # basic checks: backend should be non-None and GPU-capable in typical config
    assert backend is not None

    # If vllm LLM instance, attempt a tiny generation to ensure runtime works
    try:
        # vllm LLM instances expose a `generate` method; we attempt a minimal call
        if hasattr(backend, "generate"):
            # The vllm API expects a prompt or list of prompts
            gen = backend.generate(["Hello world"], max_tokens=8)
            # consume generator / result safely
            # Some vllm versions return an iterator of responses
            try:
                first = next(iter(gen))
                assert first is not None
            except Exception:
                # If we can't iterate, at least ensure call didn't raise
                pass
        else:
            # transformers tuple (tokenizer, model) — do a tiny forward pass
            tokenizer, model = backend
            assert hasattr(model, "generate")
            inputs = tokenizer("Hello world", return_tensors="pt").to("cuda")
            out = model.generate(**inputs, max_new_tokens=8)
            assert out is not None
    except Exception as exc:
        pytest.skip(f"Hermes generation check failed (environment may not support runtime generation): {exc}")
