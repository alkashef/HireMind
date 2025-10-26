"""Simple Hermes client wrapper for HF-format models with optional 4-bit loading.

This module provides a thin, reusable API to load an HF-format causal LM
and call `generate()` from application code. The loader supports 4-bit
quantization (bitsandbytes) and caches the loaded tokenizer+model for reuse.

Usage:
    from config.settings import AppConfig
    from utils.hermes_client import HermesClient

    cfg = AppConfig()
    client = HermesClient(model_dir="models/hermes-pro", quantize_4bit=True, cfg=cfg)
    # Prefer loading prompts from `prompts/` rather than hardcoding text
    text = client.generate_from_prompt_file("prompt_summarize_short.md", max_new_tokens=64)

Notes:
- This is HF-only (transformers) and expects HF-format weights (not GGUF).
- For 4-bit quantization, `bitsandbytes` and compatible `transformers` are required.
"""
from __future__ import annotations

from typing import Optional
import logging
import threading
from pathlib import Path

from config.settings import AppConfig

logger = logging.getLogger(__name__)

# Module-level cache to avoid re-loading heavy models
_global_lock = threading.Lock()
_global_client: "HermesClient" | None = None


class HermesClient:
    """Load and run a HF causal LM for programmatic use.

    The client caches the loaded tokenizer and model on the instance and can
    optionally load the model in 4-bit mode using BitsAndBytesConfig.

    Generation defaults may be provided via environment variables in
    `config/.env` (the app's `AppConfig` will load it). Recognized env vars:
      - HERMES_TEMPERATURE (float, default 0.0)
      - HERMES_NUM_BEAMS (int, default 1)
      - HERMES_MAX_NEW_TOKENS (int, default 128)
      - HERMES_QUANTIZE_4BIT (true/false, default true)

    Prompts can be stored in the `prompts/` folder. Use `generate(prompt_name=...)`
    to load a prompt template by filename (without folder).
    """

    def __init__(
        self,
        model_dir: str = "models/hermes-pro",
        quantize_4bit: Optional[bool] = None,
        temperature: Optional[float] = None,
        num_beams: Optional[int] = None,
        max_new_tokens: Optional[int] = None,
        cfg: Optional[AppConfig] = None,
    ):
        self.model_dir = model_dir
        # Configuration-driven defaults (AppConfig reads .env). Explicit args win.
        self.cfg = cfg or AppConfig()
        if quantize_4bit is None:
            self.quantize_4bit = self.cfg.hermes_quantize_4bit
        else:
            self.quantize_4bit = quantize_4bit

        def _env_float(name: str, default: float):
            v = os.getenv(name)
            try:
                return float(v) if v is not None else default
            except Exception:
                return default

        def _env_int(name: str, default: int):
            v = os.getenv(name)
            try:
                return int(v) if v is not None else default
            except Exception:
                return default

        self.temperature = (
            temperature if temperature is not None else float(self.cfg.hermes_temperature)
        )
        self.num_beams = num_beams if num_beams is not None else int(self.cfg.hermes_num_beams)
        self.max_new_tokens = (
            max_new_tokens if max_new_tokens is not None else int(self.cfg.hermes_max_new_tokens)
        )

        self.tokenizer = None
        self.model = None

    def _lazy_load(self):
        """Load tokenizer and model if not already loaded.

        Raises RuntimeError with actionable message if dependencies are missing.
        """
        if self.model is not None and self.tokenizer is not None:
            return

        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
        except Exception as exc:
            raise RuntimeError(f"transformers or torch not available: {exc}")

        # Load tokenizer
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir, use_fast=True)
        except Exception as exc:
            raise RuntimeError(f"Failed to load tokenizer from {self.model_dir}: {exc}")

        # Prepare kwargs for from_pretrained
        load_kwargs = dict(device_map="auto")

        if self.quantize_4bit:
            try:
                from transformers import BitsAndBytesConfig
                bnb = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                )
                load_kwargs["quantization_config"] = bnb
                # Let HF use fp16 where appropriate
                load_kwargs["torch_dtype"] = torch.float16
            except Exception as exc:
                raise RuntimeError(f"bitsandbytes / BitsAndBytesConfig not available: {exc}")
        else:
            # prefer FP16 for CUDA models
            load_kwargs["torch_dtype"] = torch.float16

        try:
            # trust_remote_code left False for safety; change if model requires it
            self.model = AutoModelForCausalLM.from_pretrained(self.model_dir, trust_remote_code=False, **load_kwargs)
        except Exception as exc:
            raise RuntimeError(f"Failed to load HF model from {self.model_dir}: {exc}")

        # Sanity check: ensure some params are on CUDA
        try:
            any_cuda = any(p.device.type == "cuda" for p in self.model.parameters())
            if not any_cuda:
                logger.warning("Model parameters not placed on CUDA after load; device_map may not have placed model on GPU")
        except Exception:
            logger.debug("Could not determine model device placement")

    def generate(self, prompt: str, max_new_tokens: int = 128, **generate_kwargs) -> str:
        """Generate text from `prompt` and return the decoded string.

        generate_kwargs are forwarded to `model.generate()`.
        """
        # Ensure model/tokenizer loaded
        self._lazy_load()

        # Merge defaults: prefer explicit args, then instance defaults, then hard defaults
        max_new_tokens = max_new_tokens or self.max_new_tokens or 128
        gen_opts = dict(max_new_tokens=max_new_tokens)

        # Sampling vs beam defaults: if num_beams>1 use beams, else deterministic greedy
        if generate_kwargs.get("do_sample") is None:
            if (self.num_beams or 1) > 1:
                gen_opts["num_beams"] = self.num_beams
                gen_opts["do_sample"] = False
            else:
                gen_opts["do_sample"] = False

        if generate_kwargs.get("temperature") is None:
            gen_opts["temperature"] = self.temperature

        # Merge user-provided kwargs (explicit wins)
        gen_opts.update(generate_kwargs)

        inputs = self.tokenizer(prompt, return_tensors="pt")
        # Rely on device_map for placement; HF will accept CPU tensors
        out = self.model.generate(**inputs, **gen_opts)
        text = self.tokenizer.decode(out[0], skip_special_tokens=True)
        return text

    def generate_from_prompt_file(self, prompt_name: str, prompt_vars: dict | None = None, **generate_kwargs) -> str:
        """Load a prompt template from `prompts/<prompt_name>` and generate.

    - prompt_name: filename inside `prompts/` (e.g., 'extract_from_cv_user.md')
        - prompt_vars: optional dict used to format the prompt with str.format()
        """
        prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
        prompt_path = prompts_dir / prompt_name
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        text = prompt_path.read_text(encoding="utf-8")
        if prompt_vars:
            try:
                text = text.format(**prompt_vars)
            except Exception as exc:
                raise ValueError(f"Failed to format prompt template: {exc}")
        return self.generate(text, **generate_kwargs)


def get_global_client(model_dir: str = "models/hermes-pro", quantize_4bit: bool = True) -> HermesClient:
    """Return a process-global HermesClient, loading lazily and caching it.

    Useful for apps that want a shared client instance.
    """
    global _global_client
    with _global_lock:
        if _global_client is None:
            cfg = AppConfig()
            _global_client = HermesClient(model_dir=model_dir, quantize_4bit=quantize_4bit, cfg=cfg)
        return _global_client


__all__ = ["HermesClient", "get_global_client"]
