"""Download the 'paraphrase-MiniLM-L12-v2' sentence-transformers model
and save it under the project's `models/` directory.

Usage (from project root):
    python scripts/download_paraphrase.py

The script will attempt the following, in order:
1. Use huggingface_hub.snapshot_download to fetch the model repo
   `sentence-transformers/paraphrase-MiniLM-L12-v2` into `models/paraphrase-MiniLM-L12-v2`.
2. If huggingface_hub is unavailable, try to use sentence_transformers.SentenceTransformer
   to download and save the model to that folder.

If neither library is installed the script will print instructions.
"""
from __future__ import annotations

import sys
from pathlib import Path

MODEL_ID = "sentence-transformers/paraphrase-MiniLM-L12-v2"
OUT_DIRNAME = "paraphrase-MiniLM-L12-v2"


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    models_dir = project_root / "models"
    target = models_dir / OUT_DIRNAME
    models_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading model {MODEL_ID} -> {target}")

    # Try huggingface_hub first (recommended)
    try:
        from huggingface_hub import snapshot_download

        try:
            print("Using huggingface_hub.snapshot_download...")
            snapshot_download(repo_id=MODEL_ID, cache_dir=str(models_dir), local_dir=str(target), allow_patterns=None)
            print(f"Model saved to: {target}")
            return 0
        except TypeError:
            # Older snapshot_download signature: return_dir param
            snapshot_download(repo_id=MODEL_ID, cache_dir=str(models_dir))
            # Hugging Face may place files under cache; try to move if needed
            print("Downloaded with older API; please verify content under the HF cache or models/ folder.")
            return 0
        except Exception as e:
            print(f"huggingface_hub download failed: {e}")
    except Exception:
        print("huggingface_hub not available; falling back to sentence-transformers if installed.")

    # Fallback: sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer

        try:
            print("Using sentence_transformers.SentenceTransformer to download and save the model...")
            model = SentenceTransformer(MODEL_ID)
            model.save(str(target))
            print(f"Model saved to: {target}")
            return 0
        except Exception as e:
            print(f"sentence-transformers download failed: {e}")
    except Exception:
        print("sentence-transformers not available.")

    print("\nNo supported downloader available. Install one of the following and retry:")
    print("  pip install huggingface-hub")
    print("  pip install sentence-transformers")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
