"""Weaviate integration helpers used by the HireMind project.

This module provides a small, opinionated wrapper around the `weaviate` Python
client. The main responsibilities are:

- Create an idempotent Weaviate schema for CV and Role documents (no sections).
- Provide simple read/write helpers for top-level documents (CVDocument,
    RoleDocument) keyed by content SHA.
- Provide a convenience orchestrator `process_file_and_upsert()` that ties
    extraction and upserting into a single call (no splitting/sections).

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
        from store.weaviate_store import WeaviateStore
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
# Local embeddings via sentence-transformers/paraphrase were removed. The
# application now relies solely on OpenAI and/or Weaviate-native vectorizers.

# Import weaviate client at module level intentionally: if the dependency is
# missing the import will raise and the calling code/test can decide how to
# handle that (per project policy: no silent fallbacks).
import weaviate

# Optional light facades for domain operations (avoid circular imports at runtime)
try:
    from store.cv_store import CVStore
    from store.role_store import RoleStore
except Exception:
    CVStore = None  # type: ignore
    RoleStore = None  # type: ignore


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

        # Local paraphrase embeddings support removed; always use server-side vectorization
        self.use_local_embeddings = False

        # Expose simple facades for domain operations (non-breaking addition)
        if 'CVStore' in globals() and CVStore is not None:
            try:
                self.cv = CVStore(self)  # type: ignore[call-arg]
            except Exception:
                self.cv = None  # type: ignore[attr-defined]
        else:
            self.cv = None  # type: ignore[attr-defined]
        if 'RoleStore' in globals() and RoleStore is not None:
            try:
                self.roles = RoleStore(self)  # type: ignore[call-arg]
            except Exception:
                self.roles = None  # type: ignore[attr-defined]
        else:
            self.roles = None  # type: ignore[attr-defined]

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

    def _schema_get(self) -> dict:
        """Retrieve the current Weaviate schema as a dict.

        Tries client methods for v3/v4 and falls back to HTTP GET /v1/schema.
        Returns an empty dict on failure (callers decide how to proceed).
        """
        assert self.client is not None, "Weaviate client not initialized"
        attempts = []
        # v3: client.schema.get()
        try:
            if hasattr(self.client, "schema") and hasattr(self.client.schema, "get"):
                res = self.client.schema.get()
                if isinstance(res, dict):
                    return res
        except Exception as e:
            attempts.append(f"schema.get(): {e}")

        # some clients expose .schema() as a callable
        try:
            if hasattr(self.client, "schema") and callable(self.client.schema):
                res = self.client.schema()
                if isinstance(res, dict):
                    return res
        except Exception as e:
            attempts.append(f"schema() callable: {e}")

        # HTTP fallback
        try:
            if self.url:
                import requests
                schema_url = self.url.rstrip("/") + "/v1/schema"
                resp = requests.get(schema_url, timeout=10)
                if resp.status_code == 200:
                    j = resp.json()
                    if isinstance(j, dict):
                        return j
        except Exception as e:
            attempts.append(f"http schema get: {e}")

        # urllib fallback
        try:
            if self.url:
                from urllib.request import urlopen
                import json as _json
                schema_url = self.url.rstrip("/") + "/v1/schema"
                with urlopen(schema_url, timeout=10) as fh:
                    return _json.load(fh)
        except Exception as e:
            attempts.append(f"urllib schema get: {e}")

        self.logger.log_kv("WEAVIATE_SCHEMA_GET_FAILED", attempts=attempts)
        return {}

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
                import requests
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key

                # Ensure class name is present and valid string
                cls_name = class_schema.get("class") if isinstance(class_schema, dict) else None
                if not cls_name or not isinstance(cls_name, str):
                    # Attempt to infer from alternative keys
                    alt = class_schema.get("className") or class_schema.get("name") if isinstance(class_schema, dict) else None
                    if isinstance(alt, str) and alt.strip():
                        class_schema["class"] = alt.strip()
                        cls_name = class_schema["class"]

                # Server accepts PUT for /v1/schema/classes (based on error: "method POST is not allowed, but [DELETE,GET,PUT] are")
                    # Try classes endpoint variants
                    schema_classes_url = self.url.rstrip("/") + "/v1/schema/classes"
                    # First try POST (most common)
                    try:
                        resp_post_classes = requests.post(schema_classes_url, json=class_schema, headers=headers, timeout=10)
                        if resp_post_classes.status_code in (200, 201):
                            self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_CREATED", class_name=class_schema.get("class"))
                            return None
                        attempts.append(f"http POST classes status {resp_post_classes.status_code}: {resp_post_classes.text[:200]}")
                    except Exception as e:
                        attempts.append(f"http POST classes error: {e}")
                    # If POST not allowed but PUT is advertised, try PUT
                    try:
                        if resp_post_classes is not None and resp_post_classes.status_code == 405 and ("PUT" in (resp_post_classes.text or "")):
                            resp_put_classes = requests.put(schema_classes_url, json=class_schema, headers=headers, timeout=10)
                            if resp_put_classes.status_code in (200, 201):
                                self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_CREATED", class_name=class_schema.get("class"))
                                return None
                            attempts.append(f"http PUT classes status {resp_put_classes.status_code}: {resp_put_classes.text[:200]}")
                    except Exception as e:
                        attempts.append(f"http PUT classes error: {e}")

                # Alternate older servers may support class-qualified PUT/POST
                if cls_name and isinstance(cls_name, str) and cls_name.strip():
                    alt_put_url = self.url.rstrip("/") + f"/v1/schema/{cls_name}"
                    alt_post_url = alt_put_url
                    try:
                        put_alt = requests.put(alt_put_url, json=class_schema, headers=headers, timeout=10)
                        if put_alt.status_code in (200, 201):
                            self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_PUT_CLASS_OK", class_name=cls_name)
                            return None
                        attempts.append(f"http PUT class status {put_alt.status_code}: {put_alt.text[:200]}")
                    except Exception as e:
                        attempts.append(f"http PUT class error: {e}")
                    try:
                        post_alt = requests.post(alt_post_url, json=class_schema, headers=headers, timeout=10)
                        if post_alt.status_code in (200, 201):
                            self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_POST_CLASS_OK", class_name=cls_name)
                            return None
                        attempts.append(f"http POST class status {post_alt.status_code}: {post_alt.text[:200]}")
                    except Exception as e:
                        attempts.append(f"http POST class error: {e}")

                # Fallback: merge into full schema and POST /v1/schema
                schema_url = self.url.rstrip("/") + "/v1/schema"
                current = requests.get(schema_url, headers=headers, timeout=10)
                if current.status_code == 200:
                    try:
                        cur = current.json()
                        classes = cur.get("classes") or []
                        # Skip if class already exists in snapshot
                        if not any(c.get("class") == class_schema.get("class") for c in classes if isinstance(c, dict)):
                            # Ensure incoming class_schema has valid 'class' field before appending
                            cname = class_schema.get("class")
                            if not cname or not isinstance(cname, str) or not cname.strip():
                                raise ValueError(f"class_schema missing valid 'class' field: {class_schema}")
                            classes.append(class_schema)
                            cur["classes"] = classes
                            # Try POST /v1/schema (server advertises [GET,POST])
                            post = requests.post(schema_url, json=cur, headers=headers, timeout=10)
                            if post.status_code in (200, 201):
                                self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_POST_OK", class_name=class_schema.get("class"))
                                return None
                            attempts.append(f"http POST schema status {post.status_code}: {post.text[:200]}")
                            # As a final fallback, try posting a minimal schema with just this class
                            minimal_payload = {"classes": [class_schema]}
                            post_single = requests.post(schema_url, json=minimal_payload, headers=headers, timeout=10)
                            if post_single.status_code in (200, 201):
                                self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_POST_SINGLE_OK", class_name=class_schema.get("class"))
                                return None
                            attempts.append(f"http POST schema(single) status {post_single.status_code}: {post_single.text[:200]}")
                        else:
                            # Class already present according to snapshot
                            self.logger.log_kv("WEAVIATE_SCHEMA_HTTP_EXISTS", class_name=class_schema.get("class"))
                            return None
                    except Exception as e:
                        attempts.append(f"schema merge/post error: {e}")
                else:
                    attempts.append(f"http GET schema status {current.status_code}: {current.text[:200]}")
        except Exception as e:
            attempts.append(f"http schema create attempt: {e}")

        raise RuntimeError(f"Unable to create Weaviate class. Attempts: {attempts}")

    def _schema_add_property(self, class_name: str, prop_schema: Dict[str, Any]) -> None:
        """Adapter to add a missing property to an existing class.

        Tries client.schema.property.create, then alternative methods, and finally
        falls back to the HTTP endpoint POST /v1/schema/{class}/properties.
        """
        assert self.client is not None, "Weaviate client not initialized"
        attempts: List[str] = []
        try:
            # v3 style
            if hasattr(self.client, "schema") and hasattr(self.client.schema, "property") and hasattr(self.client.schema.property, "create"):
                try:
                    return self.client.schema.property.create(prop_schema, class_name)  # type: ignore[arg-type]
                except TypeError:
                    return self.client.schema.property.create({"class": class_name, **prop_schema})
        except Exception as e:
            attempts.append(f"schema.property.create: {e}")
        try:
            # alternative name
            if hasattr(self.client, "schema") and hasattr(self.client.schema, "add_property"):
                return self.client.schema.add_property(class_name, prop_schema)  # type: ignore[attr-defined]
        except Exception as e:
            attempts.append(f"schema.add_property: {e}")
        # HTTP fallback
        try:
            if self.url:
                import requests
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key
                url = self.url.rstrip("/") + f"/v1/schema/{class_name}/properties"
                resp = requests.post(url, json=prop_schema, headers=headers, timeout=10)
                if resp.status_code in (200, 201):
                    self.logger.log_kv("WEAVIATE_PROPERTY_HTTP_ADDED", class_name=class_name, prop=prop_schema.get("name"))
                    return None
                attempts.append(f"http add_property status {resp.status_code}: {resp.text[:200]}")

                # Older servers: fetch class, merge prop, PUT/POST class endpoint
                class_url = self.url.rstrip("/") + f"/v1/schema/{class_name}"
                class_get = requests.get(class_url, headers=headers, timeout=10)
                if class_get.status_code == 200:
                    try:
                        cobj = class_get.json()
                        props = cobj.get("properties") or []
                        if not any((p.get("name") == prop_schema.get("name")) for p in props if isinstance(p, dict)):
                            props.append(prop_schema)
                            cobj["properties"] = props
                            up_put = requests.put(class_url, json=cobj, headers=headers, timeout=10)
                            if up_put.status_code in (200, 201):
                                self.logger.log_kv("WEAVIATE_PROPERTY_HTTP_PUT_CLASS_OK", class_name=class_name, prop=prop_schema.get("name"))
                                return None
                            attempts.append(f"http PUT class status {up_put.status_code}: {up_put.text[:200]}")
                            up_post = requests.post(class_url, json=cobj, headers=headers, timeout=10)
                            if up_post.status_code in (200, 201):
                                self.logger.log_kv("WEAVIATE_PROPERTY_HTTP_POST_CLASS_OK", class_name=class_name, prop=prop_schema.get("name"))
                                return None
                            attempts.append(f"http POST class status {up_post.status_code}: {up_post.text[:200]}")
                        else:
                            self.logger.log_kv("WEAVIATE_PROPERTY_HTTP_EXISTS", class_name=class_name, prop=prop_schema.get("name"))
                            return None
                    except Exception as e:
                        attempts.append(f"class merge error: {e}")

                # Fallback: GET full schema, merge property into class, PUT schema
                schema_url = self.url.rstrip("/") + "/v1/schema"
                cur_resp = requests.get(schema_url, headers=headers, timeout=10)
                if cur_resp.status_code == 200:
                    try:
                        cur = cur_resp.json()
                        classes = cur.get("classes") or []
                        for c in classes:
                            if isinstance(c, dict) and c.get("class") == class_name:
                                props = c.get("properties") or []
                                if not any((p.get("name") == prop_schema.get("name")) for p in props if isinstance(p, dict)):
                                    props.append(prop_schema)
                                    c["properties"] = props
                                    put = requests.put(schema_url, json=cur, headers=headers, timeout=10)
                                    if put.status_code in (200, 201):
                                        self.logger.log_kv("WEAVIATE_PROPERTY_HTTP_PUT_OK", class_name=class_name, prop=prop_schema.get("name"))
                                        return None
                                    attempts.append(f"http PUT schema status {put.status_code}: {put.text[:200]}")
                                    # POST /v1/schema fallback for servers that disallow PUT
                                    post = requests.post(schema_url, json=cur, headers=headers, timeout=10)
                                    if post.status_code in (200, 201):
                                        self.logger.log_kv("WEAVIATE_PROPERTY_HTTP_POST_OK", class_name=class_name, prop=prop_schema.get("name"))
                                        return None
                                    attempts.append(f"http POST schema status {post.status_code}: {post.text[:200]}")
                                else:
                                    self.logger.log_kv("WEAVIATE_PROPERTY_HTTP_EXISTS", class_name=class_name, prop=prop_schema.get("name"))
                                    return None
                        attempts.append("class not found in schema when merging property")
                    except Exception as e:
                        attempts.append(f"schema merge/put property error: {e}")
                else:
                    attempts.append(f"http GET schema status {cur_resp.status_code}: {cur_resp.text[:200]}")
        except Exception as e:
            attempts.append(f"http add_property: {e}")
        raise RuntimeError(f"Unable to add property to class {class_name}. Attempts: {attempts}")

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
                        headers = {"Content-Type": "application/json"}
                        if self.api_key:
                            headers["X-API-Key"] = self.api_key
                        req = Request(objects_url, data=data, headers=headers, method="POST")
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
        """Adapter for updating a data object by uuid. Raises if uuid is None."""
        assert self.client is not None, "Weaviate client not initialized"
        if uuid is None:
            raise RuntimeError(f"Cannot update data object: uuid is None for class '{class_name}'. Object must be created first.")
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

        # Final fallback: HTTP REST API to update the object
        try:
            if self.url:
                obj_url = self.url.rstrip("/") + f"/v1/objects/{uuid}"
                payload_json = {"class": class_name, "properties": props}
                if vector is not None:
                    payload_json["vector"] = vector
                try:
                    import requests

                    # Prefer PATCH for partial update; some servers accept PUT as well
                    resp = requests.patch(obj_url, json=payload_json, timeout=10)
                    if resp.status_code in (200, 201, 204):
                        return None
                    # Try PUT if PATCH not supported
                    resp2 = requests.put(obj_url, json=payload_json, timeout=10)
                    if resp2.status_code in (200, 201, 204):
                        return None
                    # Try class-qualified path as a fallback
                    obj_url2 = self.url.rstrip("/") + f"/v1/objects/{class_name}/{uuid}"
                    resp3 = requests.patch(obj_url2, json=payload_json, timeout=10)
                    if resp3.status_code in (200, 201, 204):
                        return None
                    resp4 = requests.put(obj_url2, json=payload_json, timeout=10)
                    if resp4.status_code in (200, 201, 204):
                        return None
                    attempts.append(f"http objects PATCH/PUT status {resp.status_code}/{resp2.status_code} and fallback {resp3.status_code}/{resp4.status_code}")
                except Exception as e:
                    # urllib fallback
                    try:
                        from urllib.request import Request, urlopen
                        import json as _json

                        data = _json.dumps(payload_json).encode("utf-8")
                        # Try PATCH first
                        req = Request(obj_url, data=data, headers={"Content-Type": "application/json"}, method="PATCH")
                        try:
                            with urlopen(req, timeout=10) as fh:
                                _ = fh.read()
                                return None
                        except Exception:
                            # Fallback to PUT
                            req2 = Request(obj_url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
                            with urlopen(req2, timeout=10) as fh:
                                _ = fh.read()
                                return None
                        # Final fallback: class-qualified URL
                        try:
                            obj_url2 = self.url.rstrip("/") + f"/v1/objects/{class_name}/{uuid}"
                            req3 = Request(obj_url2, data=data, headers={"Content-Type": "application/json"}, method="PATCH")
                            with urlopen(req3, timeout=10) as fh:
                                _ = fh.read()
                                return None
                        except Exception:
                            req4 = Request(obj_url2, data=data, headers={"Content-Type": "application/json"}, method="PUT")
                            with urlopen(req4, timeout=10) as fh:
                                _ = fh.read()
                                return None
                    except Exception as e2:
                        attempts.append(f"http objects urllib error: {e2}")
        except Exception as e:
            attempts.append(f"http objects update attempt: {e}")

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
                # Always request some _additional fields; default to ['id']
                addl = additional if additional is not None else ["id"]
                if hasattr(q, "with_additional"):
                    q = q.with_additional(addl)
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
                # Include requested _additional fields (default to id)
                fields = "\n".join(props)
                addl = additional if additional is not None else ["id"]
                addl_block = f"\n_additional {{ {' '.join(addl)} }}"
                if "_additional" not in fields:
                    fields = fields + addl_block
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

                # Add requested _additional (default to id)
                addl = additional if additional is not None else ["id"]
                addl_block = f"\n_additional {{ {' '.join(addl)} }}"
                if "_additional" not in fields:
                    fields = fields + addl_block
                gql = f"{{Get{{{class_name}{where_str}{{{fields}}}}}}}"
                try:
                    import requests
                    headers = {"Content-Type": "application/json"}
                    if self.api_key:
                        headers["X-API-Key"] = self.api_key
                    resp = requests.post(gql_url, json={"query": gql}, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        return resp.json()
                    attempts.append(f"http graphql status {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    try:
                        # urllib fallback
                        from urllib.request import Request, urlopen
                        import json as _json

                        data = _json.dumps({"query": gql}).encode("utf-8")
                        headers = {"Content-Type": "application/json"}
                        if self.api_key:
                            headers["X-API-Key"] = self.api_key
                        req = Request(gql_url, data=data, headers=headers, method="POST")
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
            - RoleDocument

        Returns True on success. Raises on client/server errors.
        """
        if not self.url or not self.client:
            raise RuntimeError("Weaviate URL not configured; cannot ensure schema")

        # Skip vectorizer module checks: this app always provides vectors from OpenAI
        # and the schema sets vectorizer to "none" for classes. Weaviate can accept
        # client-provided vectors without any vectorizer module installed.
        self.logger.log_kv("WEAVIATE_VECTORIZER_CHECK_SKIPPED", reason="client_provided_vectors")

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

        # Role documents mirror CV but with a RoleTitle field commonly used
        role_properties = [
            {"name": "sha", "dataType": ["string"]},
            {"name": "timestamp", "dataType": ["string"]},
            {"name": "filename", "dataType": ["string"]},
            {"name": "role_title", "dataType": ["string"]},
            {"name": "full_text", "dataType": ["text"]},
        ]

        # Sections have been removed from the design; only documents are managed.

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

        # Create missing classes, then ensure missing properties on existing ones
        created = []
        server_schema = self._schema_get()
        server_classes = {c.get("class"): c for c in (server_schema.get("classes") or [])} if isinstance(server_schema, dict) else {}
        for name, schema in classes.items():
            if not self._class_exists(name):
                self.logger.log_kv("WEAVIATE_CREATE_CLASS", class_name=name)
                self._schema_create_class(schema)
                created.append(name)
                # refresh server class snapshot
                server_schema = self._schema_get()
                server_classes = {c.get("class"): c for c in (server_schema.get("classes") or [])}
            else:
                self.logger.log_kv("WEAVIATE_CLASS_EXISTS", class_name=name)
            # Ensure properties exist
            try:
                desired_props = {p.get("name"): p for p in (schema.get("properties") or [])}
                have_props = set()
                server_cls = server_classes.get(name) or {}
                for p in (server_cls.get("properties") or []):
                    n = p.get("name")
                    if n:
                        have_props.add(n)
                for pname, pschema in desired_props.items():
                    if pname not in have_props:
                        self.logger.log_kv("WEAVIATE_ADD_MISSING_PROPERTY", class_name=name, prop=pname)
                        self._schema_add_property(name, pschema)
            except Exception as e:
                # Log but do not fail schema ensure entirely
                self.logger.log_kv("WEAVIATE_PROPERTY_ENSURE_FAILED", class_name=name, error=str(e))

        self.logger.log_kv("WEAVIATE_SCHEMA_ENSURED", created=",".join(created) if created else "none")
        return True

    def process_file_and_upsert(self, path: Path, is_role: bool = False) -> Dict[str, object]:
        """Extract -> upsert document (no sections).

        If Weaviate is not configured it will still extract text and compute the
        file SHA, returning weaviate_ok=False without raising.
        Returns: {sha, filename, weaviate_ok, errors: []}
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
                        if getattr(self, "roles", None):
                            self.roles.write(sha, p.name, text, attrs)  # type: ignore[attr-defined]
                    else:
                        if getattr(self, "cv", None):
                            self.cv.write(sha, p.name, text, attrs)  # type: ignore[attr-defined]
                except Exception as e:
                    self.logger.log_kv("WEAVIATE_DOC_UPSERT_ERROR", error=str(e), file=str(p))

            # Sections are no longer used; success depends only on document upsert
            result["weaviate_ok"] = bool(self.client)
            return result
        except Exception as e:
            self.logger.log_kv("PROCESS_FILE_ERROR", error=str(e), file=str(p))
            result["errors"].append(str(e))
            return result
