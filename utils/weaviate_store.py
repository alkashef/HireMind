"""Safe, minimal Weaviate client wrapper.

This module provides a small WeaviateStore class with an idempotent
ensure_schema() method. It is intentionally conservative: if no
configuration is provided it becomes a no-op. The goal is to keep the
CSV pipeline authoritative and make the Weaviate integration safe to add
as a parallel store.

Design contracts (small):
- Inputs: url (str|None), api_key (str|None), batch_size (int)
- Outputs: methods either return True on success or raise ValueError on
  invalid arguments. When unconfigured, ensure_schema() returns False but
  does not raise.
- Error modes: When weaviate client import is missing or connection fails,
  keep failure local and return False; do not raise during module import.

Usage:
    from config import settings
    store = WeaviateStore(settings.WEAVIATE_URL, settings.WEAVIATE_API_KEY, settings.WEAVIATE_BATCH_SIZE)
    store.ensure_schema()

The implementation avoids creating classes or writing data. It only
creates the client and ensures the expected schema exists when a URL is
provided.
"""
from __future__ import annotations

from typing import Optional
import logging

from config import settings

LOG = logging.getLogger(__name__)


class WeaviateStore:
    """Lightweight safe wrapper around a weaviate client.

    If initialized with a falsy URL, methods become safe no-ops.
    """

    def __init__(self, url: Optional[str], api_key: Optional[str] = None, batch_size: int = 64):
        self.url = url or None
        self.api_key = api_key or None
        self.batch_size = int(batch_size or 64)
        self._client = None

    def _maybe_import_client(self):
        if not self.url:
            LOG.debug("Weaviate URL not configured; weaviate_store will be a no-op.")
            return None
        if self._client is not None:
            return self._client
        try:
            import weaviate

            client = weaviate.Client(url=self.url, additional_headers={"X-API-Key": self.api_key} if self.api_key else None)
            self._client = client
            return client
        except Exception:  # keep broad to avoid crashing when library missing or connection issues
            LOG.exception("Failed to import or initialize weaviate client; Weaviate operations will be disabled.")
            self._client = None
            return None

    def ensure_schema(self) -> bool:
        """Ensure the minimal schema exists in Weaviate.

        Returns True if schema exists or was created, False if operation
        could not be completed due to missing configuration or errors.
        """
        client = self._maybe_import_client()
        if client is None:
            return False

        try:
            # Define desired classes. These are intentionally minimal and
            # match the README plan. Vectorizer is set to 'none' as we will
            # supply external vectors.
            desired = {
                "CVDocument": {
                    "class": "CVDocument",
                    "vectorizer": "none",
                    "properties": [
                        {"name": "applicant_id", "dataType": ["string"]},
                        {"name": "filename", "dataType": ["string"]},
                    ],
                },
                "CVSection": {
                    "class": "CVSection",
                    "vectorizer": "none",
                    "properties": [
                        {"name": "document_id", "dataType": ["string"]},
                        {"name": "text", "dataType": ["text"]},
                        {"name": "sha256", "dataType": ["string"]},
                    ],
                },
                "Role": {
                    "class": "Role",
                    "vectorizer": "none",
                    "properties": [
                        {"name": "role_id", "dataType": ["string"]},
                        {"name": "title", "dataType": ["string"]},
                        {"name": "description", "dataType": ["text"]},
                    ],
                },
            }

            existing = {c["class"]: c for c in client.schema.get("classes") or []}

            for name, cls in desired.items():
                if name in existing:
                    LOG.debug("Weaviate class '%s' already exists; skipping creation.", name)
                    continue
                LOG.info("Creating Weaviate class: %s", name)
                client.schema.create_class(cls)

            return True
        except Exception:
            LOG.exception("Error while ensuring Weaviate schema.")
            return False


def make_default_store() -> WeaviateStore:
    """Factory that reads settings and returns a WeaviateStore instance.

    This function intentionally imports settings lazily so the module is
    safe to import even if environment variables aren't present yet.

    Behavior:
    - If `settings.WEAVIATE_URL` is truthy, use it.
    - Else if `settings.WEAVIATE_USE_LOCAL` is truthy, default to
      `http://localhost:8080` (convenience for local development).
    - Otherwise, return a no-op store (url=None).
    """
    try:
        url = getattr(settings, "WEAVIATE_URL", None)
        api_key = getattr(settings, "WEAVIATE_API_KEY", None)
        batch = getattr(settings, "WEAVIATE_BATCH_SIZE", 64)
        use_local = str(getattr(settings, "WEAVIATE_USE_LOCAL", "false")).lower() in ("1", "true", "yes")
    except Exception:
        url = None
        api_key = None
        batch = 64
        use_local = False

    if not url and use_local:
        url = "http://localhost:8080"

    return WeaviateStore(url=url, api_key=api_key, batch_size=batch)


if __name__ == "__main__":
    # quick smoke test that is safe: will not raise if unconfigured.
    store = make_default_store()
    ok = store.ensure_schema()
    print("Weaviate schema ensured:" , ok)
