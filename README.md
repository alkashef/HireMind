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
- `TODO.md` - developer-facing actionable task list. Keep this file in sync with
    the README's Detailed step-by-step plan; `README.md` remains documentation
    while `TODO.md` is for in-progress work items and small commits.

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

