from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple

from config.settings import AppConfig
from utils.logger import AppLogger


class CSVStore:
    """Lightweight CSV store for applicants data.

    Contract:
    - Storage file: data/applicants.csv
    - Columns (in file): ID, Timestamp, CV, FullName
    - Public rows (for UI): id, timestamp, cv, full_name
    """

    FILE_NAME = "applicants.csv"
    # CSV columns (file headers)
    HEADER = [
        "ID",
        "Timestamp",
        "CV",
        # Personal Information
        "PersonalInformation_FirstName",
        "PersonalInformation_LastName",
        "PersonalInformation_FullName",
        "PersonalInformation_Email",
        "PersonalInformation_Phone",
        # Professionalism
        "Professionalism_MisspellingCount",
        "Professionalism_MisspelledWords",
        "Professionalism_VisualCleanliness",
        "Professionalism_ProfessionalLook",
        "Professionalism_FormattingConsistency",
        # Experience
        "Experience_YearsSinceGraduation",
        "Experience_TotalYearsExperience",
        "Experience_EmployerNames",
        # Stability
        "Stability_EmployersCount",
        "Stability_AvgYearsPerEmployer",
        "Stability_YearsAtCurrentEmployer",
        # Socioeconomic Standard
        "SocioeconomicStandard_Address",
        "SocioeconomicStandard_AlmaMater",
        "SocioeconomicStandard_HighSchool",
        "SocioeconomicStandard_EducationSystem",
        "SocioeconomicStandard_SecondForeignLanguage",
        # Flags
        "Flags_FlagSTEMDegree",
        "Flags_MilitaryServiceStatus",
        "Flags_WorkedAtFinancialInstitution",
        "Flags_WorkedForEgyptianGovernment",
    ]

    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger

    @property
    def csv_path(self) -> Path:
        return self.config.data_path / self.FILE_NAME

    def get_public_rows(self) -> List[dict]:
        """Return rows for UI consumption with normalized keys.

        Each row is shaped as: {id, timestamp, cv, full_name}.
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

    def write_rows(self, rows_by_id: Dict[str, dict]) -> None:
        """Write all rows (file columns). Overwrites the CSV."""
        p = self.csv_path
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with p.open("w", encoding="utf-8", newline="") as wf:
                writer = csv.writer(wf)
                writer.writerow(self.HEADER)
                for r in rows_by_id.values():
                    writer.writerow([r.get(col, "") for col in self.HEADER])
            self.logger.log_kv("CSV_WRITE_ROWS", rows=len(rows_by_id), path=str(p))
        except Exception as e:
            self.logger.log_kv("CSV_WRITE_ROWS_ERROR", error=e, path=str(p))
            raise
