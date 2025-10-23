from config.settings import AppConfig
from utils.logger import AppLogger
from utils.csv_store import CSVStore

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
            import csv
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
