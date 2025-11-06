#!/usr/bin/env python
"""
Script to clear project cache and ephemeral artifacts.

Behavior:
- Removes Python bytecode files, pytest cache, temporary files, and other cache types.
- Purges ALL contents under tests/results (but keeps the tests/results folder itself).
- Never deletes anything under tests/ref (reserved for reference fixtures).
- Skips top-level models/ and data/ to avoid deleting model artifacts or user data.
"""

import argparse
import os
import shutil
from pathlib import Path
from typing import List, Set


def find_cache_files(base_path: Path) -> List[Path]:
    """
    Find all cache files and directories in the repo.
    
    Args:
        base_path: Base directory to scan
        
    Returns:
        List of paths to cache files and directories
    """
    cache_patterns: Set[str] = {
        "__pycache__",
        ".pyc",
        ".pytest_cache",
        ".coverage",
        ".cache",
        ".huggingface_cache",
        "dist",
        "build",
        ".egg-info",
        ".ipynb_checkpoints"
    }
    
    to_delete: List[Path] = []

    tests_dir = base_path / "tests"
    tests_results_dir = tests_dir / "results"
    tests_ref_dir = tests_dir / "ref"

    # 1) Purge tests/results contents (files and subdirectories), but keep the folder itself
    if tests_results_dir.exists() and tests_results_dir.is_dir():
        for child in tests_results_dir.iterdir():
            # Do not touch tests/ref even if someone placed a link
            try:
                if tests_ref_dir.exists() and tests_ref_dir in child.parents:
                    continue
            except Exception:
                pass
            to_delete.append(child)
    
    for path in base_path.rglob("*"):
        # Never delete anything inside tests/ref
        try:
            if tests_ref_dir.exists() and tests_ref_dir in path.parents:
                continue
        except Exception:
            pass
        # Always skip anything inside `models/` or `data/` directories to avoid accidental deletions
        # This ensures the script will not remove model artifacts or user data.
    # NOTE: We intentionally handle tests/results above; this guard is for top-level dirs.
        if any(p in ("models", "data") for p in path.parts):
            continue
        # Additionally, protect the new Weaviate persistence path under store/weaviate_data
        # from any cleanup.
        if ("store" in path.parts) and ("weaviate_data" in path.parts):
            continue
            
        # Check if path matches any cache pattern
        if path.is_dir() and path.name in cache_patterns:
            to_delete.append(path)
        elif path.is_file() and any(path.name.endswith(pattern) for pattern in cache_patterns):
            to_delete.append(path)
    
    # Additionally, always remove all files and subdirectories under the top-level `logs/`
    # directory when present. We prefer to clear the contents but keep the `logs/`
    # directory itself in place.
    logs_dir = base_path / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        for child in logs_dir.iterdir():
            # Skip if child is the project `models` or `data` directories by mistake
            if any(p in ("models", "data") for p in child.parts):
                continue
            to_delete.append(child)

    return to_delete


def clear_cache(base_path: Path, dry_run: bool = False) -> None:
    """
    Delete (or preview) cache files and directories found.

    Args:
        base_path: Base directory to clean
        dry_run: If True, do not delete files; only print what would be removed.
    """
    cache_paths = find_cache_files(base_path)

    deleted_count = 0
    failed_count = 0

    if dry_run:
        print("Dry-run mode: the following paths would be removed:")
    else:
        print("Clearing cache files...")

    for path in cache_paths:
        try:
            if dry_run:
                if path.is_dir():
                    print(f"Would remove directory: {path}")
                else:
                    print(f"Would remove file: {path}")
            else:
                if path.is_dir():
                    shutil.rmtree(path)
                    print(f"Removed directory: {path}")
                else:
                    path.unlink()
                    print(f"Removed file: {path}")
            deleted_count += 1
        except Exception as e:
            print(f"Failed to remove {path}: {e}")
            failed_count += 1

    if not dry_run:
        print(f"\nCache cleaning complete:")
        print(f"- {deleted_count} items removed")
        print(f"- {failed_count} items failed to remove")
    else:
        print(f"\nDry-run summary: {len(cache_paths)} items would be removed")


if __name__ == "__main__":
    # Get the project root directory (2 levels up from this script)
    parser = argparse.ArgumentParser(description="Clear project cache files (safe-guards against deleting models/data)")
    parser.add_argument("--path", default=str(Path(__file__).parent.parent.resolve()), help="Project root path to scan")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without deleting files")
    args = parser.parse_args()

    project_root = Path(args.path).resolve()
    print(f"Cleaning cache from: {project_root}")
    clear_cache(project_root, dry_run=args.dry_run)