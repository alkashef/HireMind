#!/usr/bin/env python
"""
Script to clear all cache files from the project repository.
Removes Python bytecode files, pytest cache, temporary files, and other cache types.
"""

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
    
    for path in base_path.rglob("*"):
        # Skip the models directory
        if "models" in path.parts and path.is_dir():
            continue
            
        # Check if path matches any cache pattern
        if path.is_dir() and path.name in cache_patterns:
            to_delete.append(path)
        elif path.is_file() and any(path.name.endswith(pattern) for pattern in cache_patterns):
            to_delete.append(path)
    
    return to_delete


def clear_cache(base_path: Path) -> None:
    """
    Delete all cache files and directories found.
    
    Args:
        base_path: Base directory to clean
    """
    cache_paths = find_cache_files(base_path)
    
    deleted_count = 0
    failed_count = 0
    
    print("Clearing cache files...")
    for path in cache_paths:
        try:
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
    
    print(f"\nCache cleaning complete:")
    print(f"- {deleted_count} items removed")
    print(f"- {failed_count} items failed to remove")


if __name__ == "__main__":
    # Get the project root directory (2 levels up from this script)
    project_root = Path(__file__).parent.parent.resolve()
    
    print(f"Cleaning cache from: {project_root}")
    clear_cache(project_root)