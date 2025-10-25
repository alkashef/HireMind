"""File and text extraction utilities.

Provides lightweight helpers used by the extraction pipeline:
- pdf_to_text(path: Path) -> str
- docx_to_text(path: Path) -> str
- compute_sha256_bytes(data: bytes) -> str

These functions are intentionally small and deterministic. They do not
call external services. When a required library is missing or a file is
unreadable a clear exception is raised.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union
import hashlib
import logging

logger = logging.getLogger(__name__)


def compute_sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest for the given bytes.

    The result is a stable 64-character lowercase hex string used as an
    identifier (IDs in the project are SHA-256 content hashes).
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("compute_sha256_bytes expects bytes-like input")
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def pdf_to_text(path: Union[str, Path]) -> str:
    """Extract text from a PDF using PyMuPDF (fitz).

    Preserves page breaks by separating pages with two newlines. If the
    file cannot be read or the PyMuPDF library is not installed a ValueError
    is raised with a clear message.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"PDF file not found: {p}")

    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        logger.exception("PyMuPDF import failed")
        raise RuntimeError("PyMuPDF is required for pdf_to_text; install with 'pip install pymupdf'") from exc

    try:
        doc = fitz.open(p.as_posix())
    except Exception as exc:
        logger.warning("Unable to open PDF %s: %s", p, exc)
        raise ValueError(f"Unable to read PDF file: {p}") from exc

    pages = []
    try:
        for page in doc:
            # use 'text' extractor to get plain text preserving simple layout
            text = page.get_text("text")
            if text:
                pages.append(text.rstrip())
    finally:
        try:
            doc.close()
        except Exception:
            pass

    content = "\n\n".join(pages).strip()
    if not content:
        raise ValueError(f"PDF contained no extractable text: {p}")
    return content


def docx_to_text(path: Union[str, Path]) -> str:
    """Extract text from a .docx file using python-docx.

    Paragraphs are preserved and separated by two newlines. Raises
    ValueError on unreadable files and RuntimeError when the optional
    dependency is missing.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"DOCX file not found: {p}")

    try:
        from docx import Document
    except Exception as exc:
        logger.exception("python-docx import failed")
        raise RuntimeError("python-docx is required for docx_to_text; install with 'pip install python-docx'") from exc

    try:
        doc = Document(p.as_posix())
    except Exception as exc:
        logger.warning("Unable to open DOCX %s: %s", p, exc)
        raise ValueError(f"Unable to read DOCX file: {p}") from exc

    paragraphs = [para.text.strip() for para in doc.paragraphs if para.text and para.text.strip()]
    content = "\n\n".join(paragraphs).strip()
    if not content:
        raise ValueError(f"DOCX contained no extractable text: {p}")
    return content


__all__ = ["compute_sha256_bytes", "pdf_to_text", "docx_to_text"]
