"""E2E pipeline for Roles (PDF/DOCX -> text -> fields -> document embedding -> Weaviate -> readback).

Runs non-interactively and writes artifacts to tests/results (configurable via env).
- Accepts both PDF and DOCX role files.
- Sends text-only to OpenAI (no attachments).
- Computes an embedding for the whole role document (no sections).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import AppLogger
from utils.extractors import pdf_to_text, docx_to_text, compute_sha256_bytes
from utils.openai_manager import OpenAIManager
from config.settings import AppConfig

DEFAULT_ROLE_NAME = "Sample Role.pdf"


def _insert_tag_into_filename(base: Path, tag: str) -> Path:
    """Insert a tag before the .json extension or append if no extension.

    examples:
      tests/role_e2e.json + pdf -> tests/role_e2e_pdf.json
      tests/out.json + jd1_docx -> tests/out_jd1_docx.json
      tests/out + tag -> tests/out_tag
    """
    stem = base.stem
    suffix = base.suffix
    if suffix.lower() == ".json":
        return base.with_name(f"{stem}_{tag}{suffix}")
    return base.with_name(f"{stem}_{tag}{suffix}")


def _role_e2e_json_path(tag: str) -> Path:
    base = Path(os.getenv("TEST_ROLE_E2E_JSON", "tests/role_e2e.json"))
    if not base.is_absolute():
        base = (PROJECT_ROOT / base).resolve()
    out = _insert_tag_into_filename(base, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _role_e2e_read_json_path(tag: str) -> Path:
    base = Path(os.getenv("TEST_ROLE_E2E_JSON_READ", "tests/role_e2e_read.json"))
    if not base.is_absolute():
        base = (PROJECT_ROOT / base).resolve()
    out = _insert_tag_into_filename(base, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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


def resolve_role_paths(arg_path: Optional[str] = None) -> List[Path]:
    """Return a list of role paths (PDF then DOCX if both exist)."""
    found: List[Path] = []
    def _norm(p: Path) -> Path:
        return (Path.cwd() / p).resolve() if not p.is_absolute() else p

    if arg_path:
        p = _norm(Path(arg_path))
        if p.exists():
            return [p]

    for key in ("TEST_ROLE_PATH", "TEST_ROLE_DOCX_PATH"):
        env_path = os.environ.get(key)
        if not env_path:
            continue
        p = _norm(Path(env_path))
        if p.exists():
            found.append(p)
    if found:
        uniq: List[Path] = []
        seen: set[str] = set()
        for p in found:
            s = str(p)
            if s not in seen:
                seen.add(s)
                uniq.append(p)
        return uniq

    sample = PROJECT_ROOT / "tests" / "data" / DEFAULT_ROLE_NAME
    return [sample] if sample.exists() else []


def init_logger() -> AppLogger:
    log_path = os.environ.get("LOG_FILE_PATH") or str(PROJECT_ROOT / "logs" / "test_role_e2e.log")
    return AppLogger(log_path)


# Steps

def step1_extract_text(logger: AppLogger, path: Path, tag: str) -> Path:
    ext = path.suffix.lower()
    logger.log_kv("ROLE_STEP_START", step="extract_text", file=str(path))
    print("[1/5] Extracting role to text...")
    if ext == ".pdf":
        text = pdf_to_text(path)
    elif ext == ".docx":
        text = docx_to_text(path)
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    out = _role_e2e_json_path(tag)
    payload = _read_json(out)
    payload["filename"] = path.name
    payload["sha"] = compute_sha256_bytes(path.read_bytes())
    payload["text"] = text
    _write_json(out, payload)
    logger.log_kv("ROLE_STEP_DONE", step="extract_text", out=str(out), chars=len(text))
    print(f"UPDATED: {out} (text)")
    return out


def step2_openai_fields(logger: AppLogger, role_path: Path, tag: str) -> Path:
    logger.log_kv("ROLE_STEP_START", step="openai_extract_fields", file=str(role_path))
    print("[2/5] OpenAI: extracting role fields (single call)...")
    cfg = AppConfig()
    mgr = OpenAIManager(cfg, logger)
    data, err = mgr.extract_role_fields(role_path)
    if err:
        logger.log_kv("ROLE_OPENAI_ERROR", error=err)
        raise RuntimeError(f"OpenAI extraction failed: {err}")
    out = _role_e2e_json_path(tag)
    payload = _read_json(out)
    # Store role attributes under 'attributes' (not 'fields')
    payload["attributes"] = data or {}
    _write_json(out, payload)
    logger.log_kv("ROLE_STEP_DONE", step="openai_extract_fields", keys=len((data or {}).keys()))
    print(f"UPDATED: {out} (attributes)")
    return out


def step3_embeddings_doc(logger: AppLogger, e2e_json: Path) -> Path:
    logger.log_kv("ROLE_STEP_START", step="embed_doc", src=str(e2e_json))
    print("[3/5] Computing embeddings (document only)...")
    cfg = AppConfig()
    mgr = OpenAIManager(cfg, logger)
    payload = _read_json(e2e_json)
    text = payload.get("text", "")
    doc_vecs, err0 = mgr.embed_texts([text])
    if err0:
        raise RuntimeError(f"Embeddings (doc) failed: {err0}")
    doc_vector = doc_vecs[0] if doc_vecs else []
    model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    payload["embeddings"] = {"model": model, "vector": doc_vector}
    _write_json(e2e_json, payload)
    logger.log_kv("ROLE_STEP_DONE", step="embed_doc")
    print(f"UPDATED: {e2e_json} (doc embeddings)")
    return e2e_json


def step4_write_weaviate(logger: AppLogger, role_path: Path, e2e_json: Path) -> Path:
    logger.log_kv("ROLE_STEP_START", step="weaviate_write")
    print("[4/5] Writing role to Weaviate (no sections)...")
    os.environ.setdefault("SKIP_WEAVIATE_VECTORIZER_CHECK", "1")
    from store.weaviate_store import WeaviateStore
    ws = WeaviateStore()
    ws.ensure_schema()

    payload = _read_json(e2e_json)
    sha = payload.get("sha") or compute_sha256_bytes(role_path.read_bytes())
    filename = payload.get("filename", role_path.name)
    text = payload.get("text", "")
    attributes: Dict[str, Any] = payload.get("attributes", {}) or {}
    doc_vector: List[float] = (payload.get("embeddings", {}) or {}).get("vector", []) or []

    attrs = {
        "timestamp": os.getenv("ROLE_TIMESTAMP") or "",
        "role_title": attributes.get("job_title") or Path(filename).stem,
        "_vector": doc_vector if doc_vector else None,
        # Extended attributes mapped 1:1 from fields
        "job_title": attributes.get("job_title"),
        "employer": attributes.get("employer"),
        "job_location": attributes.get("job_location"),
        "language_requirement": attributes.get("language_requirement"),
        "onsite_requirement_percentage": attributes.get("onsite_requirement_percentage"),
        "onsite_requirement_mandatory": attributes.get("onsite_requirement_mandatory"),
        "serves_government": attributes.get("serves_government"),
        "serves_financial_institution": attributes.get("serves_financial_institution"),
        "min_years_experience": attributes.get("min_years_experience"),
        "must_have_skills": attributes.get("must_have_skills"),
        "should_have_skills": attributes.get("should_have_skills"),
        "nice_to_have_skills": attributes.get("nice_to_have_skills"),
        "min_must_have_degree": attributes.get("min_must_have_degree"),
        "preferred_universities": attributes.get("preferred_universities"),
        "responsibilities": attributes.get("responsibilities"),
        "technical_qualifications": attributes.get("technical_qualifications"),
        "non_technical_qualifications": attributes.get("non_technical_qualifications"),
    }
    doc_res = ws.roles.write(sha, filename, text, attrs)
    # Normalize id from write response
    doc_id = (doc_res.get("id") if isinstance(doc_res, dict) else doc_res)
    # Rebuild payload in the exact requested order and structure
    model = (payload.get("embeddings", {}) or {}).get("model")
    vector = doc_vector
    ordered = {
        "id": doc_id,
        "sha": sha,
        "filename": filename,
        "text": text,
        "embeddings": {
            "model": model,
            "vector": vector,
        },
        "attributes": attributes,
    }
    _write_json(e2e_json, ordered)
    logger.log_kv("ROLE_STEP_DONE", step="weaviate_write")
    return e2e_json


def step5_readback(logger: AppLogger, e2e_json: Path, tag: str) -> Path:
    logger.log_kv("ROLE_STEP_START", step="weaviate_read")
    print("[5/5] Reading role from Weaviate...")
    from store.weaviate_store import WeaviateStore

    payload = _read_json(e2e_json)
    sha = payload.get("sha")
    ws = WeaviateStore()
    doc = ws.roles.read(sha)
    out = {
        "sha": sha,
        "document": doc,
        "checks": {"doc_ok": bool(doc and doc.get("sha") == sha)},
    }
    out_path = _role_e2e_read_json_path(tag)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.log_kv("ROLE_STEP_DONE", step="weaviate_read", count=len(secs))
    print(f"WROTE: {out_path}")
    return out_path


def tag_from_path(p: Path) -> str:
    ext = p.suffix.lower().lstrip('.') or 'txt'
    stem = p.stem.replace(' ', '_')
    return f"{stem}_{ext}"


def main(argv: List[str]) -> int:
    _ = load_dotenv()
    logger = init_logger()
    arg = argv[1] if len(argv) > 1 else None
    paths = resolve_role_paths(arg)
    if not paths:
        print("No role file found. Set TEST_ROLE_PATH/TEST_ROLE_DOCX_PATH in config/.env or provide a path argument.")
        return 2

    overall_ok = True
    for idx, rp in enumerate(paths, start=1):
        try:
            print(f"\n=== Running role E2E for {rp.name} ({idx}/{len(paths)}) ===")
            tag = tag_from_path(rp)
            e2e = step1_extract_text(logger, rp, tag)
            e2e = step2_openai_fields(logger, rp, tag)
            e2e = step3_embeddings_doc(logger, e2e)
            e2e = step4_write_weaviate(logger, rp, e2e)
            _ = step5_readback(logger, e2e, tag)
        except Exception as exc:
            overall_ok = False
            logger.log_kv("ROLE_E2E_ERROR", file=str(rp), error=str(exc))
            print(f"Role E2E failed for {rp.name}: {exc}")

    if not overall_ok:
        return 5
    print("Role E2E pipeline completed successfully for all inputs.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
