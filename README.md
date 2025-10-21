# APP NAME

SHORT DESCRIPTION

## Overview

## Key Features

## Technology Stack

## Important Files:

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

This starts the web server on http://localhost:5000, where you can:

    Connect to the database
    Load the AI model
    Enter natural language queries
    Get translated SQL queries
    Execute queries and view results

Additionally, the current UI includes:
    Applicants tab: use "select CVs folder:" and the Browse button to choose a local folder; the list shows .pdf and .docx files in that folder.
    Roles tab: placeholder for future functionality.

## Batch Mode

python app.py --batch

This processes a batch of questions from the file specified in QUESTIONS_PATH in the .env file and outputs results to an Excel file.