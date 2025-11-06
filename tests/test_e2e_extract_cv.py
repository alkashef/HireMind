"""E2E pipeline (5 steps): PDF/DOCX -> text -> fields -> doc embedding -> Weaviate -> readback.

Runs non-interactively, saving artifacts to tests/results (configurable via env).
Sections are no longer used; only document-level embeddings are computed and stored.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

# Ensure project root is on sys.path so local package imports (utils.*) work
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import AppLogger
from utils.extractors import pdf_to_text, docx_to_text, compute_sha256_bytes
from utils.openai_manager import OpenAIManager
from config.settings import AppConfig

DEFAULT_CV_NAME = "Ahmad Alkashef - Resume.pdf"

def _e2e_json_path() -> Path:
    """Resolve consolidated E2E JSON path from TEST_E2E_JSON or default 'tests/e2e.json'."""
    p = Path(os.getenv("TEST_E2E_JSON", "tests/e2e.json"))
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_payload(path: Path) -> Dict[str, Any]:
    if path.exists() and path.stat().st_size > 0:
        try:
            return json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _ordered_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict with keys ordered as required for E2E output.

    Order:
      id, sha, filename, timestamp, text, embeddings {model, vector}, attributes, ...others
    """
    out: Dict[str, Any] = {}
    # Top-level ordered keys
    for key in ("id", "sha", "filename", "timestamp", "text"):
        if key in payload:
            out[key] = payload[key]

    # Embeddings with sub-order model -> vector
    if "embeddings" in payload and isinstance(payload["embeddings"], dict):
        emb = payload["embeddings"]
        emb_out: Dict[str, Any] = {}
        if "model" in emb:
            emb_out["model"] = emb["model"]
        if "vector" in emb:
            emb_out["vector"] = emb["vector"]
        # Append any other keys in embeddings afterward
        for k, v in emb.items():
            if k not in emb_out:
                emb_out[k] = v
        out["embeddings"] = emb_out

    # Attributes
    if "attributes" in payload:
        out["attributes"] = payload["attributes"]

    # Any other keys go last (preserve their insertion order but skip ones already included)
    for k, v in payload.items():
        if k not in out:
            out[k] = v
    return out


def _write_payload(path: Path, payload: Dict[str, Any]) -> None:
    ordered = _ordered_payload(payload)
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")


def _e2e_read_json_path() -> Path:
    """Resolve E2E readback JSON path from TEST_E2E_JSON_READ or default 'tests/e2e_read.json'."""
    p = Path(os.getenv("TEST_E2E_JSON_READ", "tests/e2e_read.json"))
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_dotenv(dotenv_path: Optional[Path] = None) -> dict:
    if dotenv_path is None:
        dotenv_path = PROJECT_ROOT / "config" / ".env"
    loaded: dict[str, str] = {}
    if not dotenv_path.exists():
        return loaded
    with dotenv_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ[k] = v
            loaded[k] = v
    return loaded


def resolve_cv_paths(arg_path: Optional[str] = None) -> list[Path]:
    """Return a list of CV paths to process in order: [PDF?, DOCX?].

    Priority:
    - If arg_path provided and exists, use only that
    - Else include TEST_CV_PATH if it exists
    - Also include TEST_CV_DOCX_PATH if it exists
    - Else fallback to default sample PDF under tests/results
    """
    found: list[Path] = []
    def _norm(p: Path) -> Path:
        return (Path.cwd() / p).resolve() if not p.is_absolute() else p

    if arg_path:
        p = _norm(Path(arg_path))
        if p.exists():
            return [p]

    for key in ("TEST_CV_PATH", "TEST_CV_DOCX_PATH"):
        env_path = os.environ.get(key)
        if not env_path:
            continue
        p = _norm(Path(env_path))
        if p.exists():
            found.append(p)

    if found:
        # de-duplicate while preserving order
        uniq: list[Path] = []
        seen: set[str] = set()
        for p in found:
            s = str(p)
            if s not in seen:
                seen.add(s)
                uniq.append(p)
        return uniq

    sample_pdf = PROJECT_ROOT / "tests" / "data" / DEFAULT_CV_NAME
    if sample_pdf.exists():
        return [sample_pdf]
    return []


def init_logger() -> AppLogger:
    log_path = os.environ.get("LOG_FILE_PATH") or str(PROJECT_ROOT / "logs" / "test_runner.log")
    return AppLogger(log_path)


def step1_extract_pdf_to_json(logger: AppLogger, pdf_path: Path) -> Path:
    """Extract text from PDF or DOCX and write to E2E JSON.

    Note: Function name kept for compatibility with previous references.
    """
    logger.log_kv("STEP_START", step="extract_text", file=str(pdf_path))
    print("[1/5] Extracting document to text...")
    ext = pdf_path.suffix.lower()
    if ext == ".pdf":
        text = pdf_to_text(pdf_path)
    elif ext == ".docx":
        text = docx_to_text(pdf_path)
    else:
        raise RuntimeError(f"Unsupported file extension for extraction: {ext}")
    out_path = _e2e_json_path()
    payload = _read_payload(out_path)
    # Record identifiers early for downstream steps
    try:
        sha = compute_sha256_bytes(pdf_path.read_bytes())
    except Exception:
        sha = ""
    payload["sha"] = sha
    payload["filename"] = pdf_path.name
    # Timestamp of processing (local time)
    payload["timestamp"] = datetime.now().isoformat(timespec="seconds")
    payload["text"] = text
    _write_payload(out_path, payload)
    logger.log_kv("STEP_COMPLETE", step="extract_text", out=str(out_path), chars=len(text))
    print(f"UPDATED: {out_path} (text)")
    return out_path


def step2_openai_extract_fields(logger: AppLogger, pdf_path: Path) -> Path:
    logger.log_kv("STEP_START", step="openai_extract_fields", file=str(pdf_path))
    print("[2/5] OpenAI: extracting fields (single call)...")
    cfg = AppConfig()
    mgr = OpenAIManager(cfg, logger)
    data, err = mgr.extract_full_name(pdf_path)
    if err:
        logger.log_kv("ERROR", step="openai_extract_fields", error=err)
        raise RuntimeError(f"OpenAI extraction failed: {err}")
    out_path = _e2e_json_path()
    payload = _read_payload(out_path)
    # Store extracted attributes under 'attributes' instead of 'fields'
    payload["attributes"] = data or {}
    _write_payload(out_path, payload)
    logger.log_kv("STEP_COMPLETE", step="openai_extract_fields", out=str(out_path), keys=len((data or {}).keys()))
    print(f"UPDATED: {out_path} (fields)")
    return out_path


def step3_embed_doc(logger: AppLogger, e2e_json: Path) -> Path:
    logger.log_kv("STEP_START", step="embed_doc", src=str(e2e_json))
    print("[3/5] Computing OpenAI embeddings (document only)...")
    cfg = AppConfig()
    mgr = OpenAIManager(cfg, logger)
    payload = _read_payload(e2e_json)
    text_full: str = payload.get("text", "")
    doc_vecs, err0 = mgr.embed_texts([text_full])
    if err0:
        logger.log_kv("ERROR", step="embed_doc", error=err0)
        raise RuntimeError(f"Embeddings failed (doc): {err0}")
    doc_vector = doc_vecs[0] if doc_vecs else []
    model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    payload["embeddings"] = {"model": model, "vector": doc_vector}
    _write_payload(e2e_json, payload)
    logger.log_kv("STEP_COMPLETE", step="embed_doc", out=str(e2e_json))
    print(f"UPDATED: {e2e_json} (doc embeddings)")
    return e2e_json


def step4_write_to_weaviate(logger: AppLogger, pdf: Path, e2e_json: Path) -> Path:
    logger.log_kv("STEP_START", step="weaviate_write")
    print("[4/5] Writing CV to Weaviate (no sections)...")
    from store.weaviate_store import WeaviateStore

    # Load artifacts
    payload = _read_payload(e2e_json)
    doc_props: Dict[str, Any] = {}
    sha = payload.get("sha") or compute_sha256_bytes(pdf.read_bytes())
    filename = payload.get("filename", pdf.name)
    full_text = payload.get("text", "")

    # Attributes contains all scalar properties except sha/filename/full_text
    fields_or_attrs: Dict[str, Any] = payload.get("attributes", {}) or {}
    attrs = _map_fields_to_weaviate(fields_or_attrs)
    attrs.update({
        "timestamp": payload.get("timestamp", ""),
    })
    # Attach document-level vector when present
    try:
        doc_vector = (payload.get("embeddings", {}) or {}).get("vector")
        if doc_vector:
            attrs["_vector"] = doc_vector
    except Exception:
        pass

    # Write document
    ws = WeaviateStore()
    ws.ensure_schema()
    ws.cv.write(sha=sha, filename=filename, full_text=full_text, attributes=attrs)

    # Verify readback
    readback = ws.cv.read(sha)
    if not readback:
        logger.log_kv("ERROR", step="weaviate_empty_read", sha=sha)
        raise RuntimeError(f"Weaviate returned no document for sha={sha} after write")

    # Update consolidated JSON with a short Weaviate status
    payload["id"] = readback.get("id")
    payload["weaviate"] = {"ok": True, "sha": sha, "id": readback.get("id")}
    _write_payload(e2e_json, payload)
    logger.log_kv("STEP_COMPLETE", step="weaviate_write")
    print("Weaviate write complete.")
    return e2e_json


def _load_schema() -> Dict[str, Any]:
    cfg = AppConfig()
    schema_path = cfg.weaviate_schema_path
    if not schema_path:
        return {}
    p = Path(schema_path)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _collect_prop_types(schema: Dict[str, Any], class_name: str) -> Dict[str, str]:
    """Return map of property name -> type ('int'|'string'|'text')."""
    types: Dict[str, str] = {}
    try:
        cls = schema.get("classes", {}).get(class_name, {})
        for pr in cls.get("properties", []) or []:
            name = pr.get("name")
            dt = pr.get("dataType") or []
            if not name or not isinstance(dt, list) or not dt:
                continue
            t = dt[0]
            if t in ("int", "string", "text"):
                types[name] = t
    except Exception:
        pass
    return types


def _coerce_types(props: Dict[str, Any], types_map: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in props.items():
        t = types_map.get(k)
        if t == "int":
            if v in (None, "", "null"):
                out[k] = None
            else:
                try:
                    # accept numeric strings
                    out[k] = int(str(v).strip().split(".")[0])
                except Exception:
                    out[k] = None
        elif t in ("string", "text"):
            if v is None:
                out[k] = ""
            else:
                out[k] = str(v)
        else:
            out[k] = v
    return out


def _build_weaviate_payload(logger: AppLogger, e2e_json: Path) -> Path:
    # Deprecated: sections removed; payload building handled inline in step4
    return e2e_json


def _map_fields_to_weaviate(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Map OpenAI field names into Weaviate CVDocument property names."""
    m = {
        "first_name": "personal_first_name",
        "last_name": "personal_last_name",
        "full_name": "personal_full_name",
        "email": "personal_email",
        "phone": "personal_phone",
        "misspelling_count": "professional_misspelling_count",
        "misspelled_words": "professional_misspelled_words",
        "visual_cleanliness": "professional_visual_cleanliness",
        "professional_look": "professional_look",
        "formatting_consistency": "professional_formatting_consistency",
        "years_since_graduation": "experience_years_since_graduation",
        "total_years_experience": "experience_total_years",
        "employer_names": "experience_employer_names",
        "employers_count": "stability_employers_count",
        "avg_years_per_employer": "stability_avg_years_per_employer",
        "years_at_current_employer": "stability_years_at_current_employer",
        "address": "socio_address",
        "alma_mater": "socio_alma_mater",
        "high_school": "socio_high_school",
        "education_system": "socio_education_system",
        "second_foreign_language": "socio_second_foreign_language",
        "flag_stem_degree": "flag_stem_degree",
        "military_service_status": "flag_military_service_status",
        "worked_at_financial_institution": "flag_worked_at_financial_institution",
        "worked_for_egyptian_government": "flag_worked_for_egyptian_government",
    }
    out: Dict[str, Any] = {}
    for k, v in (attrs or {}).items():
        if k in m:
            out[m[k]] = v
    return out


def step5_read_from_weaviate(logger: AppLogger, e2e_json: Path) -> Path:
    logger.log_kv("STEP_START", step="weaviate_read")
    print("[5/5] Reading CV from Weaviate...")
    from store.weaviate_store import WeaviateStore

    payload = _read_payload(e2e_json)
    sha = payload.get("sha")
    if not sha:
        raise RuntimeError("Missing sha in E2E JSON; cannot read back from Weaviate")

    ws = WeaviateStore()
    doc = ws.cv.read(sha)
    if not doc:
        raise RuntimeError(f"No CVDocument found for sha={sha}")

    out = {
        "sha": sha,
        "document": doc,
        "checks": {"doc_ok": bool(doc.get("sha") == sha and doc.get("filename") == payload.get("filename"))},
    }

    out_path = _e2e_read_json_path()
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.log_kv("STEP_COMPLETE", step="weaviate_read", out=str(out_path))
    print(f"WROTE: {out_path}")
    return out_path


    # Legacy step removed; see step5_read_from_weaviate


def _interactive_choose_path() -> Optional[Path]:
    """Prompt the user to choose between configured PDF/DOCX paths or enter a custom path.

    Returns a resolved Path or None if selection failed.
    """
    def _norm(p: Optional[str]) -> Optional[Path]:
        if not p:
            return None
        q = Path(p)
        return (PROJECT_ROOT / q).resolve() if not q.is_absolute() else q

    cand: List[Tuple[str, Path]] = []
    pdf_env = os.environ.get("TEST_CV_PATH")
    docx_env = os.environ.get("TEST_CV_DOCX_PATH")
    pdf_p = _norm(pdf_env)
    docx_p = _norm(docx_env)
    if pdf_p and pdf_p.exists():
        cand.append(("PDF (TEST_CV_PATH)", pdf_p))
    if docx_p and docx_p.exists():
        cand.append(("DOCX (TEST_CV_DOCX_PATH)", docx_p))

    print("Select input CV file:")
    for i, (label, p) in enumerate(cand, start=1):
        print(f"  {i}) {label}: {p}")
    print(f"  {len(cand)+1}) Enter a custom absolute/relative path")

    try:
        choice = input(f"Enter choice [1-{len(cand)+1}]: ").strip()
        idx = int(choice or "1")
    except Exception:
        idx = 1

    if 1 <= idx <= len(cand):
        return cand[idx-1][1]

    # custom path
    path_in = input("Enter path to CV (.pdf or .docx): ").strip().strip('"')
    if not path_in:
        return None
    p = Path(path_in)
    p = (PROJECT_ROOT / p).resolve() if not p.is_absolute() else p
    return p if p.exists() else None


def _interactive_choose_last_step() -> int:
    """Prompt for the last step to run (always starts from 1). Returns 1..5."""
    steps = [
        "1) Extract text",
        "2) OpenAI: extract fields",
        "3) Compute document embedding",
        "4) Write to Weaviate",
        "5) Read back from Weaviate",
    ]
    print("\nSelect the last step to run (pipeline runs from step 1 up to your choice):")
    for s in steps:
        print("  " + s)
    try:
        val = int(input("Enter 1-5 [5]: ").strip() or "5")
        if 1 <= val <= 5:
            return val
    except Exception:
        pass
    return 5


def main(argv: list[str]) -> int:
    loaded = load_dotenv()
    logger = init_logger()
    logger.log_kv("ENV_LOADED", count=len(loaded))

    arg = argv[1] if len(argv) > 1 else None

    # Interactive mode when no path arg provided
    if not arg:
        sel = _interactive_choose_path()
        if not sel:
            msg = "No valid CV path selected. Aborting."
            logger.log_kv("ERROR", reason="no_cv_selected", message=msg)
            print(msg)
            return 2
        last_step = _interactive_choose_last_step()
        try:
            print(f"\n=== Running E2E pipeline for: {sel.name} (steps 1..{last_step}) ===")
            e2e_json = step1_extract_pdf_to_json(logger, sel)
            if last_step >= 2:
                e2e_json = step2_openai_extract_fields(logger, sel)
            if last_step >= 3:
                e2e_json = step3_embed_doc(logger, e2e_json)
            if last_step >= 4:
                e2e_json = step4_write_to_weaviate(logger, sel, e2e_json)
            if last_step >= 5:
                _ = step5_read_from_weaviate(logger, e2e_json)
        except Exception as exc:
            logger.log_kv("ERROR", step="e2e_pipeline", file=str(sel), exc=str(exc))
            print(f"E2E failed for {sel.name}: {exc}")
            return 5
        print("E2E pipeline completed successfully.")
        return 0

    # Non-interactive: behave like before (resolve by env + optional arg)
    cv_list = resolve_cv_paths(arg)
    if not cv_list:
        msg = f"No CV found. Provide a path as an argument or place '{DEFAULT_CV_NAME}' under tests/results/"
        logger.log_kv("ERROR", reason="no_cv", message=msg)
        print(msg)
        return 2

    overall_ok = True
    for idx, cv in enumerate(cv_list, start=1):
        try:
            print(f"\n=== Running E2E pipeline for file {idx}/{len(cv_list)}: {cv.name} ===")
            e2e_json = step1_extract_pdf_to_json(logger, cv)
            e2e_json = step2_openai_extract_fields(logger, cv)
            e2e_json = step3_embed_doc(logger, e2e_json)
            e2e_json = step4_write_to_weaviate(logger, cv, e2e_json)
            _ = step5_read_from_weaviate(logger, e2e_json)
        except Exception as exc:
            overall_ok = False
            logger.log_kv("ERROR", step="e2e_pipeline", file=str(cv), exc=str(exc))
            print(f"E2E failed for {cv.name}: {exc}")

    if not overall_ok:
        return 5

    print("E2E pipeline completed successfully for all inputs.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))