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
from pathlib import Path
from typing import Tuple, Dict, Any

import openai as openai_pkg
from openai import OpenAI

from config.settings import AppConfig
from utils.logger import AppLogger


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

    def _load_prompt(self, name: str) -> str:
        """Load a prompt template from the repository `prompts/` folder.

        Parameters
        - name: Filename inside `prompts/` (e.g. 'extract_from_cv_user.md')

        Returns
        - Contents of the prompt file as a stripped string.

        Raises
        - RuntimeError when the prompt file cannot be read.
        """
        # prompts/ is at repo root; this file is utils/openai_manager.py
        root = Path(__file__).resolve().parent.parent
        p = root / "prompts" / name
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception as e:
            raise RuntimeError(f"Prompt load failed: {name} -> {e}")

    def extract_full_name(self, file_path: Path) -> Tuple[Dict[str, Any] | None, str | None]:
        """Extract a structured JSON object (profile) from a file using OpenAI.

        This method attempts the following flow:
        1. Ensure OPENAI_API_KEY is present in config
        2. Upload the file to the OpenAI files API
        3. Create a temporary vector store and attach the file
        4. Call the Responses API (SDK or HTTP fallback) with system/user prompts
           requesting a JSON object as the output format
        5. Parse and return the JSON object

        Returns
        - (data_dict, None) on success where data_dict is the parsed JSON object
        - (None, error_message) on failure with an actionable string

        Notes
        - The method cleans up temporary vector stores after use. It is
          intentionally conservative and prefers returning an error string
          rather than raising for common runtime issues (missing API key,
          network errors, etc.).
        """
        try:
            api_key = self.config.openai_api_key
            if not api_key:
                return None, "OPENAI_API_KEY not set"

            client = OpenAI()

            # Load prompts (now request a full profile JSON)
            system_text = self._load_prompt("extract_from_cv_system.md")
            user_text = self._load_prompt("extract_from_cv_user.md")

            # Upload file
            up = client.files.create(file=file_path.open("rb"), purpose="assistants")

            if hasattr(client, "responses"):
                # SDK path: create vector store and attach file for file_search
                # TODO(optimization): If self._vs_id exists, reuse it; otherwise create once
                vs = client.vector_stores.create(name="hiremind_temp_vs")
                try:
                    client.vector_stores.files.create(vector_store_id=vs.id, file_id=up.id)
                    self.logger.log_kv("OPENAI_VECTOR_STORE", id=vs.id)

                    response = client.responses.create(
                        model=self.config.openai_model,
                        input=[
                            {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": user_text},
                                    {"type": "input_file", "file_id": up.id}
                                ],
                            },
                        ],
                        tools=[{"type": "file_search", "vector_store_ids": [vs.id]}],
                        text={"format": {"type": "json_object"}},
                    )

                    content = getattr(response, "output_text", None)
                    if not content:
                        try:
                            content = response.output[0].content[0].text
                        except Exception:
                            content = ""
                    data = json.loads(content) if content else {}
                    return data or {}, None
                finally:
                    # TODO(optimization): When reusing a store, skip per-call deletion
                    # and perform cleanup at app shutdown/teardown instead.
                    try:
                        client.vector_stores.delete(vector_store_id=vs.id)
                    except Exception:
                        pass
            else:
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

                # Create vector store
                # TODO(optimization): If self._vs_id_http exists, reuse it; otherwise create once
                vs_resp = requests.post(
                    f"{base_url.rstrip('/')}/vector_stores",
                    headers=headers_json,
                    data=json.dumps({"name": "hiremind_temp_vs"}),
                    timeout=self.config.request_timeout_seconds,
                )
                if vs_resp.status_code >= 400:
                    return None, f"HTTP fallback error (vector_store create): {vs_resp.status_code} {vs_resp.text}"
                vs_id = vs_resp.json().get("id")
                if not vs_id:
                    return None, "HTTP fallback error: vector_store id missing"
                self.logger.log_kv("OPENAI_VECTOR_STORE", id=vs_id)

                # Attach file to vector store
                att_resp = requests.post(
                    f"{base_url.rstrip('/')}/vector_stores/{vs_id}/files",
                    headers=headers_json,
                    data=json.dumps({"file_id": up.id}),
                    timeout=self.config.request_timeout_seconds,
                )
                if att_resp.status_code >= 400:
                    return None, f"HTTP fallback error (vector_store attach): {att_resp.status_code} {att_resp.text}"

                # Responses call
                body = {
                    "model": self.config.openai_model,
                    "input": [
                        {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": user_text},
                                {"type": "input_file", "file_id": up.id}
                            ],
                        },
                    ],
                    "tools": [{"type": "file_search", "vector_store_ids": [vs_id]}],
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

                # Cleanup vector store
                # TODO(optimization): When reusing a store, skip per-call deletion
                # and perform cleanup at app shutdown/teardown instead.
                try:
                    requests.delete(
                        f"{base_url.rstrip('/')}/vector_stores/{vs_id}",
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=self.config.request_timeout_seconds,
                    )
                except Exception:
                    pass

                return data or {}, None
        except Exception as e:
            return None, str(e)
