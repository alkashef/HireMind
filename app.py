from __future__ import annotations

import os
import threading
from datetime import datetime
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


# --- Routes -----------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/default-folder")
def api_default_folder():
    folder = get_default_folder()
    log(f"Default folder requested -> {folder}")
    return jsonify({"folder": folder})


@app.route("/api/list-files")
def api_list_files():
    folder = get_default_folder()
    files = list_docs(folder)
    log(f"List files for folder -> {folder} | {len(files)} items")
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
        log(f"Folder picker error: {selected['error']}")
        return jsonify({"error": selected["error"]}), 500

    path = selected.get("path")
    if not path:
        log("Folder picker canceled by user")
        return jsonify({"folder": None, "files": []})

    # Update DEFAULT_FOLDER for current process only
    os.environ["DEFAULT_FOLDER"] = path
    files = list_docs(path)
    log(f"Folder picked -> {path} | {len(files)} items")
    return jsonify({"folder": path, "files": files})


@app.route("/api/extract", methods=["POST", "GET"])
def api_extract():
    """Persist selected file metadata to CSV under data/data_applicants.csv.

    Body: { "files": ["C:/path/file1.pdf", ...] }
    Writes rows with columns: filename, timestamp, id
    """
    try:
        data_dir = get_data_path()
        csv_path = data_dir / "data_applicants.csv"

        # Serve rows
        if request.method == "GET":
            if not csv_path.exists():
                return jsonify({"rows": []})
            import csv
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = [
                    {"filename": r.get("filename", ""), "timestamp": r.get("timestamp", ""), "id": r.get("id", "")}
                    for r in reader
                ]
            return jsonify({"rows": rows})

        # Append rows
        payload = request.get_json(silent=True) or {}
        files = payload.get("files") or []

        import csv
        import uuid

        is_new = not csv_path.exists()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        saved = 0
        stamp = datetime.now().isoformat()

        with csv_path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["filename", "timestamp", "id"])
            for fp in files:
                filename = str(Path(fp).name)
                uid = str(uuid.uuid4())
                writer.writerow([filename, stamp, uid])
                saved += 1

        log(f"Extract saved {saved} rows -> {csv_path}")
        return jsonify({"saved": saved, "csv": str(csv_path)})
    except Exception as e:
        log(f"Extract error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
