"""CSV manager utilities.

This module centralizes CSV-backed store functionality for applicants and roles.
It intentionally provides two public classes:
- CSVStore: manages the applicants CSV (data/applicants.csv)
- RolesStore: lightweight subclass configured for roles CSV (data/roles.csv)

Other modules in the codebase currently import `CSVStore` from
`utils.csv_store` and `RolesStore` from `utils.roles_store`. The goal of the
refactor is to consolidate the implementations here; callers will be updated
later to import from `utils.csv_manager`.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List
from config.settings import AppConfig
from utils.logger import AppLogger


__all__ = ["CSVStore", "RolesStore", "create_applicants_store", "create_roles_store"]


class CSVStore:
    """Lightweight CSV store for applicants data.

    Contract:
    - Storage file: data/applicants.csv
    - Columns (in file): ID, Timestamp, CV, Filename, FullName (and other prefixed columns)
    - Public rows (for UI): id, timestamp, cv, filename, full_name
    """

    FILE_NAME = "applicants.csv"
    # Default CSV columns (file headers)
    DEFAULT_HEADER = [
        "ID",
        "Timestamp",
        "CV",
        "Filename",
        # ...existing code...
    ]
    HEADER = list(DEFAULT_HEADER)  # Will be extended dynamically
    @staticmethod
    def flatten_json(y, parent_key='', sep='_'):
        """Flatten nested dicts/lists for CSV export."""
    """
    Recursively flattens a nested dictionary, including lists and dicts inside lists.
    For lists, if items are dicts, flatten each with index; else join as string.
    """
    out = {}
    def _flatten(val, key):
        if isinstance(val, dict):
            for k2, v2 in val.items():
                _flatten(v2, f"{key}{sep}{k2}" if key else k2)
        elif isinstance(val, list):
            for idx, item in enumerate(val):
                _flatten(item, f"{key}{sep}{idx}")
        else:
            # Serialize non-string types as JSON
            if isinstance(val, (int, float, bool)) or val is None:
                out[key] = val
            else:
                try:
                    out[key] = json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val
                except Exception:
                    out[key] = str(val)
    _flatten(y, parent_key)
    return out

    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger

    @property
    def csv_path(self) -> Path:
        return self.config.data_path / self.FILE_NAME

    def get_public_rows(self) -> List[dict]:
        """Return rows for UI consumption with normalized keys.

        Each row is shaped as: {id, timestamp, cv, filename, full_name}.
        """
        p = self.csv_path
        if not p.exists():
            self.logger.log_kv("CSV_GET_ROWS", rows=0, exists=False)
            return []
        rows: List[dict] = []
        try:
            with p.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rid = r.get("ID") or r.get("id") or r.get("Id") or ""
                    ts = r.get("Timestamp") or r.get("timestamp") or ""
                    cv = r.get("CV") or r.get("cv") or r.get("filename") or ""

                    # Helper for backward-compatible field resolution
                    def g(*keys: str) -> str:
                        for k in keys:
                            v = r.get(k)
                            if v not in (None, ""):
                                return str(v)
                        return ""

                    # Map file columns to UI/public keys
                    rows.append({
                        # meta
                        "id": rid,
                        "timestamp": ts,
                        "cv": cv,
                        # Derive a filename field (basename) for UI convenience
                        "filename": (cv or '').split('/')[-1].split('\\\\')[-1],
                        # Personal Information
                        "first_name": g("PersonalInformation_FirstName", "FirstName"),
                        "last_name": g("PersonalInformation_LastName", "LastName"),
                        "full_name": g("PersonalInformation_FullName", "FullName"),
                        "email": g("PersonalInformation_Email", "Email"),
                        "phone": g("PersonalInformation_Phone", "Phone"),
                        # Professionalism
                        "misspelling_count": g("Professionalism_MisspellingCount", "MisspellingCount"),
                        "misspelled_words": g("Professionalism_MisspelledWords", "MisspelledWords"),
                        "visual_cleanliness": g("Professionalism_VisualCleanliness", "VisualCleanliness"),
                        "professional_look": g("Professionalism_ProfessionalLook", "ProfessionalLook"),
                        "formatting_consistency": g("Professionalism_FormattingConsistency", "FormattingConsistency"),
                        # Experience
                        "years_since_graduation": g("Experience_YearsSinceGraduation", "YearsSinceGraduation"),
                        "total_years_experience": g("Experience_TotalYearsExperience", "TotalYearsExperience"),
                        "employer_names": g("Experience_EmployerNames", "Stability_EmployerNames", "EmployerNames"),
                        # Stability
                        "employers_count": g("Stability_EmployersCount", "EmployersCount"),
                        "avg_years_per_employer": g("Stability_AvgYearsPerEmployer", "AvgYearsPerEmployer"),
                        "years_at_current_employer": g("Stability_YearsAtCurrentEmployer", "YearsAtCurrentEmployer"),
                        # Socioeconomic
                        "address": g("SocioeconomicStandard_Address", "Address"),
                        "alma_mater": g("SocioeconomicStandard_AlmaMater", "AlmaMater"),
                        "high_school": g("SocioeconomicStandard_HighSchool", "HighSchool"),
                        "education_system": g("SocioeconomicStandard_EducationSystem", "EducationSystem"),
                        "second_foreign_language": g("SocioeconomicStandard_SecondForeignLanguage", "SecondForeignLanguage"),
                        # Flags
                        "flag_stem_degree": g("Flags_FlagSTEMDegree", "FlagSTEMDegree"),
                        "military_service_status": g("Flags_MilitaryServiceStatus", "MilitaryServiceStatus"),
                        "worked_at_financial_institution": g("Flags_WorkedAtFinancialInstitution", "WorkedAtFinancialInstitution"),
                        "worked_for_egyptian_government": g("Flags_WorkedForEgyptianGovernment", "WorkedForEgyptianGovernment"),
                    })
            self.logger.log_kv("CSV_GET_ROWS", rows=len(rows), exists=True)
        except Exception as e:
            self.logger.log_kv("CSV_GET_ROWS_ERROR", error=e)
        return rows

    def read_index(self) -> Dict[str, dict]:
        """Read existing rows and return a dict keyed by ID (file columns)."""
        p = self.csv_path
        index: Dict[str, dict] = {}
        if not p.exists():
            self.logger.log_kv("CSV_READ_INDEX", rows=0, exists=False)
            return index
        try:
            with p.open("r", encoding="utf-8", newline="") as rf:
                reader = csv.DictReader(rf)
                for r in reader:
                    rid = r.get("ID") or r.get("id") or r.get("Id") or ""
                    ts = r.get("Timestamp") or r.get("timestamp") or ""
                    cv = r.get("CV") or r.get("cv") or r.get("filename") or ""
                    if rid:
                        index[rid] = {**{k: r.get(k, "") for k in self.HEADER}, "ID": rid, "Timestamp": ts, "CV": cv}
            self.logger.log_kv("CSV_READ_INDEX", rows=len(index), exists=True)
        except Exception as e:
            self.logger.log_kv("CSV_READ_INDEX_ERROR", error=e)
        return index

    # CSV export removed as requested.
        all_keys = set(self.DEFAULT_HEADER)
        for r in rows_by_id.values():
            flat = self.flatten_json(r)
            flat_rows.append(flat)
            all_keys.update(flat.keys())
        header = list(all_keys)
        # Sort header for stability, keep DEFAULT_HEADER order first
        header = self.DEFAULT_HEADER + sorted([k for k in header if k not in self.DEFAULT_HEADER])
        try:
            with p.open("w", encoding="utf-8", newline="") as wf:
                writer = csv.writer(wf)
                writer.writerow(header)
                for flat in flat_rows:
                    writer.writerow([flat.get(col, "") for col in header])
            self.logger.log_kv("CSV_WRITE_ROWS", rows=len(rows_by_id), path=str(p))
        except Exception as e:
            self.logger.log_kv("CSV_WRITE_ROWS_ERROR", error=e, path=str(p))
            raise


class RolesStore(CSVStore):
    """CSV store for roles data, using CSVStore utility."""
    FILE_NAME = "roles.csv"
    HEADER = [
        "ID",
        "Timestamp",
        "Filename",
        "RoleTitle",
    ]

    def get_public_rows(self) -> list[dict]:
        """Return rows for UI consumption with normalized keys."""
        rows = []
        p = self.csv_path
        if not p.exists():
            self.logger.log_kv("ROLES_CSV_GET_ROWS", rows=0, exists=False)
            return []
        try:
            with p.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rid = r.get("ID") or r.get("id") or r.get("Id") or ""
                    ts = r.get("Timestamp") or r.get("timestamp") or ""
                    fn = r.get("Filename") or r.get("filename") or r.get("file") or ""
                    title = r.get("RoleTitle") or r.get("role_title") or ""
                    rows.append({
                        "id": rid,
                        "timestamp": ts,
                        "filename": fn,
                        "role_title": title,
                    })
            self.logger.log_kv("ROLES_CSV_GET_ROWS", rows=len(rows), exists=True)
        except Exception as e:
            self.logger.log_kv("ROLES_CSV_GET_ROWS_ERROR", error=e)
        return rows


def create_applicants_store(config: AppConfig, logger: AppLogger) -> CSVStore:
    """Factory helper to create an applicants CSVStore."""
    return CSVStore(config, logger)


def create_roles_store(config: AppConfig, logger: AppLogger) -> RolesStore:
    """Factory helper to create a RolesStore."""
    return RolesStore(config, logger)
