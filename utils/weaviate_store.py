"""Lightweight Weaviate wrapper used by HireMind.

This module implements a minimal `WeaviateStore` class with an idempotent
`ensure_schema()` method that creates three classes in Weaviate:
 - CVDocument
 - CVSection
 - Role

If `url` is not provided or the optional `weaviate` client is not installed,
`ensure_schema()` will be a no-op and return gracefully.
"""
from __future__ import annotations

from typing import Optional
import logging
import json

logger = logging.getLogger(__name__)


class WeaviateStore:
    """Small wrapper around the optional weaviate client.

    The wrapper intentionally avoids a hard dependency on the `weaviate-client`
    package. If `url` is falsy or the client package is missing, methods that
    interact with a remote Weaviate instance will return gracefully.
    """

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None, batch_size: int = 64):
        self.url = url or None
        self.api_key = api_key or None
        self.batch_size = int(batch_size or 64)
        self.client = None

        if self.url:
            try:
                import weaviate  # type: ignore

                # Prefer explicit auth helper if available, fall back to simple client
                try:
                    auth = getattr(weaviate.auth, "AuthApiKey", None)
                    if auth and self.api_key:
                        auth_obj = weaviate.auth.AuthApiKey(api_key=self.api_key)  # type: ignore
                        self.client = weaviate.Client(url=self.url, auth_client_secret=auth_obj)  # type: ignore
                    else:
                        self.client = weaviate.Client(url=self.url)  # type: ignore
                except Exception:
                    self.client = weaviate.Client(url=self.url)  # type: ignore

                logger.info("Weaviate client initialized for %s", self.url)
            except Exception as exc:
                logger.warning("Weaviate client unavailable or failed to initialize: %s", exc)
                self.client = None

    def _class_exists(self, class_name: str) -> bool:
        if not self.client:
            return False
        try:
            schema = self.client.schema.get() or {}
            classes = schema.get("classes") or []
            return any(c.get("class") == class_name for c in classes)
        except Exception:
            return False

    def ensure_schema(self) -> None:
        """Idempotently ensure the required Weaviate classes exist.

        If `weaviate_url` was not provided or the client package is missing,
        this method is a no-op and returns gracefully.
        """
        if not self.url:
            logger.debug("Skipping ensure_schema(): weaviate URL not configured")
            return

        if not self.client:
            logger.debug("Skipping ensure_schema(): weaviate client missing/unavailable")
            return

        classes = [
            {
                "class": "CVDocument",
                "vectorizer": "none",
                "properties": [
                    {"name": "sha", "dataType": ["string"]},
                    {"name": "filename", "dataType": ["string"]},
                    {"name": "metadata", "dataType": ["text"]},
                    {"name": "full_text", "dataType": ["text"]},
                ],
            },
            {
                "class": "CVSection",
                "vectorizer": "none",
                "properties": [
                    {"name": "parent_sha", "dataType": ["string"]},
                    {"name": "section_type", "dataType": ["string"]},
                    {"name": "section_text", "dataType": ["text"]},
                ],
            },
            {
                "class": "Role",
                "vectorizer": "none",
                "properties": [
                    {"name": "sha", "dataType": ["string"]},
                    {"name": "filename", "dataType": ["string"]},
                    {"name": "role_text", "dataType": ["text"]},
                ],
            },
        ]

        for cls in classes:
            class_name = cls.get("class")
            if self._class_exists(class_name):
                logger.debug("Weaviate class '%s' already exists, skipping", class_name)
                continue
            try:
                self.client.schema.create_class(cls)  # type: ignore
                logger.info("Created Weaviate class: %s", class_name)
            except Exception as exc:
                logger.warning("Failed to create Weaviate class '%s': %s", class_name, exc)

    def _find_cv_by_sha(self, sha: str) -> tuple[Optional[str], Optional[dict]]:
        """Return (uuid, properties) for the CVDocument with matching sha, or (None, None).

        Uses a GraphQL query with a where filter on the `sha` property. If the
        client is unavailable or an error occurs this returns (None, None).
        """
        if not self.client:
            return None, None

        try:
            where = {"path": ["sha"], "operator": "Equal", "valueString": sha}
            # request id via _additional
            resp = (
                self.client.query
                .get("CVDocument", ["sha", "filename", "metadata", "full_text"])
                .with_where(where)
                .with_additional(["id"])
                .do()
            )
            items = (resp.get("data", {}).get("Get", {}).get("CVDocument") or [])
            if not items:
                return None, None
            first = items[0]
            # additional id may be under _additional
            additional = first.get("_additional") or {}
            uuid = additional.get("id")
            return uuid, first
        except Exception as exc:
            logger.warning("Error querying Weaviate for sha=%s: %s", sha, exc)
            return None, None

    def write_cv_to_db(self, sha: str, filename: str, full_text: str, attributes: dict) -> dict:
        """Create or update a CVDocument record keyed by `sha`.

        This is idempotent: repeated calls with the same `sha` will update the
        existing object. When Weaviate is not configured this returns a dict
        describing the no-op and does not raise.
        Returns a dict: {sha, id, created (bool), weaviate_ok (bool)}.
        """
        if not self.client:
            logger.debug("write_cv_to_db: weaviate client missing; skipping upsert for %s", sha)
            return {"sha": sha, "id": None, "created": False, "weaviate_ok": False}

        uuid, existing = self._find_cv_by_sha(sha)

        data_obj = {
            "sha": sha,
            "filename": filename,
            # store attributes as JSON text in the 'metadata' text field
            "metadata": json.dumps(attributes or {}),
            "full_text": full_text or "",
        }

        try:
            if uuid:
                # update
                self.client.data_object.update(data_obj, "CVDocument", uuid=uuid)  # type: ignore
                logger.info("Updated CVDocument sha=%s id=%s", sha, uuid)
                return {"sha": sha, "id": uuid, "created": False, "weaviate_ok": True}
            else:
                new_id = self.client.data_object.create(data_obj, "CVDocument")  # type: ignore
                # some client versions return dict with 'id', others return id string
                new_uuid = None
                if isinstance(new_id, dict):
                    new_uuid = new_id.get("id")
                else:
                    new_uuid = new_id
                logger.info("Created CVDocument sha=%s id=%s", sha, new_uuid)
                return {"sha": sha, "id": new_uuid, "created": True, "weaviate_ok": True}
        except Exception as exc:
            logger.warning("Failed to upsert CVDocument sha=%s: %s", sha, exc)
            return {"sha": sha, "id": None, "created": False, "weaviate_ok": False}

    def read_cv_from_db(self, sha: str) -> Optional[dict]:
        """Return the CVDocument properties for the given sha, or None if missing.

        When Weaviate is not configured this returns None.
        """
        if not self.client:
            logger.debug("read_cv_from_db: weaviate client missing; returning None for %s", sha)
            return None

        uuid, props = self._find_cv_by_sha(sha)
        if not props:
            return None

        # props already contains sha, filename, metadata, full_text; metadata is JSON text
        try:
            metadata = props.get("metadata")
            if metadata:
                try:
                    metadata_obj = json.loads(metadata)
                except Exception:
                    metadata_obj = metadata
            else:
                metadata_obj = None
        except Exception:
            metadata_obj = None

        result = {
            "id": (props.get("_additional") or {}).get("id") if isinstance(props, dict) else None,
            "sha": props.get("sha"),
            "filename": props.get("filename"),
            "metadata": metadata_obj,
            "full_text": props.get("full_text"),
        }
        return result


__all__ = ["WeaviateStore"]

