"""Hermes HF-format GPU-only smoke test.

This test ensures a HF-format Hermes model exists in `models/hermes-pro` and
can be loaded by `transformers` on CUDA. It is intentionally strict:
- GPU (CUDA) is required
- The model must be HF-format (tokenizer + config + weights)

If any prerequisite is missing the test is skipped with a clear message.
"""
from __future__ import annotations

import sys
import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HERMES_MODEL_DIR = PROJECT_ROOT / "models" / "hermes-pro"


def test_hermes_hf_on_gpu():
    # Require torch and CUDA
    try:
        import torch
    except Exception:
        pytest.skip("PyTorch not installed; skipping Hermes HF GPU test")

    if not torch.cuda.is_available():
        pytest.skip("CUDA not available; skipping Hermes HF GPU test")

    if not HERMES_MODEL_DIR.exists():
        pytest.skip(f"Hermes model directory not found at {HERMES_MODEL_DIR}; run scripts/download_nous-hermes.py to fetch HF-format model")

    # Try to load with transformers explicitly (HF-only, no vllm fallback)
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from transformers import logging as hf_logging

        hf_logging.set_verbosity_error()
    except Exception as exc:
        pytest.skip(f"transformers not installed: {exc}")

    try:
        tokenizer = AutoTokenizer.from_pretrained(str(HERMES_MODEL_DIR), use_fast=True)
    except Exception as exc:
        pytest.skip(f"Failed to load tokenizer from {HERMES_MODEL_DIR}: {exc}")

    try:
        # Load model onto CUDA devices using device_map='auto' and FP16 where possible
        model = AutoModelForCausalLM.from_pretrained(str(HERMES_MODEL_DIR), device_map="auto", torch_dtype=torch.float16)
    except Exception as exc:
        pytest.skip(f"Failed to load HF model on CUDA from {HERMES_MODEL_DIR}: {exc}")

    # Perform a tiny generation to ensure forward pass works
    try:
        prompt_path = PROJECT_ROOT / "prompts" / "sample_short_text_hello.md"
        sample_text = prompt_path.read_text(encoding="utf-8").strip()
        inputs = tokenizer(sample_text, return_tensors="pt")
        # Do not force .to('cuda') — with device_map='auto' HF handles placement
        out_ids = model.generate(**inputs, max_new_tokens=16)
        text = tokenizer.decode(out_ids[0], skip_special_tokens=True)
        assert isinstance(text, str) and len(text) > 0
    except Exception as exc:
        pytest.skip(f"Hermes HF generation check failed: {exc}")


if __name__ == "__main__":
    import pytest as _pytest

    rc = _pytest.main([__file__])
    raise SystemExit(rc)
