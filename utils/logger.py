"""Lightweight file logger with [TIMESTAMP] prefix and kv helper.

All writes go to the path configured in LOG_FILE_PATH (config/.env via AppConfig).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


class AppLogger:
    """Simple file-backed logger used across the project.

    Responsibilities
    - Ensure the log directory exists on initialization.
    - Provide a small, synchronous append-only API for textual and
      key/value style logs. Each log line is prefixed with a local
      timestamp.

    The logger is intentionally tiny and synchronous to keep behavior
    deterministic during short-running scripts and tests.
    """

    def __init__(self, log_file_path: str) -> None:
        """Initialize the logger and ensure parent directory exists.

        Parameters
        - log_file_path: Path to the log file. Parent directories will be
          created if they do not exist. The path is stored as a
          :class:`pathlib.Path` instance on the logger.
        """
        self._log_path = Path(log_file_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        """Append a single-line message to the log file with a timestamp.

        Parameters
        - message: Text string to append. The logger will add a local
          timestamp in the format ``YYYY-MM-DD HH:MM:SS`` and a newline.
        """
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {message}\n")

    def log_kv(self, event: str, **fields: object) -> None:
        """Log an event name with structured key/value pairs.

        The output format is a single line where the event name is followed
        by ``k=v`` pairs separated by spaces. Example:

            MY_EVENT | user=alice count=3

        Parameters
        - event: Short event name
        - **fields: Arbitrary data values to attach to the event
        """
        parts = [f"{k}={v}" for k, v in fields.items()]
        msg = f"{event} | " + " ".join(parts) if parts else event
        self.log(msg)
