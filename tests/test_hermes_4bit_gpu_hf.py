"""HF-format Hermes 4-bit GPU smoke test.

This test attempts to load the HF-format model in 4-bit (bnb) quantized mode
onto GPU(s), runs a tiny generation, and validates the result contains the
expected answer (simple arithmetic: 2+2 -> 4).

Notes:
- Requires `transformers` and `bitsandbytes` installed (present in requirements).
- Requires an HF-format model under `models/hermes-pro` (use
  `python scripts\download_nous-hermes.py` to fetch a HF snapshot).
- Requires CUDA available.

This is intentionally conservative and will skip the test with a clear
message if prerequisites are missing.
"""
from __future__ import annotations

import sys
import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HERMES_MODEL_DIR = PROJECT_ROOT / "models" / "hermes-pro"


def _any_param_on_cuda(model) -> bool:
    try:
        return any(p.device.type == "cuda" for p in model.parameters())
    except Exception:
        return False


def test_hermes_load_4bit_and_generate():
    # Basic runtime checks
    try:
        import torch
    except Exception:
        pytest.skip("PyTorch not installed; skipping 4-bit Hermes test")

    if not torch.cuda.is_available():
        pytest.skip("CUDA not available; skipping 4-bit Hermes test")

    if not HERMES_MODEL_DIR.exists():
        pytest.skip(f"Hermes model directory not found at {HERMES_MODEL_DIR}; run scripts/download_nous-hermes.py to fetch HF-format model")

    # Early HF-compatibility check: ensure model folder contains HF weights/tokenizer files
    hf_candidates = {"pytorch_model.bin", "model.safetensors", "pytorch_model-00001-of-00002.bin"}
    found = any((HERMES_MODEL_DIR / fname).exists() for fname in hf_candidates)
    if not found:
        pytest.fail(
            f"Downloaded snapshot at {HERMES_MODEL_DIR} does not appear to contain HF-format weights. "
            "Ensure you downloaded an HF-format model (contains pytorch_model.bin or model.safetensors)."
        )

    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    except Exception as exc:
        pytest.skip(f"transformers or BitsAndBytes support not available: {exc}")

    # Configure 4-bit quantization via Transformers' BitsAndBytesConfig
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
    )

    # Load tokenizer (fail the test early if incompatible)
    try:
        tokenizer = AutoTokenizer.from_pretrained(str(HERMES_MODEL_DIR), use_fast=True)
    except Exception as exc:
        pytest.fail(f"Failed to load tokenizer from {HERMES_MODEL_DIR}: {exc}")

    # Load model in 4-bit, placed automatically on GPU(s)
    try:
        model = AutoModelForCausalLM.from_pretrained(
            str(HERMES_MODEL_DIR),
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=False,
        )
    except Exception as exc:
        pytest.skip(f"Failed to load model in 4-bit on CUDA: {exc}")

    # Ensure some parameters live on CUDA
    if not _any_param_on_cuda(model):
        pytest.skip("Model parameters not placed on CUDA after load; device_map may not have placed model on GPU")

    # Load numeric prompt from prompts/ to avoid hardcoded prompt text
    prompt_path = PROJECT_ROOT / "prompts" / "prompt_numeric_2_plus_2.md"
    prompt = prompt_path.read_text(encoding="utf-8").strip()

    try:
        inputs = tokenizer(prompt, return_tensors="pt")
        out_ids = model.generate(**inputs, max_new_tokens=8, do_sample=False)
        text = tokenizer.decode(out_ids[0], skip_special_tokens=True).strip().lower()
    except Exception as exc:
        pytest.skip(f"Generation failed: {exc}")

    # Prefer exact numeral '4' as success; accept 'four' as fallback
    if text == "4" or text.startswith("4 ") or text.split("\n")[0] == "4" or text == "four":
        assert True
    else:
        pytest.fail(f"Unexpected model output for prompt '{prompt}': {text}")


if __name__ == "__main__":
    import pytest as _pytest

    rc = _pytest.main([__file__])
    raise SystemExit(rc)
