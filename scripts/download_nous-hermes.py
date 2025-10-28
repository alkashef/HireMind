"""Download the HF-format Hermes model snapshot into `models/hermes-pro`.

This script has no CLI options: it unconditionally downloads the HF-format
snapshot of the Hermes repo into `models/hermes-pro`. Use the
`HUGGINGFACE_HUB_TOKEN` environment variable for authentication if needed.

Run from the project root:
    python scripts\download_nous-hermes.py

Notes:
- The script requires `huggingface-hub` to be installed.
- The default repo is set to an HF-format mirror of Hermes. If that repo does
  not contain HF-format weights, transformers will not be able to load them.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

try:
    from huggingface_hub import snapshot_download
except Exception:
    snapshot_download = None


DEFAULT_REPO = "NousResearch/Hermes-2-Pro-Mistral-7B"
DEFAULT_DIR = Path("models") / "hermes-pro"


def main(argv: list[str] | None = None) -> int:
    # No CLI options: fixed behavior to download HF-format snapshot
    token = os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HF_TOKEN")

    if snapshot_download is None:
        print("Error: huggingface_hub is not installed. Please run: python -m pip install huggingface-hub", file=sys.stderr)
        return 2

    out_dir = DEFAULT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    repo_id = DEFAULT_REPO
    print(f"Downloading HF-format snapshot of {repo_id} -> {out_dir}")

    try:
        path = snapshot_download(repo_id=repo_id, repo_type="model", token=token, local_dir=str(out_dir))
        print(f"Downloaded HF snapshot to: {out_dir} (snapshot dir: {path})")

        # Verify that the downloaded snapshot contains HF-format weights that
        # transformers can load (pytorch_model.bin or model.safetensors). If
        # not present, the download may be a GGUF or other format which
        # transformers cannot consume directly.
        # Accept HF single-file safetensors, sharded safetensors (model-00001-of-00004.safetensors)
        # or pytorch_model.bin variants. Also accept a safetensors index file
        hf_candidates = ["pytorch_model.bin", "model.safetensors", "pytorch_model-00001-of-00002.bin", "model.safetensors.index.json"]
        found = any((out_dir / fname).exists() for fname in hf_candidates)
        if not found:
            # check for sharded safetensors like model-00001-of-00004.safetensors
            shards = list(out_dir.glob("model-*-of-*.safetensors"))
            if shards:
                found = True
        if not found:
            print("Warning: downloaded snapshot does not appear to contain HF-format weights (no pytorch_model.bin or model.safetensors).", file=sys.stderr)
            print("This repository may publish GGUF weights or a different format. Transformers will not be able to load them for the 4-bit test.", file=sys.stderr)
            # List a few files to help debugging
            try:
                files = sorted(p.name for p in out_dir.iterdir())
                print("Files in", out_dir, ":")
                for f in files[:50]:
                    print("  ", f)
            except Exception:
                pass
            return 3
        return 0
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
