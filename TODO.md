# TODO

This file contains actionable tasks (work items). The README remains the
primary documentation; this file is for TODOs only.

## Current actionable todos

1. Add extractor utilities (PDF/DOCX) and SHA helper (local, deterministic)
   - Files to edit/create:
     - `utils/extractors.py` (create)
     - small helper in `utils/__init__.py` or `utils/extractors.py` for `compute_sha256_bytes(data: bytes) -> str`
   - Functions to implement:
     - `pdf_to_text(path: Path) -> str` — PyMuPDF extraction, preserve newlines; raise a clear ValueError on unreadable file.
     - `docx_to_text(path: Path) -> str` — python-docx extraction, preserve paragraphs separated by newline.
     - `compute_sha256_bytes(data: bytes) -> str` — deterministic hex digest used as IDs.
   - Description:
     - These are pure-local, deterministic utilities used by subsequent steps. Keep behavior simple and well-documented.
   - Constraints / do not:
     - Do not call OpenAI or Weaviate here. Do not add heavy heuristics or language-specific logic — keep extraction literal.
   - Acceptance:
     - Given a sample PDF and DOCX in tests (or local files), `pdf_to_text()`/`docx_to_text()` return non-empty strings and `compute_sha256_bytes()` returns a stable 64-char hex string.

1. Add embedding adapter (local paraphrase model) and text splitter helper
   - Files to edit/create:
     - `utils/embeddings.py` (create)
     - small splitter helper: `_split_into_sections(text: str) -> List[dict]` (can live in `utils/weaviate_store.py` or `utils/extractors.py` but prefer `utils/weaviate_store.py` for close coupling)
   - Methods to implement:
     - `text_to_embedding(text: str) -> List[float]` — runs local paraphrase model (via sentence-transformers or transformers) and returns a float vector.
     - `_split_into_sections(text: str) -> List[dict]` — deterministic split into sections with `section_type` and `section_text` keys.
   - Description:
     - `text_to_embedding()` must be implemented with an adapter pattern so it can be swapped to a remote provider later. Keep model-loading lazy and cache the model object in module scope.
   - Constraints / do not:
     - Do not attempt to download or install models automatically during runtime. The function should raise a clear error if the model artifacts are missing and mention `scripts/download_paraphrase.py`.
   - Acceptance:
     - `text_to_embedding('hello world')` returns a numeric vector (list of floats) of consistent length; `_split_into_sections()` returns at least one section for non-empty text.

1. Upsert CV sections with vectors and process-file flow
   - Files to edit/create:
     - `utils/weaviate_store.py` (extend)
   - Methods to implement:
     - `write_cv_to_db(...)` (if not already implemented in step 3, ensure it exists)
     - `upsert_cv_section(parent_sha: str, section_type: str, section_text: str, embedding: List[float], metadata: dict) -> dict`
     - `process_file_and_upsert(path: Path, is_role: bool = False)` — orchestrates extraction, sha, write_cv_to_db/write_role_to_db, splitting, embedding, and upserting sections.
   - Description:
     - `process_file_and_upsert()` is a single convenience function that: reads file bytes, computes sha, extracts text with `pdf_to_text`/`docx_to_text`, calls `write_cv_to_db` (or `write_role_to_db`), calls `_split_into_sections()`, calls `text_to_embedding()` per section (or in batch), and calls `upsert_cv_section()` for each section. Keep all operations idempotent by `sha` and section index.
   - Constraints / do not:
     - Keep the CSV write path authoritative; do not remove or alter CSV writes. This function should *also* be safe to run when Weaviate is not configured — in that case it should return a clear status and exit gracefully.
   - Acceptance:
     - `process_file_and_upsert()` returns a dict summarizing `sha`, `num_sections`, and `weaviate_ok: bool`. When Weaviate is configured, `CVSection` objects exist with non-empty vectors.

   - Status: partial — `write_cv_to_db` and `read_cv_from_db` have been implemented in `utils/weaviate_store.py` (the schema was expanded to explicit CSV-mapped properties and `read_cv_from_db` now returns an `attributes` dict). Remaining: `upsert_cv_section` and `process_file_and_upsert` orchestration.

1. Add role write/read helpers (mirror CV helpers) and small API endpoints (safe)
   - Files to edit/create:
     - `utils/weaviate_store.py` (extend)
     - `app.py` (extend, non-breaking)
   - Methods to implement:
     - `write_role_to_db(sha: str, filename: str, full_text: str, attributes: dict) -> dict`
     - `read_role_from_db(sha: str) -> dict | None`
     - In `app.py` add two read-only endpoints:
       - `GET /api/weaviate/cv/<sha>` -> uses `read_cv_from_db`
       - `GET /api/weaviate/role/<sha>` -> uses `read_role_from_db`
   - Description:
     - Role helpers mirror CV helpers. Endpoints are read-only and must return a graceful JSON error if Weaviate is not configured.
   - Constraints / do not:
     - Do not auto-trigger any processing or writes from these endpoints. They are strictly read-only.
   - Acceptance:
     - Hitting the endpoints returns 200 with JSON body when object exists, or 404/400 with a helpful message when not.

1. Validation scripts and smoke-checks (final small commit)
   - Files to edit/create:
     - `scripts/weaviate_smoke.py` (create)
   - Script responsibilities:
     - Run a minimal set of checks: import `WeaviateStore`, call `ensure_schema()`, run `process_file_and_upsert()` on 1–2 representative files in `APPLICANTS_FOLDER`/`ROLES_FOLDER` (if present), and `read_cv_from_db()` to verify data. Print a machine-readable summary (JSON) and return non-zero exit on failure.
   - Constraints / do not:
     - This script is a smoke-check only: it should not perform bulk migration and must be safe to run in dev environments; if Weaviate is not configured it should exit gracefully with a clear exit code and message.
   - Acceptance:
     - Script runs and prints a JSON summary showing `weaviate_ok`, `num_upserts`, `num_sections` for each file, or a clear message explaining why checks were skipped.

### Notes on naming and behavior

- Use the standardized function names in the steps above: `pdf_to_text`, `docx_to_text`, `text_to_embedding`, `write_cv_to_db`, `read_cv_from_db`, `write_role_to_db`, `read_role_from_db`, `process_file_and_upsert`, `upsert_cv_section`.
- Keep the CSV pipeline unchanged and authoritative. All Weaviate work runs in parallel and is idempotent by `sha`.
- Each step must be implemented as a small, self-contained commit that passes its acceptance checks before moving to the next step.

- Flags_MilitaryServiceStatus, Flags_WorkedAtFinancialInstitution, Flags_WorkedForEgyptianGovernment
IDs are SHA-256 content hashes of files; identical-content files share the same ID (last write wins for CV name).
 During extraction, files whose content hash already exists are skipped—no additional API calls are made.
 
Extraction schema (flat JSON, CSV columns mirror these where applicable):
 - Personal Information: full_name, first_name, last_name, email, phone
 - Professionalism: misspelling_count, misspelled_words, visual_cleanliness, professional_look, formatting_consistency
 - Experience: years_since_graduation, total_years_experience
 - Stability: employers_count, employer_names, avg_years_per_employer, years_at_current_employer
 - Socioeconomic Standard: address, alma_mater, high_school, education_system, second_foreign_language
 - Flags: flag_stem_degree, military_service_status, worked_at_financial_institution, worked_for_egyptian_government