"""Pytest conftest for HireMind tests.

Responsibilities:
- Load `config/.env` into os.environ for test runs (without overwriting existing env vars).
- Provide minimal, tidy CLI messages when tests start so test output is self-descriptive.
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from datetime import datetime
from typing import Dict


def _load_config_dotenv() -> None:
    """Load simple KEY=VALUE pairs from `config/.env` into os.environ.

    This function is intentionally conservative: it does not overwrite any
    existing process environment variables. It supports quoted values and
    skips blank lines or lines starting with '#'.
    """
    project_root = Path(__file__).resolve().parents[1]
    dotenv = project_root / "config" / ".env"
    if not dotenv.exists():
        return

    try:
        with dotenv.open("r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue

                if "=" not in s:
                    continue

                key, val = s.split("=", 1)
                key = key.strip()
                val = val.strip()
                # strip optional surrounding quotes
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]

                # do not overwrite existing environment variables
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        # Be conservative: never raise during env loading for tests
        return


# load env right away so tests can rely on values from config/.env
_load_config_dotenv()


# Simple collection index so we can show "N of M" in the pre-test banner
_ITEM_INDEX: Dict[str, int] = {}
_TOTAL_ITEMS: int = 0


def _color(text: str, code: str) -> str:
    try:
        return f"\x1b[{code}m{text}\x1b[0m"
    except Exception:
        return text


def pytest_collection_modifyitems(session, config, items):
    """Populate a mapping of nodeid -> sequential index for prettier banners."""
    global _ITEM_INDEX, _TOTAL_ITEMS
    _TOTAL_ITEMS = len(items)
    for idx, item in enumerate(items, start=1):
        _ITEM_INDEX[item.nodeid] = idx


def pytest_runtest_setup(item):
    """Print a concise, colored banner before each test.

    Prints:
      RUN [n/M] test_name  YYYY-MM-DD HH:MM:SS
      What it does: <first line of docstring>

    Only the test name (function name) is shown, not the full nodeid.
    """
    try:
        idx = _ITEM_INDEX.get(item.nodeid, "?")
        total = _TOTAL_ITEMS or "?"
        name = getattr(item, "name", None) or item.nodeid.split("::")[-1]
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"{_color('RUN', '36')} [{idx}/{total}] {name}  {ts}", flush=True)

        # short description from docstring
        desc = None
        try:
            func = getattr(item, "obj", None)
            if func is None and hasattr(item, "function"):
                func = item.function
            if func is not None:
                import inspect

                doc = inspect.getdoc(func)
                if doc:
                    for line in doc.splitlines():
                        line = line.strip()
                        if line:
                            desc = line
                            break
        except Exception:
            desc = None

        if desc:
            print(f"{_color('What it does:', '33')} {desc}", flush=True)
    except Exception:
        # never let test-reporting blow up the test run
        return


def pytest_runtest_logreport(report):
    """Highlight the result after the test call phase and add a blank line.

    This hook prints a colored PASS/FAIL line after the test finishes
    (during the 'call' phase) and an empty line for readability.
    """
    try:
        if report.when != "call":
            return

        outcome = report.outcome.upper()
        if outcome == "PASSED":
            col = "32"  # green
        elif outcome == "FAILED":
            col = "31"  # red
        else:
            col = "33"  # yellow for skipped or other

        duration = f"{getattr(report, 'duration', 0):.2f}s"
        print(f"{_color(outcome, col)} ({duration})", flush=True)
        # spacer line
        print(flush=True)
    except Exception:
        # be defensive; never raise from a reporting helper
        return
