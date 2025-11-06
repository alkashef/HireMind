from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from store.weaviate_store import WeaviateStore


class CVStore:
    """CVDocument domain facade.

    Holds CV-specific shaping, coercions, and query prop lists while using
    the Weaviate plumbing exposed by the parent `WeaviateStore`.
    """

    def __init__(self, store: 'WeaviateStore') -> None:
        self.store = store

    # ---------------------------- internals ---------------------------------
    def _find_by_sha(self, sha: str) -> Optional[Dict[str, object]]:
        """Return the first CVDocument object matching sha or None.

        Returns a dict with keys 'id' and 'properties' when found.
        """
        if not self.store.client:
            raise RuntimeError("Weaviate client not initialized")

        where = {"path": ["sha"], "operator": "Equal", "valueString": sha}
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
        try:
            res = self.store._query_do("CVDocument", props, where, additional=["id", "vector"])  # type: ignore[attr-defined]
            objs = (res.get("data", {}) or {}).get("Get", {}).get("CVDocument", [])
            if objs:
                first = objs[0]
                return {"id": first.get("id") or (first.get("_additional") or {}).get("id"), "properties": first}
            return None
        except Exception as e:
            self.store.logger.log_kv("WEAVIATE_QUERY_ERROR", error=str(e))
            raise

    # ---------------------------- public API --------------------------------
    def write(self, sha: str, filename: str, full_text: str, attributes: Dict[str, object]) -> Dict[str, object]:
        """Create or update a CVDocument object keyed by `sha`.

        Maps the provided `attributes` dict into the explicit CVDocument
        properties declared in the schema. Stores raw text in `full_text`.
        """
        if not self.store.client:
            raise RuntimeError("Weaviate client not initialized")

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
            "_vector": attributes.get("_vector") if isinstance(attributes, dict) else None,
        }

        def _as_int(v):
            if v is None or v == "":
                return None
            try:
                s = str(v).strip()
                if s == "":
                    return None
                return int(float(s))
            except Exception:
                return None

        def _as_str(v):
            if v is None:
                return ""
            return str(v)

        int_fields = {
            "professional_misspelling_count",
            "experience_years_since_graduation",
            "experience_total_years",
            "stability_employers_count",
        }

        for k in list(props.keys()):
            if k == "_vector":
                continue
            if k in int_fields:
                props[k] = _as_int(props[k])
            else:
                props[k] = _as_str(props[k])

        found = self._find_by_sha(sha)
        if found:
            obj_id = found.get("id")
            if obj_id is not None:
                self.store._data_object_update(props, "CVDocument", obj_id)  # type: ignore[attr-defined]
                self.store.logger.log_kv("WEAVIATE_CV_UPDATED", id=obj_id, sha=sha)
                return {"id": obj_id, "properties": props}
            obj_id = self.store._data_object_create(props, "CVDocument")  # type: ignore[attr-defined]
            nid = obj_id.get("id") if isinstance(obj_id, dict) else obj_id
            self.store.logger.log_kv("WEAVIATE_CV_CREATED", id=nid, sha=sha)
            return {"id": obj_id, "properties": props}
        else:
            obj_id = self.store._data_object_create(props, "CVDocument")  # type: ignore[attr-defined]
            nid = obj_id.get("id") if isinstance(obj_id, dict) else obj_id
            self.store.logger.log_kv("WEAVIATE_CV_CREATED", id=nid, sha=sha)
            return {"id": obj_id, "properties": props}

    def read(self, sha: str) -> Optional[Dict[str, object]]:
        """Read CVDocument by sha and return attributes and full_text.

        Returns a dict with keys: id, sha, filename, attributes (dict), full_text.
        """
        if not self.store.client:
            raise RuntimeError("Weaviate client not initialized")

        found = self._find_by_sha(sha)
        if not found:
            return None
        props = found.get("properties", {}) or {}

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
            "vector": (props.get("_additional") or {}).get("vector"),
        }
        return result

    def list(self) -> List[Dict[str, object]]:
        """Query all CVDocument records and return simplified dicts."""
        if not self.store.client:
            raise RuntimeError("Weaviate client not initialized")

        props = [
            "sha", "filename", "timestamp",
            "personal_first_name", "personal_last_name", "personal_full_name",
            "personal_email", "personal_phone",
            "professional_misspelling_count", "professional_misspelled_words",
            "professional_visual_cleanliness", "professional_look",
            "professional_formatting_consistency",
            "experience_years_since_graduation", "experience_total_years",
            "experience_employer_names",
            "stability_employers_count", "stability_avg_years_per_employer",
            "stability_years_at_current_employer",
            "socio_address", "socio_alma_mater", "socio_high_school",
            "socio_education_system", "socio_second_foreign_language",
            "flag_stem_degree", "flag_military_service_status",
            "flag_worked_at_financial_institution",
            "flag_worked_for_egyptian_government",
        ]
        result = self.store._query_do("CVDocument", props, where=None, additional=["id"])  # type: ignore[attr-defined]
        data = result.get("data", {}) or {}
        get = data.get("Get", {}) or {}
        items = get.get("CVDocument", []) or []

        records: List[Dict[str, object]] = []
        for item in items:
            props_dict = item.get("properties", {}) if "properties" in item else item
            records.append({
                "id": (item.get("_additional") or {}).get("id") or item.get("id"),
                "sha": props_dict.get("sha"),
                "filename": props_dict.get("filename"),
                "timestamp": props_dict.get("timestamp"),
                "personal_first_name": props_dict.get("personal_first_name"),
                "personal_last_name": props_dict.get("personal_last_name"),
                "personal_full_name": props_dict.get("personal_full_name"),
                "personal_email": props_dict.get("personal_email"),
                "personal_phone": props_dict.get("personal_phone"),
                "professional_misspelling_count": props_dict.get("professional_misspelling_count"),
                "professional_misspelled_words": props_dict.get("professional_misspelled_words"),
                "professional_visual_cleanliness": props_dict.get("professional_visual_cleanliness"),
                "professional_look": props_dict.get("professional_look"),
                "professional_formatting_consistency": props_dict.get("professional_formatting_consistency"),
                "experience_years_since_graduation": props_dict.get("experience_years_since_graduation"),
                "experience_total_years": props_dict.get("experience_total_years"),
                "experience_employer_names": props_dict.get("experience_employer_names"),
                "stability_employers_count": props_dict.get("stability_employers_count"),
                "stability_avg_years_per_employer": props_dict.get("stability_avg_years_per_employer"),
                "stability_years_at_current_employer": props_dict.get("stability_years_at_current_employer"),
                "socio_address": props_dict.get("socio_address"),
                "socio_alma_mater": props_dict.get("socio_alma_mater"),
                "socio_high_school": props_dict.get("socio_high_school"),
                "socio_education_system": props_dict.get("socio_education_system"),
                "socio_second_foreign_language": props_dict.get("socio_second_foreign_language"),
                "flag_stem_degree": props_dict.get("flag_stem_degree"),
                "flag_military_service_status": props_dict.get("flag_military_service_status"),
                "flag_worked_at_financial_institution": props_dict.get("flag_worked_at_financial_institution"),
                "flag_worked_for_egyptian_government": props_dict.get("flag_worked_for_egyptian_government"),
            })
        return records
