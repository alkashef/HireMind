#!/usr/bin/env python
"""Hermes per-field extraction report (standalone script).

- Loads the OpenAI-backed canonical fixture to get the CV text and expected values
  under `openai_extraction`.
- Uses the per-field prompt (`prompts/extract_field_user.md`) and optional hints
  from `prompts/field_hints.json`.
- Extracts each field via the local Hermes model and prints a clean table:

    Field | Test Output | Expected | Result

- Suppresses warnings. Uses try/except to catch and report errors without stack traces.

Run (Windows cmd.exe):
    python scripts\hermes_field_extraction_report.py
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

# Suppress noisy warnings
warnings.filterwarnings("ignore")

# Ensure repository root is on sys.path so `config` and `utils` are importable
try:
    _repo_root = Path(__file__).resolve().parents[1]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))
except Exception:
    pass


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cv_and_expected(fixture_path: Path) -> tuple[str, Dict[str, Any]]:
    data = _read_json(fixture_path)
    cv_text: str = ""
    expected: Dict[str, Any] = {}
    if isinstance(data, dict):
        cv_text = data.get("text", "") or ""
        expected = data.get("openai_extraction", {}) or {}
    if not isinstance(cv_text, str) or not cv_text.strip():
        # try sections concatenation
        sections = (data.get("sections") if isinstance(data, dict) else None) or []
        if isinstance(sections, list):
            texts = []
            for s in sections:
                if isinstance(s, dict) and s.get("text"):
                    texts.append(s.get("text"))
                elif isinstance(s, str):
                    texts.append(s)
            cv_text = "\n\n".join(t for t in texts if t)
    if not isinstance(expected, dict):
        expected = {}
    return cv_text, expected


def _truncate(s: str, n: int = 120) -> str:
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def _normalize_for_assert(field_name: str, s: str) -> str:
    if s is None:
        return ""
    s = s.strip()
    if field_name == "first_name":
        s = s.rstrip(".,;:")
        parts = [p for p in s.split() if p]
        return parts[0] if parts else s
    if field_name == "last_name":
        return s.rstrip(".,;:")
    if field_name == "email":
        return s.lower()
    if field_name == "phone":
        return s.strip()
    return s


def _is_numeric_like(s: str) -> bool:
    if s is None:
        return False
    t = s.strip()
    if t == "":
        return True
    try:
        float(t)
        return True
    except Exception:
        return False


def _to_float_or_none(s: str) -> Optional[float]:
    try:
        return float(s.strip())
    except Exception:
        return None


def is_valid_output(s: str, cv_sample: str) -> bool:
    if s is None:
        return False
    if not isinstance(s, str):
        return False
    t = s.strip()
    if t == "":
        return True
    if "\n" in t:
        return False
    if len(t) > 200:
        return False
    sample_tokens = [tok for tok in re.split(r"\W+", cv_sample) if len(tok) > 4][:3]
    for tok in sample_tokens:
        if tok and tok in t:
            return False
    bad_markers = [
        "Return only the value",
        "requested field",
        "If the requested",
        "{field}",
        "CV START",
        "CV END",
        "Examples",
    ]
    for m in bad_markers:
        if m in t:
            return False
    if "{" in t or "}" in t or t.startswith("["):
        return False
    return True


def extract_with_retry(client, cv_text: str, field: str, hint: str = "") -> str:
    """Generate a single-line value for `field`; retry once with stricter prompt."""
    try:
        out = client.generate_from_prompt_file(
            "extract_field_user.md",
            prompt_vars={"cv": cv_text, "field": field, "hint": hint},
            max_new_tokens=32,
        )
        if isinstance(out, str) and is_valid_output(out, cv_text):
            return out.strip()
    except Exception:
        pass

    # Retry with stricter inline instruction
    inline = (
        f"Return exactly one line containing only the value of the field {field} from the CV below.\n"
        f"If missing, return an empty line.\n\nCV START\n{cv_text}\nCV END\n"
    )
    try:
        out2 = client.generate(inline, max_new_tokens=32, do_sample=False, temperature=0.0)
        if isinstance(out2, str) and is_valid_output(out2, cv_text):
            return out2.strip()
    except Exception:
        pass

    return (out2 if isinstance(locals().get("out2"), str) else (out if isinstance(locals().get("out"), str) else "")).strip()


def print_table(rows: List[Dict[str, Any]]) -> None:
    col1, col2, col3, col4 = "Field", "Test Output", "Expected", "Result"

    def _lim(s: str, n: int = 60) -> str:
        return s if len(s) <= n else s[: n - 3] + "..."

    header = [col1, col2, col3, col4]
    data = []
    for r in rows:
        res = "PASS" if r.get("passed") else "FAIL"
        if not r.get("passed") and r.get("reason"):
            res += f" ({r['reason']})"
        data.append([r.get("field", ""), _lim(r.get("got", "")), _lim(r.get("want", "")), res])

    widths = [
        max(len(header[0]), *(len(d[0]) for d in data)) if data else len(header[0]),
        max(len(header[1]), *(len(d[1]) for d in data)) if data else len(header[1]),
        max(len(header[2]), *(len(d[2]) for d in data)) if data else len(header[2]),
        max(len(header[3]), *(len(d[3]) for d in data)) if data else len(header[3]),
    ]

    def _fmt_row(cols: List[str]) -> str:
        return (
            f"{cols[0]:<{widths[0]}} | "
            f"{cols[1]:<{widths[1]}} | "
            f"{cols[2]:<{widths[2]}} | "
            f"{cols[3]:<{widths[3]}}"
        )

    sep = "-" * (sum(widths) + 3 * 3)
    print(_fmt_row(header))
    print(sep)
    for d in data:
        print(_fmt_row(d))


def main() -> int:
    # Resolve paths
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests" / "data" / "Ahmad Alkashef - Resume - OpenAI.json"
    hints_path = repo_root / "prompts" / "field_hints.json"

    # Load inputs
    try:
        cv_text, expected_map = load_cv_and_expected(fixture)
    except Exception as e:
        print(f"ERROR: Failed to read fixture: {e}")
        return 2

    try:
        field_hints_map = _read_json(hints_path)
        if not isinstance(field_hints_map, dict):
            field_hints_map = {}
    except Exception:
        field_hints_map = {}

    if not isinstance(cv_text, str) or not cv_text.strip():
        print("ERROR: Empty CV text from fixture; cannot proceed")
        return 2

    # Lazy import hermes client; handle missing deps gracefully
    try:
        from config.settings import AppConfig
        from utils.hermes_client import get_global_client
    except Exception as exc:
        print(f"ERROR: Hermes client not importable: {exc}")
        print("Hint: Ensure 'torch' and 'transformers' are installed. On Windows/CPU, set HERMES_QUANTIZE_4BIT=false in config/.env.")
        return 2

    cfg = AppConfig()
    try:
        client = get_global_client(model_dir=cfg.hermes_model_dir, quantize_4bit=cfg.hermes_quantize_4bit)
    except Exception as exc:
        print(f"ERROR: Hermes runtime not available: {exc}")
        print("Hint: If you don't have bitsandbytes or a compatible GPU, set HERMES_QUANTIZE_4BIT=false in config/.env and retry.")
        return 2

    # Determine fields: use keys from expected map to cover all fields
    all_fields = sorted(list(expected_map.keys()))

    numeric_fields = {
        "misspelling_count",
        "visual_cleanliness",
        "professional_look",
        "formatting_consistency",
        "years_since_graduation",
        "total_years_experience",
        "employers_count",
        "avg_years_per_employer",
        "years_at_current_employer",
    }

    results: List[Dict[str, Any]] = []
    for field in all_fields:
        want = expected_map.get(field)
        try:
            got_raw = extract_with_retry(client, cv_text, field, field_hints_map.get(field, ""))
        except Exception as e:
            results.append({
                "field": field,
                "got": f"<error: {e}>",
                "want": str(want if want is not None else ""),
                "passed": False,
                "reason": "exception",
            })
            continue

        got_display = _truncate(got_raw or "")
        norm_got = _normalize_for_assert(field, got_raw or "")
        norm_want = _normalize_for_assert(field, str(want)) if want is not None else None

        passed = True
        reason = ""
        if field in expected_map:
            if field in numeric_fields:
                got_num = _to_float_or_none(norm_got)
                want_num = _to_float_or_none(str(want)) if want is not None else None
                if want_num is None:
                    passed = (got_num is None) or (norm_got == "")
                else:
                    passed = got_num is not None and abs(got_num - want_num) <= 1e-2
                if not passed:
                    reason = f"numeric mismatch (got={got_num}, want={want})"
            else:
                passed = (norm_got == norm_want)
                if not passed:
                    reason = "mismatch"
        elif field in numeric_fields:
            passed = _is_numeric_like(norm_got)
            if not passed:
                reason = "not numeric-like"
        else:
            passed = is_valid_output(norm_got, cv_text)
            if not passed:
                reason = "invalid format/content"

        results.append({
            "field": field,
            "got": got_display,
            "want": str(want if want is not None else ""),
            "passed": passed,
            "reason": reason,
        })

    print_table(results)

    failures = [r for r in results if not r.get("passed")]
    if failures:
        print(f"\nSummary: {len(results) - len(failures)}/{len(results)} fields passed, {len(failures)} failed.")
    else:
        print(f"\nSummary: All {len(results)} fields passed.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        raise SystemExit(130)
