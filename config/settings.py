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
        # Also attempt to load a repository-root .env (higher precedence for
        # developer machines that place their secrets at repo root).
        try:
            repo_root = root.parent
            repo_env = repo_root / ".env"
            if repo_env.exists():
                load_dotenv(dotenv_path=repo_env)
        except Exception:
            # best-effort: don't fail construction if dotfiles are inaccessible
            pass

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
        """Deprecated alias for applicants_folder (reads APPLICANTS_FOLDER)."""
        return os.getenv("APPLICANTS_FOLDER", str(Path.home()))

    @property
    def roles_folder(self) -> str:
        """Default Roles repository folder.

        Falls back to APPLICANTS_FOLDER when ROLES_FOLDER is not set.
        """
        return os.getenv("ROLES_FOLDER", os.getenv("APPLICANTS_FOLDER", str(Path.home())))

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

    @property
    def weaviate_url(self) -> str | None:
        """Optional Weaviate endpoint URL (e.g. https://<host>/v1)."""
        return os.getenv("WEAVIATE_URL")

    @property
    def weaviate_api_key(self) -> str | None:
        """Optional Weaviate API key or token."""
        return os.getenv("WEAVIATE_API_KEY")

    @property
    def weaviate_batch_size(self) -> int:
        try:
            return int(os.getenv("WEAVIATE_BATCH_SIZE", "64"))
        except Exception:
            return 64

    @property
    def weaviate_data_path(self) -> Path:
        """Host path where Weaviate should persist data when running locally.

        Defaults to `<repo_root>/store/weaviate_data`. Returns a Path and ensures
        the directory exists.
        """
        root = Path(__file__).resolve().parent.parent
        default = root / "store" / "weaviate_data"
        path = Path(os.getenv("WEAVIATE_DATA_PATH", str(default)))
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def weaviate_grpc_port(self) -> int | None:
        """Optional explicit gRPC port for Weaviate connections.

        If set via the WEAVIATE_GRPC_PORT environment variable, returns the
        integer port. Otherwise returns None so callers can choose a sensible
        default.
        """
        v = os.getenv("WEAVIATE_GRPC_PORT")
        if v is None or v == "":
            return None

    @property
    def weaviate_schema_path(self) -> str | None:
        """Path to the external Weaviate schema JSON file (required for startup).

        Read from WEAVIATE_SCHEMA_PATH. If not set callers should treat this as
        a fatal configuration error.
        """
        v = os.getenv("WEAVIATE_SCHEMA_PATH")
        if v is None or v == "":
            return None
        return v
        try:
            return int(v)
        except Exception:
            return None

    # Prompt template filenames (inside the `prompts/` folder).
    # These return the filename (string). Callers should join with the prompts
    # folder when opening the file (e.g., Path('prompts') / cfg.prompt_...).
    # Unified prompt bundle replaces legacy system/user prompt files.

    @property
    def prompt_cv_full_name_system(self) -> str:
        return os.getenv("PROMPT_CV_FULL_NAME_SYSTEM", "cv_full_name_system.md")

    @property
    def prompt_cv_full_name_user(self) -> str:
        return os.getenv("PROMPT_CV_FULL_NAME_USER", "cv_full_name_user.md")

    # Removed obsolete prompt properties (numeric_2_plus_2, summarize_short,
    # sample_short_hello, hello_world, summarize_this). Project no longer uses them.

    # Local model configuration removed: project uses OpenAI and/or server-side vectorization only.

    @property
    def prompt_extract_cv_fields_json(self) -> str:
        """Filename of consolidated per-field extraction prompt (JSON with template + hints)."""
        return os.getenv("PROMPT_EXTRACT_CV_FIELDS_JSON", "prompt_extract_cv_fields.json")

    @property
    def prompt_extract_role_fields_json(self) -> str:
        """Filename of consolidated role extraction prompt (JSON with template + hints)."""
        return os.getenv("PROMPT_EXTRACT_ROLE_FIELDS_JSON", "prompt_extract_role_fields.json")
