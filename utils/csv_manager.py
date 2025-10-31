"""Minimal CSV manager shim.

This file provides a small, well-tested CSVStore API used by the app and
by tests. It intentionally does not perform any CSV *writes*; write
operations are no-ops to satisfy the requirement "remove CSV-writing
logic from the repo" while keeping read paths working.

Keep this file small and stable so other modules can import it safely.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

from config.settings import AppConfig
from utils.logger import AppLogger


__all__ = ["CSVStore", "RolesStore", "create_applicants_store", "create_roles_store"]


class CSVStore:
    """Lightweight CSV store for applicants data.

    This minimal implementation supports read-only operations used by the
    web UI and tests. The `write_rows` method is intentionally a no-op.
    """

    FILE_NAME = "applicants.csv"

    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger

    @property
    def csv_path(self) -> Path:
        return Path(self.config.data_path) / self.FILE_NAME

    @staticmethod
    def flatten_json(value: dict, parent_key: str = "", sep: str = "_") -> Dict[str, object]:
        """Recursively flatten a nested dict/list structure into a flat map.

        Lists that contain dicts are indexed (key_0, key_1, ...). Non-string
        primitive values are left as-is; other values are JSON-serialized.
        """
        out: Dict[str, object] = {}

        def _flatten(v, k: str):
            if isinstance(v, dict):
                for kk, vv in v.items():
                    _flatten(vv, f"{k}{sep}{kk}" if k else kk)
            elif isinstance(v, list):
                for idx, item in enumerate(v):
                    _flatten(item, f"{k}{sep}{idx}" if k else str(idx))
            else:
                if v is None or isinstance(v, (int, float, bool)):
                    out[k] = v
                else:
                    try:
                        out[k] = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                    except Exception:
                        out[k] = str(v)

        _flatten(value, parent_key)
        return out

    def get_public_rows(self) -> List[dict]:
        """Return rows for UI consumption with normalized keys.

        This reads CSV if present and maps columns to a stable public schema.
        If the CSV file is missing, returns an empty list.
        """
        p = self.csv_path
        if not p.exists():
            self.logger.log_kv("CSV_GET_ROWS", rows=0, exists=False)
            return []

        rows: List[dict] = []
        try:
            with p.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for r in reader:
                    rid = r.get("ID") or r.get("id") or r.get("Id") or ""
                    ts = r.get("Timestamp") or r.get("timestamp") or ""
                    cv = r.get("CV") or r.get("cv") or r.get("filename") or ""

                    def g(*keys: str) -> str:
                        for k in keys:
                            v = r.get(k)
                            if v not in (None, ""):
                                return str(v)
                        return ""

                    rows.append({
                        "id": rid,
                        "timestamp": ts,
                        "cv": cv,
                        "filename": (cv or "").split("/")[-1].split("\\\\")[-1],
                        "first_name": g("PersonalInformation_FirstName", "FirstName"),
                        "last_name": g("PersonalInformation_LastName", "LastName"),
                        "full_name": g("PersonalInformation_FullName", "FullName"),
                        "email": g("PersonalInformation_Email", "Email"),
                        "phone": g("PersonalInformation_Phone", "Phone"),
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
                    if rid:
                        index[rid] = dict(r)
            self.logger.log_kv("CSV_READ_INDEX", rows=len(index), exists=True)
        except Exception as e:
            self.logger.log_kv("CSV_READ_INDEX_ERROR", error=e)
        return index

    def write_rows(self, rows_by_id: Dict[str, dict]) -> None:
        """No-op write: intentionally disabled to avoid persisting CSV files.

        This keeps the public API for callers but prevents any file-system
        writes. Callers expecting a CSV file should instead set up an explicit
        export tool outside the test/repo.
        """
        # Log an informational event and return without writing.
        try:
            self.logger.log_kv("CSV_WRITE_ROWS_SKIPPED", rows=len(rows_by_id))
        except Exception:
            pass
        return


class RolesStore(CSVStore):
    FILE_NAME = "roles.csv"


def create_applicants_store(config: AppConfig, logger: AppLogger) -> CSVStore:
    return CSVStore(config, logger)


def create_roles_store(config: AppConfig, logger: AppLogger) -> RolesStore:
    return RolesStore(config, logger)
