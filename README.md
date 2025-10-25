# Hire Mind

HireMind orchestrates a CV extraction workflow that feeds candidate documents through the OpenAI API and consolidates normalized fields into CSV files stored under `data/`.

## Key Features

- Batch CV ingestion with structured CSV export to `data/applicants.csv`
- Rich server-side logging for key events (listing, picks, hashing, extraction, OpenAI calls; folder events use APPLICANTS_FOLDER and ROLES_FOLDER)
- Flask single-page UI for browsing folders, selecting CVs, triggering extraction, and viewing results
- UI now uses a 3-column layout: left-most column for the CV file list (with Select All and Extract), and two columns for details split into 6 titled sections (Personal Information, Experience, Stability, Professionalism, Socioeconomic Standard, Flags). Section titles are grey text above each table; tables share a consistent left-column width.
 - Roles tab mirrors the Applicants left-side layout: Roles Repository picker (path text box + Browse + Refresh) and a list of .pdf/.docx role files.
 - The folder path + Browse/Refresh control sits in the left column and matches the file list width; selected files are visually highlighted with a left accent line.
  
Note: the extraction pipeline is intentionally generic — it applies to both CVs (applicants) and role/job-description files. The same file-reading, OpenAI extraction, sectioning, embedding and upsert pipeline will be reused for both file types. The only differences are the downstream CSV columns/attributes and the Weaviate class properties which are mapped per-type (applicants vs roles).
- Duplicate detection by content hash; clear status bar with live progress and elapsed time
    - Duplicate highlighting marks all files in each duplicate group (both the original and its copies)
- OpenAI Responses API via latest SDK with automatic HTTP fallback; `text.format` set to `json_object`
 - Expanded extraction fields saved to CSV and shown in UI: Personal Information, Professionalism, Experience, Stability, Socioeconomic Standard, and Flags (see schema below)
 - Skips re-extraction for files already processed (by content hash)

## Technology Stack

<!-- ChromaDB removed from the project. Vector storage is planned to use Weaviate. -->

## Important Files:
- `app.py` – Flask app exposing the UI and API endpoints
- `templates/index.html` – single-page UI (file list + details table + status bar)
- `static/styles.css` – styles, including the fixed first column for the details table
- `static/status.js` – shared in-app status and progress helpers used by the UI
 - `utils/csv_manager.py` – CSVStore and RolesStore encapsulating read/write of `data/applicants.csv` and `data/roles.csv`
- `utils/openai_manager.py` – encapsulates OpenAI SDK + HTTP fallback (vector stores, file_search, text.format)
- `prompts/` – prompt templates used by the OpenAI extraction flow (e.g., `cv_full_name_system.md`, `cv_full_name_user.md`)
- `config/.env` – runtime configuration (mirrored by `config/.env-example`)
- `config/settings.py` – central AppConfig loader for environment and paths
- `utils/logger.py` – AppLogger writing to `LOG_FILE_PATH` with [TIMESTAMP] and kv helper

## Quick file reference
Brief one-line summary of core files and their primary purpose.

- `app.py` — Flask server: endpoints for listing files, extracting CVs/roles, progress, and simple admin routes.
- `templates/index.html` — Single-page UI that drives file selection, extraction actions, and displays result tables.
- `static/main.js` / `static/roles.js` — Frontend behaviour for Applicants and Roles views (selection, extract, fetch details).
- `static/status.js` — Shared status/progress helpers used by the UI.


OpenAI SDK version

- This project now targets the latest OpenAI Python SDK (see requirements.txt). The Responses API uses `text.format`; we set `text.format` to `json_object` to return structured JSON. If you previously installed a different version globally, reinstall with `python -m pip install -r requirements.txt`.

Older CSVs (from before prefixing) are read with backward-compatible field mapping so existing extractions continue to show in the UI. Employer names are now mapped under Experience (fallback reads Stability_EmployerNames).

### How to Test

Run tests to verify the application components are working correctly:
Test Database Connection

python test/test_db.py

This test connects to the Teradata database, retrieves the schema, and executes a sample query to validate connectivity.
Test Model Integration

python test/test_model.py

This test verifies that:

    The model files are present
    The model loads correctly
    The model can generate responses to prompts

Test SQL Extraction

python test/test_extract_sql.py

This test validates the SQL extraction logic from model outputs.
How to Run

The application can be run in two modes:
Web UI Mode (Default)

python app.py

This starts the web server on http://localhost:5000. On launch, the log will include entries like `APP_START` (server starting) and `APP_READY` (first request can be served). The `APP_START` log also includes `openai_version` and `has_responses` to help diagnose SDK mismatches. You can then:

    Connect to the database
    Load the AI model
    Enter natural language queries
    Get translated SQL queries
    Execute queries and view results

Additionally, the current UI includes:
    Applicants tab: use "CVs Repository:" and the Browse button to choose a local folder. The top bar includes a Refresh button to reload the list. The UI is split: left pane (50% width) shows the file list with filenames only (no full paths) and a footer with Select All and Extract buttons; single-click selects one file, while Ctrl/⌘-click toggles multiple and Shift-click selects a range. The list shows `N files | M selected | X duplicates found` and highlights duplicates (by content hash) in pink. The right pane renders a read-only, transposed two-column detail table (Header | Value) that is always visible: when a file is selected, it shows that record; when nothing is selected or not yet extracted, it remains visible with empty values. Selection is preserved after extraction. The first column width is fixed for readability. A status bar at the bottom is verbose: it shows loading states (e.g., computing duplicates, loading results), live extraction progress with elapsed time, and completion summaries (saved count and error count).
    Roles tab: placeholder for future functionality.

## Batch Mode

python app.py --batch

This processes a batch of questions from the file specified in QUESTIONS_PATH in the .env file and outputs results to an Excel file.

---

## Weaviate integration — parallel implementation (planning only)

### Purpose

This section documents a clear, step-by-step plan for adding Weaviate as a parallel vector & document store. IMPORTANT: we will not perform a migration or retire the CSV pipeline here — both systems will run in parallel during development and validation. The goal is to make Weaviate a fully-featured, optional back-end service that mirrors the CSV content (metadata + CV text + section embeddings) and provides vector search and filtered retrieval.

### High-level goals

- Store structured OpenAI-extracted attributes (booleans/ints/strings) on a CVDocument record.
- Store full CV text and break it into semantic sections; each section will have its own embedding and metadata.
- Store roles as Role objects with role_text, attributes, and embeddings.
- Keep CSV export/writes unchanged and authoritative during development; Weaviate writes are concurrent and idempotent.

Note on generic handling: the pipeline is shared for both CVs and Roles — the implementation will treat each input file the same through extraction, sectioning and embedding. A lightweight mapping layer will translate the extracted attributes into the correct CSV columns (`data/applicants.csv` vs `data/roles.csv`) and into the corresponding Weaviate class properties (`CVDocument` vs `Role`).

### Design constraints

- No CSV retirement steps in this document. All work is explicitly for parallel integration.
- Small, testable commits are preferred. Each step below is scoped to a minimal change that can be validated independently.
- Keep Weaviate classes vectorizer="none" and supply vectors on create so we control embedding provider and model version.

### Acceptance criteria (planning)

### Acceptance criteria (planning)

- All planned steps are documented here in README and each step is small and independently testable.
- Weaviate integration is designed to run concurrently with the CSV pipeline; no migration/retirement actions are included.
- Each incremental step has a clear, minimal acceptance test (create/ensure schema, upsert CV, upsert section, retrieve CV) to reduce blast radius.

### Detailed step-by-step plan (numbered, implementation-ready)

Below is a single numbered list of small, independent implementation steps. Each step is written so it can be implemented as one small commit by an LLM agent (e.g., GPT-5 mini in agent mode). Every step includes: files to edit/create, method names (use the standardized names), a concise description, constraints and "do not do" notes, and an explicit acceptance checklist that must pass before moving to the next step.

Local Weaviate — setup & run (quick start)
---------------------------------------

If you want to run Weaviate locally for development and testing, follow these quick, platform-specific steps. The project provides a minimal `docker-compose.weaviate.yml` that launches a single-node Weaviate with vectorizer disabled (we supply vectors).

Windows (cmd.exe)

1. Make sure Docker Desktop is running.
2. From the project root, start Weaviate:

```
docker compose -f docker-compose.weaviate.yml up -d
```

3. Wait a few seconds, then verify the container is running:

```
docker ps
docker logs -f hiremind_weaviate
```

4. Probe the running instance using the included lightweight test:

```
set WEAVIATE_USE_LOCAL=true
python tests/test_weaviate_local.py
```

PowerShell

1. Start Docker Desktop.
2. From the project root:

```
docker compose -f docker-compose.weaviate.yml up -d
```

3. Check status and logs:

```
docker ps
docker logs -f hiremind_weaviate
```

4. Run the probe (PowerShell):

```
$env:WEAVIATE_USE_LOCAL = "true"; python tests/test_weaviate_local.py
```

Helper scripts (Windows)

Two convenient helpers are provided under `scripts/` to start and stop the local Weaviate stack from the project root:

```
scripts\run_weaviate.bat   # starts Weaviate using docker compose
scripts\stop_weaviate.bat  # stops and removes the compose stack
```

Run them from a cmd.exe prompt in the repository root. They wrap the `docker compose` commands and print status/errors to make local dev easier.

Environment variable: WEAVIATE_DATA_PATH

You can override where Weaviate persists its data on the host by setting `WEAVIATE_DATA_PATH` in `config/.env` or your environment. By default the project uses `data/weaviate_data`. If you set this variable, update the compose/run commands to mount that path.

Example (cmd.exe):

```
set WEAVIATE_DATA_PATH=C:\path\to\persisted\weaviate
docker compose -f docker-compose.weaviate.yml up -d
```


Fallback: run the container directly (no compose)

If Compose has issues, you can run the Weaviate image directly (cmd.exe example):

```
docker pull semitechnologies/weaviate:1.19.3
docker run -d --name hiremind_weaviate -p 8080:8080 ^
  -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true ^
  -e PERSISTENCE_DATA_PATH=/var/lib/weaviate ^
  -e DEFAULT_VECTORIZER_MODULE=none ^
  -e ENABLE_MODULES=none ^
  -v %cd%\\data\\weaviate_data:/var/lib/weaviate ^
  semitechnologies/weaviate:1.19.3
```

Notes & troubleshooting

- If the Docker CLI reports it cannot connect to the engine (named-pipe / EOF errors on Windows), start or restart Docker Desktop and retry. `docker version` and `docker info` should report a running engine.
- If the probe returns HTTP 200 but `tests/test_weaviate_local.py` prints "Skipping ensure_schema() (client missing)" then install the optional Python client in your virtualenv to enable `ensure_schema()`:

```
pip install weaviate-client
```

- To create the schema from the repository code (idempotent):

```
python -c "from utils.weaviate_store import WeaviateStore; s=WeaviateStore(url='http://localhost:8080'); print('ensure_schema:', s.ensure_schema())"
```

- To have `make_default_store()` pick up your environment automatically, set `WEAVIATE_URL`:

```
set WEAVIATE_URL=http://localhost:8080
```

These quick steps are intended for development. The README's numbered plan above documents the production-safe, idempotent workflow we follow when adding Weaviate integration in the codebase.

1) Add runtime config keys (safe, non-breaking)
   - Files to edit/create:
     - `config/.env-example` (edit)
     - `config/settings.py` (ensure properties exposed)
   - Methods/props to add or confirm:
     - `AppConfig.weaviate_url`, `AppConfig.weaviate_api_key`, `AppConfig.weaviate_batch_size`
   - Description:
     - Add placeholder env vars to `.env-example` and expose read-only properties in `config/settings.py` so other modules can import the config without changing runtime behavior when values are unset.
   - Constraints / do not:
     - Do not connect to Weaviate or add logic that fails if the keys are missing. Keep behavior read-only and optional.
   - Acceptance (one-line checks):
     - `config/settings.py` imports and exposes the three properties and `config/.env-example` contains the three placeholder keys.

2) Create minimal `utils/weaviate_store.py` skeleton with `ensure_schema()` (idempotent)
   - Files to edit/create:
     - `utils/weaviate_store.py` (create)
   - Methods/classes to implement:
     - class `WeaviateStore` with `__init__(self, url: str | None, api_key: str | None, batch_size: int = 64)`
     - `ensure_schema(self) -> None` — only schema creation; do not write documents.
   - Description:
     - Implement a small wrapper that optionally initializes a Weaviate client when `weaviate_url` is set. `ensure_schema()` creates three classes: `CVDocument`, `CVSection`, and `Role` with `vectorizer: "none"` and minimal properties (sha, filename, metadata, full_text for CVDocument; parent_sha, section_type, section_text for CVSection; role_text for Role).
   - Constraints / do not:
     - Do not create or upsert any CV/Section objects here. Keep class creation idempotent. If `weaviate_url` is unset, `ensure_schema()` should be a no-op that returns gracefully.
   - Acceptance:
     - Importing `WeaviateStore` and calling `WeaviateStore(...).ensure_schema()` does not raise if `weaviate_url` is not configured, and when configured, required classes exist in Weaviate.

3) Add CV write/read minimal helpers (metadata-only, no sections yet)
   - Files to edit/create:
     - `utils/weaviate_store.py` (extend)
   - Methods to add:
     - `write_cv_to_db(sha: str, filename: str, full_text: str, attributes: dict) -> dict` — create or update a `CVDocument` record (metadata + full_text). Implementation may call internal `_find_by_sha()` and `_create_or_update()` helpers.
     - `read_cv_from_db(sha: str) -> dict | None` — return the CVDocument metadata and `full_text` (no sections yet).
   - Description:
     - Implement idempotent upsert behavior keyed by `sha`. Do not split text or create sections. Persist metadata fields in Weaviate properties that map to the CSV columns.
   - Constraints / do not:
     - Do not attempt to compute or store section embeddings. Keep embeddings and sections out of scope for this step.
   - Acceptance:
     - After calling `write_cv_to_db(...)`, `read_cv_from_db(sha)` returns the same metadata and `full_text`.

4) Add extractor utilities (PDF/DOCX) and SHA helper (local, deterministic)
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

5) Add embedding adapter (local paraphrase model) and text splitter helper
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

6) Upsert CV sections with vectors and process-file flow
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

7) Add role write/read helpers (mirror CV helpers) and small API endpoints (safe)
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

8) Validation scripts and smoke-checks (final small commit)
   - Files to edit/create:
     - `scripts/weaviate_smoke.py` (create)
   - Script responsibilities:
     - Run a minimal set of checks: import `WeaviateStore`, call `ensure_schema()`, run `process_file_and_upsert()` on 1–2 representative files in `APPLICANTS_FOLDER`/`ROLES_FOLDER` (if present), and `read_cv_from_db()` to verify data. Print a machine-readable summary (JSON) and return non-zero exit on failure.
   - Constraints / do not:
     - This script is a smoke-check only: it should not perform bulk migration and must be safe to run in dev environments; if Weaviate is not configured it should exit gracefully with a clear exit code and message.
   - Acceptance:
     - Script runs and prints a JSON summary showing `weaviate_ok`, `num_upserts`, `num_sections` for each file, or a clear message explaining why checks were skipped.

Notes on naming and behavior

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