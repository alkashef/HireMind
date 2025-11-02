"""E2E pipeline (6 steps): PDF -> text -> fields -> sections -> embeddings -> Weaviate -> readback.

Redesigned to run non-interactively in 6 clear steps, saving artifacts to JSON
files under tests/data (configurable via env). Uses only utils/* modules.

Steps
1) Extract PDF to text and save to JSON
2) Call OpenAI via utils.openai_manager to extract fields JSON (single call)
3) Slice text into titled sections using utils.slice.slice_sections, save JSON
4) Compute OpenAI embeddings for each section, save embeddings JSON
5) Write document and sections to Weaviate (server-side vectors)
6) Read back document and sections from Weaviate and write a separate verification JSON
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# Ensure project root is on sys.path so local package imports (utils.*) work
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import AppLogger
from utils.extractors import pdf_to_text, docx_to_text, compute_sha256_bytes
from utils.slice import slice_sections
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


def _write_payload(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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
    - Else fallback to default sample PDF under tests/data
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
    print("[1/6] Extracting document to text...")
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
    payload["text"] = text
    _write_payload(out_path, payload)
    logger.log_kv("STEP_COMPLETE", step="extract_text", out=str(out_path), chars=len(text))
    print(f"UPDATED: {out_path} (text)")
    return out_path


def step2_openai_extract_fields(logger: AppLogger, pdf_path: Path) -> Path:
    logger.log_kv("STEP_START", step="openai_extract_fields", file=str(pdf_path))
    print("[2/6] OpenAI: extracting fields (single call)...")
    cfg = AppConfig()
    mgr = OpenAIManager(cfg, logger)
    data, err = mgr.extract_full_name(pdf_path)
    if err:
        logger.log_kv("ERROR", step="openai_extract_fields", error=err)
        raise RuntimeError(f"OpenAI extraction failed: {err}")
    out_path = _e2e_json_path()
    payload = _read_payload(out_path)
    payload["fields"] = data or {}
    _write_payload(out_path, payload)
    logger.log_kv("STEP_COMPLETE", step="openai_extract_fields", out=str(out_path), keys=len((data or {}).keys()))
    print(f"UPDATED: {out_path} (fields)")
    return out_path


def step3_slice_sections(logger: AppLogger, e2e_json: Path) -> Path:
    logger.log_kv("STEP_START", step="slice_sections", src=str(e2e_json))
    print("[3/6] Slicing text into titled sections...")
    payload = _read_payload(e2e_json)
    text = payload.get("text", "")
    sec_map = slice_sections(text)
    payload["sections"] = sec_map
    _write_payload(e2e_json, payload)
    logger.log_kv("STEP_COMPLETE", step="slice_sections", out=str(e2e_json), count=len(sec_map))
    print(f"UPDATED: {e2e_json} (sections)")
    return e2e_json


def step4_embed_sections(logger: AppLogger, e2e_json: Path) -> Path:
    logger.log_kv("STEP_START", step="embed_sections", src=str(e2e_json))
    print("[4/6] Computing OpenAI embeddings (doc + sections)...")
    cfg = AppConfig()
    mgr = OpenAIManager(cfg, logger)
    payload = _read_payload(e2e_json)
    text_full: str = payload.get("text", "")
    sec_map: Dict[str, str] = payload.get("sections", {}) or {}
    titles: List[str] = list(sec_map.keys())
    texts: List[str] = [sec_map[t] for t in titles]
    # document embedding
    doc_vecs, err0 = mgr.embed_texts([text_full])
    if err0:
        logger.log_kv("ERROR", step="embed_doc", error=err0)
        raise RuntimeError(f"Embeddings failed (doc): {err0}")
    doc_vector = doc_vecs[0] if doc_vecs else []
    # section embeddings
    vectors, err = mgr.embed_texts(texts)
    if err:
        logger.log_kv("ERROR", step="embed_sections", error=err)
        raise RuntimeError(f"Embeddings failed (sections): {err}")
    model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    emb_map = {title: (vectors[i] if i < len(vectors) else []) for i, title in enumerate(titles)}
    payload["embeddings"] = {"model": model, "doc_vector": doc_vector, "embeddings": emb_map}
    _write_payload(e2e_json, payload)
    logger.log_kv("STEP_COMPLETE", step="embed_sections", out=str(e2e_json), count=len(emb_map))
    print(f"UPDATED: {e2e_json} (embeddings)")
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
    """Derive weaviate-ready document and sections from consolidated payload.

    Writes keys:
    - weaviate_document: dict matching CVDocument properties
    - weaviate_sections: list of dicts matching CVSection properties
    """
    payload = _read_payload(e2e_json)
    schema = _load_schema()
    types_map = _collect_prop_types(schema, "CVDocument")

    sha = payload.get("sha", "")
    filename = payload.get("filename", "")
    text = payload.get("text", "")
    fields: Dict[str, Any] = payload.get("fields", {}) or {}

    # Map AI fields -> CVDocument property names
    mapped = _map_fields_to_weaviate(fields)
    mapped.update({
        "sha": sha,
        "timestamp": payload.get("timestamp", ""),
        "cv": json.dumps({"fields": fields, "has_embeddings": bool(payload.get("embeddings"))}, ensure_ascii=False),
        "filename": filename,
        "full_text": text,
    })
    mapped = _coerce_types(mapped, types_map)

    # Sections
    sections_map: Dict[str, str] = payload.get("sections", {}) or {}
    sections_list = [
        {"parent_sha": sha, "section_type": title, "section_text": content}
        for title, content in sections_map.items()
    ]

    payload["weaviate_document"] = mapped
    payload["weaviate_sections"] = sections_list
    _write_payload(e2e_json, payload)
    logger.log_kv("WEAVIATE_PAYLOAD_BUILT", doc_keys=len(mapped), sections=len(sections_list))
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


def step5_write_to_weaviate(logger: AppLogger, pdf: Path, e2e_json: Path) -> Path:
    logger.log_kv("STEP_START", step="weaviate_write")
    print("[5/6] Writing document and sections to Weaviate...")
    from utils.weaviate_store import WeaviateStore

    # Load artifacts
    # Ensure weaviate payload exists and is up-to-date
    _build_weaviate_payload(logger, e2e_json)
    payload = _read_payload(e2e_json)
    raw = payload
    doc_props: Dict[str, Any] = payload.get("weaviate_document", {}) or {}
    sections_list: List[Dict[str, Any]] = payload.get("weaviate_sections", []) or []
    # Map section titles to vectors (if available)
    sec_vecs: Dict[str, List[float]] = {}
    try:
        e = payload.get("embeddings", {}) or {}
        sec_vecs = e.get("embeddings", {}) or {}
    except Exception:
        sec_vecs = {}

    # Compute sha and initialize client
    sha = payload.get("sha") or compute_sha256_bytes(pdf.read_bytes())
    # We don't require server vectorizers; use client-provided vectors
    os.environ.setdefault("SKIP_WEAVIATE_VECTORIZER_CHECK", "1")
    ws = WeaviateStore()
    ws.ensure_schema()

    # Upsert document
    # Split props into known fields for write_cv_to_db: it expects attributes + full_text separately
    full_text = doc_props.pop("full_text", raw.get("text", ""))
    filename = doc_props.pop("filename", pdf.name)
    # Attributes contains all scalar properties except sha/filename/full_text
    attrs = {k: v for k, v in doc_props.items() if k not in ("sha",)}
    # Attach document-level vector when present
    try:
        doc_vector = (raw.get("embeddings", {}) or {}).get("doc_vector")
        if doc_vector:
            attrs["_vector"] = doc_vector
    except Exception:
        pass
    ws.write_cv_to_db(sha=sha, filename=filename, full_text=full_text, attributes=attrs)

    # Upsert sections (server-side vectorization)
    ok = True
    for sec in sections_list:
        title = sec.get("section_type", "section")
        vec = sec_vecs.get(title)
        up = ws.upsert_cv_section(
            parent_sha=sec.get("parent_sha", sha),
            section_type=title,
            section_text=sec.get("section_text", ""),
            vector=vec,
        )
        ok = ok and bool(up.get("weaviate_ok"))

    # Verify readback
    readback = ws.read_cv_from_db(sha)
    if not readback:
        logger.log_kv("ERROR", step="weaviate_empty_read", sha=sha)
        raise RuntimeError(f"Weaviate returned no document for sha={sha} after write")

    # Update consolidated JSON with a short Weaviate status
    payload["weaviate"] = {"ok": True, "sha": sha, "id": readback.get("id")}
    _write_payload(e2e_json, payload)

    # Optional CSV dump path (kept for compatibility)
    csv_out = os.environ.get("TEST_CV_CSV_OUTPUT")
    if csv_out:
        csv_path = Path(csv_out)
        if not csv_path.is_absolute():
            csv_path = PROJECT_ROOT / csv_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
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
        rows.append(("id", dtype(readback.get("id")), readback.get("id")))
        rows.append(("sha", dtype(readback.get("sha")), readback.get("sha")))
        rows.append(("filename", dtype(readback.get("filename")), readback.get("filename")))
        attrs_rb = readback.get("attributes", {}) or {}
        for k, v in sorted(attrs_rb.items()):
            val = v
            if isinstance(v, (dict, list)):
                try:
                    val = json.dumps(v, ensure_ascii=False)
                except Exception:
                    val = str(v)
            rows.append((k, dtype(v), val))
        rows.append(("full_text", dtype(readback.get("full_text")), readback.get("full_text")))
        with csv_path.open("w", encoding="utf-8") as fh:
            fh.write("Attribute|Data Type|Value\n")
            for a, t, v in rows:
                line = f"{a}|{t}|{(v if v is not None else '')}\n"
                fh.write(line)
        logger.log_kv("STEP_COMPLETE", step="weaviate_write", csv=str(csv_path), sections=len(sections_list), ok=ok)
        print(f"WROTE WEAVIATE CSV: {csv_path}")
        return csv_path

    logger.log_kv("STEP_COMPLETE", step="weaviate_write", sections=len(sections_list), ok=ok)
    print("Weaviate write complete (CSV dump skipped).")
    # return a log file path placeholder to keep signature
    return Path(os.getenv("LOG_FILE_PATH", str(PROJECT_ROOT / "logs" / "weaviate_write.log")))


def step6_read_from_weaviate(logger: AppLogger, e2e_json: Path) -> Path:
    logger.log_kv("STEP_START", step="weaviate_read")
    print("[6/6] Reading CV and sections from Weaviate...")
    from utils.weaviate_store import WeaviateStore

    payload = _read_payload(e2e_json)
    sha = payload.get("sha")
    if not sha:
        raise RuntimeError("Missing sha in E2E JSON; cannot read back from Weaviate")

    ws = WeaviateStore()
    doc = ws.read_cv_from_db(sha)
    if not doc:
        raise RuntimeError(f"No CVDocument found for sha={sha}")
    sections = ws.read_cv_sections(sha)

    # Build simple checks against previous JSON
    expected_sections = payload.get("weaviate_sections")
    if not expected_sections:
        # fallback to titles from sliced sections
        expected_sections = [
            {"parent_sha": sha, "section_type": t, "section_text": s}
            for t, s in (payload.get("sections", {}) or {}).items()
        ]
    expected_count = len(expected_sections)
    doc_ok = (doc.get("sha") == sha) and (doc.get("filename") == payload.get("filename"))
    sections_count_ok = (len(sections) == expected_count)

    out = {
        "sha": sha,
        "document": doc,
        "sections": sections,
        "checks": {
            "doc_ok": bool(doc_ok),
            "sections_count_ok": bool(sections_count_ok),
            "expected_sections": expected_count,
            "actual_sections": len(sections),
        },
    }

    out_path = _e2e_read_json_path()
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.log_kv("STEP_COMPLETE", step="weaviate_read", out=str(out_path), doc_ok=doc_ok, count=len(sections))
    print(f"WROTE: {out_path}")
    return out_path


def main(argv: list[str]) -> int:
    loaded = load_dotenv()
    logger = init_logger()
    logger.log_kv("ENV_LOADED", count=len(loaded))

    arg = argv[1] if len(argv) > 1 else None
    cv_list = resolve_cv_paths(arg)
    if not cv_list:
        msg = f"No CV found. Provide a path as an argument or place '{DEFAULT_CV_NAME}' under tests/data/"
        logger.log_kv("ERROR", reason="no_cv", message=msg)
        print(msg)
        return 2

    overall_ok = True
    for idx, cv in enumerate(cv_list, start=1):
        try:
            print(f"\n=== Running E2E pipeline for file {idx}/{len(cv_list)}: {cv.name} ===")
            e2e_json = step1_extract_pdf_to_json(logger, cv)
            e2e_json = step2_openai_extract_fields(logger, cv)
            e2e_json = step3_slice_sections(logger, e2e_json)
            e2e_json = step4_embed_sections(logger, e2e_json)
            _ = step5_write_to_weaviate(logger, cv, e2e_json)
            _ = step6_read_from_weaviate(logger, e2e_json)
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