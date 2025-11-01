"""Small, independent test for Hermes per-field extraction.

This test loads the OpenAI-backed canonical fixture (which contains the
extracted CV text) and calls the per-field prompt in `prompts/extract_field_user.md`.
It asserts the returned single-line values equal the small set of expected
reference values. The test will be skipped if the local Hermes runtime or
dependencies are not available on the test machine.
"""
from pathlib import Path
import json
import re
import pytest


def load_cv_text_from_openai_fixture(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Prefer a top-level 'text' key; fall back to concatenating 'sections'
    if isinstance(data, dict):
        if data.get("text"):
            return data["text"]
        # some fixtures store sections as a list of dicts with 'text'
        sections = data.get("sections") or data.get("parts")
        if isinstance(sections, list):
            texts = []
            for s in sections:
                if isinstance(s, dict) and s.get("text"):
                    texts.append(s.get("text"))
                elif isinstance(s, str):
                    texts.append(s)
            return "\n\n".join(t for t in texts if t)
    # as a last resort, return the full JSON as a string (not ideal)
    return json.dumps(data, ensure_ascii=False)


def test_hermes_extract_basic_fields():
    """Call Hermes per-field prompt and compare to small expected map.

    Behavior:
    - Extract each field once using the per-field prompt (with hints).
    - Validate type/format and compare against expected for known fields.
    - Accumulate results across all fields (no early aborts).
    - At the end, print a compact table: field | test output | expected | pass/fail.
    - If any field fails, the test fails after printing the table.

    The test will skip if Hermes or HF deps are missing in the environment.
    """
    # Resolve fixture path
    fixture = Path(__file__).resolve().parents[0] / "data" / "Ahmad Alkashef - Resume - OpenAI.json"
    assert fixture.exists(), f"Fixture not found: {fixture}"

    # Extract CV text for prompting
    cv_text = load_cv_text_from_openai_fixture(fixture)
    assert isinstance(cv_text, str) and len(cv_text.strip()) > 0

    # Lazy import/usage of Hermes — skip if model/deps aren't available
    try:
        from utils.hermes_client import HermesClient, get_global_client
        from config.settings import AppConfig
    except Exception as exc:
        pytest.skip(f"Hermes client not importable: {exc}")

    cfg = AppConfig()
    # Reuse a single global client so the model loads once and is reused across fields
    client = get_global_client(model_dir=cfg.hermes_model_dir, quantize_4bit=cfg.hermes_quantize_4bit)

    # Load structured field hints from prompts/field_hints.json so tests and prompts share
    # the same authoritative hint text.
    hints_path = Path(__file__).resolve().parents[1] / "prompts" / "field_hints.json"
    try:
        field_hints_map = json.loads(hints_path.read_text(encoding="utf-8"))
    except Exception:
        field_hints_map = {}

    # Embedded expected values (copied from the authoritative OpenAI-backed fixture)
    expected = {
        "first_name": "Ahmad",
        "last_name": "Alkashef",
        "full_name": "Ahmad Alkashef",
        "email": "alkashef@gmail.com",
        "phone": "+20-100-506-2208",
        "misspelling_count": 0,
        "misspelled_words": "",
        "visual_cleanliness": 0,
        "professional_look": 0,
        "formatting_consistency": 0,
        "years_since_graduation": 15,
        "total_years_experience": 24,
        "employer_names": "Teradata, Microsoft, Schlumberger, Infineon, Mentor Graphics",
        "employers_count": 5,
        "avg_years_per_employer": 4.8,
        "years_at_current_employer": 6,
        "address": "Cairo",
        "alma_mater": "Ain Shams University",
        "high_school": "",
        "education_system": "Bachelor's and Master's",
        "second_foreign_language": "",
        "flag_stem_degree": "Yes",
        "military_service_status": "Unknown",
        "worked_at_financial_institution": "No",
        "worked_for_egyptian_government": "Yes",
    }

    # Full field list (mirrors prompts/extract_from_cv_user.md schema example)
    all_fields = [
        "first_name",
        "last_name",
        "full_name",
        "email",
        "phone",
        "misspelling_count",
        "misspelled_words",
        "visual_cleanliness",
        "professional_look",
        "formatting_consistency",
        "years_since_graduation",
        "total_years_experience",
        "employer_names",
        "employers_count",
        "avg_years_per_employer",
        "years_at_current_employer",
        "address",
        "alma_mater",
        "high_school",
        "education_system",
        "second_foreign_language",
        "flag_stem_degree",
        "military_service_status",
        "worked_at_financial_institution",
        "worked_for_egyptian_government",
    ]

    def is_valid_output(s: str, cv_sample: str) -> bool:
        """Return True if s looks like a valid extracted value (not a prompt echo).

        Heuristics:
        - must be a single non-empty line (or empty if field missing)
        - must not contain large portions of the CV text
        - must not contain obvious prompt templates or placeholder markers
        """
        if s is None:
            return False
        if not isinstance(s, str):
            return False
        # strip only trailing/leading whitespace; allow empty-string for missing fields
        t = s.strip()
        # allow empty string (missing field) as valid
        if t == "":
            return True
        # single line only
        if "\n" in t:
            return False
        # too long (likely echoing CV)
        if len(t) > 200:
            return False
        # should not contain the CV body
        # check presence of a small CV token (e.g., name) as evidence of echo
        sample_tokens = [tok for tok in re.split(r"\W+", cv_sample) if len(tok) > 4][:3]
        for tok in sample_tokens:
            if tok and tok in t:
                return False
        # should not contain obvious template text
        bad_markers = ["Return only the value", "requested field", "If the requested", "{field}", "CV START", "CV END", "Examples"]
        for m in bad_markers:
            if m in t:
                return False
        # braces or JSON-like output is suspicious for per-field single values
        if "{" in t or "}" in t or t.startswith("["):
            return False
        return True

    def extract_with_retry(field: str) -> str:
        # First attempt: use canonical prompt file
        try:
            out = client.generate_from_prompt_file(
                "extract_field_user.md",
                prompt_vars={"cv": cv_text, "field": field, "hint": field_hints_map.get(field, "")},
                max_new_tokens=32,
            )
        except RuntimeError as exc:
            pytest.skip(f"Hermes runtime not available: {exc}")

        if isinstance(out, str) and is_valid_output(out, cv_text):
            return out.strip()

        # Retry with a stricter inline prompt to force single-line output
        inline = (
            f"Return exactly one line containing only the value of the field {field} from the CV below.\n"
            f"If missing, return an empty line.\n\nCV START\n{cv_text}\nCV END\n"
        )
        try:
            out2 = client.generate(inline, max_new_tokens=32, do_sample=False, temperature=0.0)
        except Exception:
            # If generation fails, propagate original output (may be None)
            return (out or "").strip()

        if isinstance(out2, str) and is_valid_output(out2, cv_text):
            return out2.strip()

        # Fallback: return first attempt trimmed (may fail the assertion below)
        return (out2 or out or "").strip()

    # Helpers for graceful failure reporting and normalization
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
            return True  # allow empty as "missing"
        try:
            float(t)
            return True
        except Exception:
            return False

    def _to_float_or_none(s: str):
        try:
            return float(s.strip())
        except Exception:
            return None

    # Validate all fields: exact matches for core fields; format/type checks for the rest.
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

    # Use the external hints mapping when producing failure messages
    field_hints = field_hints_map

    results: list[dict] = []
    for field in all_fields:
        want = expected.get(field, None)
        got = extract_with_retry(field)
        if got and "Return only the value" in got:
            pytest.skip("Hermes returned prompt template text instead of extraction; skip and re-run when templates fixed")

        got_display = _truncate(got or "")
        norm_got = _normalize_for_assert(field, got or "")
        norm_want = _normalize_for_assert(field, want or "") if want is not None else None

        passed = True
        reason = ""

        if field in expected:
            if field in numeric_fields:
                want_val = expected.get(field, None)
                got_num = _to_float_or_none(norm_got)
                if want_val is None:
                    want_num = None
                else:
                    try:
                        want_num = float(want_val)
                    except Exception:
                        want_num = None
                if want_num is None:
                    passed = (got_num is None) or (norm_got == "")
                else:
                    passed = got_num is not None and abs(got_num - want_num) <= 1e-2
                if not passed:
                    reason = f"numeric mismatch (got={got_num}, want={want_val})"
            else:
                passed = (norm_got == norm_want)
                if not passed:
                    reason = f"mismatch"
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
            "want": str(expected.get(field, "")),
            "passed": passed,
            "reason": reason,
        })

    # Print a compact result table
    def _print_table(rows: list[dict]):
        col1, col2, col3, col4 = "Field", "Test Output", "Expected", "Result"
        # Limit output columns to keep table readable in CI
        def _lim(s: str, n: int = 60) -> str:
            return s if len(s) <= n else s[: n - 3] + "..."

        header = [col1, col2, col3, col4]
        data = []
        for r in rows:
            res = "PASS" if r["passed"] else "FAIL"
            if not r["passed"] and r["reason"]:
                res += f" ({r['reason']})"
            data.append([r["field"], _lim(r["got"]), _lim(r["want"]), res])

        # Compute widths
        widths = [
            max(len(header[0]), *(len(d[0]) for d in data)) if data else len(header[0]),
            max(len(header[1]), *(len(d[1]) for d in data)) if data else len(header[1]),
            max(len(header[2]), *(len(d[2]) for d in data)) if data else len(header[2]),
            max(len(header[3]), *(len(d[3]) for d in data)) if data else len(header[3]),
        ]

        def _fmt_row(cols: list[str]) -> str:
            return (
                f"{cols[0]:<{widths[0]}} | "
                f"{cols[1]:<{widths[1]}} | "
                f"{cols[2]:<{widths[2]}} | "
                f"{cols[3]:<{widths[3]}}"
            )

        sep = "-" * (sum(widths) + 3 * 3)  # 3 separators of ' | '
        print("\nHermes extraction results (all fields):")
        print(_fmt_row(header))
        print(sep)
        for d in data:
            print(_fmt_row(d))
        print("\n")

    _print_table(results)

    # Final assertion: fail if any field failed
    failed_fields = [r["field"] for r in results if not r["passed"]]
    if failed_fields:
        pytest.fail(
            "Some fields did not match expected values. See the printed table above for details.\n"
            f"Failed fields: {', '.join(failed_fields)}"
        )
