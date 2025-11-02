from __future__ import annotations

"""OpenAI integration helpers.

This module provides a small helper class, :class:`OpenAIManager`, which
encapsulates calls to the OpenAI Responses API using the official SDK when
available and falling back to raw HTTP requests when necessary.

Primary responsibility:
- Upload a file to the OpenAI file API
- Create a temporary vector store and attach the file
- Call the Responses API (or HTTP fallback) with system/user prompts
- Parse the JSON object response and return structured data or an error

The implementation is defensive and returns (data, error) where `error` is
an error string when something failed. Callers can handle the error and
decide whether to proceed.
"""

import json
import os
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional

import openai as openai_pkg
from openai import OpenAI

from config.settings import AppConfig
from utils.logger import AppLogger
from utils.prompt_loader import get_prompt_bundle
from utils.extractors import pdf_to_text, docx_to_text


class OpenAIManager:
    """Encapsulates OpenAI Responses API integration (SDK + HTTP fallback).

    Responsibilities
    - Use the modern OpenAI SDK (`OpenAI`) when it provides the Responses API.
    - Fall back to HTTP+requests when the SDK is unavailable or lacks responses.
    - Upload files, create temporary vector stores, attach files, and call
      the Responses API asking for a JSON-object formatted output.

    The class returns tuples of ``(data_dict | None, error_str | None)`` so
    callers can handle failures without raising exceptions for expected
    runtime issues (missing API key, network failures, etc.).
    """

    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger
        # TODO(optimization): Reuse a single session-level vector store instead of
        # creating/deleting a store per file. This reduces API calls and latency.
        # Strategy:
        #   - Keep a persistent store id (e.g., self._vs_id) created on first use
        #   - Attach each uploaded file to that store
        #   - Delete the store only on app shutdown/teardown (or rotate after N files)
        # Consideration: Retrieval contamination across files; mitigate with strict
        # prompts and passing the current CV via input_file, or rotate per batch.
        self._vs_id: str | None = None  # SDK-managed vector store id (future reuse)
        self._vs_id_http: str | None = None  # HTTP fallback vector store id (future reuse)

    def _load_prompts(self) -> tuple[str, str]:
        """Load system and user prompts from the unified JSON bundle."""
        bundle = get_prompt_bundle(prompt_key="extract_cv_fields_json", cfg=self.config)
        system_text = bundle.get("system", "")
        user_text = bundle.get("user", "")
        if not system_text or not user_text:
            raise RuntimeError("Unified prompt JSON is missing system or user text")
        return system_text, user_text

    def _load_prompts_role(self) -> tuple[str, str]:
        """Load system and user prompts for role extraction from unified JSON bundle."""
        bundle = get_prompt_bundle(prompt_key="extract_role_fields_json", cfg=self.config)
        system_text = bundle.get("system", "")
        user_text = bundle.get("user", "")
        if not system_text or not user_text:
            raise RuntimeError("Role prompt JSON is missing system or user text")
        return system_text, user_text

    def extract_full_name(self, file_path: Path) -> Tuple[Dict[str, Any] | None, str | None]:
        """Extract a structured JSON object (profile) from a file using OpenAI.

        Behavior by file type
        - PDF: upload file, attach to a temporary vector store, and invoke Responses with file_search tool.
        - DOCX (and others): extract plain text locally and invoke Responses with input_text only (no attachments/tools).

        Returns
        - (data_dict, None) on success where data_dict is the parsed JSON object
        - (None, error_message) on failure with an actionable string
        """
        try:
            api_key = self.config.openai_api_key
            if not api_key:
                return None, "OPENAI_API_KEY not set"

            client = OpenAI()

            # Load prompts (system + user) from unified JSON
            system_text, user_text = self._load_prompts()
            # Always send plain text input (no file attachments/tools) for all types
            ext = file_path.suffix.lower()
            text_content: str = ""
            try:
                if ext == ".pdf":
                    text_content = pdf_to_text(file_path)
                elif ext == ".docx":
                    text_content = docx_to_text(file_path)
                else:
                    text_content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                return None, f"Failed to read text from file ({ext}): {e}"

            # SDK path
            if hasattr(client, "responses"):
                response = client.responses.create(
                    model=self.config.openai_model,
                    input=[
                        {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": user_text},
                                {"type": "input_text", "text": text_content},
                            ],
                        },
                    ],
                    text={"format": {"type": "json_object"}},
                )

                content = getattr(response, "output_text", None)
                if not content:
                    try:
                        content = response.output[0].content[0].text
                    except Exception:
                        content = ""
                data = json.loads(content) if content else {}
                self.logger.log_kv("OPENAI_TEXT_MODE", size=len(text_content))
                return data or {}, None
            # HTTP fallback path
            try:
                import requests
            except Exception:
                ver = getattr(openai_pkg, "__version__", "unknown")
                return None, (
                    f"OpenAI SDK {ver} lacks Responses API and 'requests' is unavailable for HTTP fallback. "
                    "Add 'requests' to requirements.txt and reinstall."
                )

            base_url = self.config.openai_base_url
            headers_json = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": self.config.openai_model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_text},
                            {"type": "input_text", "text": text_content},
                        ],
                    },
                ],
                "text": {"format": {"type": "json_object"}},
            }
            try:
                resp = requests.post(
                    f"{base_url.rstrip('/')}/responses",
                    headers=headers_json,
                    data=json.dumps(body),
                    timeout=self.config.request_timeout_seconds,
                )
            except Exception as e:
                return None, f"HTTP fallback error: {e}"
            if resp.status_code >= 400:
                return None, f"HTTP fallback error: {resp.status_code} {resp.text}"

            try:
                payload = resp.json()
            except Exception:
                payload = {}

            content = payload.get("output_text")
            if not content:
                try:
                    content = payload["output"][0]["content"][0]["text"]
                except Exception:
                    content = ""
            data = json.loads(content) if content else {}
            self.logger.log_kv("OPENAI_TEXT_MODE", size=len(text_content))
            return data or {}, None
        except Exception as e:
            return None, str(e)

    def extract_role_fields(self, file_path: Path) -> Tuple[Dict[str, Any] | None, str | None]:
        """Extract structured role fields using OpenAI with text-only input.

        Uses the unified role prompt bundle referenced by PROMPT_EXTRACT_ROLE_FIELDS_JSON.
        """
        try:
            api_key = self.config.openai_api_key
            if not api_key:
                return None, "OPENAI_API_KEY not set"

            client = OpenAI()
            system_text, user_text = self._load_prompts_role()

            # Always send text content
            ext = file_path.suffix.lower()
            try:
                if ext == ".pdf":
                    text_content = pdf_to_text(file_path)
                elif ext == ".docx":
                    text_content = docx_to_text(file_path)
                else:
                    text_content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                return None, f"Failed to read text from file ({ext}): {e}"

            if hasattr(client, "responses"):
                response = client.responses.create(
                    model=self.config.openai_model,
                    input=[
                        {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
                        {"role": "user", "content": [
                            {"type": "input_text", "text": user_text},
                            {"type": "input_text", "text": text_content},
                        ]},
                    ],
                    text={"format": {"type": "json_object"}},
                )
                content = getattr(response, "output_text", None)
                if not content:
                    try:
                        content = response.output[0].content[0].text
                    except Exception:
                        content = ""
                data = json.loads(content) if content else {}
                self.logger.log_kv("OPENAI_TEXT_MODE_ROLE", size=len(text_content))
                return data or {}, None

            # HTTP fallback
            try:
                import requests
            except Exception:
                ver = getattr(openai_pkg, "__version__", "unknown")
                return None, (
                    f"OpenAI SDK {ver} lacks Responses API and 'requests' is unavailable for HTTP fallback. "
                    "Add 'requests' to requirements.txt and reinstall."
                )

            base_url = self.config.openai_base_url
            headers_json = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": self.config.openai_model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
                    {"role": "user", "content": [
                        {"type": "input_text", "text": user_text},
                        {"type": "input_text", "text": text_content},
                    ]},
                ],
                "text": {"format": {"type": "json_object"}},
            }
            try:
                resp = requests.post(
                    f"{base_url.rstrip('/')}/responses",
                    headers=headers_json,
                    data=json.dumps(body),
                    timeout=self.config.request_timeout_seconds,
                )
            except Exception as e:
                return None, f"HTTP fallback error: {e}"
            if resp.status_code >= 400:
                return None, f"HTTP fallback error: {resp.status_code} {resp.text}"

            try:
                payload = resp.json()
            except Exception:
                payload = {}

            content = payload.get("output_text")
            if not content:
                try:
                    content = payload["output"][0]["content"][0]["text"]
                except Exception:
                    content = ""
            data = json.loads(content) if content else {}
            self.logger.log_kv("OPENAI_TEXT_MODE_ROLE", size=len(text_content))
            return data or {}, None
        except Exception as e:
            return None, str(e)

    # ---------------------------------------------------------------------
    # Embeddings
    def embed_texts(self, texts: List[str], model: Optional[str] = None) -> Tuple[List[List[float]] | None, str | None]:
        """Compute OpenAI embeddings for a list of texts.

        Parameters
        - texts: list of input strings (non-empty list)
        - model: optional embedding model name; when omitted, reads
          OPENAI_EMBEDDING_MODEL from AppConfig/env or defaults to
          'text-embedding-3-small'.

        Returns
        - (embeddings, None) on success where embeddings is a list of vectors
          (list[float]) in the same order as input texts.
        - (None, error_message) on failure.
        """
        try:
            if not texts:
                return [], None

            m = model or os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"

            # Use official SDK path
            client = OpenAI()
            resp = client.embeddings.create(model=m, input=texts)
            # SDK returns .data list with .embedding vectors
            vectors: List[List[float]] = []
            for item in getattr(resp, "data", []) or []:
                vec = getattr(item, "embedding", None)
                if isinstance(vec, list):
                    vectors.append([float(x) for x in vec])
                else:
                    # preserve order; append empty vector if missing
                    vectors.append([])

            if len(vectors) != len(texts):
                return None, "embeddings count mismatch"

            # small trace in logs (avoid dumping vectors)
            self.logger.log_kv("OPENAI_EMBEDDINGS_OK", count=len(vectors), model=m)
            return vectors, None
        except Exception as e:
            return None, str(e)
