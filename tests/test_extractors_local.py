import sys
import pathlib
import pytest

# When running this file directly (python tests/test_extractors_local.py)
# Python sets sys.path[0] to the tests directory. Ensure the project root is
# on sys.path so `import utils.*` works the same as when running via pytest
# from the repository root.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.extractors import pdf_to_text, docx_to_text


PDF_PATH = (
    r"C:/Users/aa186095/OneDrive - Teradata/Consulting Egypt/07. Resourcing & Hiring/RR/CVs/EslamAhmedAbdAlaziz_CV.pdf"
)

DOCX_PATH = (
    r"C:/Users/aa186095/OneDrive - Teradata/Consulting Egypt/07. Resourcing & Hiring/RR/Job Descriptions/[Egypt Consulting] 2023.07.12 - Staff SW Engineer - JD.docx"
)


def test_pdf_to_text_local():
    """Minimal smoke test for PDF extraction against a local file.

    Skips the test if PyMuPDF is not installed or the file is unreadable/missing.
    """
    try:
        text = pdf_to_text(PDF_PATH)
    except RuntimeError as exc:
        pytest.fail(f"PyMuPDF not available: {exc}")
    except ValueError as exc:
        pytest.fail(f"PDF unreadable or missing: {exc}")

    assert isinstance(text, str) and text.strip(), "PDF extraction returned empty text"


def test_docx_to_text_local():
    """Minimal smoke test for DOCX extraction against a local file.

    Skips the test if python-docx is not installed or the file is unreadable/missing.
    """
    try:
        text = docx_to_text(DOCX_PATH)
    except RuntimeError as exc:
        pytest.fail(f"python-docx not available: {exc}")
    except ValueError as exc:
        pytest.fail(f"DOCX unreadable or missing: {exc}")

    assert isinstance(text, str) and text.strip(), "DOCX extraction returned empty text"


def main() -> int:
    """Standalone runner so this script can be executed directly.

    Exit codes:
      0 - success
      2 - one or both files missing
      3 - missing dependencies or extraction error
      4 - unexpected exception
    """
    # Check files exist quickly by attempting extraction and interpreting exceptions
    try:
        pdf_text = pdf_to_text(PDF_PATH)
        print(f"PDF extracted {len(pdf_text)} chars; sample:\n{pdf_text[:400]!r}")
    except RuntimeError as exc:
        print(f"Missing dependency for PDF extraction: {exc}")
        return 3
    except ValueError as exc:
        print(f"PDF file missing or unreadable: {exc}")
        return 2
    except Exception as exc:
        print(f"Unexpected error extracting PDF: {exc}")
        return 4

    try:
        docx_text = docx_to_text(DOCX_PATH)
        print(f"DOCX extracted {len(docx_text)} chars; sample:\n{docx_text[:400]!r}")
    except RuntimeError as exc:
        print(f"Missing dependency for DOCX extraction: {exc}")
        return 3
    except ValueError as exc:
        print(f"DOCX file missing or unreadable: {exc}")
        return 2
    except Exception as exc:
        print(f"Unexpected error extracting DOCX: {exc}")
        return 4

    print("SUCCESS: both files extracted")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
        sys.exit(rc)
    except Exception as e:
        print("Unexpected error during test run:", repr(e))
        sys.exit(4)
