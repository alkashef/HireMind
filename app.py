from __future__ import annotations

import os
import threading
from datetime import datetime
import hashlib
from pathlib import Path
from typing import List
import json

from flask import Flask, jsonify, render_template, request

from config.settings import AppConfig
from utils.logger import AppLogger
from utils.openai_manager import OpenAIManager
from utils.csv_manager import CSVStore, RolesStore


app = Flask(__name__)

# Centralized config and logger
config = AppConfig()
logger = AppLogger(config.log_file_path)
openai_mgr = OpenAIManager(config, logger)
csv_store = CSVStore(config, logger)
roles_store = RolesStore(config, logger)

# In-memory extraction progress (per-process state)
EXTRACT_PROGRESS: dict = {"active": False, "total": 0, "done": 0, "start": None}
ROLES_EXTRACT_PROGRESS: dict = {"active": False, "total": 0, "done": 0, "start": None}


def log(message: str) -> None:
        """Log a simple message to the application log file.

        This is a thin convenience wrapper around the project-wide ``AppLogger``
        instance configured in this module. Use this for short, human-readable
        event messages that don't need structured key/value fields.

        Parameters
        - message: Short text message to append to the log file. The logger will
            prefix the message with a timestamp.
        """
        logger.log(message)


def log_kv(event: str, **fields: object) -> None:
        """Log a structured event with key/value pairs.

        The event name is a short identifier (e.g. "EXTRACT_POST_DONE") and
        additional keyword arguments are formatted by the logger into a single
        line. This is meant for machine-readable telemetry stored alongside
        human messages in the same log file.

        Parameters
        - event: Short event name
        - **fields: Arbitrary key/value pairs that will be rendered as
            ``k=v`` tokens in the log line.
        """
        logger.log_kv(event, **fields)


# Log once when the app handles the first request (Flask 3.x safe)
@app.before_request
def _app_ready() -> None:
    """Mark the Flask app as ready once and emit a startup log event.

    This handler runs before the first request and logs a single ``APP_READY``
    event. It stores a process-local flag in ``app.config`` to avoid
    repeated logs across subsequent requests.
    """
    if not app.config.get("_APP_READY_LOGGED"):
        log("APP_READY")
        app.config["_APP_READY_LOGGED"] = True


def get_default_folder() -> str:
    """Return the configured default folder for applicant documents.

    The value is read from `AppConfig().default_folder` which falls back to
    the user's home directory when not explicitly set via environment.
    """
    return config.default_folder

def get_roles_default_folder() -> str:
    """Return the configured default folder for role documents.

    Falls back to the configured applicants folder when a separate roles
    folder is not set.
    """
    return config.roles_folder


def get_data_path() -> Path:
    """Return the project's data directory as a :class:`pathlib.Path`.

    This convenience function delegates to ``AppConfig.data_path`` which
    ensures the directory exists before returning it.
    """
    return config.data_path


def list_docs(folder: str) -> List[str]:
    """Return a sorted list of document file paths for a folder.

    Only files with extensions in the allowed set (currently ``.pdf`` and
    ``.docx``) are returned. The function ignores subdirectories and
    non-file entries.

    Parameters
    - folder: Path to search (string); may be absolute or relative.

    Returns
    - Sorted list of matching file paths as strings.
    """
    exts = {".pdf", ".docx"}
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        return []
    paths = [str(fp) for fp in p.iterdir() if fp.is_file() and fp.suffix.lower() in exts]
    return sorted(paths)

def list_role_docs(folder: str) -> List[str]:
    """List role documents in `folder`.

    This is a thin alias around :func:`list_docs` but exists for clarity in
    the roles-related routes and to allow future divergence if role file
    handling requires special casing.
    """
    return list_docs(folder)


def sha256_file(path: Path) -> str:
    """Compute the lowercase hex SHA-256 digest of a file's bytes.

    Parameters
    - path: :class:`pathlib.Path` pointing to an existing file.

    Returns
    - 64-character lowercase hex string representing SHA-256(file_bytes).

    Notes
    - The function reads the file in 1MB chunks to avoid using excessive
      memory for large files.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_max_file_mb() -> int:
    """Return maximum allowed file size in megabytes from config."""
    return config.max_file_mb


def get_openai_model() -> str:
    """Return the configured OpenAI model identifier from AppConfig.

    This is a convenience wrapper used by parts of the app that need the
    model name without importing AppConfig directly.
    """
    return config.openai_model

# OpenAI integration has been moved to utils/openai_manager.OpenAIManager


# --- Routes -----------------------------------------------------------------


@app.route("/")
def index():
    log("INDEX_VIEW")
    return render_template("index.html")


@app.route("/api/default-folder")
def api_default_folder():
    folder = get_default_folder()
    # Log with updated env naming for clarity
    log_kv("APPLICANTS_FOLDER", folder=folder)
    return jsonify({"folder": folder})


@app.route("/api/list-files")
def api_list_files():
    folder = get_default_folder()
    files = list_docs(folder)
    log_kv("LIST_FILES", folder=folder, count=len(files))
    return jsonify({"folder": folder, "files": files})

@app.route("/api/roles/default-folder")
def api_roles_default_folder():
    folder = get_roles_default_folder()
    log_kv("ROLES_FOLDER", folder=folder)
    return jsonify({"folder": folder})

@app.route("/api/roles/list-files")
def api_roles_list_files():
    folder = get_roles_default_folder()
    files = list_role_docs(folder)
    log_kv("ROLES_LIST_FILES", folder=folder, count=len(files))
    return jsonify({"folder": folder, "files": files})


@app.route("/api/pick-folder")
def api_pick_folder():
    """Open a Windows folder browser dialog and return selected path.

    Uses tkinter.filedialog.askdirectory in a separate thread to avoid blocking
    the main server thread.
    """
    selected: dict = {"path": None}

    def _pick():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(title="Select a folder")
            root.destroy()
            selected["path"] = path or None
        except Exception as e:
            selected["error"] = str(e)

    t = threading.Thread(target=_pick)
    t.start()
    t.join()

    if selected.get("error"):
        log_kv("FOLDER_PICK_ERROR", error=selected['error'])
        return jsonify({"error": selected["error"]}), 500

    path = selected.get("path")
    if not path:
        log("FOLDER_PICK_CANCELED")
        return jsonify({"folder": None, "files": []})

    # Update APPLICANTS_FOLDER for current process only
    os.environ["APPLICANTS_FOLDER"] = path
    files = list_docs(path)
    log_kv("FOLDER_PICKED", path=path, count=len(files))
    return jsonify({"folder": path, "files": files})

@app.route("/api/roles/pick-folder")
def api_roles_pick_folder():
    """Open a Windows folder browser dialog for Roles repository and return selected path."""
    selected: dict = {"path": None}

    def _pick():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(title="Select a roles folder")
            root.destroy()
            selected["path"] = path or None
        except Exception as e:
            selected["error"] = str(e)

    t = threading.Thread(target=_pick)
    t.start()
    t.join()

    if selected.get("error"):
        log_kv("ROLES_FOLDER_PICK_ERROR", error=selected['error'])
        return jsonify({"error": selected["error"]}), 500

    path = selected.get("path")
    if not path:
        log("ROLES_FOLDER_PICK_CANCELED")
        return jsonify({"folder": None, "files": []})

    # Update ROLES_FOLDER for current process only
    os.environ["ROLES_FOLDER"] = path
    files = list_role_docs(path)
    log_kv("ROLES_FOLDER_PICKED", path=path, count=len(files))
    return jsonify({"folder": path, "files": files})


@app.route("/api/roles/extract", methods=["POST", "GET"])
def api_roles_extract():
    """Persist selected role files to CSV under data/roles.csv.

    Body: { "files": ["C:/path/file1.pdf", ...] }
    Columns: ID (sha256), Timestamp, Filename, RoleTitle (parsed from filename by default)
    """
    try:
        if request.method == "GET":
            rows = roles_store.get_public_rows()
            log_kv("ROLES_EXTRACT_GET", rows=len(rows))
            return jsonify({"rows": rows})

        payload = request.get_json(silent=True) or {}
        files = payload.get("files") or []

        saved = 0
        stamp = datetime.now().isoformat()
        log_kv("ROLES_EXTRACT_POST_START", files=len(files), csv=str(roles_store.csv_path))
        ROLES_EXTRACT_PROGRESS.update({
            "active": True,
            "total": len(files),
            "done": 0,
            "start": datetime.now().timestamp(),
        })

        index_by_id: dict[str, dict] = roles_store.read_index()
        updated_by_id: dict[str, dict] = dict(index_by_id)
        errors: list[str] = []

        for fp in files:
            p = Path(fp)
            try:
                if not p.exists() or not p.is_file():
                    errors.append(f"Not found or not a file: {p}")
                    log_kv("ROLES_EXTRACT_SKIP_NOTFOUND", path=str(p))
                    continue
                rid = sha256_file(p)
                filename = p.name
                # Default role title: filename without extension
                role_title = p.stem

                if rid in updated_by_id:
                    log_kv("ROLES_EXTRACT_SKIP_ALREADY_DONE", id=rid, file=filename)
                    continue

                row = {
                    "ID": rid,
                    "Timestamp": stamp,
                    "Filename": filename,
                    "RoleTitle": role_title,
                }
                if rid not in updated_by_id:
                    saved += 1
                    log_kv("ROLES_EXTRACT_ROW_NEW", id=rid, file=filename)
                updated_by_id[rid] = row
            except Exception as e:
                errors.append(f"General error [{p.name}]: {e}")
                log_kv("ROLES_EXTRACT_FILE_ERROR", name=p.name, error=e)
            finally:
                try:
                    ROLES_EXTRACT_PROGRESS["done"] = min(
                        int(ROLES_EXTRACT_PROGRESS.get("done", 0)) + 1,
                        int(ROLES_EXTRACT_PROGRESS.get("total", 0))
                    )
                except Exception:
                    pass

        roles_store.write_rows(updated_by_id)
        ROLES_EXTRACT_PROGRESS.update({"active": False})
        log_kv("ROLES_EXTRACT_POST_DONE", saved=saved, errors=len(errors), csv=str(roles_store.csv_path), total_rows=len(updated_by_id))
        return jsonify({"saved": saved, "csv": str(roles_store.csv_path), "errors": errors})
    except Exception as e:
        log(f"Roles extract error: {e}")
        ROLES_EXTRACT_PROGRESS.update({"active": False})
        return jsonify({"error": str(e)}), 500


@app.route("/api/roles/extract/progress")
def api_roles_extract_progress():
    try:
        return jsonify({
            "active": bool(ROLES_EXTRACT_PROGRESS.get("active", False)),
            "total": int(ROLES_EXTRACT_PROGRESS.get("total", 0)),
            "done": int(ROLES_EXTRACT_PROGRESS.get("done", 0)),
            "start": ROLES_EXTRACT_PROGRESS.get("start"),
        })
    except Exception as e:
        log_kv("ROLES_EXTRACT_PROGRESS_ERROR", error=e)
        return jsonify({"active": False, "total": 0, "done": 0, "start": None})


@app.route("/api/hashes", methods=["POST"])
def api_hashes():
    """Compute content hashes and report duplicates for a list of files.

    Body: { "files": ["C:/path/file1.pdf", ...] }
    Returns: {
        duplicates: ["path1", ...],                 # later occurrences only (back-compat)
        duplicates_all: ["path1", ...],             # all members of duplicate groups (including originals)
        duplicate_count: N                           # count of duplicates_all
    }
    """
    try:
        payload = request.get_json(silent=True) or {}
        files = payload.get("files") or []
        seen: dict[str, str] = {}
        dups: list[str] = []  # later duplicates only
        groups: dict[str, list[str]] = {}
        for fp in files:
            p = Path(fp)
            if not p.exists() or not p.is_file():
                continue
            h = sha256_file(p)
            if h in seen:
                dups.append(fp)
            else:
                seen[h] = fp
            groups.setdefault(h, []).append(fp)

        # Build full set of duplicates (include originals) for any hash with >= 2 files
        dup_all: list[str] = []
        for paths in groups.values():
            if len(paths) >= 2:
                dup_all.extend(paths)

        log_kv("HASHES_DONE", files=len(files), duplicates=len(dup_all))
        return jsonify({
            "duplicates": dups,
            "duplicates_all": dup_all,
            "duplicate_count": len(dup_all)
        })
    except Exception as e:
        log_kv("HASHES_ERROR", error=e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/extract", methods=["POST", "GET"])
def api_extract():
    """Persist selected file metadata to CSV under data/applicants.csv.

    Body: { "files": ["C:/path/file1.pdf", ...] }
    Writes/updates rows with columns: ID, Timestamp, CV, FullName
    """
    try:
        # Serve rows
        if request.method == "GET":
            rows = csv_store.get_public_rows()
            log_kv("EXTRACT_GET", rows=len(rows))
            return jsonify({"rows": rows})

    # Append/update rows for all selected files
        payload = request.get_json(silent=True) or {}
        files = payload.get("files") or []

        is_new = not csv_store.csv_path.exists()
        saved = 0
        stamp = datetime.now().isoformat()
        log_kv("EXTRACT_POST_START", files=len(files), csv=str(csv_store.csv_path))
        # Initialize progress
        EXTRACT_PROGRESS.update({
            "active": True,
            "total": len(files),
            "done": 0,
            "start": datetime.now().timestamp(),
        })

        # Load existing rows by ID (content hash)
        index_by_id: dict[str, dict] = csv_store.read_index()

        errors: list[str] = []
        max_bytes = get_max_file_mb() * 1024 * 1024
        openai_failed_once = False
        updated_by_id: dict[str, dict] = dict(index_by_id)

        for fp in files:
            p = Path(fp)
            try:
                if not p.exists() or not p.is_file():
                    errors.append(f"Not found or not a file: {p}")
                    log_kv("EXTRACT_FILE_SKIP_NOTFOUND", path=str(p))
                    continue
                size = p.stat().st_size
                if size > max_bytes:
                    mb = get_max_file_mb()
                    errors.append(f"File exceeds {mb}MB: {p.name}")
                    log_kv("EXTRACT_FILE_SKIP_OVERSIZE", name=p.name, size=size, max_mb=mb)
                    continue

                rid = sha256_file(p)
                cv_name = p.name
                log_kv("EXTRACT_FILE_HASHED", name=cv_name, id=rid)

                # Skip re-extraction if this content hash already exists
                if rid in updated_by_id:
                    log_kv("EXTRACT_SKIP_ALREADY_DONE", id=rid, cv=cv_name)
                    continue

                # Default extracted fields (empty)
                extracted = {}
                if not openai_failed_once:
                    data, err = openai_mgr.extract_full_name(p)
                    if err:
                        errors.append(f"OpenAI error [{p.name}]: {err}")
                        log_kv("OPENAI_ERROR", name=p.name, error=err)
                        openai_failed_once = True
                    else:
                        extracted = data or {}
                        log_kv("OPENAI_OK", name=p.name, keys=len(extracted))

                # Map extracted public keys -> CSV file columns with defaults
                def val(k: str) -> str:
                    v = extracted.get(k, "")
                    # Normalize lists to comma-separated strings if any
                    if isinstance(v, list):
                        return ", ".join(str(x) for x in v)
                    return str(v)

                row = {
                    "ID": rid,
                    "Timestamp": stamp,
                    "CV": cv_name,
                    "Filename": cv_name,
                    # Personal Information
                    "PersonalInformation_FirstName": val("first_name"),
                    "PersonalInformation_LastName": val("last_name"),
                    "PersonalInformation_FullName": val("full_name"),
                    "PersonalInformation_Email": val("email"),
                    "PersonalInformation_Phone": val("phone"),
                    # Professionalism
                    "Professionalism_MisspellingCount": val("misspelling_count"),
                    "Professionalism_MisspelledWords": val("misspelled_words"),
                    "Professionalism_VisualCleanliness": val("visual_cleanliness"),
                    "Professionalism_ProfessionalLook": val("professional_look"),
                    "Professionalism_FormattingConsistency": val("formatting_consistency"),
                    # Experience
                    "Experience_YearsSinceGraduation": val("years_since_graduation"),
                    "Experience_TotalYearsExperience": val("total_years_experience"),
                    "Experience_EmployerNames": val("employer_names"),
                    # Stability
                    "Stability_EmployersCount": val("employers_count"),
                    "Stability_AvgYearsPerEmployer": val("avg_years_per_employer"),
                    "Stability_YearsAtCurrentEmployer": val("years_at_current_employer"),
                    # Socioeconomic
                    "SocioeconomicStandard_Address": val("address"),
                    "SocioeconomicStandard_AlmaMater": val("alma_mater"),
                    "SocioeconomicStandard_HighSchool": val("high_school"),
                    "SocioeconomicStandard_EducationSystem": val("education_system"),
                    "SocioeconomicStandard_SecondForeignLanguage": val("second_foreign_language"),
                    # Flags
                    "Flags_FlagSTEMDegree": val("flag_stem_degree"),
                    "Flags_MilitaryServiceStatus": val("military_service_status"),
                    "Flags_WorkedAtFinancialInstitution": val("worked_at_financial_institution"),
                    "Flags_WorkedForEgyptianGovernment": val("worked_for_egyptian_government"),
                }
                if rid not in updated_by_id:
                    saved += 1
                    log_kv("EXTRACT_ROW_NEW", id=rid, cv=cv_name)
                else:
                    log_kv("EXTRACT_ROW_UPDATE", id=rid, cv=cv_name)
                updated_by_id[rid] = row
            except Exception as e:
                errors.append(f"General error [{p.name}]: {e}")
                log_kv("EXTRACT_FILE_ERROR", name=p.name, error=e)
            finally:
                # Count this file as processed for progress (even if skipped or errored)
                try:
                    EXTRACT_PROGRESS["done"] = min(
                        int(EXTRACT_PROGRESS.get("done", 0)) + 1,
                        int(EXTRACT_PROGRESS.get("total", 0))
                    )
                except Exception:
                    pass

        # Write back file (header + rows)
        csv_store.write_rows(updated_by_id)

        EXTRACT_PROGRESS.update({"active": False})
        log_kv("EXTRACT_POST_DONE", saved=saved, errors=len(errors), csv=str(csv_store.csv_path), total_rows=len(updated_by_id))
        return jsonify({"saved": saved, "csv": str(csv_store.csv_path), "errors": errors})
    except Exception as e:
        log(f"Extract error: {e}")
        EXTRACT_PROGRESS.update({"active": False})
        return jsonify({"error": str(e)}), 500

@app.route("/api/applicants/pipeline", methods=["POST"])
def api_applicants_pipeline():
    """Run the 7-step pipeline for a single selected CV and return artifacts.

    Body: { "file": "C:/path/file.pdf" }
    Returns: { sha, filename, fields, sections, embeddings_model, weaviate: { ok, id }, readback: { document, sections } }
    """
    payload = request.get_json(silent=True) or {}
    fpath = payload.get("file")
    if not fpath:
        return jsonify({"error": "file is required"}), 400
    p = Path(fpath)
    if not p.exists() or not p.is_file():
        return jsonify({"error": "file not found"}), 404

    # Step 1: extract text and sha
    log_kv("PIPELINE_STEP", step="1/6", action="extract_text")
    text = ''
    sha = sha256_file(p)
    try:
        from utils.extractors import pdf_to_text
        text = pdf_to_text(p)
    except Exception as e:
        return jsonify({"error": f"pdf extract failed: {e}"}), 500

    # Step 2: OpenAI extract fields
    log_kv("PIPELINE_STEP", step="2/6", action="openai_extract_fields")
    fields, err = openai_mgr.extract_full_name(p)
    if err:
        return jsonify({"error": f"openai extract failed: {err}"}), 500

    # Step 3: slice sections
    log_kv("PIPELINE_STEP", step="3/6", action="slice_sections")
    from utils.slice import slice_sections
    sections_map = slice_sections(text)

    # Step 4: embeddings for sections
    log_kv("PIPELINE_STEP", step="4/6", action="openai_embeddings")
    titles = list(sections_map.keys())
    texts = [sections_map[t] for t in titles]
    vectors, err2 = openai_mgr.embed_texts(texts)
    if err2:
        return jsonify({"error": f"embeddings failed: {err2}"}), 500
    emb_model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"

    # Step 5 & 6: write to Weaviate using vectors and then read back
    log_kv("PIPELINE_STEP", step="5/6", action="write_weaviate")
    os.environ.setdefault("SKIP_WEAVIATE_VECTORIZER_CHECK", "1")
    from utils.weaviate_store import WeaviateStore
    ws = WeaviateStore()
    ws.ensure_schema()

    # Map fields into CVDocument attributes expected by write_cv_to_db
    def fget(k: str) -> str:
        v = (fields or {}).get(k)
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return '' if v is None else str(v)
    attrs = {
        "timestamp": datetime.now().isoformat(),
        "cv": p.name,
        "personal_first_name": fget("first_name"),
        "personal_last_name": fget("last_name"),
        "personal_full_name": fget("full_name"),
        "personal_email": fget("email"),
        "personal_phone": fget("phone"),
        "professional_misspelling_count": int(fields.get("misspelling_count")) if str(fields.get("misspelling_count", "")).isdigit() else None,
        "professional_misspelled_words": fget("misspelled_words"),
        "professional_visual_cleanliness": fget("visual_cleanliness"),
        "professional_look": fget("professional_look"),
        "professional_formatting_consistency": fget("formatting_consistency"),
        "experience_years_since_graduation": int(fields.get("years_since_graduation")) if str(fields.get("years_since_graduation", "")).isdigit() else None,
        "experience_total_years": int(fields.get("total_years_experience")) if str(fields.get("total_years_experience", "")).isdigit() else None,
        "experience_employer_names": fget("employer_names"),
        "stability_employers_count": int(fields.get("employers_count")) if str(fields.get("employers_count", "")).isdigit() else None,
        "stability_avg_years_per_employer": fget("avg_years_per_employer"),
        "stability_years_at_current_employer": fget("years_at_current_employer"),
        "socio_address": fget("address"),
        "socio_alma_mater": fget("alma_mater"),
        "socio_high_school": fget("high_school"),
        "socio_education_system": fget("education_system"),
        "socio_second_foreign_language": fget("second_foreign_language"),
        "flag_stem_degree": fget("flag_stem_degree"),
        "flag_military_service_status": fget("military_service_status"),
        "flag_worked_at_financial_institution": fget("worked_at_financial_institution"),
        "flag_worked_for_egyptian_government": fget("worked_for_egyptian_government"),
    }
    doc_res = ws.write_cv_to_db(sha, p.name, text, attrs)

    # Upsert sections with vectors
    for idx, title in enumerate(titles):
        sec_text = sections_map[title]
        vec = vectors[idx] if vectors and idx < len(vectors) else None
        ws.upsert_cv_section(sha, title, sec_text, vector=vec)

    # Readback
    log_kv("PIPELINE_STEP", step="6/6", action="readback_weaviate")
    doc = ws.read_cv_from_db(sha)
    secs = ws.read_cv_sections(sha)

    log_kv("PIPELINE_COMPLETE", sha=sha, filename=p.name)
    return jsonify({
        "sha": sha,
        "filename": p.name,
        "fields": fields or {},
        "sections": sections_map,
        "embeddings_model": emb_model,
        "weaviate": {"ok": True, "id": (doc_res or {}).get("id")},
        "readback": {"document": doc, "sections": secs},
    })


@app.route("/api/extract/progress")
def api_extract_progress():
    """Return current extraction progress.

    Shape: { active: bool, total: int, done: int, start: float|null }
    """
    try:
        return jsonify({
            "active": bool(EXTRACT_PROGRESS.get("active", False)),
            "total": int(EXTRACT_PROGRESS.get("total", 0)),
            "done": int(EXTRACT_PROGRESS.get("done", 0)),
            "start": EXTRACT_PROGRESS.get("start"),
        })
    except Exception as e:
        log_kv("EXTRACT_PROGRESS_ERROR", error=e)
        return jsonify({"active": False, "total": 0, "done": 0, "start": None})


@app.route("/api/weaviate/cv/<sha>")
def api_weaviate_cv_read(sha: str):
    """Read-only endpoint to fetch CV document by sha from Weaviate (safe)."""
    try:
        from utils.weaviate_store import WeaviateStore
        ws = WeaviateStore()
        if not ws.client:
            return jsonify({"error": "Weaviate not configured"}), 503
        obj = ws.read_cv_from_db(sha)
        if not obj:
            return jsonify({"error": "Not found"}), 404
        return jsonify(obj)
    except Exception as e:
        log_kv("WEAVIATE_CV_READ_ERROR", error=str(e), sha=sha)
        return jsonify({"error": str(e)}), 500

@app.route("/api/weaviate/cv_all/<sha>")
def api_weaviate_cv_all(sha: str):
    """Return document and sections for a CV by sha."""
    try:
        from utils.weaviate_store import WeaviateStore
        ws = WeaviateStore()
        if not ws.client:
            return jsonify({"error": "Weaviate not configured"}), 503
        doc = ws.read_cv_from_db(sha)
        if not doc:
            return jsonify({"error": "Not found"}), 404
        secs = ws.read_cv_sections(sha)
        return jsonify({"document": doc, "sections": secs})
    except Exception as e:
        log_kv("WEAVIATE_CV_ALL_ERROR", error=str(e), sha=sha)
        return jsonify({"error": str(e)}), 500

@app.route("/api/weaviate/cv_by_path")
def api_weaviate_cv_by_path():
    """Resolve sha for a file path and return document + sections if present."""
    try:
        path = request.args.get("path")
        if not path:
            return jsonify({"error": "path query param required"}), 400
        p = Path(path)
        if not p.exists() or not p.is_file():
            return jsonify({"error": "file not found"}), 404
        sha = sha256_file(p)
        return api_weaviate_cv_all(sha)  # type: ignore
    except Exception as e:
        log_kv("WEAVIATE_CV_BY_PATH_ERROR", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/api/weaviate/role/<sha>")
def api_weaviate_role_read(sha: str):
    """Read-only endpoint to fetch Role data by sha from Weaviate (safe)."""
    try:
        from utils.weaviate_store import WeaviateStore
        ws = WeaviateStore()
        if not ws.client:
            return jsonify({"error": "Weaviate not configured"}), 503
        obj = ws.read_role_from_db(sha)
        if not obj:
            return jsonify({"error": "Not found"}), 404
        return jsonify(obj)
    except Exception as e:
        log_kv("WEAVIATE_ROLE_READ_ERROR", error=str(e), sha=sha)
        return jsonify({"error": str(e)}), 500


@app.route("/api/weaviate/flush", methods=["POST"])
def api_weaviate_flush():
    """Delete all CVDocument and CVSection objects from Weaviate."""
    try:
        from utils.weaviate_store import WeaviateStore
        ws = WeaviateStore()
        if not ws.client:
            return jsonify({"error": "Weaviate not configured"}), 503
        
        # Delete all objects by querying and deleting in batches
        deleted_docs = 0
        deleted_secs = 0
        
        # Delete all CVDocument objects
        while True:
            res = ws._query_do("CVDocument", ["sha"], None, additional=["id"])
            items = res.get("data", {}).get("Get", {}).get("CVDocument", [])
            if not items:
                break
            for it in items:
                obj_id = (it.get("_additional") or {}).get("id") or it.get("id")
                if obj_id:
                    try:
                        # Use HTTP DELETE since we don't have a delete adapter yet
                        import requests
                        url = ws.url.rstrip("/") + f"/v1/objects/{obj_id}"
                        resp = requests.delete(url, timeout=10)
                        if resp.status_code in (200, 204):
                            deleted_docs += 1
                    except Exception:
                        pass
        
        # Delete all CVSection objects
        while True:
            res = ws._query_do("CVSection", ["parent_sha"], None, additional=["id"])
            items = res.get("data", {}).get("Get", {}).get("CVSection", [])
            if not items:
                break
            for it in items:
                obj_id = (it.get("_additional") or {}).get("id") or it.get("id")
                if obj_id:
                    try:
                        import requests
                        url = ws.url.rstrip("/") + f"/v1/objects/{obj_id}"
                        resp = requests.delete(url, timeout=10)
                        if resp.status_code in (200, 204):
                            deleted_secs += 1
                    except Exception:
                        pass
        
        log_kv("WEAVIATE_FLUSH", docs=deleted_docs, sections=deleted_secs)
        return jsonify({"ok": True, "deleted_documents": deleted_docs, "deleted_sections": deleted_secs})
    except Exception as e:
        log_kv("WEAVIATE_FLUSH_ERROR", error=str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Log application launch with OpenAI SDK diagnostics
    try:
        import openai as _openai_diag
        from openai import OpenAI as _OpenAI
        _ver = getattr(_openai_diag, "__version__", "unknown")
        try:
            _has_responses = hasattr(_OpenAI(), "responses")
        except Exception:
            _has_responses = False
        log_kv("APP_START", host="127.0.0.1", port=5000, debug=True, openai_version=_ver, has_responses=_has_responses)
    except Exception as _e:
        log_kv("APP_START", host="127.0.0.1", port=5000, debug=True, openai_diag_error=_e)
    app.run(host="127.0.0.1", port=5000, debug=True)
