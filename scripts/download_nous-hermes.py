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
        return 0
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
