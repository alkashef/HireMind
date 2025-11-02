import sys
import pathlib
import time
import warnings
import os

# When running this file directly (python tests/test_extractors_local.py)
# Python sets sys.path[0] to the tests directory. Ensure the project root is
# on sys.path so `import utils.*` works the same as when running via pytest
# from the repository root.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.extractors import pdf_to_text, docx_to_text

from config.settings import AppConfig


cfg = AppConfig()

# Read paths from environment (config/.env) when available, otherwise fall back
# to the legacy hard-coded developer paths.
PDF_PATH = os.getenv("TEST_CV_PATH") or os.getenv("TEST_PDF_PATH") or (
    r"C:/Users/aa186095/OneDrive - Teradata/Consulting Egypt/07. Resourcing & Hiring/RR/CVs/EslamAhmedAbdAlaziz_CV.pdf"
)

DOCX_PATH = os.getenv("TEST_DOCX_PATH") or (
    r"C:/Users/aa186095/OneDrive - Teradata/Consulting Egypt/07. Resourcing & Hiring/RR/Job Descriptions/[Egypt Consulting] 2023.07.12 - Staff SW Engineer - JD.docx"
)


def _truncate(s: str, n: int = 400) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def main() -> int:
    """High-verbosity standalone smoke test for local PDF/DOCX extractors.

    - Runs as a plain Python script (no pytest).
    - Prints progress and timing for each step.
    - Suppresses warnings to keep output clean.

    Exit codes:
      0 - success
      2 - one or both files missing or unreadable
      3 - missing dependencies or extraction error
      4 - unexpected exception
    """
    # No warnings
    warnings.filterwarnings("ignore")

    print("[INFO] Starting local extractors smoke test (high verbosity)")
    print(f"[INFO] Project root: {PROJECT_ROOT}")
    print(f"[INFO] PDF path:  {PDF_PATH}")
    print(f"[INFO] DOCX path: {DOCX_PATH}")

    # Step 1: PDF extraction
    print("[STEP 1/2] Extracting PDF text...")
    t0 = time.perf_counter()
    try:
        pdf_text = pdf_to_text(PDF_PATH)
    except RuntimeError as exc:
        print(f"[ERROR] Missing dependency for PDF extraction: {exc}")
        return 3
    except ValueError as exc:
        print(f"[ERROR] PDF file missing or unreadable: {exc}")
        return 2
    except Exception as exc:
        print(f"[ERROR] Unexpected error extracting PDF: {exc}")
        return 4
    t1 = time.perf_counter()
    print(f"[OK] PDF extracted in {t1 - t0:.2f}s; length={len(pdf_text)} chars")
    print("[PDF SAMPLE]\n" + _truncate(pdf_text, 600))

    # Step 2: DOCX extraction
    print("\n[STEP 2/2] Extracting DOCX text...")
    t2 = time.perf_counter()
    try:
        docx_text = docx_to_text(DOCX_PATH)
    except RuntimeError as exc:
        print(f"[ERROR] Missing dependency for DOCX extraction: {exc}")
        return 3
    except ValueError as exc:
        print(f"[ERROR] DOCX file missing or unreadable: {exc}")
        return 2
    except Exception as exc:
        print(f"[ERROR] Unexpected error extracting DOCX: {exc}")
        return 4
    t3 = time.perf_counter()
    print(f"[OK] DOCX extracted in {t3 - t2:.2f}s; length={len(docx_text)} chars")
    print("[DOCX SAMPLE]\n" + _truncate(docx_text, 600))

    # Final summary (clear test results)
    print("\n===== Test Results =====")
    print("Status      : SUCCESS")
    print(f"PDF length  : {len(pdf_text)} chars (elapsed {t1 - t0:.2f}s)")
    print(f"DOCX length : {len(docx_text)} chars (elapsed {t3 - t2:.2f}s)")
    print("=======================\n")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
        sys.exit(rc)
    except Exception as e:
        print("Unexpected error during test run:", repr(e))
        sys.exit(4)
