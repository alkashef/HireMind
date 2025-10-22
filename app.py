from __future__ import annotations

import os
import threading
from datetime import datetime
import hashlib
from pathlib import Path
from typing import List

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv


app = Flask(__name__)


# --- Env & Logger -----------------------------------------------------------

def _load_env() -> None:
    env_path = Path(__file__).resolve().parent / "config" / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)


def log(message: str) -> None:
    """Append a log line to LOG_FILE_PATH with [TIMESTAMP] prefix."""
    _load_env()
    log_path = os.getenv("LOG_FILE_PATH", "logs/app.log")
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {message}\n")


def log_kv(event: str, **fields: object) -> None:
    """Structured logging helper: EVENT | k=v ..."""
    parts = [f"{k}={v}" for k, v in fields.items()]
    msg = f"{event} | " + " ".join(parts) if parts else event
    log(msg)


def get_default_folder() -> str:
    _load_env()
    return os.getenv("DEFAULT_FOLDER", str(Path.home()))


def get_data_path() -> Path:
    """Return base data folder from env (DATA_PATH) or default 'data'."""
    _load_env()
    base = Path(os.getenv("DATA_PATH", "data"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def list_docs(folder: str) -> List[str]:
    exts = {".pdf", ".docx"}
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        return []
    paths = [str(fp) for fp in p.iterdir() if fp.is_file() and fp.suffix.lower() in exts]
    return sorted(paths)


def sha256_file(path: Path) -> str:
    """Return hex sha256 of a file's content."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_max_file_mb() -> int:
    _load_env()
    try:
        return int(os.getenv("MAX_FILE_MB", "10"))
    except Exception:
        return 10


def get_openai_model() -> str:
    _load_env()
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_openai_api_key() -> str | None:
    _load_env()
    return os.getenv("OPENAI_API_KEY")


def extract_full_name_with_openai(file_path: Path) -> tuple[str | None, str | None]:
    """Call OpenAI Responses API with file attachment to extract full_name.

    Returns (full_name, error_message). If failed, full_name is None and error_message is set.
    """
    try:
        api_key = get_openai_api_key()
        if not api_key:
            return None, "OPENAI_API_KEY not set"
        from openai import OpenAI
        client = OpenAI()

        # Upload the file and force JSON extraction
        up = client.files.create(file=file_path.open("rb"), purpose="assistants")

        system_text = (
            "You extract fields from the attached CV. "
            'Return strict JSON: {"full_name":""}. If unknown, use empty string.'
        )
        response = client.responses.create(
            model=get_openai_model(),
            input=[
                {"role": "system", "content": [{"type": "text", "text": system_text}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Extract the candidate's full legal name as JSON with key full_name."}
                    ],
                    "attachments": [
                        {"file_id": up.id, "tools": [{"type": "file_search"}]}
                    ],
                },
            ],
            tools=[{"type": "file_search"}],
            response_format={"type": "json_object"},
        )

        # Extract JSON content
        try:
            content = response.output[0].content[0].text
        except Exception:
            content = getattr(response, "output_text", None) or ""
        import json
        data = json.loads(content) if content else {}
        full_name = data.get("full_name") or ""
        return full_name, None
    except Exception as e:
        return None, str(e)


# --- Routes -----------------------------------------------------------------


@app.route("/")
def index():
    log("INDEX_VIEW")
    return render_template("index.html")


@app.route("/api/default-folder")
def api_default_folder():
    folder = get_default_folder()
    log_kv("DEFAULT_FOLDER", folder=folder)
    return jsonify({"folder": folder})


@app.route("/api/list-files")
def api_list_files():
    folder = get_default_folder()
    files = list_docs(folder)
    log_kv("LIST_FILES", folder=folder, count=len(files))
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

    # Update DEFAULT_FOLDER for current process only
    os.environ["DEFAULT_FOLDER"] = path
    files = list_docs(path)
    log_kv("FOLDER_PICKED", path=path, count=len(files))
    return jsonify({"folder": path, "files": files})


@app.route("/api/hashes", methods=["POST"])
def api_hashes():
    """Compute content hashes and report duplicates for a list of files.

    Body: { "files": ["C:/path/file1.pdf", ...] }
    Returns: { duplicates: ["path1", ...], duplicate_count: N }
    """
    try:
        payload = request.get_json(silent=True) or {}
        files = payload.get("files") or []
        seen: dict[str, str] = {}
        dups: list[str] = []
        for fp in files:
            p = Path(fp)
            if not p.exists() or not p.is_file():
                continue
            h = sha256_file(p)
            if h in seen:
                dups.append(fp)
            else:
                seen[h] = fp
        log_kv("HASHES_DONE", files=len(files), duplicates=len(dups))
        return jsonify({"duplicates": dups, "duplicate_count": len(dups)})
    except Exception as e:
        log_kv("HASHES_ERROR", error=e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/extract", methods=["POST", "GET"])
def api_extract():
    """Persist selected file metadata to CSV under data/data_applicants.csv.

    Body: { "files": ["C:/path/file1.pdf", ...] }
    Writes/updates rows with columns: ID, Timestamp, CV, FullName
    """
    try:
        data_dir = get_data_path()
        csv_path = data_dir / "data_applicants.csv"

        # Serve rows
        if request.method == "GET":
            if not csv_path.exists():
                log_kv("EXTRACT_GET", rows=0)
                return jsonify({"rows": []})
            import csv
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = []
                for r in reader:
                    rid = r.get("ID") or r.get("id") or r.get("Id") or ""
                    ts = r.get("Timestamp") or r.get("timestamp") or ""
                    cv = r.get("CV") or r.get("cv") or r.get("filename") or ""
                    fn = r.get("FullName") or r.get("full_name") or ""
                    rows.append({"id": rid, "timestamp": ts, "cv": cv, "full_name": fn})
            log_kv("EXTRACT_GET", rows=len(rows))
            return jsonify({"rows": rows})

    # Append/update rows for all selected files
        payload = request.get_json(silent=True) or {}
        files = payload.get("files") or []

        import csv

        is_new = not csv_path.exists()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        saved = 0
        stamp = datetime.now().isoformat()
        log_kv("EXTRACT_POST_START", files=len(files), csv=str(csv_path))

        # Load existing rows by ID (content hash)
        existing: list[dict] = []
        index_by_id: dict[str, dict] = {}
        header = ["ID", "Timestamp", "CV", "FullName"]
        if csv_path.exists():
            try:
                with csv_path.open("r", encoding="utf-8", newline="") as rf:
                    reader = csv.DictReader(rf)
                    if reader.fieldnames:
                        for r in reader:
                            rid = r.get("ID") or r.get("id") or r.get("Id") or ""
                            ts = r.get("Timestamp") or r.get("timestamp") or ""
                            cv = r.get("CV") or r.get("cv") or r.get("filename") or ""
                            fn = r.get("FullName") or r.get("full_name") or ""
                            row = {"ID": rid, "Timestamp": ts, "CV": cv, "FullName": fn}
                            if rid:
                                existing.append(row)
                                index_by_id[rid] = row
            except Exception as e:
                log_kv("EXTRACT_READ_EXISTING_ERROR", error=e)

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

                full_name_val = ""
                if not openai_failed_once:
                    fn, err = extract_full_name_with_openai(p)
                    if err:
                        errors.append(f"OpenAI error [{p.name}]: {err}")
                        log_kv("OPENAI_ERROR", name=p.name, error=err)
                        openai_failed_once = True
                    else:
                        full_name_val = fn or ""
                        log_kv("OPENAI_OK", name=p.name, full_name_len=len(full_name_val))

                row = {"ID": rid, "Timestamp": stamp, "CV": cv_name, "FullName": full_name_val}
                if rid not in updated_by_id:
                    saved += 1
                    log_kv("EXTRACT_ROW_NEW", id=rid, cv=cv_name)
                else:
                    log_kv("EXTRACT_ROW_UPDATE", id=rid, cv=cv_name)
                updated_by_id[rid] = row
            except Exception as e:
                errors.append(f"General error [{p.name}]: {e}")
                log_kv("EXTRACT_FILE_ERROR", name=p.name, error=e)

        # Write back file (header + rows)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as wf:
            writer = csv.writer(wf)
            writer.writerow(header)
            for r in updated_by_id.values():
                writer.writerow([r["ID"], r["Timestamp"], r["CV"], r.get("FullName", "")])

        log_kv("EXTRACT_POST_DONE", saved=saved, errors=len(errors), csv=str(csv_path), total_rows=len(updated_by_id))
        return jsonify({"saved": saved, "csv": str(csv_path), "errors": errors})
    except Exception as e:
        log(f"Extract error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
