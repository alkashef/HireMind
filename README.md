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
- `static/styles.css` — UI styles and layout.
- `utils/csv_manager.py` — CSV-backed stores: `CSVStore` for applicants and `RolesStore` for roles; read/write and public row normalization.
- `utils/openai_manager.py` — Encapsulates OpenAI Responses API usage and file-based extraction prompts.
- `utils/logger.py` — Simple file logger used across services; writes timestamped KV logs to configured log file.
- `config/settings.py` & `config/.env-example` — Centralized configuration: paths, API keys, and runtime knobs.
- `scripts/download_paraphrase.py` — Downloader for the paraphrase embedding model (paraphrase-MiniLM-L12-v2) used for local embeddings.
- `scripts/download_nous-hermes.py` — Downloader for the Hermes Pro GGUF model (defaults to `models/hermes-pro/`).
- `requirements.txt` — Python dependencies for the project (OpenAI SDK, PyMuPDF, sentence-transformers, weaviate-client, etc.).
- `data/applicants.csv` & `data/roles.csv` — Canonical CSV outputs produced by the extract flow (IDs are SHA256 content hashes).
- `utils/weaviate_store.py` (planned) — Weaviate client wrapper and schema helpers to store CVDocument/Role and section embeddings (design and plan in README).

## Setup for Development

### Conda Environment

1. Create a new Conda environment:
```
conda create --name select-ai 
```
1. Install pip:
```
conda install pip
```
1. Install project dependencies:
```
pip install -r requirements.txt
```

Verify the OpenAI SDK and Responses API support using the same interpreter:
```
python -c "import openai; print('openai', openai.__version__); from openai import OpenAI; print('has_responses', hasattr(OpenAI(), 'responses'))"
```
Expected: `has_responses True`. If it's False, ensure you're installing with the same Python: `python -m pip install -r requirements.txt`.

If the SDK still reports `has_responses False`, the app will automatically fall back to calling the Responses REST API directly (requires `requests`, included in `requirements.txt`). No UI changes are needed. The app uses `text.format: json_object` for `full_name` extraction.

### GPU Configuration

Download and install the Nvidia driver appropriate for your GPU

Install the CUDA toolkit:

    Download from: https://developer.nvidia.com/cuda-downloads?target_os=Windows&target_arch=x86_64&target_version=11&target_type=exe_local
    Follow the installation instructions

Install CUDA deep learning package (cuDNN):

    Download from: https://developer.nvidia.com/cudnn-downloads?target_os=Windows&target_arch=x86_64&target_version=10&target_type=exe_local
    Extract and follow installation instructions

Set up PyTorch with CUDA support:

In your Conda environment
pip uninstall torch torchvision torchaudio -y
pip install torch --index-url https://download.pytorch.org/whl/cu126

Verify CUDA installation:

import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA device count: {torch.cuda.device_count()}")
print(f"CUDA device name: {torch.cuda.get_device_name(0)}")

### Mac GPUs (Apple Silicon or Metal-compatible Intel)
Ensure PyTorch 2.0+ is installed:

pip install --upgrade torch

### Download Model

The application uses the Code Llama 7B Instruct model for NL-to-SQL conversion.

    Use the download script:

    python scripts/download_model.py --repo_id codellama/CodeLlama-7b-Instruct-hf --save_path ./models/code-llama-7b-instruct

The model will be downloaded to the models/code-llama-7b-instruct/ directory.

For offline usage, set the environment variable:

export HF_HUB_OFFLINE=1  # Linux/Mac
set HF_HUB_OFFLINE=1     # Windows

### Database Setup
Create a Teradata account on the Clearscape Analytics platform: https://clearscape.teradata.com/
Use the scripts/td_init.sql SQL script to create the database, the tables, and insert sample data.
Configure database credentials in config/.env:

TD_HOST=your-teradata-host.com
TD_NAME=your-database-name
TD_USER=your-username
TD_PASSWORD=your-password
TD_PORT=1025

### Data Path
Set the base data folder in `config/.env`:

DATA_PATH=data

# Applicants and Roles repositories
APPLICANTS_FOLDER=C:\Users\<YourUser>\Documents\Applicants
# If not set, ROLES_FOLDER defaults to APPLICANTS_FOLDER
ROLES_FOLDER=C:\Users\<YourUser>\Documents\Roles

The Extract action writes rows to `DATA_PATH/applicants.csv` with columns: `ID, Timestamp, CV` and category-prefixed fields such as:
- PersonalInformation_FirstName, PersonalInformation_LastName, PersonalInformation_FullName
- Professionalism_MisspellingCount, ...
- Experience_YearsSinceGraduation, Experience_TotalYearsExperience, Experience_EmployerNames
- Stability_EmployersCount, Stability_AvgYearsPerEmployer, Stability_YearsAtCurrentEmployer
- SocioeconomicStandard_Address, ...
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

### Related files → classes → key functions (brief)

- `utils/weaviate_store.py` (planned)
  - class `WeaviateStore`: `ensure_schema()`, `upsert_cv_document()`, `upsert_cv_section()`, `get_cv_by_sha()`, `process_file_and_upsert()`
- `utils/openai_manager.py`
  - class `OpenAIManager`: `extract_full_name_from_file(file_path)`; (planned) `get_embedding(text)` adapter
- `utils/csv_manager.py`
  - classes `CSVStore`, `RolesStore`: `read_index()`, `write_rows()`, `get_public_rows()`
- `config/settings.py`
  - `AppConfig` properties: `weaviate_url`, `weaviate_api_key`, `weaviate_batch_size`
- `app.py`
  - endpoints: `/api/extract` (existing), (planned) `/api/weaviate/cv/<sha>` and `/api/weaviate/role/<sha>`
- `scripts/weaviate_migrate.py` (planned)
  - `batch_upsert_from_csv()` (batch migration helper)

### Explicit method map (design-only, no implementation here)

The pipeline will call small, focused methods (names below). Embeddings are generated locally from the paraphrase model under `models/` and supplied to Weaviate. These are design placeholders and will be implemented as small functions in `utils/` (for example `utils/extractors.py`, `utils/embeddings.py`, and `utils/weaviate_store.py`). Use PascalCase for classes and snake_case for functions.

- pdf_to_text(path: Path) -> str
  - Purpose: extract raw text from a PDF using PyMuPDF (preserve line breaks/spacing).
  - Suggested location: `utils/extractors.py` (or inside `utils/weaviate_store.py` for a minimal design).

- docx_to_text(path: Path) -> str
  - Purpose: extract raw text from a DOCX using python-docx (preserve paragraphs).
  - Suggested location: `utils/extractors.py`.

- text_to_embedding(text: str) -> List[float]
  - Purpose: run the local paraphrase model (from `models/`) to produce an embedding vector for a piece of text.
  - Suggested location: `utils/embeddings.py` or as `WeaviateStore.embed_texts()`.

- write_cv_to_db(sha: str, filename: str, full_text: str, attributes: dict)
  - Purpose: write or upsert a `CVDocument` record to Weaviate: store metadata, `full_text`, and create `CVSection` objects with vectors.
  - Suggested location: `utils/weaviate_store.py` (wraps `upsert_cv_document()` + `upsert_cv_section()`).

- read_cv_from_db(sha: str) -> dict
  - Purpose: read all CV attributes and sections from Weaviate for UI display.
  - Suggested location: `utils/weaviate_store.py` (`get_cv_by_sha()`).

- write_role_to_db(sha: str, filename: str, full_text: str, attributes: dict)
  - Purpose: same as `write_cv_to_db` but writes a `Role` object (job description) and its sections/embeddings.
  - Suggested location: `utils/weaviate_store.py` (`upsert_role()` / reuse `upsert_cv_section()` flow).

- read_role_from_db(sha: str) -> dict
  - Purpose: read a `Role` record and its sections from Weaviate for UI display.
  - Suggested location: `utils/weaviate_store.py` (`get_role_by_id()` / similar to `get_cv_by_sha`).

### UI note

- Add a new right-most column in both Applicants and Roles tabs that displays Weaviate data for the selected file. The frontend should call `GET /api/weaviate/cv/<sha>` or `GET /api/weaviate/role/<sha>` and render a compact table: metadata, full_text snippet, and a list of sections (type + snippet + option to view full section).

### Detailed step-by-step plan (each step is intentionally small)

1) do: add runtime config and examples (small)
    - brief: expose Weaviate connection values in the config so other modules can read them.
    - change(s):
      - update `config/.env-example` to include placeholders: WEAVIATE_URL, WEAVIATE_API_KEY, WEAVIATE_BATCH_SIZE
      - ensure `config/settings.py` exposes `weaviate_url`, `weaviate_api_key`, and `weaviate_batch_size` properties
    - why: keeps configuration explicit and safe; no runtime behavior changes.

2) do: write a minimal client wrapper and schema initializer (small)
    - brief: create `utils/weaviate_store.py` with client initialization and `ensure_schema()` that creates three classes: `CVDocument`, `CVSection`, and `Role` (all vectorizer="none").
    - change(s):
      - file `utils/weaviate_store.py`: add `WeaviateStore` class with `__init__()` and `ensure_schema()` only.
    - acceptance: a dev can run a small Python snippet that imports the module and calls `WeaviateStore(...).ensure_schema()` and confirm classes exist.

3) do: add CV upsert and get-by-sha helpers (small)
    - brief: implement `upsert_cv(sha256, filename, full_text, metadata)` and `get_cv_by_sha(sha256)` to create or update CVDocument objects (no section handling yet).
    - change(s):
      - update `utils/weaviate_store.py`: add `upsert_cv()` and `get_cv_by_sha()` methods.
    - acceptance: can create a CVDocument for a sample file and retrieve it by sha256.

4) do: add section splitting + embedding helper (small)
    - brief: add a deterministic, simple text-splitting helper and an adapter that can call a chosen embedding provider (local paraphrase model or remote provider).
    - change(s):
      - update `utils/weaviate_store.py`: add `_split_into_sections(text)` and `embed_texts(texts)` helpers. Keep both testable independently.
    - acceptance: given a sample CV text, `_split_into_sections()` returns multiple sections; `embed_texts()` returns vectors for each section.

5) do: upsert sections with vectors (small)
    - brief: implement `upsert_section(parent_sha, section_type, section_text, embedding, filename, metadata)` and a convenience `process_file_and_upsert()` that runs CV upsert + section upserts.
    - change(s):
      - update `utils/weaviate_store.py`: add `upsert_section()` and `process_file_and_upsert()`.
    - acceptance: call `process_file_and_upsert()` on one file and verify CVDocument + multiple CVSection objects exist in Weaviate; each CVSection must have a vector.

6) do: add a read API for the UI (small)
    - brief: expose a backend route that returns `get_cv_by_sha(sha)` JSON (CV metadata + sections) so the frontend can render a details table.
    - change(s):
      - add a safe, non-intrusive endpoint in `app.py` like `GET /api/weaviate/cv/<sha>` that returns the Weaviate record or an error if Weaviate is not configured.
    - acceptance: UI can fetch and render CV/sections for a sha without modifying the CSV behavior.

7) do: validation checklist & smoke tests (small)
    - brief: create a short checklist and smoke scripts (not a migration) to verify idempotency, basic retrieval, and vector presence.
    - change(s):
      - small script or notebook (optional) that calls `upsert_cv`, `process_file_and_upsert`, and `get_cv_by_sha` for 1–3 representative CVs and asserts expected shapes.
    - acceptance: automatic checks confirm CV and sections persisted and retrievable.

### Operational notes (parallel-first approach)

- Writes to Weaviate must be idempotent by `sha256`. Implement `upsert_cv` to search by sha and update existing objects instead of creating duplicates.
- Keep the CSV write path completely unchanged and authoritative until you explicitly flip an operator-controlled toggle.
- Weaviate schema uses `vectorizer: "none"` so embedding model version and provider remain under our control.
- When embedding offline, keep a small `models/` folder and a lightweight downloader (existing `scripts/download_paraphrase.py`) to pin the embedding model used for local reproducibility.

### Acceptance criteria (planning)

- All planned steps are documented here in README and each step is small and independently testable.
- Weaviate integration is designed to run concurrently with the CSV pipeline; no migration/retirement actions are included.
- Each incremental step has a clear, minimal acceptance test (create/ensure schema, upsert CV, upsert section, retrieve CV) to reduce blast radius.
