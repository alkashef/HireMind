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
    logger.log(message)


def log_kv(event: str, **fields: object) -> None:
    logger.log_kv(event, **fields)


# Log once when the app handles the first request (Flask 3.x safe)
@app.before_request
def _app_ready() -> None:
    if not app.config.get("_APP_READY_LOGGED"):
        log("APP_READY")
        app.config["_APP_READY_LOGGED"] = True


def get_default_folder() -> str:
    return config.default_folder

def get_roles_default_folder() -> str:
    return config.roles_folder


def get_data_path() -> Path:
    return config.data_path


def list_docs(folder: str) -> List[str]:
    exts = {".pdf", ".docx"}
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        return []
    paths = [str(fp) for fp in p.iterdir() if fp.is_file() and fp.suffix.lower() in exts]
    return sorted(paths)

def list_role_docs(folder: str) -> List[str]:
    """List role documents (same extensions as CVs)."""
    return list_docs(folder)


def sha256_file(path: Path) -> str:
    """Return hex sha256 of a file's content."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_max_file_mb() -> int:
    return config.max_file_mb


def get_openai_model() -> str:
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
