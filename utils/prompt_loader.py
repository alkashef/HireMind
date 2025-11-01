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
from typing import Dict, Optional, Tuple, Any
import json

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
        - prompt_filename: direct filename inside `prompts/` (e.g. 'prompt_extract_cv_fields.json').
        - prompt_key: logical key to resolve via AppConfig (e.g. 'extract_cv_fields_json' or
            'prompt_extract_cv_fields_json'). The function will try to read `cfg.prompt_<key>`.
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


def load_prompt_json(
    prompt_filename: Optional[str] = None,
    prompt_key: Optional[str] = None,
    cfg: Optional[AppConfig] = None,
) -> Dict[str, Any]:
    """Load a JSON prompt file and return its parsed object.

    The JSON file is expected to contain at least a "template" string and may include
    a "hints" object mapping field names to guidance. Additional keys are ignored here.

    Returns the parsed dict. Raises on IO or JSON parse errors.
    """
    raw = load_prompt(prompt_filename=prompt_filename, prompt_key=prompt_key, cfg=cfg)
    try:
        data = json.loads(raw)
    except Exception as ex:
        raise ValueError("Prompt JSON parse failed") from ex
    if not isinstance(data, dict):
        raise ValueError("Prompt JSON must be a JSON object at top-level")
    return data


def get_template_and_hints(
    prompt_filename: Optional[str] = None,
    prompt_key: Optional[str] = None,
    cfg: Optional[AppConfig] = None,
) -> Tuple[str, Dict[str, str]]:
    """Convenience helper to read a JSON prompt and extract (template, hints).

    - If prompt_filename is provided it takes precedence; otherwise prompt_key is used.
    - Returns a tuple (template, hints_map). If no hints are present, returns an empty dict.
    """
    data = load_prompt_json(prompt_filename=prompt_filename, prompt_key=prompt_key, cfg=cfg)
    template = str(data.get("template", ""))
    hints = data.get("hints")
    if not isinstance(hints, dict):
        hints = {}
    # Ensure all hint values are strings
    hints_str: Dict[str, str] = {str(k): (str(v) if v is not None else "") for k, v in hints.items()}
    return template, hints_str


def get_prompt_bundle(
    prompt_filename: Optional[str] = None,
    prompt_key: Optional[str] = None,
    cfg: Optional[AppConfig] = None,
) -> Dict[str, Any]:
    """Return the full prompt bundle from a JSON prompt file.

    Bundle keys:
    - system: str
    - user: str
    - template: str  (per-field extraction; optional)
    - fields: List[str]
    - hints: Dict[str, str]
    - instructions: List[str]
    - formatting_rules: List[str]
    """
    data = load_prompt_json(prompt_filename=prompt_filename, prompt_key=prompt_key, cfg=cfg)
    bundle: Dict[str, Any] = {
        "system": str(data.get("system", "")),
        "user": str(data.get("user", "")),
        "template": str(data.get("template", "")),
        "fields": list(data.get("fields") or []),
        "hints": data.get("hints") or {},
        "instructions": list(data.get("instructions") or []),
        "formatting_rules": list(data.get("formatting_rules") or []),
    }
    # Normalize hints values to strings
    if isinstance(bundle["hints"], dict):
        bundle["hints"] = {str(k): (str(v) if v is not None else "") for k, v in bundle["hints"].items()}
    else:
        bundle["hints"] = {}
    return bundle


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


__all__ = [
    "load_prompt",
    "generate_from_prompt",
    "load_prompt_json",
    "get_template_and_hints",
    "get_prompt_bundle",
]
