#!/usr/bin/env python3
"""Minimal standalone test to verify a local Weaviate instance is reachable.

Usage:
    python tests/test_weaviate_local.py

Environment variables:
  WEAVIATE_USE_LOCAL  - if 'true'|'1'|'yes', defaults URL to http://localhost:8080
  WEAVIATE_URL        - explicit base URL (overrides local helper if present)
  WEAVIATE_API_KEY    - optional API key (not required for probe)

Exit codes:
  0 - success (Weaviate reachable)
  2 - no configuration found (nothing to test)
  3 - HTTP probe failed / unreachable
  4 - unexpected exception

This script is intentionally minimal and uses only the Python standard
library for the HTTP probe so it can be run without extra dependencies.
If the optional `weaviate-client` is installed, the script will also
attempt to import and call `utils.weaviate_store.WeaviateStore.ensure_schema()`
and print its boolean result.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _load_weaviate_env_from_file() -> None:
    """Load WEAVIATE_* environment variables from config/.env into os.environ.

    Behavior:
    - Looks for the file at <repo_root>/config/.env (repo root is two levels up from this test file).
    - Parses simple KEY=VALUE lines, skips blank lines and lines starting with '#' or ';'.
    - Handles optional leading 'export ' on the key and strips surrounding double-quotes from values.
    - Only sets variables whose key starts with 'WEAVIATE_' to avoid clobbering unrelated env vars.
    - Does not override variables already present in the environment (existing env wins).
    """
    try:
        repo_root = Path(__file__).resolve().parent.parent
        env_path = repo_root / "config" / ".env"
        if not env_path.exists():
            return
        loaded = 0
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            # Optional leading 'export '
            if line.lower().startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            # strip optional surrounding quotes
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            # Only import WEAVIATE_ prefixed variables to avoid side-effects
            if not k.startswith("WEAVIATE_"):
                continue
            if k not in os.environ:
                os.environ[k] = v
                loaded += 1
        if loaded:
            print(f"Loaded {loaded} WEAVIATE_* variables from {env_path}")
    except Exception as e:
        print("Failed to load env file for weaviate vars:", repr(e))


# Load WEAVIATE_* variables from config/.env (if present) before running probes
_load_weaviate_env_from_file()


def get_target_url() -> str | None:
    url = os.environ.get("WEAVIATE_URL", "").strip()
    use_local = os.environ.get("WEAVIATE_USE_LOCAL", "").lower() in ("1", "true", "yes")
    if url:
        return url.rstrip("/")
    if use_local:
        return "http://localhost:8080"
    return None


def probe_http(base_url: str) -> bool:
    probe_url = base_url.rstrip("/") + "/v1/"
    print("Probing Weaviate at:", probe_url)
    try:
        req = urllib.request.Request(probe_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.getcode()
            body = resp.read(2048)
            print("HTTP status:", status)
            try:
                parsed = json.loads(body.decode("utf-8"))
                # show a small summary of keys so output is helpful but compact
                if isinstance(parsed, dict):
                    print("Response keys:", list(parsed.keys())[:10])
            except Exception:
                print("Non-JSON or truncated response:", body.decode("utf-8", "replace")[:300])
            return status == 200
    except urllib.error.HTTPError as e:
        print("HTTPError:", e.code, getattr(e, "reason", ""))
        return False
    except Exception as e:
        print("Probe exception:", repr(e))
        return False


def try_ensure_schema(base_url: str) -> None:
    try:
        # The import may fail if `weaviate-client` isn't installed; that's OK.
        from utils.weaviate_store import WeaviateStore

        print("weaviate-client available: attempting ensure_schema() via WeaviateStore")
        ws = WeaviateStore(url=base_url, api_key=os.environ.get("WEAVIATE_API_KEY"), batch_size=int(os.environ.get("WEAVIATE_BATCH_SIZE", "64")))
        ok = ws.ensure_schema()
        print("ensure_schema() returned:", ok)
    except Exception as e:
        print("Skipping ensure_schema() (client missing or error):", repr(e))


def main() -> int:
    url = get_target_url()
    if not url:
        print("No Weaviate configuration found. Set WEAVIATE_URL or WEAVIATE_USE_LOCAL=true to run this test.")
        return 2

    ok = probe_http(url)
    if not ok:
        print("HTTP probe failed. Is Weaviate running at:", url)
        return 3

    # optional: try client-based schema ensure if available
    try_ensure_schema(url)

    print("SUCCESS: Weaviate reachable at", url)
    return 0


if __name__ == "__main__":
    try:
        rc = main()
        sys.exit(rc)
    except Exception as e:
        print("Unexpected error during test:", repr(e))
        sys.exit(4)
