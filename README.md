# APP NAME

SHORT DESCRIPTION

## Overview

HireMind orchestrates a CV extraction workflow that feeds candidate documents through the OpenAI API and consolidates normalized fields into CSV files stored under `data/`.

## Key Features

- Batch CV ingestion with structured CSV export to `data/data_applicants.csv`
- Rich server-side logging for key events (listing, picks, hashing, extraction, OpenAI calls)
- Streamlit UI for configuring folders, triggering runs, and downloading results
- Flask utility endpoints for browsing local folders inside the desktop helper app

## Technology Stack

## Important Files:
- `app.py` – Flask helper for the desktop folder browser UI
- `ui/streamlit_app.py` – Streamlit front-end for running extractions
- `services/cv_processor.py` – batch processor that writes CSV output to `data/`
- `prompts/` – prompt templates used by the OpenAI extraction flow (e.g., `cv_full_name_system.md`, `cv_full_name_user.md`)
- `config/.env` – runtime configuration (mirrored by `config/.env-example`)
- `config/settings.py` – central AppConfig loader for environment and paths
- `utils/logger.py` – AppLogger writing to `LOG_FILE_PATH` with [TIMESTAMP] and kv helper
- `static/status.js` – shared in-app status and progress helpers used by the UI

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

The Extract action writes rows to `DATA_PATH/data_applicants.csv` with columns: `ID,Timestamp,CV,FullName`.
IDs are SHA-256 content hashes of files; identical-content files share the same ID (last write wins for CV name).

OpenAI SDK version

- This project now targets the latest OpenAI Python SDK (see requirements.txt). The Responses API uses `text.format`; we set `text.format` to `json_object` to return structured JSON. If you previously installed a different version globally, reinstall with `python -m pip install -r requirements.txt`.

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
    Applicants tab: use "CVs Repository:" and the Browse button to choose a local folder. The top bar includes a Refresh button to reload the list. The UI is split: left pane (50% width) shows the file list with filenames only (no full paths) and a footer with Select All and Extract buttons; single-click selects one file, while Ctrl/⌘-click toggles multiple and Shift-click selects a range. The list shows `N files | M selected | X duplicates found` and highlights duplicates (by content hash) in pink. The right pane renders a read-only, transposed two-column detail table (Header | Value) that is always visible: when a file is selected, it shows that record; when nothing is selected or not yet extracted, it remains visible with empty values. After extraction, the selection is cleared. A status bar at the bottom is now more verbose: it shows loading states (e.g., computing duplicates, loading results), live extraction progress with elapsed time, and completion summaries (saved count and error count).
    Roles tab: placeholder for future functionality.

## Batch Mode

python app.py --batch

This processes a batch of questions from the file specified in QUESTIONS_PATH in the .env file and outputs results to an Excel file.