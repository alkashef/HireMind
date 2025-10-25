"""Helper to load/run local LLMs (Hermes-Pro) preferring GPU backends.

This lightweight adapter tries multiple backends in order to use the GPU
when available:
 - vllm (preferred) — fast GPU inference if installed
 - transformers + accelerate/device_map (fallback)

The functions here are conservative: they only attempt imports when called
and raise clear RuntimeError messages describing how to enable GPU support
if the required packages are missing.
"""
from __future__ import annotations

from typing import Optional
import logging

logger = logging.getLogger(__name__)


def load_hermes_model(model_dir: str):
    """Attempt to load the Hermes-Pro model from `model_dir` using a GPU backend.

    Returns a backend-specific model object. The caller should inspect the
    returned object and use the appropriate generation API.

    Raises RuntimeError with actionable instructions when no suitable backend
    is installed.
    """
    # Try vllm first
    try:
        from vllm import LLM

        # vllm will pick GPUs automatically; pass model path
        logger.info("Loading Hermes model via vllm from %s", model_dir)
        llm = LLM(model=model_dir)
        return llm
    except Exception as exc:
        logger.debug("vllm backend unavailable or failed: %s", exc)

    # Fallback: try transformers with device_map='auto' (requires gpu + accelerate)
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from transformers import logging as hf_logging

        hf_logging.set_verbosity_error()

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available for transformers backend")

        logger.info("Attempting to load Hermes model via transformers on CUDA")
        tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
        model = AutoModelForCausalLM.from_pretrained(model_dir, device_map="auto", torch_dtype=torch.float16)
        return (tokenizer, model)
    except Exception as exc:
        logger.debug("transformers backend unavailable or failed: %s", exc)

    # Neither backend available or usable
    raise RuntimeError(
        "No GPU-capable LLM backend available. Install and configure one of:\n"
        "  - vllm (recommended for GPU inference with GGUF models)\n"
        "  - transformers + accelerate (models convertible to HF format, with CUDA)\n"
        "Alternatively run on CPU or convert the GGUF model to a compatible format."
    )


__all__ = ["load_hermes_model"]
