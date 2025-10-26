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

        self.client: Optional[weaviate.Client] = None
        if self.url:
            # Prepare auth header if API key provided
            headers = {"X-API-Key": self.api_key} if self.api_key else None
            self.logger.log_kv("WEAVIATE_CLIENT_INIT", url=self.url, batch_size=self.batch_size)
            # Create client (may raise if weaviate package missing or invalid args)
            self.client = weaviate.Client(url=self.url, additional_headers=headers)

    def _class_exists(self, class_name: str) -> bool:
        assert self.client is not None, "Weaviate client not initialized"
        schema = self.client.schema.get()
        classes = schema.get("classes", []) if isinstance(schema, dict) else []
        for c in classes:
            if c.get("class") == class_name:
                return True
        return False

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

        # Define class schemas (vectorizer: none to store vectors externally)
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

        classes: Dict[str, Dict[str, Any]] = {
            "CVDocument": {"class": "CVDocument", "vectorizer": "none", "properties": cv_properties},
            "CVSection": {"class": "CVSection", "vectorizer": "none", "properties": cv_section_props},
            "RoleDocument": {"class": "RoleDocument", "vectorizer": "none", "properties": role_properties},
            "RoleSection": {"class": "RoleSection", "vectorizer": "none", "properties": role_section_props},
        }

        # Create missing classes only
        created = []
        for name, schema in classes.items():
            if not self._class_exists(name):
                self.logger.log_kv("WEAVIATE_CREATE_CLASS", class_name=name)
                self.client.schema.create_class(schema)
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

            res = self.client.query.get("CVDocument", props).with_where(where).do()
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
            self.client.data_object.update(props, "CVDocument", uuid=obj_id)
            self.logger.log_kv("WEAVIATE_CV_UPDATED", id=obj_id, sha=sha)
            return {"id": obj_id, "properties": props}
        else:
            obj_id = self.client.data_object.create(props, "CVDocument")
            self.logger.log_kv("WEAVIATE_CV_CREATED", id=obj_id, sha=sha)
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
            res = self.client.query.get("CVSection", ["parent_sha", "section_type", "section_text"]).with_where(where).with_additional(["id"]).do()
            items = res.get("data", {}).get("Get", {}).get("CVSection", [])
            for it in items:
                txt = it.get("section_text") or ""
                if txt.strip() == (section_text or "").strip():
                    return {"id": it.get("_additional", {}).get("id") or it.get("id"), "properties": it}
            return None
        except Exception as e:
            self.logger.log_kv("WEAVIATE_SECTION_QUERY_ERROR", error=str(e))
            return None

    def upsert_cv_section(self, parent_sha: str, section_type: str, section_text: str, embedding: List[float]) -> Dict[str, object]:
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
                # update
                self.client.data_object.update(props, "CVSection", uuid=obj_id)
                self.logger.log_kv("WEAVIATE_CVSECTION_UPDATED", id=obj_id, parent_sha=parent_sha)
                return {"id": obj_id, "created": False, "weaviate_ok": True}
            else:
                # create with vector
                new_id = self.client.data_object.create(props, "CVSection", vector=embedding)
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
            res = self.client.query.get("RoleDocument", ["sha"]).with_where(where).do()
            objs = res.get("data", {}).get("Get", {}).get("RoleDocument", [])
            if objs:
                found = objs[0]
        except Exception:
            pass

        if found:
            obj_id = found.get("id") or (found.get("_additional") or {}).get("id")
            self.client.data_object.update(props, "RoleDocument", uuid=obj_id)
            self.logger.log_kv("WEAVIATE_ROLE_UPDATED", id=obj_id, sha=sha)
            return {"id": obj_id, "properties": props}
        else:
            obj_id = self.client.data_object.create(props, "RoleDocument")
            self.logger.log_kv("WEAVIATE_ROLE_CREATED", id=obj_id, sha=sha)
            return {"id": obj_id, "properties": props}

    def read_role_from_db(self, sha: str) -> Optional[Dict[str, object]]:
        """Read RoleDocument by sha. Returns same shape as read_cv_from_db."""
        if not self.client:
            raise RuntimeError("Weaviate client not initialized")

        try:
            where = {"path": ["sha"], "operator": "Equal", "valueString": sha}
            res = self.client.query.get("RoleDocument", ["sha", "filename", "role_title", "full_text"]).with_where(where).with_additional(["id"]).do()
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

    def upsert_role_section(self, parent_sha: str, section_type: str, section_text: str, embedding: List[float]) -> Dict[str, object]:
        """Create or update a RoleSection object; mirrors CV section upsert."""
        if not self.client:
            return {"id": None, "created": False, "weaviate_ok": False}
        props = {"parent_sha": parent_sha, "section_type": section_type, "section_text": section_text}
        try:
            # simple dedupe by parent + exact section_text
            where = {"path": ["parent_sha"], "operator": "Equal", "valueString": parent_sha}
            res = self.client.query.get("RoleSection", ["parent_sha", "section_text"]).with_where(where).with_additional(["id"]).do()
            items = res.get("data", {}).get("Get", {}).get("RoleSection", [])
            for it in items:
                if (it.get("section_text") or "").strip() == (section_text or "").strip():
                    obj_id = it.get("_additional", {}).get("id") or it.get("id")
                    self.client.data_object.update(props, "RoleSection", uuid=obj_id)
                    self.logger.log_kv("WEAVIATE_ROLESECTION_UPDATED", id=obj_id, parent_sha=parent_sha)
                    return {"id": obj_id, "created": False, "weaviate_ok": True}
            new_id = self.client.data_object.create(props, "RoleSection", vector=embedding)
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
        from utils.paraphrase_client import text_to_embedding
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
                try:
                    emb = text_to_embedding(sec_text)
                except Exception as e:
                    all_ok = False
                    self.logger.log_kv("EMBEDDING_ERROR", error=str(e))
                    result["errors"].append(str(e))
                    emb = None

                if emb is not None and self.client:
                    try:
                        if is_role:
                            up = self.upsert_role_section(sha, sec_type, sec_text, emb)
                        else:
                            up = self.upsert_cv_section(sha, sec_type, sec_text, emb)
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
 

