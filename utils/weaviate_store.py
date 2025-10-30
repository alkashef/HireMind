"""Weaviate integration helpers used by the HireMind project.

This module provides a small, opinionated wrapper around the `weaviate` Python
client. The main responsibilities are:

- Create an idempotent Weaviate schema for CV and Role documents/sections.
- Provide simple read/write helpers for top-level documents (CVDocument,
    RoleDocument) keyed by content SHA.
- Provide section upsert helpers that attach vector embeddings to section
    objects (CVSection/RoleSection) and keep operations idempotent.
- Provide a convenience orchestrator `process_file_and_upsert()` that ties
    extraction, splitting, embedding, and upserting into a single call.

Design and error-handling notes
- Configuration: values are read from `config.settings.AppConfig` when the
    constructor arguments are not provided. Use env vars or AppConfig to change
    runtime behavior.
- Dependency policy: the module intentionally imports `weaviate` at the top so
    missing dependency errors are visible early (no silent fallbacks).
- Safety: methods that perform network calls raise on fatal client errors; the
    orchestrator is defensive and will still return extraction results when the
    Weaviate client is not configured (useful for local testing).

Quick usage example
        from utils.weaviate_store import WeaviateStore
        ws = WeaviateStore()             # reads settings from AppConfig
        ws.ensure_schema()               # create classes if missing
        res = ws.process_file_and_upsert(Path("/path/to/cv.pdf"))

The module focuses on clarity and determinism rather than providing a
feature-complete ODM. Keep the CSV pipeline unchanged; Weaviate is a
parallel, optional store.
"""
from __future__ import annotations

import os
import json
from typing import Optional, Dict, Any

from config.settings import AppConfig
from utils.logger import AppLogger
from pathlib import Path
from typing import List
from utils.paraphrase_client import get_global_paraphrase_client

# Import weaviate client at module level intentionally: if the dependency is
# missing the import will raise and the calling code/test can decide how to
# handle that (per project policy: no silent fallbacks).
import weaviate


class WeaviateStore:
    """Small wrapper around the `weaviate.Client` that ensures schema exists.

    Constructor parameters are optional to support the local test runner which
    passes explicit values. When an argument is None the value is read from
    `AppConfig()` (which itself reads from config/.env).
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        cfg = AppConfig()
        # keep config on the instance for use by helpers that need ports
        self.cfg = cfg

        # Resolve final runtime values: prefer explicit args, then AppConfig/env
        self.url = (url or cfg.weaviate_url) or (
            "http://localhost:8080" if os.environ.get("WEAVIATE_USE_LOCAL", "").lower() in ("1", "true", "yes") else None
        )
        self.api_key = api_key or cfg.weaviate_api_key
        try:
            self.batch_size = int(batch_size if batch_size is not None else cfg.weaviate_batch_size)
        except Exception:
            self.batch_size = 64

        # Always use project logger
        self.logger = AppLogger(cfg.log_file_path)

        # Create client adaptively to support both v3 and v4 weaviate Python clients.
        # The installed client may expose different constructors/signatures
        # (v3: weaviate.Client(url=..., additional_headers=...),
        #  v4: weaviate.WeaviateClient(...) or weaviate.connect(...)).
        self.client: Optional[object] = None
        if self.url:
            # Prepare auth header if API key provided
            headers = {"X-API-Key": self.api_key} if self.api_key else None
            self.logger.log_kv("WEAVIATE_CLIENT_INIT", url=self.url, batch_size=self.batch_size)
            # Build client using a tolerant strategy and clear logging on failure
            try:
                self.client = self._build_client(headers)
            except Exception as e:
                # Record and re-raise so the test runner / caller sees the cause
                self.logger.log_kv("WEAVIATE_CLIENT_INIT_FAILED", error=str(e))
                raise

        # Local paraphrase embeddings: detect if a local paraphrase model is
        # available and enable embedding-on-application-side if so. The
        # environment variable USE_LOCAL_EMBEDDINGS=1 can also force this.
        self.use_local_embeddings = False
        try:
            use_env = os.environ.get("USE_LOCAL_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes")
            model_dir = Path(self.cfg.paraphrase_model_dir)
            if use_env or (model_dir.exists() and any(model_dir.iterdir())):
                # don't raise here; only enable and lazy-load when needed
                self.use_local_embeddings = True
                self.logger.log_kv("PARAPHRASE_EMBEDDINGS_ENABLED", model_dir=str(model_dir), via_env=use_env)
        except Exception:
            # best-effort detection: if something goes wrong, leave disabled
            self.use_local_embeddings = False

    def _build_client(self, additional_headers: Optional[dict]) -> object:
        """Attempt multiple client construction patterns to support v3 and v4.

        Tries (in order):
          - weaviate.Client(url=..., additional_headers=...) (v3 typical)
          - weaviate.Client(self.url, additional_headers=...)
          - weaviate.WeaviateClient(url=..., additional_headers=...)
          - weaviate.WeaviateClient(self.url, additional_headers=...)
          - weaviate.connect(url=..., additional_headers=...)

        Raises a RuntimeError with collected attempt errors when all fail.
        """
        attempts = []

        # Preferred path for weaviate-client v4: try the high-level connect helper first
        if hasattr(weaviate, "connect"):
            try:
                # try common positional and kwarg forms for connect
                if callable(weaviate.connect):
                    try:
                        return weaviate.connect(self.url)
                    except Exception as e:
                        attempts.append(f"connect(positional): {e}")
                    try:
                        return weaviate.connect(self.url, additional_headers)
                    except Exception as e:
                        attempts.append(f"connect(positional+headers): {e}")
                    try:
                        return weaviate.connect(url=self.url)
                    except Exception as e:
                        attempts.append(f"connect(url=): {e}")
                    try:
                        return weaviate.connect(url=self.url, additional_headers=additional_headers)
                    except Exception as e:
                        attempts.append(f"connect(url+headers): {e}")
                # sometimes connect is a module exposing a connect symbol
                if hasattr(weaviate.connect, "connect") and callable(weaviate.connect.connect):
                    try:
                        return weaviate.connect.connect(self.url)
                    except Exception as e:
                        attempts.append(f"connect.module(positional): {e}")
                    try:
                        return weaviate.connect.connect(self.url, additional_headers)
                    except Exception as e:
                        attempts.append(f"connect.module(positional+headers): {e}")
                    try:
                        return weaviate.connect.connect(url=self.url, additional_headers=additional_headers)
                    except Exception as e:
                        attempts.append(f"connect.module(url+headers): {e}")
            except Exception as e:
                attempts.append(f"v4 connect wrapper: {e}")

        # Try explicit WeaviateClient simple constructors (some v4 layouts support passing url directly)
        if hasattr(weaviate, "WeaviateClient"):
            try:
                return weaviate.WeaviateClient(self.url)
            except Exception as e:
                attempts.append(f"WeaviateClient(positional): {e}")
            try:
                return weaviate.WeaviateClient(url=self.url, additional_headers=additional_headers)
            except Exception as e:
                attempts.append(f"WeaviateClient(url): {e}")
            try:
                return weaviate.WeaviateClient(self.url, additional_headers)
            except Exception as e:
                attempts.append(f"WeaviateClient(positional+headers): {e}")

        # Try constructing typed ConnectionParams/ProtocolParams (v4 strict API)
        try:
            from urllib.parse import urlparse
            import importlib

            conn_mod = None
            for candidate in ("weaviate.connection", "weaviate.connections", "weaviate.connect"):
                try:
                    conn_mod = importlib.import_module(candidate)
                    break
                except Exception:
                    conn_mod = None

            if conn_mod is not None:
                Proto = getattr(conn_mod, "ProtocolParams", None)
                ConnP = getattr(conn_mod, "ConnectionParams", None)
                if Proto is not None and ConnP is not None:
                    parsed = urlparse(self.url)
                    host = parsed.hostname or "localhost"
                    port = parsed.port or (443 if parsed.scheme == "https" else 8080)
                    scheme = parsed.scheme or "http"
                    try:
                        grpc_port = int(getattr(self.cfg, "weaviate_grpc_port", None) or (port + 1))
                    except Exception:
                        grpc_port = port + 1

                    # Build ProtocolParams using the signature found in v4: (host, port, secure)
                    proto_http = None
                    try:
                        secure = True if scheme == "https" else False
                        proto_http = Proto(host=host, port=port, secure=secure)
                    except Exception as e:
                        attempts.append(f"Proto(http host/port/secure): {e}")

                    # Build grpc ProtocolParams (usually not secure unless configured)
                    proto_grpc = None
                    try:
                        proto_grpc = Proto(host=host, port=grpc_port, secure=False)
                    except Exception as e:
                        attempts.append(f"Proto(grpc host/port/secure): {e}")


                    # Build ConnectionParams using keyword-only http/grpc params
                    conn_params = None
                    try:
                        conn_params = ConnP(http=proto_http, grpc=proto_grpc)
                    except Exception as e:
                        attempts.append(f"ConnP(http,grpc): {e}")

                    if conn_params is not None:
                        try:
                            if hasattr(weaviate, "WeaviateClient"):
                                return weaviate.WeaviateClient(conn_params)
                        except Exception as e:
                            attempts.append(f"WeaviateClient(conn_params): {e}")
                        try:
                            if hasattr(weaviate, "connect") and callable(weaviate.connect):
                                return weaviate.connect(conn_params)
                        except Exception as e:
                            attempts.append(f"connect(conn_params): {e}")
        except Exception as e:
            attempts.append(f"v4-connection-param-attempts: {e}")

        # Fallback: older v3-style Client constructor attempts
        if hasattr(weaviate, "Client"):
            try:
                return weaviate.Client(url=self.url, additional_headers=additional_headers)
            except Exception as e:
                attempts.append(f"Client(url): {e}")
            try:
                return weaviate.Client(self.url, additional_headers)
            except Exception as e:
                attempts.append(f"Client(positional): {e}")

        # If we get here, none of the construction attempts worked
        raise RuntimeError(f"Unable to construct weaviate client. Attempts: {attempts}")

    def _class_exists(self, class_name: str) -> bool:
        assert self.client is not None, "Weaviate client not initialized"
        schema = self._schema_get()
        classes = schema.get("classes", []) if isinstance(schema, dict) else []
        for c in classes:
            if c.get("class") == class_name:
                return True
        return False

    # ---------------------- client adapters -------------------------------
    def _schema_get(self) -> Dict[str, Any]:
        """Adapter for retrieving Weaviate schema across client versions."""
        assert self.client is not None, "Weaviate client not initialized"
        attempts: List[str] = []
        client_repr = repr(self.client)

        # common: client.schema.get() or client.schema.get_all()
        if hasattr(self.client, "schema"):
            schema_obj = getattr(self.client, "schema")
            # try get()
            if hasattr(schema_obj, "get"):
                try:
                    return schema_obj.get()
                except Exception as e:
                    attempts.append(f"schema.get() raised: {e}")
            else:
                attempts.append("client.schema.get not present")

            # try get_all()
            if hasattr(schema_obj, "get_all"):
                try:
                    return schema_obj.get_all()
                except Exception as e:
                    attempts.append(f"schema.get_all() raised: {e}")
            else:
                attempts.append("client.schema.get_all not present")
        else:
            attempts.append("client.schema attribute not present")

        # last resort: direct client.get_schema()
        if hasattr(self.client, "get_schema"):
            try:
                return self.client.get_schema()
            except Exception as e:
                attempts.append(f"client.get_schema() raised: {e}")
        else:
            attempts.append("client.get_schema not present")

        # Final fallback: try to fetch schema directly from the Weaviate HTTP API
        # using the configured URL. This covers client shapes that don't expose
        # a schema facade (some v4 client instances) and ensures we can still
        # read the authoritative schema.
        try:
            if self.url:
                schema_url = self.url.rstrip("/") + "/v1/schema"
                try:
                    import requests

                    resp = requests.get(schema_url, timeout=5)
                    if resp.status_code == 200:
                        return resp.json()
                    attempts.append(f"http schema GET status {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    # try urllib fallback
                    try:
                        from urllib.request import urlopen
                        import json as _json

                        with urlopen(schema_url, timeout=5) as fh:
                            return _json.load(fh)
                    except Exception as e2:
                        attempts.append(f"http schema urllib error: {e2}")
        except Exception as e:
            attempts.append(f"http schema attempt: {e}")

        # Provide helpful diagnostics including the client representation
        raise RuntimeError(
            f"Unable to read Weaviate schema. Attempts: {attempts}; client={client_repr}"
        )

    def _schema_create_class(self, class_schema: Dict[str, Any]) -> None:
        """Adapter for creating a class in the Weaviate schema."""
        assert self.client is not None, "Weaviate client not initialized"
        attempts = []
        try:
            if hasattr(self.client, "schema") and hasattr(self.client.schema, "create_class"):
                return self.client.schema.create_class(class_schema)
        except Exception as e:
            attempts.append(f"schema.create_class(): {e}")
        try:
            if hasattr(self.client, "schema") and hasattr(self.client.schema, "create"):
                return self.client.schema.create(class_schema)
        except Exception as e:
            attempts.append(f"schema.create(): {e}")
        # Final fallback: use the HTTP REST API to create the class directly.
        try:
            if self.url:
                schema_url = self.url.rstrip("/") + "/v1/schema"
                try:
                    import requests

                    resp = requests.post(schema_url, json=class_schema, timeout=10)
                    if resp.status_code in (200, 201):
                        self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_CREATED", class_name=class_schema.get("class"))
                        return None
                    attempts.append(f"http POST status {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    # urllib fallback
                    try:
                        from urllib.request import Request, urlopen
                        import json as _json

                        data = _json.dumps(class_schema).encode("utf-8")
                        req = Request(schema_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
                        with urlopen(req, timeout=10) as fh:
                            # assume success if no exception; try to read result
                            _ = fh.read()
                            self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_CREATED", class_name=class_schema.get("class"))
                            return None
                    except Exception as e2:
                        attempts.append(f"http urllib POST error: {e2}")
        except Exception as e:
            attempts.append(f"http schema create attempt: {e}")

        raise RuntimeError(f"Unable to create Weaviate class. Attempts: {attempts}")

    def _data_object_create(self, props: Dict[str, Any], class_name: str):
        """Adapter for creating a data object. Returns created id or raw result."""
        assert self.client is not None, "Weaviate client not initialized"
        attempts: List[str] = []
        # Optional `vector` param can be passed by callers when application
        # computes embeddings locally. We accept a vector kwarg via props or
        # separate call-site; check for a special key '_vector' in props.
        vector = None
        if isinstance(props, dict) and "_vector" in props:
            vector = props.pop("_vector")

        # v4: client.data_object.create(properties, class_name, vector=...)
        try:
            if hasattr(self.client, "data_object") and hasattr(self.client.data_object, "create"):
                try:
                    if vector is not None:
                        return self.client.data_object.create(props, class_name, vector=vector)
                    return self.client.data_object.create(props, class_name)
                except TypeError:
                    # signature may differ; try alternate ordering
                    if vector is not None:
                        return self.client.data_object.create(class_name, props, vector)
                    return self.client.data_object.create(class_name, props)
        except Exception as e:
            attempts.append(f"data_object.create(...): {e}")

        # older or alternate API: client.data.create(...)
        try:
            if hasattr(self.client, "data") and hasattr(self.client.data, "create"):
                # try: data.create(class_name, props, vector=...)
                try:
                    if vector is not None:
                        return self.client.data.create(class_name, props, vector=vector)
                    return self.client.data.create(class_name, props)
                except TypeError:
                    # try reversed ordering
                    if vector is not None:
                        return self.client.data.create(props, class_name, vector)
                    try:
                        return self.client.data.create(props, class_name)
                    except Exception:
                        # final fallback try
                        return self.client.data.create(class_name, props)
        except Exception as e:
            attempts.append(f"data.create(...): {e}")

        # Final fallback: create object using Weaviate HTTP REST API (/v1/objects)
        try:
            if self.url:
                objects_url = self.url.rstrip("/") + "/v1/objects"
                payload_json = {"class": class_name, "properties": props}
                if vector is not None:
                    payload_json["vector"] = vector
                try:
                    import requests

                    resp = requests.post(objects_url, json=payload_json, timeout=10)
                    if resp.status_code in (200, 201):
                        # weaviate returns {'id': '<uuid>'} on success
                        try:
                            j = resp.json()
                            return j.get("id") or j
                        except Exception:
                            return resp.text
                    attempts.append(f"http objects POST status {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    # urllib fallback
                    try:
                        from urllib.request import Request, urlopen
                        import json as _json

                        data = _json.dumps(payload_json).encode("utf-8")
                        req = Request(objects_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
                        with urlopen(req, timeout=10) as fh:
                            data = fh.read()
                            try:
                                j = _json.loads(data)
                                return j.get("id") or j
                            except Exception:
                                return data.decode("utf-8", errors="ignore")
                    except Exception as e2:
                        attempts.append(f"http objects urllib error: {e2}")
        except Exception as e:
            attempts.append(f"http objects attempt: {e}")

        raise RuntimeError(f"Unable to create data object. Attempts: {attempts}")

    def _data_object_update(self, props: Dict[str, Any], class_name: str, uuid: str) -> None:
        """Adapter for updating a data object by uuid."""
        assert self.client is not None, "Weaviate client not initialized"
        attempts: List[str] = []
        vector = None
        if isinstance(props, dict) and "_vector" in props:
            vector = props.pop("_vector")

        try:
            if hasattr(self.client, "data_object") and hasattr(self.client.data_object, "update"):
                # try common signature: update(properties, class_name, uuid=...)
                try:
                    if vector is not None:
                        return self.client.data_object.update(props, class_name, uuid=uuid, vector=vector)
                    return self.client.data_object.update(props, class_name, uuid=uuid)
                except TypeError:
                    # some older signatures expect (uuid, properties)
                    if vector is not None:
                        return self.client.data_object.update(uuid, props, vector)
                    return self.client.data_object.update(uuid, props)
        except Exception as e:
            attempts.append(f"data_object.update(...): {e}")

        try:
            if hasattr(self.client, "data") and hasattr(self.client.data, "update"):
                try:
                    if vector is not None:
                        return self.client.data.update(class_name, uuid, props, vector=vector)
                    return self.client.data.update(class_name, uuid, props)
                except Exception:
                    if vector is not None:
                        return self.client.data.update(uuid, class_name, props, vector)
                    return self.client.data.update(uuid, class_name, props)
        except Exception as e:
            attempts.append(f"data.update(...): {e}")

        raise RuntimeError(f"Unable to update data object. Attempts: {attempts}")

    def _query_do(self, class_name: str, props: List[str], where: Optional[dict] = None, additional: Optional[List[str]] = None) -> dict:
        """Adapter to perform a GraphQL-style get query with optional where/additional."""
        assert self.client is not None, "Weaviate client not initialized"
        attempts = []
        try:
            if hasattr(self.client, "query") and hasattr(self.client.query, "get"):
                q = self.client.query.get(class_name, props)
                if where is not None and hasattr(q, "with_where"):
                    q = q.with_where(where)
                if additional is not None and hasattr(q, "with_additional"):
                    q = q.with_additional(additional)
                if hasattr(q, "do"):
                    return q.do()
        except Exception as e:
            attempts.append(f"query.get().do(): {e}")
        # fallback: some clients expose a raw_graphql or graphql method
        try:
            if hasattr(self.client, "graphql"):
                # attempt a minimal query build
                where_clause = ""
                if where:
                    # best-effort conversion; leave to server if not supported
                    where_clause = ""
                # Ensure we request _additional.id so callers can locate object ids
                fields = "\n".join(props)
                if "_additional" not in fields:
                    fields = fields + "\n_additional { id }"
                gql = f"{{Get{{{class_name}{{{fields}}}}}}}"
                return self.client.graphql(gql)
        except Exception as e:
            attempts.append(f"graphql(...): {e}")
        # Final fallback: call the Weaviate GraphQL HTTP endpoint directly
        try:
            if self.url:
                gql_url = self.url.rstrip("/") + "/v1/graphql"
                # Build a simple GraphQL Get query with optional where clause
                fields = "\n".join(props)
                where_str = ""
                if where and isinstance(where, dict):
                    try:
                        # support simple equality where with single path
                        path = where.get("path") or []
                        op = where.get("operator")
                        # valueString/valueNumber handling
                        val_str = None
                        if "valueString" in where:
                            import json as _json

                            # JSON-encode the string value to ensure escaping
                            val_str = _json.dumps(where.get("valueString"))
                        elif "valueNumber" in where:
                            val_str = str(where.get("valueNumber"))

                        if path and op and val_str is not None:
                            # Build inline where clause
                            # Example: where:{path:["sha"],operator:Equal,valueString:"abc"}
                            where_str = f"(where:{{path:[\"{path[0]}\"],operator:{op},valueString:{val_str}}})"
                    except Exception as e:
                        attempts.append(f"where-build-error: {e}")

                gql = f"{{Get{{{class_name}{where_str}{{{fields}}}}}}}"
                try:
                    import requests

                    resp = requests.post(gql_url, json={"query": gql}, timeout=10)
                    if resp.status_code == 200:
                        return resp.json()
                    attempts.append(f"http graphql status {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    try:
                        # urllib fallback
                        from urllib.request import Request, urlopen
                        import json as _json

                        data = _json.dumps({"query": gql}).encode("utf-8")
                        req = Request(gql_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
                        with urlopen(req, timeout=10) as fh:
                            data = fh.read()
                            try:
                                return _json.loads(data)
                            except Exception:
                                return {"data": {}}
                    except Exception as e2:
                        attempts.append(f"http graphql urllib error: {e2}")
        except Exception as e:
            attempts.append(f"http graphql attempt: {e}")

        raise RuntimeError(f"Unable to run query. Attempts: {attempts}")

    def ensure_schema(self) -> bool:
        """Ensure the minimal schema exists in Weaviate.

        Creates the following classes if missing:
          - CVDocument
          - CVSection
          - RoleDocument
          - RoleSection

        Returns True on success. Raises on client/server errors.
        """
        if not self.url or not self.client:
            raise RuntimeError("Weaviate URL not configured; cannot ensure schema")

        # Small runtime check: verify the Weaviate server exposes the expected
        # vectorizer module before creating classes. This is a fast, explicit
        # test that fails early with a clear message when the server is not
        # configured for native vectorization as the repository schema expects.
        # You can bypass this check for local convenience by setting
        # SKIP_WEAVIATE_VECTORIZER_CHECK=1 in your environment (not recommended
        # for production as it may mask misconfiguration).
        required_vectorizer = "text2vec-transformers"
        skip_check = os.environ.get("SKIP_WEAVIATE_VECTORIZER_CHECK", "0").strip() in ("1", "true", "yes")
        # If local paraphrase embeddings are enabled, skip the server-side
        # vectorizer module check because the application will supply vectors.
        if self.use_local_embeddings:
            skip_check = True
            self.logger.log_kv("WEAVIATE_VECTORIZER_CHECK_AUTOSKIPPED", reason="local_paraphrase_model")
        if skip_check:
            self.logger.log_kv("WEAVIATE_VECTORIZER_CHECK_SKIPPED", url=self.url)
            # skip the modules check entirely
            modules_json = {"modules": ["<skipped>"]}
        else:
            try:
                # Prefer requests (common); fall back to urllib to avoid adding new deps.
                modules_url = self.url.rstrip("/") + "/v1/modules"
                modules_json = None
                try:
                    import requests

                    resp = requests.get(modules_url, timeout=5)
                    if resp.status_code == 200:
                        modules_json = resp.json()
                except Exception:
                    # fallback: urllib
                    try:
                        from urllib.request import urlopen
                        import json as _json

                        with urlopen(modules_url, timeout=5) as fh:
                            modules_json = _json.load(fh)
                    except Exception:
                        modules_json = None

                modules_list = []
                if isinstance(modules_json, dict):
                    # Try common shapes: {'modules': [{'name': 'text2vec-transformers', ...}, ...]}
                    if "modules" in modules_json and isinstance(modules_json["modules"], list):
                        for m in modules_json["modules"]:
                            if isinstance(m, dict):
                                name = m.get("name") or m.get("module")
                                if name:
                                    modules_list.append(name)
                            elif isinstance(m, str):
                                modules_list.append(m)
                    else:
                        # Some versions may return a flat list or other shape; stringify as fallback
                        modules_list = [str(modules_json)]

                if not any(required_vectorizer in m for m in modules_list):
                    raise RuntimeError(
                        f"Required Weaviate vectorizer module '{required_vectorizer}' not available on server {self.url}; found: {modules_list}"
                    )
            except Exception as e:
                # Bubble up with a clear message for the caller/tests to act on.
                self.logger.log_kv("WEAVIATE_VECTORIZER_CHECK_FAILED", error=str(e))
                raise

        # Define class schemas (vectorizer configured in external schema file)
        # Explicit CVDocument properties mapped to CSV columns used by app.py
        cv_properties = [
            {"name": "sha", "dataType": ["string"]},
            {"name": "timestamp", "dataType": ["string"]},
            {"name": "cv", "dataType": ["string"]},
            {"name": "filename", "dataType": ["string"]},
            {"name": "personal_first_name", "dataType": ["string"]},
            {"name": "personal_last_name", "dataType": ["string"]},
            {"name": "personal_full_name", "dataType": ["string"]},
            {"name": "personal_email", "dataType": ["string"]},
            {"name": "personal_phone", "dataType": ["string"]},
            {"name": "professional_misspelling_count", "dataType": ["int"]},
            {"name": "professional_misspelled_words", "dataType": ["text"]},
            {"name": "professional_visual_cleanliness", "dataType": ["string"]},
            {"name": "professional_look", "dataType": ["string"]},
            {"name": "professional_formatting_consistency", "dataType": ["string"]},
            {"name": "experience_years_since_graduation", "dataType": ["int"]},
            {"name": "experience_total_years", "dataType": ["int"]},
            {"name": "experience_employer_names", "dataType": ["text"]},
            {"name": "stability_employers_count", "dataType": ["int"]},
            {"name": "stability_avg_years_per_employer", "dataType": ["string"]},
            {"name": "stability_years_at_current_employer", "dataType": ["string"]},
            {"name": "socio_address", "dataType": ["text"]},
            {"name": "socio_alma_mater", "dataType": ["string"]},
            {"name": "socio_high_school", "dataType": ["string"]},
            {"name": "socio_education_system", "dataType": ["string"]},
            {"name": "socio_second_foreign_language", "dataType": ["string"]},
            {"name": "flag_stem_degree", "dataType": ["string"]},
            {"name": "flag_military_service_status", "dataType": ["string"]},
            {"name": "flag_worked_at_financial_institution", "dataType": ["string"]},
            {"name": "flag_worked_for_egyptian_government", "dataType": ["string"]},
            {"name": "full_text", "dataType": ["text"]},
        ]

        cv_section_props = [
            {"name": "parent_sha", "dataType": ["string"]},
            {"name": "section_type", "dataType": ["string"]},
            {"name": "section_text", "dataType": ["text"]},
        ]

        # Role documents mirror CV but with a RoleTitle field commonly used
        role_properties = [
            {"name": "sha", "dataType": ["string"]},
            {"name": "timestamp", "dataType": ["string"]},
            {"name": "filename", "dataType": ["string"]},
            {"name": "role_title", "dataType": ["string"]},
            {"name": "full_text", "dataType": ["text"]},
        ]

        role_section_props = cv_section_props
        role_section_props = cv_section_props

        # Load schema path from AppConfig (required). The application will
        # crash if the configuration is missing or the file cannot be read so
        # that schema management is an explicit operational step.
        schema_path_cfg = self.cfg.weaviate_schema_path
        if not schema_path_cfg:
            raise RuntimeError(
                "WEAVIATE_SCHEMA_PATH not set in config/.env or environment; schema is required"
            )

        schema_path = Path(schema_path_cfg)
        # If a relative path was provided, resolve it relative to the repo root
        if not schema_path.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent
            schema_path = (repo_root / schema_path).resolve()

        if not schema_path.exists():
            raise RuntimeError(f"Weaviate schema file not found at: {schema_path}")

        with schema_path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)

        # Expect either {"classes": {...}} or a direct classes mapping
        if isinstance(loaded, dict) and "classes" in loaded:
            classes = loaded["classes"]
        elif isinstance(loaded, dict):
            classes = loaded
        else:
            raise RuntimeError(f"Invalid weaviate schema format in {schema_path}")

        # Create missing classes only
        # If we're providing local embeddings, adapt the external schema so
        # classes that request server-side `text2vec-transformers` are
        # converted to `none` (server not running that module in dev).
        if self.use_local_embeddings and isinstance(classes, dict):
            for _nm, sch in classes.items():
                try:
                    vec = sch.get("vectorizer") if isinstance(sch, dict) else None
                    if isinstance(vec, str) and "text2vec-transformers" in vec.lower():
                        # mutate schema in-memory for local dev
                        sch["vectorizer"] = "none"
                        self.logger.log_kv("WEAVIATE_SCHEMA_ADJUSTED", class_name=_nm, from_vectorizer=vec, to_vectorizer="none")
                except Exception:
                    # best-effort: don't fail if schema shape unexpected
                    continue

        created = []
        for name, schema in classes.items():
            if not self._class_exists(name):
                self.logger.log_kv("WEAVIATE_CREATE_CLASS", class_name=name)
                self._schema_create_class(schema)
                created.append(name)
            else:
                self.logger.log_kv("WEAVIATE_CLASS_EXISTS", class_name=name)

        self.logger.log_kv("WEAVIATE_SCHEMA_ENSURED", created=",".join(created) if created else "none")
        return True

    # ---------------------------- CV helpers ---------------------------------
    def _find_cv_by_sha(self, sha: str) -> Optional[Dict[str, Any]]:
        """Return the first CVDocument object matching sha or None.

        Returns a dict with keys 'id' and 'properties' when found.
        """
        if not self.client:
            raise RuntimeError("Weaviate client not initialized")

        try:
            where = {
                "path": ["sha"],
                "operator": "Equal",
                "valueString": sha,
            }
            # request the explicit CVDocument properties declared in the schema
            props = [
                "sha",
                "timestamp",
                "cv",
                "filename",
                "personal_first_name",
                "personal_last_name",
                "personal_full_name",
                "personal_email",
                "personal_phone",
                "professional_misspelling_count",
                "professional_misspelled_words",
                "professional_visual_cleanliness",
                "professional_look",
                "professional_formatting_consistency",
                "experience_years_since_graduation",
                "experience_total_years",
                "experience_employer_names",
                "stability_employers_count",
                "stability_avg_years_per_employer",
                "stability_years_at_current_employer",
                "socio_address",
                "socio_alma_mater",
                "socio_high_school",
                "socio_education_system",
                "socio_second_foreign_language",
                "flag_stem_degree",
                "flag_military_service_status",
                "flag_worked_at_financial_institution",
                "flag_worked_for_egyptian_government",
                "full_text",
            ]

            res = self._query_do("CVDocument", props, where)
            objs = res.get("data", {}).get("Get", {}).get("CVDocument", [])
            if objs:
                first = objs[0]
                return {"id": first.get("id") or (first.get("_additional") or {}).get("id"), "properties": first}
            return None
        except Exception as e:
            self.logger.log_kv("WEAVIATE_QUERY_ERROR", error=str(e))
            raise

    def write_cv_to_db(self, sha: str, filename: str, full_text: str, attributes: Dict[str, object]) -> Dict[str, object]:
        """Create or update a CVDocument object keyed by `sha`.

        Maps the provided `attributes` dict into the explicit CVDocument
        properties declared in the schema (instead of storing a single
        JSON-encoded `metadata` blob). The `full_text` is stored in the
        `full_text` property. Returns the created/updated object's id and
        stored properties.
        """
        if not self.client:
            raise RuntimeError("Weaviate client not initialized")

        # Map attributes into explicit CVDocument properties. Use sensible
        # defaults when a key is missing to avoid nulls in Weaviate where
        # possible. The 'attributes' dict is expected to contain keys that map
        # to the CSV columns; we only read known fields here.
        props = {
            "sha": sha,
            "timestamp": attributes.get("timestamp", ""),
            "cv": attributes.get("cv", ""),
            "filename": filename,
            "personal_first_name": attributes.get("personal_first_name", ""),
            "personal_last_name": attributes.get("personal_last_name", ""),
            "personal_full_name": attributes.get("personal_full_name", ""),
            "personal_email": attributes.get("personal_email", ""),
            "personal_phone": attributes.get("personal_phone", ""),
            "professional_misspelling_count": attributes.get("professional_misspelling_count", None),
            "professional_misspelled_words": attributes.get("professional_misspelled_words", ""),
            "professional_visual_cleanliness": attributes.get("professional_visual_cleanliness", ""),
            "professional_look": attributes.get("professional_look", ""),
            "professional_formatting_consistency": attributes.get("professional_formatting_consistency", ""),
            "experience_years_since_graduation": attributes.get("experience_years_since_graduation", None),
            "experience_total_years": attributes.get("experience_total_years", None),
            "experience_employer_names": attributes.get("experience_employer_names", ""),
            "stability_employers_count": attributes.get("stability_employers_count", None),
            "stability_avg_years_per_employer": attributes.get("stability_avg_years_per_employer", ""),
            "stability_years_at_current_employer": attributes.get("stability_years_at_current_employer", ""),
            "socio_address": attributes.get("socio_address", ""),
            "socio_alma_mater": attributes.get("socio_alma_mater", ""),
            "socio_high_school": attributes.get("socio_high_school", ""),
            "socio_education_system": attributes.get("socio_education_system", ""),
            "socio_second_foreign_language": attributes.get("socio_second_foreign_language", ""),
            "flag_stem_degree": attributes.get("flag_stem_degree", ""),
            "flag_military_service_status": attributes.get("flag_military_service_status", ""),
            "flag_worked_at_financial_institution": attributes.get("flag_worked_at_financial_institution", ""),
            "flag_worked_for_egyptian_government": attributes.get("flag_worked_for_egyptian_government", ""),
            "full_text": full_text,
        }

        found = self._find_cv_by_sha(sha)
        if found:
            obj_id = found.get("id")
            # update existing
            self._data_object_update(props, "CVDocument", obj_id)
            self.logger.log_kv("WEAVIATE_CV_UPDATED", id=obj_id, sha=sha)
            return {"id": obj_id, "properties": props}
        else:
            obj_id = self._data_object_create(props, "CVDocument")
            # created id may be dict or raw id
            nid = obj_id.get("id") if isinstance(obj_id, dict) else obj_id
            self.logger.log_kv("WEAVIATE_CV_CREATED", id=nid, sha=sha)
            return {"id": obj_id, "properties": props}

    def read_cv_from_db(self, sha: str) -> Optional[Dict[str, object]]:
        """Read CVDocument by sha and return attributes and full_text.

        Returns a dict with keys: id, sha, filename, attributes (dict), full_text.
        """
        if not self.client:
            raise RuntimeError("Weaviate client not initialized")

        found = self._find_cv_by_sha(sha)
        if not found:
            return None
        props = found.get("properties", {}) or {}

        # Build a simplified result exposing the explicit fields and a
        # convenience `attributes` dict containing the other CSV-mapped values.
        attributes = {
            "timestamp": props.get("timestamp"),
            "cv": props.get("cv"),
            "personal_first_name": props.get("personal_first_name"),
            "personal_last_name": props.get("personal_last_name"),
            "personal_full_name": props.get("personal_full_name"),
            "personal_email": props.get("personal_email"),
            "personal_phone": props.get("personal_phone"),
            "professional_misspelling_count": props.get("professional_misspelling_count"),
            "professional_misspelled_words": props.get("professional_misspelled_words"),
            "professional_visual_cleanliness": props.get("professional_visual_cleanliness"),
            "professional_look": props.get("professional_look"),
            "professional_formatting_consistency": props.get("professional_formatting_consistency"),
            "experience_years_since_graduation": props.get("experience_years_since_graduation"),
            "experience_total_years": props.get("experience_total_years"),
            "experience_employer_names": props.get("experience_employer_names"),
            "stability_employers_count": props.get("stability_employers_count"),
            "stability_avg_years_per_employer": props.get("stability_avg_years_per_employer"),
            "stability_years_at_current_employer": props.get("stability_years_at_current_employer"),
            "socio_address": props.get("socio_address"),
            "socio_alma_mater": props.get("socio_alma_mater"),
            "socio_high_school": props.get("socio_high_school"),
            "socio_education_system": props.get("socio_education_system"),
            "socio_second_foreign_language": props.get("socio_second_foreign_language"),
            "flag_stem_degree": props.get("flag_stem_degree"),
            "flag_military_service_status": props.get("flag_military_service_status"),
            "flag_worked_at_financial_institution": props.get("flag_worked_at_financial_institution"),
            "flag_worked_for_egyptian_government": props.get("flag_worked_for_egyptian_government"),
        }

        result = {
            "id": found.get("id"),
            "sha": props.get("sha"),
            "filename": props.get("filename"),
            "attributes": attributes,
            "full_text": props.get("full_text"),
        }
        return result

    # ------------------------- sections & processing -----------------------
    def _split_into_sections(self, text: str, max_chars: int = 800) -> List[dict]:
        """Deterministic text splitter used to create section candidates.

        This splitter is intentionally simple and deterministic: it first
        breaks the document by blank-line paragraph boundaries and then
        accumulates paragraphs into chunks of approximately ``max_chars``
        characters. The approach favors readability and reproducibility over
        semantic boundaries.

        Parameters
        - text: full document text (non-empty string)
        - max_chars: target maximum characters per resulting section

        Returns
        - list[dict]: each dict contains:
            - 'section_type' (currently always 'section')
            - 'section_text' (string)

        Notes
        - The function guarantees at least one section for non-empty input.
        - Keep this function lightweight so it can be called in-process for
        many documents without heavy CPU/memory use.
        """
        if not text:
            return []
        # Split into paragraphs by blank lines first
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        sections: List[dict] = []
        buf = []
        buf_len = 0
        for p in paras:
            plen = len(p)
            if buf_len + plen + 2 > max_chars and buf:
                sections.append({"section_type": "section", "section_text": "\n\n".join(buf).strip()})
                buf = [p]
                buf_len = plen
            else:
                buf.append(p)
                buf_len += plen + 2
        if buf:
            sections.append({"section_type": "section", "section_text": "\n\n".join(buf).strip()})
        return sections

    def _find_section_by_parent_and_text(self, parent_sha: str, section_text: str) -> Optional[Dict[str, object]]:
        """Return existing CVSection object matching parent_sha and section_text, or None."""
        if not self.client:
            return None
        try:
            where = {"path": ["parent_sha"], "operator": "Equal", "valueString": parent_sha}
            res = self._query_do("CVSection", ["parent_sha", "section_type", "section_text"], where, additional=["id"])
            items = res.get("data", {}).get("Get", {}).get("CVSection", [])
            for it in items:
                txt = it.get("section_text") or ""
                if txt.strip() == (section_text or "").strip():
                    return {"id": it.get("_additional", {}).get("id") or it.get("id"), "properties": it}
            return None
        except Exception as e:
            self.logger.log_kv("WEAVIATE_SECTION_QUERY_ERROR", error=str(e))
            return None

    def upsert_cv_section(self, parent_sha: str, section_type: str, section_text: str) -> Dict[str, object]:
        """Create or update a CVSection. Uses (parent_sha, section_text) to dedupe.

        Returns dict: {id, created(bool), weaviate_ok(bool)}.
        """
        if not self.client:
            return {"id": None, "created": False, "weaviate_ok": False}

        props = {"parent_sha": parent_sha, "section_type": section_type, "section_text": section_text}
        try:
            found = self._find_section_by_parent_and_text(parent_sha, section_text)
            if found:
                obj_id = found.get("id")
                # update (compute and attach vector if local embeddings enabled)
                if self.use_local_embeddings:
                    try:
                        pc = get_global_paraphrase_client(self.cfg)
                        vec = pc.text_to_embedding(section_text)
                        props_with_vec = dict(props)
                        props_with_vec["_vector"] = vec
                        self._data_object_update(props_with_vec, "CVSection", obj_id)
                    except Exception as e:
                        # if embeddings fail, fall back to update without vector
                        self.logger.log_kv("PARAPHRASE_EMBED_ERROR", error=str(e), sha=parent_sha)
                        self._data_object_update(props, "CVSection", obj_id)
                else:
                    self._data_object_update(props, "CVSection", obj_id)
                self.logger.log_kv("WEAVIATE_CVSECTION_UPDATED", id=obj_id, parent_sha=parent_sha)
                return {"id": obj_id, "created": False, "weaviate_ok": True}
            else:
                # create (compute embedding locally if enabled and pass to server)
                if self.use_local_embeddings:
                    try:
                        pc = get_global_paraphrase_client(self.cfg)
                        vec = pc.text_to_embedding(section_text)
                        props_with_vec = dict(props)
                        props_with_vec["_vector"] = vec
                        new_id = self._data_object_create(props_with_vec, "CVSection")
                    except Exception as e:
                        self.logger.log_kv("PARAPHRASE_EMBED_ERROR", error=str(e), sha=parent_sha)
                        new_id = self._data_object_create(props, "CVSection")
                else:
                    new_id = self._data_object_create(props, "CVSection")
                nid = new_id.get("id") if isinstance(new_id, dict) else new_id
                self.logger.log_kv("WEAVIATE_CVSECTION_CREATED", id=nid, parent_sha=parent_sha)
                return {"id": nid, "created": True, "weaviate_ok": True}
        except Exception as e:
            self.logger.log_kv("WEAVIATE_CVSECTION_UPSERT_ERROR", error=str(e), parent_sha=parent_sha)
            return {"id": None, "created": False, "weaviate_ok": False}

    def write_role_to_db(self, sha: str, filename: str, full_text: str, attributes: Dict[str, object]) -> Dict[str, object]:
        """Create or update a RoleDocument object keyed by `sha`.

        Mirrors `write_cv_to_db` but targets the RoleDocument class and stores
        role-specific properties (role_title, full_text, etc.). Returns the
        created/updated object's id and stored properties.
        """
        if not self.client:
            raise RuntimeError("Weaviate client not initialized")

        props = {
            "sha": sha,
            "timestamp": attributes.get("timestamp", ""),
            "filename": filename,
            "role_title": attributes.get("role_title", ""),
            "full_text": full_text,
        }

        found = None
        try:
            where = {"path": ["sha"], "operator": "Equal", "valueString": sha}
            res = self._query_do("RoleDocument", ["sha"], where)
            objs = res.get("data", {}).get("Get", {}).get("RoleDocument", [])
            if objs:
                found = objs[0]
        except Exception:
            pass

        if found:
            obj_id = found.get("id") or (found.get("_additional") or {}).get("id")
            self._data_object_update(props, "RoleDocument", obj_id)
            self.logger.log_kv("WEAVIATE_ROLE_UPDATED", id=obj_id, sha=sha)
            return {"id": obj_id, "properties": props}
        else:
            obj_id = self._data_object_create(props, "RoleDocument")
            self.logger.log_kv("WEAVIATE_ROLE_CREATED", id=(obj_id.get("id") if isinstance(obj_id, dict) else obj_id), sha=sha)
            return {"id": obj_id, "properties": props}

    def read_role_from_db(self, sha: str) -> Optional[Dict[str, object]]:
        """Read RoleDocument by sha. Returns same shape as read_cv_from_db."""
        if not self.client:
            raise RuntimeError("Weaviate client not initialized")

        try:
            where = {"path": ["sha"], "operator": "Equal", "valueString": sha}
            res = self._query_do("RoleDocument", ["sha", "filename", "role_title", "full_text"], where, additional=["id"])
            items = res.get("data", {}).get("Get", {}).get("RoleDocument", [])
            if not items:
                return None
            first = items[0]
            return {
                "id": first.get("_additional", {}).get("id") or first.get("id"),
                "sha": first.get("sha"),
                "filename": first.get("filename"),
                "attributes": {"role_title": first.get("role_title")},
                "full_text": first.get("full_text"),
            }
        except Exception as e:
            self.logger.log_kv("WEAVIATE_ROLE_READ_ERROR", error=str(e), sha=sha)
            return None

    def upsert_role_section(self, parent_sha: str, section_type: str, section_text: str) -> Dict[str, object]:
        """Create or update a RoleSection object; mirrors CV section upsert."""
        if not self.client:
            return {"id": None, "created": False, "weaviate_ok": False}
        props = {"parent_sha": parent_sha, "section_type": section_type, "section_text": section_text}
        try:
            # simple dedupe by parent + exact section_text
            where = {"path": ["parent_sha"], "operator": "Equal", "valueString": parent_sha}
            res = self._query_do("RoleSection", ["parent_sha", "section_text"], where, additional=["id"])
            items = res.get("data", {}).get("Get", {}).get("RoleSection", [])
            for it in items:
                if (it.get("section_text") or "").strip() == (section_text or "").strip():
                    obj_id = it.get("_additional", {}).get("id") or it.get("id")
                    # update with local embedding if enabled
                    if self.use_local_embeddings:
                        try:
                            pc = get_global_paraphrase_client(self.cfg)
                            vec = pc.text_to_embedding(section_text)
                            props_with_vec = dict(props)
                            props_with_vec["_vector"] = vec
                            self._data_object_update(props_with_vec, "RoleSection", obj_id)
                        except Exception as e:
                            self.logger.log_kv("PARAPHRASE_EMBED_ERROR", error=str(e), sha=parent_sha)
                            self._data_object_update(props, "RoleSection", obj_id)
                    else:
                        self._data_object_update(props, "RoleSection", obj_id)
                    self.logger.log_kv("WEAVIATE_ROLESECTION_UPDATED", id=obj_id, parent_sha=parent_sha)
                    return {"id": obj_id, "created": False, "weaviate_ok": True}
            # create (compute embedding locally if enabled and pass to server)
            if self.use_local_embeddings:
                try:
                    pc = get_global_paraphrase_client(self.cfg)
                    vec = pc.text_to_embedding(section_text)
                    props_with_vec = dict(props)
                    props_with_vec["_vector"] = vec
                    new_id = self._data_object_create(props_with_vec, "RoleSection")
                except Exception as e:
                    self.logger.log_kv("PARAPHRASE_EMBED_ERROR", error=str(e), sha=parent_sha)
                    new_id = self._data_object_create(props, "RoleSection")
            else:
                new_id = self._data_object_create(props, "RoleSection")
            nid = new_id.get("id") if isinstance(new_id, dict) else new_id
            self.logger.log_kv("WEAVIATE_ROLESECTION_CREATED", id=nid, parent_sha=parent_sha)
            return {"id": nid, "created": True, "weaviate_ok": True}
        except Exception as e:
            self.logger.log_kv("WEAVIATE_ROLESECTION_UPSERT_ERROR", error=str(e), parent_sha=parent_sha)
            return {"id": None, "created": False, "weaviate_ok": False}

    def process_file_and_upsert(self, path: Path, is_role: bool = False) -> Dict[str, object]:
        """Orchestrate extract -> split -> embed -> upsert.

        This function is best-effort: if Weaviate is not configured it will
        still extract text and compute the file SHA, but will return
        weaviate_ok=False and will not raise.
        Returns: {sha, filename, num_sections, weaviate_ok, errors: []}
        """
        from utils.extractors import compute_sha256_bytes, pdf_to_text, docx_to_text
        import traceback

        result = {"sha": None, "filename": None, "num_sections": 0, "weaviate_ok": False, "errors": []}
        p = Path(path)
        if not p.exists() or not p.is_file():
            result["errors"].append(f"File not found: {p}")
            return result

        try:
            data = p.read_bytes()
            sha = compute_sha256_bytes(data)
            result["sha"] = sha
            result["filename"] = p.name

            # Extract text depending on suffix
            text = ""
            if p.suffix.lower() == ".pdf":
                text = pdf_to_text(p)
            elif p.suffix.lower() == ".docx":
                text = docx_to_text(p)
            else:
                text = p.read_text(encoding="utf-8", errors="ignore")

            # Basic attributes
            attrs = {"timestamp": "", "filename": p.name}
            if is_role:
                attrs["role_title"] = p.stem

            # Attempt to write the document if client is present
            if self.client:
                try:
                    if is_role:
                        self.write_role_to_db(sha, p.name, text, attrs)
                    else:
                        self.write_cv_to_db(sha, p.name, text, attrs)
                except Exception as e:
                    self.logger.log_kv("WEAVIATE_DOC_UPSERT_ERROR", error=str(e), file=str(p))

            # Split into sections and upsert each with embeddings
            sections = self._split_into_sections(text)
            result["num_sections"] = len(sections)
            all_ok = True
            for sec in sections:
                sec_text = sec.get("section_text", "")
                sec_type = sec.get("section_type", "section")
                # Let Weaviate compute vectors natively; do not compute or pass
                # embeddings from the application to avoid duplication and
                # respect the external schema contract.
                if self.client:
                    try:
                        if is_role:
                            up = self.upsert_role_section(sha, sec_type, sec_text)
                        else:
                            up = self.upsert_cv_section(sha, sec_type, sec_text)
                        if not up.get("weaviate_ok"):
                            all_ok = False
                    except Exception as e:
                        all_ok = False
                        self.logger.log_kv("WEAVIATE_SECTION_UPSERT_EXCEPTION", error=str(e))
                        result["errors"].append(traceback.format_exc())

            result["weaviate_ok"] = bool(self.client) and all_ok
            return result
        except Exception as e:
            self.logger.log_kv("PROCESS_FILE_ERROR", error=str(e), file=str(p))
            result["errors"].append(str(e))
            return result
 

