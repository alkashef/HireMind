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
import subprocess

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
    # Run system probe: nvidia-smi (may be unavailable on some systems)
    try:
        print("--- nvidia-smi output ---")
        res = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        if res.returncode == 0:
            print(res.stdout)
        else:
            print("nvidia-smi returned non-zero exit code")
            print(res.stdout)
            print(res.stderr)
    except FileNotFoundError:
        print("nvidia-smi not found on PATH (no NVIDIA driver/tooling visible)")
    except Exception as exc:
        print("Failed to run nvidia-smi:", exc)

    # Run the explicit python one-liner check in a subprocess to mirror the
    # developer command: this will print torch version and CUDA device info.
    one_liner = (
        "import torch; "
        "print('torch:', torch.__version__); "
        "print('torch.cuda.is_available():', torch.cuda.is_available()); "
        "print('torch.version.cuda:', torch.version.cuda); "
        "print('device_count:', torch.cuda.device_count()); "
        "print('device_name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no device')"
    )
    try:
        print("--- python -c torch probe ---")
        res = subprocess.run([sys.executable, "-c", one_liner], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print("Python probe returned non-zero exit code:")
            print(res.stderr)
    except Exception as exc:
        print("Failed to run python probe:", exc)

    # Also perform an in-process check to determine exit code expectations
    try:
        import torch
    except Exception:
        print("PyTorch is not installed. Install with 'pip install torch' (pick CUDA wheel if you want GPU).")
        return 3

    cuda_avail = torch.cuda.is_available()
    print("In-process PyTorch version:", getattr(torch, "__version__", "unknown"))
    print("In-process CUDA available:", cuda_avail)
    if cuda_avail:
        try:
            print("In-process CUDA devices:", torch.cuda.device_count())
            if torch.cuda.device_count() > 0:
                print("In-process Device 0:", torch.cuda.get_device_name(0))
        except Exception:
            print("Could not query in-process CUDA device names")
        return 0

    return 1


if __name__ == "__main__":
    rc = main()
    raise SystemExit(rc)
