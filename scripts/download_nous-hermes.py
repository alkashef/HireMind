"""Download Nous-Hermes GGUF model into ./models/nous-hermes/

Usage (from project root):
    python scripts\download_nous-hermes.py

Options:
    --repo REPO_ID            Hugging Face repo id (default: nousresearch/Nous-Hermes-2-Mistral-7B)
    --filename FILENAME       Filename in the repo (default: Nous-Hermes-2-Mistral-7B.Q4_K_M.gguf)
    --output-dir PATH         Destination directory under ./models (default: models/nous-hermes)
    --token TOKEN             HF token (optional, env HUGGINGFACE_HUB_TOKEN used if not provided)

This script uses huggingface_hub.hf_hub_download which will respect cached files and
the HUGGINGFACE_HUB_TOKEN environment variable if provided.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

try:
    from huggingface_hub import hf_hub_download
except Exception:
    hf_hub_download = None


DEFAULT_REPO = "NousResearch/Hermes-2-Pro-Mistral-7B-GGUF"
DEFAULT_FILENAME = "Hermes-2-Pro-Mistral-7B.Q4_K_M.gguf"
DEFAULT_DIR = Path("models") / "hermes-pro"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Nous-Hermes GGUF model to models/nous-hermes/")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Hugging Face repo id (e.g., nousresearch/Nous-Hermes-2-Mistral-7B)")
    parser.add_argument("--filename", default=DEFAULT_FILENAME, help="Filename in the repo to download")
    parser.add_argument("--output-dir", default=str(DEFAULT_DIR), help="Local folder to save the model")
    parser.add_argument("--token", default=os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HF_TOKEN"), help="Hugging Face token (optional). If omitted, env HUGGINGFACE_HUB_TOKEN will be used if set.")

    args = parser.parse_args(argv)

    if hf_hub_download is None:
        print("Error: huggingface_hub is not installed. Please run: python -m pip install huggingface-hub", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    repo_id = args.repo
    filename = args.filename

    print(f"Downloading {filename} from {repo_id} -> {out_dir}")

    try:
        # hf_hub_download will cache the file; local_dir will contain the file with original name
        path = hf_hub_download(repo_id=repo_id, filename=filename, repo_type="model", token=args.token, local_dir=str(out_dir), local_dir_use_symlinks=False)
        print(f"Downloaded to: {path}")
        return 0
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
