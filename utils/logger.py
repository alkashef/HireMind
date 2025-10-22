"""Lightweight file logger with [TIMESTAMP] prefix and kv helper.

All writes go to the path configured in LOG_FILE_PATH (config/.env via AppConfig).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


class AppLogger:
    def __init__(self, log_file_path: str) -> None:
        self._log_path = Path(log_file_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {message}\n")

    def log_kv(self, event: str, **fields: object) -> None:
        parts = [f"{k}={v}" for k, v in fields.items()]
        msg = f"{event} | " + " ".join(parts) if parts else event
        self.log(msg)
