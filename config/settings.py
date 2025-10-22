"""Centralized application configuration.

Reads from config/.env and exposes strongly-typed properties with sane defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv


class AppConfig:
    """Application configuration loaded from config/.env with defaults.

    - Ensures data and logs directories exist when accessed.
    """

    def __init__(self) -> None:
        # Load .env from config/.env relative to project root
        root = Path(__file__).resolve().parent
        env_path = root / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)

    @property
    def data_path(self) -> Path:
        base = Path(os.getenv("DATA_PATH", "data"))
        base.mkdir(parents=True, exist_ok=True)
        return base

    @property
    def log_file_path(self) -> str:
        path = os.getenv("LOG_FILE_PATH", "logs/app.log")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def default_folder(self) -> str:
        return os.getenv("DEFAULT_FOLDER", str(Path.home()))

    @property
    def openai_api_key(self) -> str | None:
        return os.getenv("OPENAI_API_KEY")

    @property
    def openai_model(self) -> str:
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def max_file_mb(self) -> int:
        try:
            return int(os.getenv("MAX_FILE_MB", "10"))
        except Exception:
            return 10

    @property
    def request_timeout_seconds(self) -> float:
        try:
            return float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
        except Exception:
            return 60.0

    @property
    def openai_base_url(self) -> str:
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
