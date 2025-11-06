from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from store.weaviate_store import WeaviateStore


class RoleStore:
    """RoleDocument domain facade.

    Houses role-specific shaping/coercions and queries, using the Weaviate
    plumbing from the parent store.
    """

    def __init__(self, store: 'WeaviateStore') -> None:
        self.store = store

    def write(self, sha: str, filename: str, full_text: str, attributes: Dict[str, object]) -> Dict[str, object]:
        """Create or update a RoleDocument keyed by sha."""
        if not self.store.client:
            raise RuntimeError("Weaviate client not initialized")

        def _opt_str(v):
            if v is None:
                return None
            if isinstance(v, str) and v.strip() == "":
                return None
            return str(v)

        def _as_list_strs(v):
            if v is None:
                return None
            if isinstance(v, list):
                return [str(x) for x in v]
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    return None
                try:
                    import json as _json
                    parsed = _json.loads(s)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except Exception:
                    pass
                return [s]
            return [str(v)]

        def _as_bool(v):
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                s = v.strip().lower()
                if s in ("true", "yes", "y", "1"):
                    return True
                if s in ("false", "no", "n", "0"):
                    return False
            return None

        props = {
            "sha": sha,
            "timestamp": _opt_str(attributes.get("timestamp")),
            "filename": filename,
            "role_title": _opt_str(attributes.get("role_title")),
            "full_text": full_text,
            "_vector": attributes.get("_vector") if isinstance(attributes, dict) else None,
            # Extended role fields (optional)
            "job_title": _opt_str(attributes.get("job_title")),
            "employer": _opt_str(attributes.get("employer")),
            "job_location": _opt_str(attributes.get("job_location")),
            "language_requirement": _as_list_strs(attributes.get("language_requirement")),
            "onsite_requirement_percentage": attributes.get("onsite_requirement_percentage", None),
            "onsite_requirement_mandatory": _as_bool(attributes.get("onsite_requirement_mandatory")),
            "serves_government": _as_bool(attributes.get("serves_government")),
            "serves_financial_institution": _as_bool(attributes.get("serves_financial_institution")),
            "min_years_experience": attributes.get("min_years_experience", None),
            "must_have_skills": _as_list_strs(attributes.get("must_have_skills")),
            "should_have_skills": _as_list_strs(attributes.get("should_have_skills")),
            "nice_to_have_skills": _as_list_strs(attributes.get("nice_to_have_skills")),
            "min_must_have_degree": _opt_str(attributes.get("min_must_have_degree")),
            "preferred_universities": _as_list_strs(attributes.get("preferred_universities")),
            "responsibilities": _as_list_strs(attributes.get("responsibilities")),
            "technical_qualifications": _as_list_strs(attributes.get("technical_qualifications")),
            "non_technical_qualifications": _as_list_strs(attributes.get("non_technical_qualifications")),
        }

        # find existing by sha
        found = None
        try:
            where = {"path": ["sha"], "operator": "Equal", "valueString": sha}
            res = self.store._query_do("RoleDocument", ["sha"], where)  # type: ignore[attr-defined]
            objs = (res.get("data", {}) or {}).get("Get", {}).get("RoleDocument", [])
            if objs:
                found = objs[0]
        except Exception:
            pass

        if found:
            obj_id = found.get("id") or (found.get("_additional") or {}).get("id")
            self.store._data_object_update(props, "RoleDocument", obj_id)  # type: ignore[attr-defined]
            self.store.logger.log_kv("WEAVIATE_ROLE_UPDATED", id=obj_id, sha=sha)
            return {"id": obj_id, "properties": props}
        obj_id = self.store._data_object_create(props, "RoleDocument")  # type: ignore[attr-defined]
        self.store.logger.log_kv("WEAVIATE_ROLE_CREATED", id=(obj_id.get("id") if isinstance(obj_id, dict) else obj_id), sha=sha)
        return {"id": obj_id, "properties": props}

    def read(self, sha: str) -> Optional[Dict[str, object]]:
        """Read RoleDocument by sha. Returns same shape as CV read."""
        if not self.store.client:
            raise RuntimeError("Weaviate client not initialized")

        try:
            def _none_if_empty(v):
                if v is None:
                    return None
                if isinstance(v, str) and v.strip() == "":
                    return None
                return v

            where = {"path": ["sha"], "operator": "Equal", "valueString": sha}
            res = self.store._query_do(  # type: ignore[attr-defined]
                "RoleDocument",
                [
                    "sha", "filename", "role_title", "full_text",
                    "job_title", "employer", "job_location", "language_requirement",
                    "onsite_requirement_percentage", "onsite_requirement_mandatory",
                    "serves_government", "serves_financial_institution",
                    "min_years_experience", "must_have_skills", "should_have_skills",
                    "nice_to_have_skills", "min_must_have_degree", "preferred_universities",
                    "responsibilities", "technical_qualifications", "non_technical_qualifications",
                ],
                where,
                additional=["id", "vector"],
            )
            items = (res.get("data", {}) or {}).get("Get", {}).get("RoleDocument", [])
            if not items:
                return None
            first = items[0]
            props = first.get("properties", {}) if isinstance(first, dict) and "properties" in first else first
            return {
                "id": (first.get("_additional") or {}).get("id") or first.get("id"),
                "sha": props.get("sha"),
                "filename": props.get("filename"),
                "attributes": {
                    "role_title": _none_if_empty(props.get("role_title")),
                    "job_title": _none_if_empty(props.get("job_title")),
                    "employer": _none_if_empty(props.get("employer")),
                    "job_location": _none_if_empty(props.get("job_location")),
                    "language_requirement": _none_if_empty(props.get("language_requirement")),
                    "onsite_requirement_percentage": props.get("onsite_requirement_percentage"),
                    "onsite_requirement_mandatory": _none_if_empty(props.get("onsite_requirement_mandatory")),
                    "serves_government": _none_if_empty(props.get("serves_government")),
                    "serves_financial_institution": _none_if_empty(props.get("serves_financial_institution")),
                    "min_years_experience": props.get("min_years_experience"),
                    "must_have_skills": _none_if_empty(props.get("must_have_skills")),
                    "should_have_skills": _none_if_empty(props.get("should_have_skills")),
                    "nice_to_have_skills": _none_if_empty(props.get("nice_to_have_skills")),
                    "min_must_have_degree": _none_if_empty(props.get("min_must_have_degree")),
                    "preferred_universities": _none_if_empty(props.get("preferred_universities")),
                    "responsibilities": _none_if_empty(props.get("responsibilities")),
                    "technical_qualifications": _none_if_empty(props.get("technical_qualifications")),
                    "non_technical_qualifications": _none_if_empty(props.get("non_technical_qualifications")),
                },
                "full_text": props.get("full_text"),
                "vector": (first.get("_additional") or {}).get("vector"),
            }
        except Exception as e:
            self.store.logger.log_kv("WEAVIATE_ROLE_READ_ERROR", error=str(e), sha=sha)
            return None

    def list(self) -> List[Dict[str, object]]:
        """List RoleDocument records with common fields."""
        if not self.store.client:
            raise RuntimeError("Weaviate client not initialized")

        props = [
            "sha", "filename", "timestamp", "role_title",
            "job_title", "employer", "job_location",
        ]
        result = self.store._query_do("RoleDocument", props, where=None, additional=["id"])  # type: ignore[attr-defined]
        data = result.get("data", {}) or {}
        items = (data.get("Get", {}) or {}).get("RoleDocument", []) or []
        records: List[Dict[str, object]] = []
        for item in items:
            props_dict = item.get("properties", {}) if "properties" in item else item
            records.append({
                "id": (item.get("_additional") or {}).get("id") or item.get("id"),
                "sha": props_dict.get("sha"),
                "filename": props_dict.get("filename"),
                "timestamp": props_dict.get("timestamp"),
                "role_title": props_dict.get("role_title"),
                "job_title": props_dict.get("job_title"),
                "employer": props_dict.get("employer"),
                "job_location": props_dict.get("job_location"),
            })
        return records
