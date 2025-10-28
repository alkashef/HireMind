"""Hermes HF-format smoke test that runs two checks sequentially and fails
fast: the test will immediately fail if any check fails.

- FP16 (standard HF) load + small generation
- 4-bit (BitsAndBytes) load + numeric-generation correctness check

Checks are executed sequentially and the test stops on the first failure to
make CI runs fail fast and easier to debug.
"""
from __future__ import annotations

import sys
import pathlib
import traceback
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


def test_hermes_fp16_and_4bit():
    fp16_ok = False
    bnb_ok = False
    fp16_msg = ""
    bnb_msg = ""

    # --- FP16 HF load + generation -------------------------------------------------
    try:
        try:
            import torch
        except Exception:
            raise RuntimeError("PyTorch not installed")

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available")

        if not HERMES_MODEL_DIR.exists():
            raise RuntimeError(f"Hermes model directory not found at {HERMES_MODEL_DIR}; run scripts/download_nous-hermes.py to fetch HF-format model")

        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            from transformers import logging as hf_logging

            hf_logging.set_verbosity_error()
        except Exception as exc:
            raise RuntimeError(f"transformers not installed: {exc}")

        try:
            tokenizer = AutoTokenizer.from_pretrained(str(HERMES_MODEL_DIR), use_fast=True)
        except Exception as exc:
            raise RuntimeError(f"Failed to load tokenizer from {HERMES_MODEL_DIR}: {exc}")

        try:
            model = AutoModelForCausalLM.from_pretrained(str(HERMES_MODEL_DIR), device_map="auto", torch_dtype=torch.float16)
        except Exception as exc:
            raise RuntimeError(f"Failed to load HF model on CUDA from {HERMES_MODEL_DIR}: {exc}")

        # Tiny generation
        prompt_path = PROJECT_ROOT / "prompts" / "sample_short_text_hello.md"
        sample_text = prompt_path.read_text(encoding="utf-8").strip()
        inputs = tokenizer(sample_text, return_tensors="pt")
        # Ensure inputs are on the same device as the model to avoid warnings
        try:
            device = next(model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
        except Exception:
            # best-effort; if it fails, continue and let generate raise if needed
            pass
        out_ids = model.generate(**inputs, max_new_tokens=16)
        text = tokenizer.decode(out_ids[0], skip_special_tokens=True)
        if isinstance(text, str) and len(text) > 0:
            fp16_ok = True
            fp16_msg = "FP16 load and generation succeeded"
        else:
            fp16_msg = "FP16 generation produced empty output"
    except Exception as exc:
        fp16_msg = f"FP16 check failed: {exc}\n{traceback.format_exc()}"

    # --- 4-bit (bnb) load + numeric generation ------------------------------------
    try:
        try:
            import torch
        except Exception:
            raise RuntimeError("PyTorch not installed")

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available")

        if not HERMES_MODEL_DIR.exists():
            raise RuntimeError(f"Hermes model directory not found at {HERMES_MODEL_DIR}; run scripts/download_nous-hermes.py to fetch HF-format model")

        # Early HF-compatibility check: ensure model folder contains HF weights/tokenizer files
        # Accept single-file safetensors, sharded safetensors with an index, or pytorch_model.bin
        hf_candidates = {"pytorch_model.bin", "model.safetensors", "pytorch_model-00001-of-00002.bin", "model.safetensors.index.json"}
        found = any((HERMES_MODEL_DIR / fname).exists() for fname in hf_candidates)
        if not found:
            # check for sharded safetensors like model-00001-of-00004.safetensors
            shards = list(HERMES_MODEL_DIR.glob("model-*-of-*.safetensors"))
            if shards:
                found = True

        if not found:
            raise RuntimeError(
                "Downloaded snapshot does not appear to contain HF-format weights (no pytorch_model.bin, model.safetensors, or sharded safetensors)."
            )

        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        except Exception as exc:
            raise RuntimeError(f"transformers or BitsAndBytes support not available: {exc}")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
        )

        try:
            tokenizer2 = AutoTokenizer.from_pretrained(str(HERMES_MODEL_DIR), use_fast=True)
        except Exception as exc:
            raise RuntimeError(f"Failed to load tokenizer for 4-bit test: {exc}")

        # Try loading normally first; if device placement fails due to insufficient VRAM,
        # attempt a fallback using fp32 CPU offload for int8/4-bit quantization.
        model2 = None
        load_exc = None
        try:
            model2 = AutoModelForCausalLM.from_pretrained(
                str(HERMES_MODEL_DIR),
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=False,
            )
        except Exception as exc:
            load_exc = exc

        # If initial load failed with a VRAM/offload hint, try enabling fp32 CPU offload
        if model2 is None:
            msg = str(load_exc) if load_exc is not None else ""
            if "Some modules are dispatched on the CPU" in msg or "offload" in msg.lower() or "dispatched" in msg.lower():
                try:
                    bnb_config_offload = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.float16,
                        llm_int8_enable_fp32_cpu_offload=True,
                    )

                    # Provide a conservative max_memory hint for the auto device mapper.
                    # We'll attempt to infer available GPU memory and leave ~1GB headroom
                    # so machines with 8GB VRAM use ~7GB, if available.
                    try:
                        # torch is already imported above; get device total memory in GB
                        total_bytes = torch.cuda.get_device_properties(0).total_memory
                        total_gb = int(total_bytes // (1024 ** 3))
                        cuda_hint_gb = max(total_gb - 1, 2)
                        max_memory = {"cuda:0": f"{cuda_hint_gb}GB", "cpu": "90GB"}
                    except Exception:
                        # Fallback conservative hint
                        max_memory = {"cuda:0": "6GB", "cpu": "90GB"}

                    model2 = AutoModelForCausalLM.from_pretrained(
                        str(HERMES_MODEL_DIR),
                        quantization_config=bnb_config_offload,
                        device_map="auto",
                        max_memory=max_memory,
                        trust_remote_code=False,
                    )
                except Exception as exc2:
                    # If offload attempt also fails, print diagnostics and skip the 4-bit test since hardware can't support it
                    try:
                        print("DEBUG: attempted max_memory:", max_memory)
                    except Exception:
                        print("DEBUG: max_memory not set")
                    try:
                        print("DEBUG: original load exception:", load_exc)
                    except Exception:
                        pass
                    print("DEBUG: offload exception:", exc2)
                    pytest.skip(f"Skipping 4-bit Hermes check: failed to load with offload: {exc2}")
            else:
                raise RuntimeError(f"Failed to load model in 4-bit on CUDA: {load_exc}")

        # If model loaded but no params placed on CUDA, print diagnostics and skip the 4-bit test
        if not _any_param_on_cuda(model2):
            # Diagnostics to help tune max_memory or build a manual device_map
            try:
                print("DEBUG: computed max_memory hint:", max_memory)
            except Exception:
                print("DEBUG: max_memory not available")
            try:
                devmap = getattr(model2, "hf_device_map", None)
                print("DEBUG: model.hf_device_map:", devmap)
            except Exception as _:
                print("DEBUG: failed to read model.hf_device_map")
            try:
                total = 0
                cuda_cnt = 0
                for p in model2.parameters():
                    total += int(p.numel())
                    if getattr(p, "device", None) is not None and getattr(p.device, "type", None) == "cuda":
                        cuda_cnt += int(p.numel())
                print(f"DEBUG: params total={total}, on_cuda={cuda_cnt}, on_cpu={total-cuda_cnt}")
            except Exception:
                print("DEBUG: failed to count params on devices")
            pytest.skip("4-bit model loaded but no parameters placed on CUDA (insufficient GPU RAM); skipping 4-bit checks")

        prompt_path2 = PROJECT_ROOT / "prompts" / "prompt_numeric_2_plus_2.md"
        prompt = prompt_path2.read_text(encoding="utf-8").strip()
        inputs2 = tokenizer2(prompt, return_tensors="pt")

        # Ensure inputs are on the same device as the model
        try:
            device2 = next(model2.parameters()).device
            inputs2 = {k: v.to(device2) for k, v in inputs2.items()}
        except Exception:
            pass

        out_ids2 = model2.generate(**inputs2, max_new_tokens=8, do_sample=False)
        text2 = tokenizer2.decode(out_ids2[0], skip_special_tokens=True).strip().lower()

        if text2 == "4" or text2.startswith("4 ") or text2.split("\n")[0] == "4" or text2 == "four":
            bnb_ok = True
            bnb_msg = "4-bit load and numeric generation succeeded"
        else:
            bnb_msg = f"4-bit generation unexpected output: {text2}"
    except Exception as exc:
        bnb_msg = f"4-bit check failed: {exc}\n{traceback.format_exc()}"

    # Fail-fast: if FP16 check failed, stop immediately
    print(f"FP16 check: {'OK' if fp16_ok else 'FAIL'} - {fp16_msg}")
    if not fp16_ok:
        pytest.fail(f"FP16 Hermes check failed: {fp16_msg}")

    # Proceed to 4-bit check; fail immediately on failure
    print(f"Proceeding to 4-bit check...")
    print(f"4-bit check: {'OK' if bnb_ok else 'FAIL'} - {bnb_msg}")
    if not bnb_ok:
        pytest.fail(f"4-bit Hermes check failed: {bnb_msg}")


if __name__ == "__main__":
    import pytest as _pytest

    rc = _pytest.main([__file__])
    raise SystemExit(rc)
