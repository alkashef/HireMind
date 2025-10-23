from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from config.settings import AppConfig
from utils.logger import AppLogger


class RolesStore:
    """CSV store for roles data.

    File: data/data_roles.csv
    Columns: ID, Timestamp, Filename, RoleTitle
    Public rows keys: id, timestamp, filename, role_title
    """

    FILE_NAME = "data_roles.csv"
    HEADER = [
        "ID",
        "Timestamp",
        "Filename",
        "RoleTitle",
    ]

    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger

    @property
    def csv_path(self) -> Path:
        return self.config.data_path / self.FILE_NAME

    def get_public_rows(self) -> List[dict]:
        p = self.csv_path
        if not p.exists():
            self.logger.log_kv("ROLES_CSV_GET_ROWS", rows=0, exists=False)
            return []
        rows: List[dict] = []
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

    def read_index(self) -> Dict[str, dict]:
        p = self.csv_path
        index: Dict[str, dict] = {}
        if not p.exists():
            self.logger.log_kv("ROLES_CSV_READ_INDEX", rows=0, exists=False)
            return index
        try:
            with p.open("r", encoding="utf-8", newline="") as rf:
                reader = csv.DictReader(rf)
                for r in reader:
                    rid = r.get("ID") or r.get("id") or r.get("Id") or ""
                    ts = r.get("Timestamp") or r.get("timestamp") or ""
                    fn = r.get("Filename") or r.get("filename") or r.get("file") or ""
                    if rid:
                        index[rid] = {**{k: r.get(k, "") for k in self.HEADER}, "ID": rid, "Timestamp": ts, "Filename": fn}
            self.logger.log_kv("ROLES_CSV_READ_INDEX", rows=len(index), exists=True)
        except Exception as e:
            self.logger.log_kv("ROLES_CSV_READ_INDEX_ERROR", error=e)
        return index

    def write_rows(self, rows_by_id: Dict[str, dict]) -> None:
        p = self.csv_path
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with p.open("w", encoding="utf-8", newline="") as wf:
                writer = csv.writer(wf)
                writer.writerow(self.HEADER)
                for r in rows_by_id.values():
                    writer.writerow([r.get(col, "") for col in self.HEADER])
            self.logger.log_kv("ROLES_CSV_WRITE_ROWS", rows=len(rows_by_id), path=str(p))
        except Exception as e:
            self.logger.log_kv("ROLES_CSV_WRITE_ROWS_ERROR", error=e, path=str(p))
            raise
