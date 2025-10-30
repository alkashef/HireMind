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
 - `prompts/` – prompt templates used by the OpenAI extraction flow (e.g., `extract_from_cv_system.md`, `extract_from_cv_user.md`)
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

## Setup for Development

#### Conda Environment

1. Create a new Conda environment (Windows cmd.exe):

```cmd
conda create --name hiremind python=3.11
conda activate hiremind
```

2. Install pip and build tools (if needed):

```cmd
conda install pip
```

3. Install project dependencies:

```cmd
pip install -r requirements.txt
```

#### GPU Configuration (recommended: CUDA 12.6 / cu126)

1. Install NVIDIA driver appropriate for your GPU (use NVIDIA site or
     your package manager). Verify with `nvidia-smi`.
2. Install the CUDA toolkit and cuDNN (follow NVIDIA instructions).
3. Install PyTorch with a matching CUDA wheel. The project recommends CUDA
     12.6 (cu126) for reproducible developer and CI setups. Two options:

```cmd
# Option A: use the helper (prints and can run the install)
python scripts\download_cuda.py --cuda 12.6

# Option B: run pip directly (uses the index URL for cu126)
pip uninstall torch torchvision torchaudio -y
pip install torch --index-url https://download.pytorch.org/whl/cu126
```

4. Verify the CUDA-enabled torch install:

```cmd
python -c "import torch; print('torch:', torch.__version__); print('torch.cuda.is_available():', torch.cuda.is_available()); print('torch.version.cuda:', torch.version.cuda); print('device_count:', torch.cuda.device_count()); print('device_name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no device')"
```

Notes:
- If you cannot use CUDA on your machine, a CPU-only `torch` install is
    supported but some local model tests will be skipped or slower.

#### Download Models

The project uses local models for embeddings and (optionally) LLM inference.
Use the included scripts to download them into `models/`.

- Paraphrase embeddings (sentence-transformers):

```cmd
python scripts\download_paraphrase.py
```

- Hermes / Nous models (GGUF / HF):

```cmd
python scripts\download_nous-hermes.py
```

Set `HF_HUB_OFFLINE=1` (or `set HF_HUB_OFFLINE=1` on Windows) to force
offline usage of cached Hugging Face files once downloaded.

### Quick GPU env setup and test (Windows cmd)

If you want a minimal, repeatable sequence to get a CUDA-enabled dev env and run the Hermes smoke test, follow these steps on Windows (cmd.exe). This lists the essential steps we use during development and CI validation.

1) Install NVIDIA drivers

    - Download and install the latest NVIDIA driver for your GPU from https://www.nvidia.com/Download/index.aspx. Reboot if prompted.
    - Verify drivers are installed with:

```cmd
nvidia-smi
```

2) Install CUDA toolkit (matching recommended runtime)

    - Install the CUDA toolkit that matches the project's recommended runtime (CUDA 12.6 / cu126) from https://developer.nvidia.com/cuda-toolkit. Follow NVIDIA's installer instructions for Windows.
    - After install, verify with `nvidia-smi` and by checking `torch` once installed (see step 4).

3) Create and activate the Conda environment

```cmd
conda create --name hiremind python=3.11 -y
conda activate hiremind
```

4) Install Python dependencies

```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

5) Run the Hermes smoke test (FP16 + optional 4-bit)

```cmd
# run the single Hermes smoke test (fast, focused)
pytest -q tests/test_hermes_local.py

# or run directly with python (useful for quick manual runs)
python tests/test_hermes_local.py
```

Notes:
- If your GPU has limited VRAM (e.g., ~8GB), the 4-bit (BitsAndBytes) load may be skipped by the test — FP16 is still validated. The test contains a fallback that attempts CPU offload for 4-bit quantization and will `skip` if the local hardware cannot place parameters on CUDA.
- If you need reliable 4-bit testing, run on a machine with more GPU RAM or use a cloud VM with a larger GPU.

#### Data and CSV

- The CSV pipeline (`data/applicants.csv`, `data/roles.csv`) remains the
    authoritative export. Weaviate integration runs in parallel and is optional.

## How to Test

Run the project's test suite with `pytest`. Examples:

- Run everything:

```cmd
python -m pytest -q
```

- Run specific tests (fast probes):

```cmd
python -m pytest tests/test_gpu.py -q          # GPU probe and torch checks
python -m pytest tests/test_weaviate_local.py -q  # Weaviate probe (if running locally)
python -m pytest tests/test_extractors_local.py -q
```

Notes:
- Some tests require optional packages or model files (e.g., `sentence-transformers`, `torch` with CUDA, Hermes models). The tests are written to skip with helpful messages when prerequisites are missing.
- Prefer running tests in the project's virtual environment (`conda activate hiremind`).

Environment sourcing for tests
------------------------------

The test suite now reads runtime configuration from `config/.env` automatically
before tests run. Any KEY=VALUE lines in that file that are not already set in
the process environment will be exported into `os.environ`. This makes it
convenient to keep local settings (for example `TEST_CV_PATH` or
`TEST_CV_JSON_OUTPUT`) in `config/.env` while allowing sensitive values like
`OPENAI_API_KEY` to be provided via the shell if you prefer.

Commands (Windows cmd.exe)
--------------------------

Run all tests:

```cmd
python -m pytest -q
```

Run the PDF end-to-end tests (extraction + optional OpenAI steps):

```cmd
python -m pytest -q tests/test_end2end_extract_pdf.py -s
```

Notes about OpenAI-dependent tests
---------------------------------

- Tests that call the OpenAI API require `OPENAI_API_KEY` and valid SSL
    certificate env vars. You can either provide those in `config/.env` or set
    them in your shell. The test runner will read `config/.env` so values placed
    there are picked up automatically.

Security note: keep real API keys out of the repository; use `config/.env` as
a local-only file and ensure it's ignored by git. Keep `config/.env-example`
in the repo to show required variable names.

## How to Run

#### Web UI Mode (Default)

```cmd
python app.py
```

Starts the Flask UI on `http://localhost:5000`.

#### Batch Mode

```cmd
python app.py --batch
```

Processes the batch file specified by `QUESTIONS_PATH` in `config/.env` and writes results to an Excel file.

## Developer notes

- Developer TODOs and ongoing work items live in `TODO.md`. Keep that file
    synced with this README's Detailed step-by-step plan; `README.md` is
    documentation-only while `TODO.md` is for in-progress tasks and small
    commits.
- Safe cleaning: `scripts/clear_cache.py` will skip anything inside
    `models/` and `data/` to avoid accidental deletion of model artifacts or
    user data. Use `--dry-run` to preview deletions.
- Configuration: use `config/.env` (local) and keep `config/.env-example` as
    the template for required and optional environment variables.
 - Developer GPU guidance: for reproducible developer setups we recommend
   using CUDA 12.6 (package tag `cu126`) as the canonical dev CUDA runtime.
   The repository's `requirements.txt` includes an extra-index-url for `cu126`
   and `scripts/download_cuda.py --cuda 12.6` prints a matching `pip install`
   command. If you want GPU-enabled `torch`, install the wheel for `cu126` to
   match CI/dev expectations and local tests.

## Batch Mode

python app.py --batch

This processes a batch of questions from the file specified in QUESTIONS_PATH in the .env file and outputs results to an Excel file.

---

## Weaviate integration — parallel implementation (planning only)

### Purpose

This section documents a clear, step-by-step plan for adding Weaviate as a parallel vector & document store. IMPORTANT: we will not perform a migration or retire the CSV pipeline here — both systems will run in parallel during development and validation. The goal is to make Weaviate a fully-featured, optional back-end service that mirrors the CSV content (metadata + CV text + section embeddings) and provides vector search and filtered retrieval.

Schema contract: the canonical schema lives in `data/weaviate_schema.json`; point `WEAVIATE_SCHEMA_PATH` in `config/.env` to this file so the app can load and apply it at startup — the application will raise and exit if the schema file is missing or malformed.

### High-level goals

- Store structured OpenAI-extracted attributes (booleans/ints/strings) on a CVDocument record.
- Store full CV text and break it into semantic sections; each section will have its own embedding and metadata.
- Store roles as Role objects with role_text, attributes, and embeddings.
- Keep CSV export/writes unchanged and authoritative during development; Weaviate writes are concurrent and idempotent.

Note on generic handling: the pipeline is shared for both CVs and Roles — the implementation will treat each input file the same through extraction, sectioning and embedding. A lightweight mapping layer will translate the extracted attributes into the correct CSV columns (`data/applicants.csv` vs `data/roles.csv`) and into the corresponding Weaviate class properties (`CVDocument` vs `Role`).

### Design constraints

- No CSV retirement steps in this document. All work is explicitly for parallel integration.
- Small, testable commits are preferred. Each step below is scoped to a minimal change that can be validated independently.
- Schema is an explicit contract stored in `data/weaviate_schema.json` (referenced by `WEAVIATE_SCHEMA_PATH`) and must be respected by the application; the app will fail fast if the schema is missing or invalid.

Note on vectorization: this repository's schema uses Weaviate-native vectorization (`text2vec-transformers`) for documents and sections; ensure your Weaviate deployment enables the `text2vec-transformers` module (or update the schema to a vectorizer available in your environment).

### Acceptance criteria (planning)

### Acceptance criteria (planning)

- All planned steps are documented here in README and each step is small and independently testable.
- Weaviate integration is designed to run concurrently with the CSV pipeline; no migration/retirement actions are included.
- Each incremental step has a clear, minimal acceptance test (create/ensure schema, upsert CV, upsert section, retrieve CV) to reduce blast radius.

### Detailed step-by-step plan (numbered, implementation-ready)

Below is a single numbered list of small, independent implementation steps. Each step is written so it can be implemented as one small commit by an LLM agent (e.g., GPT-5 mini in agent mode). Every step includes: files to edit/create, method names (use the standardized names), a concise description, constraints and "do not do" notes, and an explicit acceptance checklist that must pass before moving to the next step.

Local Weaviate — setup & run (quick start)
---------------------------------------

If you want to run Weaviate locally for development and testing, follow these quick, platform-specific steps. The project provides a minimal `docker-compose.weaviate.yml` that launches a single-node Weaviate; adjust the compose settings to enable the `text2vec-transformers` module if you want Weaviate to compute vectors natively.

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

Note about env sourcing

The `scripts\run_weaviate.bat` helper will source environment variables from `config/.env` before launching Weaviate. It parses simple `KEY=VALUE` lines (skips comments and blank lines), handles optional `export ` prefixes and quoted values, and sets them into the script process so `docker compose` picks up the same configuration used by the app. This makes it convenient to run Weaviate with the same `WEAVIATE_*` and `WEAVIATE_DATA_PATH` settings defined for local development.

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
    -e DEFAULT_VECTORIZER_MODULE=text2vec-transformers ^
    -e ENABLE_MODULES=text2vec-transformers ^
  -v %cd%\\data\\weaviate_data:/var/lib/weaviate ^
  semitechnologies/weaviate:1.19.3
```

Notes & troubleshooting

- If the Docker CLI reports it cannot connect to the engine (named-pipe / EOF errors on Windows), start or restart Docker Desktop and retry. `docker version` and `docker info` should report a running engine.
- If the probe returns HTTP 200 but `tests/test_weaviate_local.py` prints "Skipping ensure_schema() (client missing)" then install the optional Python client in your virtualenv to enable `ensure_schema()`:
 - If the probe returns HTTP 200 but `tests/test_weaviate_local.py` prints "Skipping ensure_schema() (client missing)" then install the optional Python client in your virtualenv to enable `ensure_schema()` (project now targets weaviate-client v4):

```cmd
pip install "weaviate-client>=4.17.0"
```

- To create the schema from the repository code (idempotent):

```
python -c "from utils.weaviate_store import WeaviateStore; s=WeaviateStore(url='http://localhost:8080'); print('ensure_schema:', s.ensure_schema())"
```

- To have `make_default_store()` pick up your environment automatically, set `WEAVIATE_URL`:

```
set WEAVIATE_URL=http://localhost:8080
```

