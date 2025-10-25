"""Helper to produce or run the recommended pip command for installing PyTorch
with a CUDA-enabled wheel for common CUDA versions on Windows.

This script does NOT download NVIDIA drivers or CUDA toolkit; it only
prints (and optionally runs) the `pip install` command that installs the
appropriate `torch` wheel for the selected CUDA version. Use this when you
want to install a GPU-enabled `torch` build for the project's tests and
models.

Examples (from project root):

    # Print a recommended command for CUDA 12.1
    python scripts\download_cuda.py --cuda 12.1

    # Actually run the pip install (will call pip in the current Python)
    python scripts\download_cuda.py --cuda 12.1 --install

Supported CUDA values: 11.7, 11.8, 12.1, 12.6, cpu
If you specify `cpu` the script will recommend a CPU-only `torch` install.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from typing import Tuple


def recommended_command(cuda: str) -> Tuple[str, str]:
    """Return (short_label, pip_command) for the requested CUDA version.

    Note: The exact pip command may change over time; this helper surface the
    common installation commands today and should be updated if PyTorch
    packaging changes.
    """
    if cuda == "cpu":
        return (
            "cpu",
            "pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu",
        )

    # Map a few common CUDA versions to PyTorch index URLs used by the
    # official PyTorch wheels. Replace with the recommended command from
    # https://pytorch.org/get-started/locally/ if needed.
    mapping = {
        "11.7": "https://download.pytorch.org/whl/cu117",
        "11.8": "https://download.pytorch.org/whl/cu118",
        "12.1": "https://download.pytorch.org/whl/cu121",
        "12.6": "https://download.pytorch.org/whl/cu126",
    }

    index = mapping.get(cuda)
    if index is None:
        raise ValueError(f"Unsupported CUDA version: {cuda}. Supported: {', '.join(mapping.keys())}, cpu")

    cmd = f"pip install torch torchvision --index-url {index}"
    return (cuda, cmd)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Recommend or run pip install for PyTorch with CUDA wheels")
    p.add_argument("--cuda", default="cpu", help="CUDA version to target (e.g. 11.7, 11.8, 12.1, 12.6, cpu)")
    p.add_argument("--install", action="store_true", help="Actually run the pip install command")
    args = p.parse_args(argv)

    try:
        label, cmd = recommended_command(args.cuda)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    print("Recommended command:")
    print(cmd)

    if args.install:
        print("Running install command...")
        try:
            parts = shlex.split(cmd)
            # Execute using the current Python's pip module for environment correctness
            res = subprocess.run([sys.executable, "-m"] + parts, check=False)
            return res.returncode
        except Exception as e:
            print(f"Install failed: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
