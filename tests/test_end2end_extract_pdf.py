"""CLI-style test: simulate selecting a PDF CV and extracting text.

This test runs in a pure-CLI style (no browser). Steps:
1. Create a temporary PDF (using PyMuPDF if available).
2. Call the `pdf_to_text` extractor.
3. Print the extracted text to stdout (so running the test with `-s` shows it).
4. Do a simple assertion that known marker text is present.

The test will skip cleanly if PyMuPDF (`fitz`) is not installed on the test machine.
"""

from __future__ import annotations
import os
import re
import sys
from pathlib import Path
import pytest

# Make sure project root is on sys.path so `import utils` works when running tests directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_CV_NAME = "Ahmad Alkashef - Resume.pdf"


def _ensure_openai_env_or_fail() -> None:
    """Ensure OpenAI env and SSL vars are present and valid; fail tests if not.

    Behavior change: tests should not be skipped. If the environment is not
    correctly configured for live OpenAI calls, this helper will call
    pytest.fail(...) with a clear message so failures are explicit.

    Checks performed:
    - OPENAI_API_KEY must be present either in process env or in `config/.env`.
    - For SSL vars (SSL_CERT_FILE, REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE) the
      helper will accept values from process env or `config/.env` and will
      fail if any such var is set but the referenced file does not exist.
    """
    # 1) Find OPENAI_API_KEY in process env or config/.env
    key = os.environ.get("OPENAI_API_KEY")
    config_vals: dict[str, str] = {}
    try:
        dotenv_path = Path(__file__).resolve().parents[1] / "config" / ".env"
        if dotenv_path.exists():
            with dotenv_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    config_vals[k.strip()] = v.strip().strip('"').strip("'")
            if not key:
                key = config_vals.get("OPENAI_API_KEY")
    except Exception:
        # best-effort only; fall through to fail below if not found
        pass

    if not key:
        pytest.fail("OPENAI_API_KEY not found in process environment or config/.env; tests that call OpenAI must provide this key.")

    # 2) Validate SSL cert env vars: accept values from process env or config/.env
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        val = os.environ.get(var) or config_vals.get(var)
        if val:
            p = Path(val)
            if not p.exists():
                pytest.fail(f"{var} is set to '{val}' (env or config/.env) but the file does not exist; fix or unset this variable before running tests.")


def resolve_cv_path(arg_path: str | None = None) -> Path | None:
    """Resolve the CV path to use for extraction.

    Resolution order:
    1. If arg_path is provided and exists, use it.
    2. If environment variable TEST_CV_PATH is set and exists, use it.
    3. If a file exists at tests/data/<DEFAULT_CV_NAME>, use that.
    4. If none found, return None.
    """
    # 1: explicit arg (may be relative or absolute)
    if arg_path:
        p = Path(arg_path)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if p.exists():
            return p

    # 2: environment variable from the running env
    env_path = os.environ.get("TEST_CV_PATH")
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if p.exists():
            return p

    # 2b: load variables from project config/.env (if present) and respect TEST_CV_PATH there
    try:
        project_root = Path(__file__).resolve().parents[1]
        dotenv_path = project_root / "config" / ".env"
        if dotenv_path.exists():
            with dotenv_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    if "=" not in s:
                        continue
                    key, val = s.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "TEST_CV_PATH" and val:
                        p = Path(val)
                        if not p.is_absolute():
                            p = (project_root / p).resolve()
                        if p.exists():
                            return p
    except Exception:
        # best-effort: don't fail if .env can't be read
        pass

    # 3: tests/data default file name
    sample_pdf = Path(__file__).resolve().parents[0] / "data" / DEFAULT_CV_NAME
    if sample_pdf.exists():
        return sample_pdf

    return None


def test_cli_extract_pdf_simulation():
    """Extract raw text from a sample PDF and write it under the "text" key to the JSON output <FILE_NAME>."""

    pdf = resolve_cv_path()
    if pdf is None:
        pytest.fail(f"No sample PDF found; place '{DEFAULT_CV_NAME}' under tests/data/ or set TEST_CV_PATH to a file path.")

    from utils.extractors import pdf_to_text

    extracted = pdf_to_text(pdf)
    # Save extracted text to the single JSON file defined by TEST_CV_JSON_OUTPUT
    json_out = os.environ.get("TEST_CV_JSON_OUTPUT")
    if not json_out:
        # also try to load from config/.env (conftest should have already loaded it)
        pytest.fail("TEST_CV_JSON_OUTPUT not set in environment or config/.env; tests must write to a single JSON output path")

    out_path = Path(json_out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parents[1] / out_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"text": extracted}, indent=2, ensure_ascii=False))

    # Basic sanity check: ensure extraction returned non-empty text and file was written
    assert isinstance(extracted, str) and len(extracted.strip()) > 0
    assert out_path.exists() and out_path.stat().st_size > 0


def test_extract_save_json_sections():
    """Split the extracted text into granular sections and merge them into the same JSON file under "sections"."""
    pdf = resolve_cv_path()
    if pdf is None:
        pytest.fail("No sample PDF found; cannot run extraction/json save test")

    from utils.extractors import pdf_to_text
    import json as _json

    extracted = pdf_to_text(pdf)
    # Split into sections by page breaks (form-feed) or two+ consecutive newlines
    # This makes sections more granular: new section on page break or paragraph gap.
    parts = re.split(r"(?:\f+|\n{2,})", extracted)
    sections = [s.strip() for s in parts if s and s.strip()]

    # Resolve output JSON path: require TEST_CV_JSON_OUTPUT env so all tests use one file
    json_out = os.environ.get("TEST_CV_JSON_OUTPUT")
    if not json_out:
        pytest.fail("TEST_CV_JSON_OUTPUT not set in environment or config/.env; tests must write to a single JSON output path")
    out_path = Path(json_out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parents[1] / out_path

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing JSON (created by the raw-extract test) and merge sections
    existing: dict = {}
    if out_path.exists():
        try:
            with out_path.open("r", encoding="utf-8") as fh:
                existing = _json.load(fh) or {}
        except Exception:
            existing = {}

    existing["sections"] = sections

    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(_json.dumps(existing, indent=2, ensure_ascii=False))

    print(f"WROTE JSON: {out_path}")
    # quick assertion: JSON file exists and is non-empty
    assert out_path.exists() and out_path.stat().st_size > 0


def test_openai_extract_and_append_json():
    """Run local Hermes-Pro extraction and append the structured result under "hermes_extraction" in the same JSON file."""
    pdf = resolve_cv_path()
    if pdf is None:
        pytest.fail("No sample PDF found; cannot run Hermes extraction test")

    # Look for JSON produced by the extraction step (require TEST_CV_JSON_OUTPUT)
    json_out = os.environ.get("TEST_CV_JSON_OUTPUT")
    if not json_out:
        pytest.fail("TEST_CV_JSON_OUTPUT not set in environment or config/.env; run the extraction test first to create the JSON file")
    json_path = Path(json_out)
    if not json_path.is_absolute():
        json_path = Path(__file__).resolve().parents[1] / json_path
    if not json_path.exists():
        pytest.fail(f"Prerequisite JSON missing: {json_path}. Run extraction/json save test first.")

    # Load extracted text from JSON
    import json
    with json_path.open("r", encoding="utf-8") as fh:
        try:
            existing = json.load(fh)
        except Exception:
            existing = {}
    cv_text = existing.get("text", "")
    if not cv_text:
        pytest.fail("No 'text' found in canonical JSON for Hermes extraction.")

    # Cleanup any leftover CSV produced by earlier runs to avoid confusion
    try:
        csv_candidate = Path(__file__).resolve().parents[0] / "data" / f"{pdf.stem}.csv"
        if csv_candidate.exists():
            csv_candidate.unlink()
    except Exception:
        # non-fatal cleanup failure
        pass

    # Load Hermes client
    from config.settings import AppConfig
    from utils.logger import AppLogger
    from utils.hermes_client import HermesClient
    cfg = AppConfig()
    logger = AppLogger(cfg.log_file_path)
    hermes = HermesClient(model_dir="models/hermes-pro", quantize_4bit=True, cfg=cfg)

    # Define extraction prompts and output keys
    # Use canonical prompt for all extraction keys to avoid deprecated/sample content
    # Request one field per generation call using a concise prompt that asks
    # just for the requested field value. This prevents the model from
    # returning/echoing the entire schema or prompt text.
    extraction_tasks = [
        ("extract_field_user.md", "full_name"),
        ("extract_field_user.md", "first_name"),
        ("extract_field_user.md", "last_name"),
        ("extract_field_user.md", "email"),
        ("extract_field_user.md", "phone"),
        ("extract_field_user.md", "address"),
        ("extract_field_user.md", "alma_mater"),
    ]
    hermes_extraction = {}
    for prompt_file, key in extraction_tasks:
        try:
            result = hermes.generate_from_prompt_file(prompt_file, prompt_vars={"cv": cv_text}, max_new_tokens=64)
            hermes_extraction[key] = result.strip()
        except Exception as exc:
            hermes_extraction[key] = f"ERROR: {exc}"

    existing["hermes_extraction"] = hermes_extraction

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2, ensure_ascii=False)

    print(f"Appended Hermes extraction to: {json_path}")
    # sanity: ensure file exists and is non-empty
    assert json_path.exists() and json_path.stat().st_size > 0


def test_paraphrase_vectorize_and_append_json():
    """Run a local paraphrase model to produce embeddings for the extracted sections/text and append them to the JSON file under "paraphrase_embeddings"."""
    # Resolve JSON output path
    json_out = os.environ.get("TEST_CV_JSON_OUTPUT")
    if not json_out:
        pytest.fail("TEST_CV_JSON_OUTPUT not set in environment or config/.env; tests must write/read the canonical JSON output path")

    out_p = Path(json_out)
    if not out_p.is_absolute():
        out_p = Path(__file__).resolve().parents[1] / out_p

    if not out_p.exists():
        pytest.fail(f"Prerequisite JSON missing: {out_p}. Run extraction tests first to create the canonical JSON file.")

    # Load existing JSON
    import json as _json

    try:
        with out_p.open("r", encoding="utf-8") as fh:
            existing = _json.load(fh) or {}
    except Exception as exc:
        pytest.fail(f"Failed to read existing JSON at {out_p}: {exc}")

    # Prefer sections if present, otherwise fall back to text
    texts = []
    if isinstance(existing.get("sections"), list) and existing.get("sections"):
        texts = existing.get("sections")
    elif isinstance(existing.get("text"), str) and existing.get("text").strip():
        texts = [existing.get("text")]
    else:
        pytest.fail("No 'sections' or 'text' found in canonical JSON to vectorize.")

    # Limit the number of items to embed to keep test fast; user can extend locally
    MAX_EMBED = int(os.environ.get("TEST_PARAPHRASE_MAX", "16"))
    texts = texts[:MAX_EMBED]

    # Import the sentence-transformers encoder
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        pytest.fail("sentence-transformers package not available; install 'sentence-transformers' to run paraphrase vectorization tests")

    # Prefer local model in repo if available
    model_dir = Path(__file__).resolve().parents[1] / "models" / "paraphrase-MiniLM-L12-v2"
    try:
        if model_dir.exists():
            model = SentenceTransformer(str(model_dir))
        else:
            # fallback to model name (may attempt to download)
            model = SentenceTransformer("paraphrase-MiniLM-L12-v2")
    except Exception as exc:
        pytest.fail(f"Failed to load paraphrase model: {exc}")

    try:
        embeddings = model.encode(texts, convert_to_numpy=True)
    except Exception as exc:
        pytest.fail(f"Failed to compute embeddings: {exc}")

    # Normalize to plain Python lists for JSON serialization
    try:
        emb_list = [e.tolist() for e in embeddings]
    except Exception:
        # If embeddings is a single vector (1-D), wrap accordingly
        try:
            emb_list = [embeddings.tolist()]
        except Exception as exc:
            pytest.fail(f"Failed to serialize embeddings: {exc}")

    # Attach to JSON under 'paraphrase_embeddings'
    existing["paraphrase_embeddings"] = [
        {"text": t, "embedding": v} for t, v in zip(texts, emb_list)
    ]

    try:
        with out_p.open("w", encoding="utf-8") as fh:
            fh.write(_json.dumps(existing, indent=2, ensure_ascii=False))
    except Exception as exc:
        pytest.fail(f"Failed to write updated JSON with embeddings: {exc}")

    # Quick sanity checks
    assert out_p.exists() and out_p.stat().st_size > 0
    assert "paraphrase_embeddings" in existing and isinstance(existing["paraphrase_embeddings"], list)


def test_write_json_to_weaviate_and_dump_csv():
    """Write the canonical JSON produced by previous tests to Weaviate, then
    read it back and write a CSV file with columns: Attribute | Data Type | Value.

    The CSV output path is taken from TEST_CV_CSV_OUTPUT (env or config/.env).
    This test is best-effort: it will fail if Weaviate is not configured/accessible
    to make failures explicit to the test runner.
    """
    # Resolve JSON output path
    json_out = os.environ.get("TEST_CV_JSON_OUTPUT")
    if not json_out:
        pytest.fail("TEST_CV_JSON_OUTPUT not set in environment or config/.env; cannot run Weaviate write/read test")

    json_path = Path(json_out)
    if not json_path.is_absolute():
        json_path = Path(__file__).resolve().parents[1] / json_path
    if not json_path.exists():
        pytest.fail(f"Prerequisite JSON missing: {json_path}. Run earlier extraction tests first.")

    import json as _json

    try:
        with json_path.open("r", encoding="utf-8") as fh:
            payload = _json.load(fh) or {}
    except Exception as exc:
        pytest.fail(f"Failed to read canonical JSON at {json_path}: {exc}")

    # Resolve CV file and compute sha (weaviate keys use file content sha)
    pdf = resolve_cv_path()
    if pdf is None:
        pytest.fail("No sample PDF found; cannot compute sha to write to Weaviate")

    from utils.extractors import compute_sha256_bytes
    try:
        sha = compute_sha256_bytes(pdf.read_bytes())
    except Exception as exc:
        pytest.fail(f"Failed to compute SHA for CV file {pdf}: {exc}")

    # Prepare Weaviate store and write the document
    try:
        from utils.weaviate_store import WeaviateStore
    except Exception as exc:
        pytest.fail(f"Weaviate integration not available: {exc}")

    ws = WeaviateStore()
    # Ensure schema exists (will raise if client not configured)
    try:
        ws.ensure_schema()
    except Exception as exc:
        pytest.fail(f"Failed to ensure Weaviate schema or connect to Weaviate: {exc}")

    # Use the extracted JSON as attributes where sensible; also store the
    # full JSON dump in the 'cv' property so no data is lost.
    attrs = dict(payload) if isinstance(payload, dict) else {"payload": payload}
    # store full json string under 'cv' so it is queryable as text
    try:
        attrs["cv"] = _json.dumps(payload, ensure_ascii=False)
    except Exception:
        attrs["cv"] = str(payload)

    try:
        res = ws.write_cv_to_db(sha=sha, filename=pdf.name, full_text=payload.get("text", ""), attributes=attrs)
    except Exception as exc:
        pytest.fail(f"Failed to write CV to Weaviate: {exc}")

    # Read back from Weaviate
    try:
        readback = ws.read_cv_from_db(sha)
    except Exception as exc:
        pytest.fail(f"Failed to read CV from Weaviate after write: {exc}")

    if not readback:
        pytest.fail(f"Weaviate returned no document for sha={sha} after write")

    # Prepare CSV rows: include top-level id/sha/filename + attributes and full_text
    rows = []
    # helper to determine data type string
    def dtype(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        if isinstance(v, (list, tuple)):
            return "list"
        if isinstance(v, dict):
            return "dict"
        return "string"

    # top-level metadata
    rows.append(("id", dtype(readback.get("id")), readback.get("id")))
    rows.append(("sha", dtype(readback.get("sha")), readback.get("sha")))
    rows.append(("filename", dtype(readback.get("filename")), readback.get("filename")))

    # attributes dict
    attrs = readback.get("attributes", {}) or {}
    for k, v in sorted(attrs.items()):
        val = v
        if isinstance(v, (dict, list)):
            try:
                val = _json.dumps(v, ensure_ascii=False)
            except Exception:
                val = str(v)
        rows.append((k, dtype(v), val))

    # full text
    rows.append(("full_text", dtype(readback.get("full_text")), readback.get("full_text")))

    # Resolve CSV output path from env or config/.env
    csv_out = os.environ.get("TEST_CV_CSV_OUTPUT")
    if not csv_out:
        # try config/.env
        try:
            project_root = Path(__file__).resolve().parents[1]
            dotenv_path = project_root / "config" / ".env"
            if dotenv_path.exists():
                with dotenv_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        s = line.strip()
                        if not s or s.startswith("#") or "=" not in s:
                            continue
                        k, v = s.split("=", 1)
                        if k.strip() == "TEST_CV_CSV_OUTPUT":
                            csv_out = v.strip().strip('"').strip("'")
                            break
        except Exception:
            csv_out = None

    if not csv_out:
        # CSV output not configured for this environment; skip CSV write instead
        pytest.skip("TEST_CV_CSV_OUTPUT not set in environment or config/.env; skipping CSV write")

    csv_path = Path(csv_out)
    if not csv_path.is_absolute():
        csv_path = Path(__file__).resolve().parents[1] / csv_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Write CSV with pipe separator and header
    try:
        with csv_path.open("w", encoding="utf-8") as fh:
            fh.write("Attribute|Data Type|Value\n")
            for a, t, v in rows:
                line = f"{a}|{t}|{(v if v is not None else '')}\n"
                fh.write(line)
    except Exception as exc:
        pytest.fail(f"Failed to write CSV to {csv_path}: {exc}")

    print(f"WROTE WEAVIATE CSV: {csv_path}")
    assert csv_path.exists() and csv_path.stat().st_size > 0


if __name__ == "__main__":
    # Allow running the test file directly: accept optional path arg
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    pdf = resolve_cv_path(arg)
    if pdf is None:
        print(f"No CV found. Provide a path as an argument or place '{DEFAULT_CV_NAME}' under tests/data/")
        raise SystemExit(2)

    try:
        from utils.extractors import pdf_to_text
    except Exception as exc:
        print(f"Failed to import extractor: {exc}")
        raise SystemExit(3)

    try:
        text = pdf_to_text(pdf)
        print("EXTRACTED_TEXT:\n", text)
    except Exception as exc:
        print(f"Extraction failed: {exc}")
        raise SystemExit(4)


