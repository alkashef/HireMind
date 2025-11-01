#!/usr/bin/env python
"""OpenAI per-field extraction report (standalone script under tests/).

- Loads CV text and expected values from the canonical fixture.
- Uses the OpenAI API to produce a full JSON extraction.
- Prints a clean table to stdout and writes a Markdown table to TEST_RESULTS/extract_fields_openai.md.
- Suppresses warnings; catches errors and prints friendly messages.

Run (Windows cmd.exe):
    python tests\test_extract_cv_fields.py
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path
import os
from typing import Any, Dict, List, Optional
import time

warnings.filterwarnings("ignore")

# Ensure repository root on sys.path
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


def extract_with_retry(client, cv_text: str, field: str, hint: str = "", template: Optional[str] = None) -> str:
    try:
        inline_prompt = (
            template.format(cv=cv_text, field=field, hint=hint)
            if template else
            f"Return exactly one line containing only the value of the field {field} from the CV below.\n"
            f"If missing, return an empty line.\n\nCV START\n{cv_text}\nCV END\n"
        )
        out = client.generate(inline_prompt, max_new_tokens=32, do_sample=False, temperature=0.0)
        if isinstance(out, str) and is_valid_output(out, cv_text):
            return out.strip()
    except Exception:
        pass

    inline2 = (
        f"Return exactly one line containing only the value of the field {field} from the CV below.\n"
        f"If missing, return an empty line.\n\nCV START\n{cv_text}\nCV END\n"
    )
    try:
        out2 = client.generate(inline2, max_new_tokens=32, do_sample=False, temperature=0.0)
        if isinstance(out2, str) and is_valid_output(out2, cv_text):
            return out2.strip()
    except Exception:
        pass

    return (out2 if isinstance(locals().get("out2"), str) else (out if isinstance(locals().get("out"), str) else "")).strip()


def print_table(rows: List[Dict[str, Any]]) -> None:
    col1, col2, col3, col4, col5 = (
        "Field",
        "Test Output",
        "Expected",
        "Infer Time",
        "Result",
    )

    def _lim(s: str, n: int = 60) -> str:
        return s if len(s) <= n else s[: n - 3] + "..."

    header = [col1, col2, col3, col4, col5]
    data = []
    for r in rows:
        res = "PASS" if r.get("passed") else "FAIL"
        if not r.get("passed") and r.get("reason"):
            res += f" ({r['reason']})"
        infer_s = r.get("infer_s")
        data.append([
            r.get("field", ""),
            _lim(r.get("got", "")),
            _lim(r.get("want", "")),
            f"{infer_s:.2f}" if isinstance(infer_s, (int, float)) else "",
            res,
        ])

    widths = [
        max(len(header[0]), *(len(d[0]) for d in data)) if data else len(header[0]),
        max(len(header[1]), *(len(d[1]) for d in data)) if data else len(header[1]),
        max(len(header[2]), *(len(d[2]) for d in data)) if data else len(header[2]),
        max(len(header[3]), *(len(d[3]) for d in data)) if data else len(header[3]),
        max(len(header[4]), *(len(d[4]) for d in data)) if data else len(header[4]),
    ]

    def _fmt_row(cols: List[str]) -> str:
        return (
            f"{cols[0]:<{widths[0]}} | "
            f"{cols[1]:<{widths[1]}} | "
            f"{cols[2]:<{widths[2]}} | "
            f"{cols[3]:>{widths[3]}} | "
            f"{cols[4]:<{widths[4]}}"
        )

    sep = "-" * (sum(widths) + 4 * 3)
    print(_fmt_row(header))
    print(sep)
    for d in data:
        print(_fmt_row(d))


def build_markdown_table(rows: List[Dict[str, Any]]) -> str:
    header = ["Field", "Test Output", "Expected", "Infer Time", "Result"]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    def _esc(s: str) -> str:
        return (s or "").replace("|", "\\|")
    def _lim(s: str, n: int = 60) -> str:
        return s if len(s) <= n else s[: n - 3] + "..."
    for r in rows:
        res = "PASS" if r.get("passed") else "FAIL"
        if not r.get("passed") and r.get("reason"):
            res += f" ({r['reason']})"
        infer_s = r.get("infer_s")
        fields = [
            r.get("field", ""),
            _lim(r.get("got", "")),
            _lim(r.get("want", "")),
            f"{infer_s:.2f}" if isinstance(infer_s, (int, float)) else "",
            res,
        ]
        lines.append("| " + " | ".join(_esc(str(x)) for x in fields) + " |")
    return "\n".join(lines)


def _ordered_fields_from_hints_map(hints_map: Dict[str, Any]) -> List[str]:
    """Return the field names in the exact order provided by the hints map (insertion order)."""
    if isinstance(hints_map, dict):
        return list(hints_map.keys())
    return []


def _run_openai(pdf_path: Path, expected_map: Dict[str, Any], ordered_fields: List[str]) -> tuple[List[Dict[str, Any]], float]:
    """Run a single OpenAI extraction on the PDF and compare fields. Returns (results, load_ms)."""
    from config.settings import AppConfig
    from utils.logger import AppLogger
    from utils.openai_manager import OpenAIManager

    cfg = AppConfig()
    logger = AppLogger(cfg.log_file_path)

    if not pdf_path.exists():
        raise RuntimeError(f"PDF fixture not found: {pdf_path}")
    print("OpenAI: uploading PDF and extracting (single request)...")

    t0 = time.perf_counter()
    mgr = OpenAIManager(cfg, logger)
    data, err = mgr.extract_full_name(pdf_path)
    t1 = time.perf_counter()
    infer_s_total = (t1 - t0)
    load_ms = 0.0

    if err:
        raise RuntimeError(f"OpenAI extraction failed: {err}")
    out_map: Dict[str, Any] = data or {}

    # Build results using the exact ordered fields from hints (no more, no less)
    keys = ordered_fields
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
    for idx, field in enumerate(keys, start=1):
        want = expected_map.get(field)
        got_val = out_map.get(field)
        got_str = "" if got_val is None else str(got_val)
        norm_got = _normalize_for_assert(field, got_str)
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

        results.append({
            "field": field,
            "got": _truncate(got_str),
            "want": str(want if want is not None else ""),
            "passed": passed,
            "reason": reason,
            # Single OpenAI request time shown across rows for visibility (seconds)
            "infer_s": infer_s_total,
        })

    print(f"OpenAI: extraction complete in {infer_s_total:.2f} s")
    return results, load_ms


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    # Ensure .env is loaded, then resolve paths from environment (no hard-coded constants)
    from config.settings import AppConfig as _Cfg
    from utils.prompt_loader import get_prompt_bundle
    cfg = _Cfg()
    env_cv_json = os.getenv("TEST_CV_REF_JSON") or os.getenv("TEST_CV_JSON_OUTPUT")
    env_cv_pdf = os.getenv("TEST_CV_PATH")
    env_results_dir = os.getenv("TEST_RESULTS")

    if not env_cv_json:
        print("ERROR: TEST_CV_REF_JSON/TEST_CV_JSON_OUTPUT is not set in environment (.env).")
        return 2
    if not env_cv_pdf:
        print("ERROR: TEST_CV_PATH is not set in environment (.env).")
        return 2
    if not env_results_dir:
        print("ERROR: TEST_RESULTS is not set in environment (.env).")
        return 2

    fixture = Path(env_cv_json)
    pdf_path = Path(env_cv_pdf)
    results_dir = Path(env_results_dir)
    # Consolidated JSON prompt (template + hints) via AppConfig / .env

    # Inputs
    try:
        cv_text, expected_map = load_cv_and_expected(fixture)
    except Exception as e:
        print(f"ERROR: Failed to read fixture: {e}")
        return 2

    # Load consolidated JSON prompt (template + hints) through loader
    try:
        bundle = get_prompt_bundle(prompt_key="extract_cv_fields_json", cfg=cfg)
    except Exception:
        bundle = {"template": "", "hints": {}, "fields": []}
    template = bundle.get("template", "")
    field_hints_map = bundle.get("hints", {})
    fields_from_bundle = bundle.get("fields", [])

    if not isinstance(cv_text, str) or not cv_text.strip():
        print("ERROR: Empty CV text from fixture; cannot proceed")
        return 2

    # Determine ordered fields from hints and run OpenAI-only
    # Prefer explicit fields order from bundle; fallback to hints order
    ordered_fields = list(fields_from_bundle) if isinstance(fields_from_bundle, list) and fields_from_bundle else _ordered_fields_from_hints_map(field_hints_map)
    if not ordered_fields:
        print("ERROR: Could not read ordered fields from prompts/prompt_extract_cv_fields.json")
        return 2
    try:
        results, _ = _run_openai(pdf_path, expected_map, ordered_fields)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2

    # Determine output filename and header (OpenAI-only)
    out_md = results_dir / "extract_fields_openai.md"
    md_header = "## OpenAI extraction results"

    # Console table
    print_table(results)

    # Markdown output
    try:
        md = [md_header, "", build_markdown_table(results), ""]
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("\n".join(md), encoding="utf-8")
        print(f"\nWrote Markdown table to: {out_md}")
    except Exception as e:
        print(f"ERROR: Failed to write Markdown report: {e}")

    # Summary
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
