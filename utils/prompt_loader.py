"""Generic prompt loader and formatter.

This module centralizes reading prompt templates from the `prompts/` folder
and formatting them with variables. Callers should prefer passing a prompt
key (for values exposed in `config/.env` and `config.settings.AppConfig`) or a
direct filename.

Examples
--------
from config.settings import AppConfig
from utils.prompt_loader import generate_from_prompt

cfg = AppConfig()
text = generate_from_prompt(prompt_key='extract_from_cv_user', prompt_vars={'name': 'Alice'})
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from config.settings import AppConfig

logger = logging.getLogger(__name__)


def _resolve_prompts_dir() -> Path:
    """Return the repository `prompts/` directory path.

    Prefer a `prompts` folder relative to the current working directory. If
    that doesn't exist (e.g. when running from tests with a different CWD),
    fall back to the folder next to the repository root.
    """
    cwd = Path.cwd() / "prompts"
    if cwd.exists():
        return cwd
    # Fallback: the repo layout is assumed: <repo>/utils/prompt_loader.py
    alt = Path(__file__).resolve().parents[1] / "prompts"
    return alt


def load_prompt(
    prompt_filename: Optional[str] = None,
    prompt_key: Optional[str] = None,
    cfg: Optional[AppConfig] = None,
) -> str:
    """Load a prompt template by filename or by prompt key (AppConfig property).

    Parameters
    - prompt_filename: direct filename inside `prompts/` (e.g. 'extract_from_cv_user.md').
    - prompt_key: logical key to resolve via AppConfig (e.g. 'extract_from_cv_user' or
      'prompt_extract_from_cv_user'). The function will try to read `cfg.prompt_<key>`.
    - cfg: optional AppConfig instance; a new one is created when omitted.

    Returns the prompt text as a string. Raises FileNotFoundError or ValueError
    when the prompt cannot be located.
    """
    cfg = cfg or AppConfig()

    filename = None
    if prompt_filename:
        filename = prompt_filename
    elif prompt_key:
        # Try common attribute names on AppConfig: prompt_<key> or the key itself
        attempts = [f"prompt_{prompt_key}", prompt_key]
        for attr in attempts:
            val = getattr(cfg, attr, None)
            if val:
                filename = val
                break

    if not filename:
        raise ValueError(
            "No prompt filename resolved. Provide prompt_filename or prompt_key, or set the corresponding env var in config/.env."
        )

    prompts_dir = _resolve_prompts_dir()
    prompt_path = prompts_dir / filename
    logger.debug("Loading prompt from %s", prompt_path)

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path!s}. Check that your prompts folder exists and that the AppConfig value or env var points to a valid filename."
        )

    text = prompt_path.read_text(encoding="utf8")
    return text


def generate_from_prompt(
    prompt_key: Optional[str] = None,
    prompt_filename: Optional[str] = None,
    prompt_vars: Optional[Dict[str, object]] = None,
    cfg: Optional[AppConfig] = None,
) -> str:
    """Load a prompt template and format it with `prompt_vars`.

    - If `prompt_filename` is provided, it takes precedence.
    - Otherwise `prompt_key` is used to resolve a filename via `AppConfig`.

    Returns the formatted prompt string.
    """
    raw = load_prompt(prompt_filename=prompt_filename, prompt_key=prompt_key, cfg=cfg)
    if not prompt_vars:
        return raw

    try:
        return raw.format(**prompt_vars)
    except KeyError as ex:
        missing = ex.args[0] if ex.args else "<unknown>"
        raise ValueError(f"Missing prompt variable: {missing}") from ex


__all__ = ["load_prompt", "generate_from_prompt"]
