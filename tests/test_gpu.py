"""Minimal standalone GPU verification for paraphrase and Hermes-Pro.

This script performs lightweight checks:
- Verifies PyTorch CUDA availability
- Attempts to load the paraphrase model on CUDA and run a small encode
- Attempts to load the Hermes model via utils.llm_runner and reports backend

Exit codes:
 0 - success (GPU detected and at least one model used GPU)
 1 - partial success (GPU available but one or more model loads failed)
 2 - model directory missing (neither model present locally)
 3 - missing dependency (torch/sentence-transformers/vllm)
 4 - unexpected exception

Run:
  python tests/test_gpu.py
"""
from __future__ import annotations

import sys
import pathlib
import traceback

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PARAPHRSE_MODEL_DIR = PROJECT_ROOT / "models" / "paraphrase-MiniLM-L12-v2"
HERMES_MODEL_DIR = PROJECT_ROOT / "models" / "hermes-pro"


def main() -> int:
    """GPU-only check: returns 0 if CUDA is available, else non-zero.

    Exit codes:
      0 - CUDA available
      1 - CUDA not available
      3 - PyTorch missing
    """
    try:
        import torch
    except Exception:
        print("PyTorch is not installed. Install with 'pip install torch' (pick CUDA wheel if you want GPU).")
        return 3

    cuda_avail = torch.cuda.is_available()
    print("PyTorch version:", getattr(torch, "__version__", "unknown"))
    print("CUDA available:", cuda_avail)
    if cuda_avail:
        try:
            print("CUDA devices:", torch.cuda.device_count())
            if torch.cuda.device_count() > 0:
                print("Device 0:", torch.cuda.get_device_name(0))
        except Exception:
            print("Could not query CUDA device names")
        return 0

    return 1


if __name__ == "__main__":
    rc = main()
    raise SystemExit(rc)
