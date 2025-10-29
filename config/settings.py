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

        Defaults to `<repo_root>/data/weaviate_data`. Returns a Path and ensures
        the directory exists.
        """
        root = Path(__file__).resolve().parent.parent
        default = root / "data" / "weaviate_data"
        path = Path(os.getenv("WEAVIATE_DATA_PATH", str(default)))
        path.mkdir(parents=True, exist_ok=True)
        return path

    # Prompt template filenames (inside the `prompts/` folder).
    # These return the filename (string). Callers should join with the prompts
    # folder when opening the file (e.g., Path('prompts') / cfg.prompt_...).
    @property
    def prompt_extract_from_cv_system(self) -> str:
        return os.getenv("PROMPT_EXTRACT_FROM_CV_SYSTEM", "extract_from_cv_system.md")

    @property
    def prompt_extract_from_cv_user(self) -> str:
        return os.getenv("PROMPT_EXTRACT_FROM_CV_USER", "extract_from_cv_user.md")

    @property
    def prompt_cv_full_name_system(self) -> str:
        return os.getenv("PROMPT_CV_FULL_NAME_SYSTEM", "cv_full_name_system.md")

    @property
    def prompt_cv_full_name_user(self) -> str:
        return os.getenv("PROMPT_CV_FULL_NAME_USER", "cv_full_name_user.md")

    @property
    def prompt_numeric_2_plus_2(self) -> str:
        return os.getenv("PROMPT_NUMERIC_2_PLUS_2", "prompt_numeric_2_plus_2.md")

    @property
    def prompt_summarize_short(self) -> str:
        return os.getenv("PROMPT_SUMMARIZE_SHORT", "prompt_summarize_short.md")

    @property
    def prompt_sample_short_hello(self) -> str:
        return os.getenv("PROMPT_SAMPLE_SHORT_HELLO", "sample_short_text_hello.md")

    @property
    def prompt_hello_world(self) -> str:
        return os.getenv("PROMPT_HELLO_WORLD", "hello_world.txt")

    @property
    def prompt_summarize_this(self) -> str:
        return os.getenv("PROMPT_SUMMARIZE_THIS", "summarize_this.txt")

    # Hermes model configuration (HF-format model runtime defaults)
    @property
    def hermes_model_dir(self) -> str:
        return os.getenv("HERMES_MODEL_DIR", "models/hermes-pro")

    @property
    def hermes_quantize_4bit(self) -> bool:
        v = os.getenv("HERMES_QUANTIZE_4BIT")
        if v is None:
            return True
        return str(v).lower() in ("1", "true", "yes")

    @property
    def hermes_temperature(self) -> float:
        try:
            return float(os.getenv("HERMES_TEMPERATURE", "0.0"))
        except Exception:
            return 0.0

    @property
    def hermes_num_beams(self) -> int:
        try:
            return int(os.getenv("HERMES_NUM_BEAMS", "1"))
        except Exception:
            return 1

    @property
    def hermes_max_new_tokens(self) -> int:
        try:
            return int(os.getenv("HERMES_MAX_NEW_TOKENS", "128"))
        except Exception:
            return 128

    # Paraphrase/embedding model configuration
    @property
    def paraphrase_model_dir(self) -> str:
        return os.getenv("PARAPHRASE_MODEL_DIR", "models/paraphrase-MiniLM-L12-v2")

    @property
    def paraphrase_device(self) -> str:
        # Default to cuda so embeddings load on GPU when available
        return os.getenv("PARAPHRASE_DEVICE", "cuda")
