# HireMind 🧠# HireMind 🧠# HireMind 🧠# HireMind 🧠# Hire Mind



## Overview



HireMind batches CVs through an OpenAI Agent workflow, extracts structured insights, and stores the results in a CSV file. A Streamlit UI wraps the workflow so recruiters can point at a folder of resumes, launch the extraction, and download a clean dataset for downstream review.## Overview



## Key Features



- Folder-based CV ingestion supporting PDF, DOCX, and TXT formatsHireMind is an intelligent CV processing system that leverages OpenAI's Agent SDK to extract structured insights from candidate resumes. The app processes entire folders of CVs, produces detailed markdown analyses, and writes the results to a CSV file for downstream review.## Overview

- OpenAI `o1-pro` agent with high reasoning effort for rich analysis

- Structured CSV output containing source metadata, raw markdown, and normalized fields

- Streamlit dashboard with live progress, error reporting, and CSV download

- Modular services for file parsing, agent orchestration, and prompt management## Key Features



## Technology Stack



- **AI Engine**: OpenAI Agent SDK (`agents` package)- Batch CV ingestion from a local folder (PDF, DOCX, TXT)HireMind is an intelligent CV processing system that leverages OpenAI's Agent SDK to extract structured information from candidate resumes. The application processes CVs in batch mode, extracting comprehensive candidate data and generating organized CSV reports.## Overview

- **Frontend**: Streamlit

- **Backend**: Python 3.10+- AI-powered extraction using OpenAI's `o1-pro` model with high reasoning effort

- **Data Processing**: Pandas, Pydantic

- **File Handling**: PyPDF2, pdfplumber, python-docx- Structured CSV output including timestamps, source file metadata, and extracted fields

- **Configuration**: python-dotenv

- **Logging**: Loguru- Streamlit UI with real-time progress updates and download support



## Project Structure- Modular services for file handling, processing, and prompt management### Key Features## Overview



```

HireMind/

├── app.py                          # CLI entrypoint that launches Streamlit## Technology Stack

├── requirements.txt                # Python dependencies

├── README.md

├── LICENSE

├── config/- **AI Engine**: OpenAI Agent SDK (`agents` package)- **Batch CV Processing**: Process multiple CVs from a folder with a single clickHireMind is an intelligent CV processing system that leverages OpenAI's Agent SDK to extract structured information from candidate resumes. The application processes CVs in batch mode, extracting comprehensive candidate data and generating organized CSV reports.

│   ├── .env                        # Environment variables (API keys, paths)

│   └── agent_config.py             # Agent configuration model- **Frontend**: Streamlit

├── prompts/

│   └── cv_extractor.md             # Prompt template consumed by the agent- **Backend**: Python 3.10+- **Multi-Format Support**: Handles PDF, DOCX, and TXT file formats

├── app_agents/

│   ├── __init__.py- **Data Handling**: Pandas, Pydantic

│   └── cv_extractor_agent.py       # Wrapper around the OpenAI Agent workflow

├── services/- **File Processing**: PyPDF2, pdfplumber, python-docx- **AI-Powered Extraction**: Uses OpenAI's o1-pro model with high reasoning effort...

│   ├── __init__.py

│   ├── file_handler.py             # Text extraction utilities- **Configuration**: python-dotenv

│   └── cv_processor.py             # Batch workflow + CSV writer

├── ui/- **Logging**: Loguru- **Structured Output**: Generates CSV files with timestamp and file location tracking

│   ├── __init__.py

│   └── streamlit_app.py            # Streamlit experience

├── models/                         # Reserved for local models or schemas

├── data/## Project Structure- **Comprehensive Data Extraction**: Covers experience, stability, socioeconomic indicators, and more### Key Features

│   └── cvs/                        # Default CV folder (create locally)

├── output/

│   └── cv_extractions.csv          # Default CSV output path

└── logs/                           # Rotating log files```- **User-Friendly Interface**: Streamlit-based web UI for easy interaction

```

HireMind/

## Setup

├── app.py                          # Launches the Streamlit UI- **Append Mode**: Option to append new results to existing CSV filesKey features:

1. **Clone & enter the repo**

   ```bash├── requirements.txt                # Python dependencies

   git clone https://github.com/alkashef/HireMind.git

   cd HireMind├── README.md                       # This guide

   ```

2. **Create a Conda environment**├── LICENSE

   ```bash

   conda create --name hiremind python=3.10├── config/## Technology Stack- **Batch CV Processing**: Process multiple CVs from a folder with a single click

   conda activate hiremind

   ```│   ├── .env                        # Environment variables (API keys, paths)

3. **Install dependencies**

   ```bash│   └── agent_config.py             # Agent configuration dataclass

   pip install -r requirements.txt

   ```├── prompts/

4. **Configure environment variables** in `config/.env`

   ```env│   └── cv_extractor.md             # Prompt template for the CV agent- **AI Engine**: OpenAI Agent SDK (o1-pro model)- **Multi-Format Support**: Handles PDF, DOCX, and TXT file formats-

   OPENAI_API_KEY=sk-your-actual-api-key-here

   AGENT_MODEL=o1-pro├── app_agents/

   AGENT_REASONING_EFFORT=high

   WORKFLOW_ID=wf_68e60e3448f88190876d9d86fda0b37b0897b64fb74e981c│   ├── __init__.py- **Frontend**: Streamlit

   DEBUG_MODE=false

   LOG_LEVEL=INFO│   └── cv_extractor_agent.py       # Wrapper around the OpenAI Agent SDK workflow

   OUTPUT_CSV_PATH=output/cv_extractions.csv

   CV_FOLDER_PATH=data/cvs├── services/- **Backend**: Python 3.x with async support- **AI-Powered Extraction**: Uses OpenAI's o1-pro model with high reasoning effort-

   MAX_CONCURRENT_PROCESSING=3

   ```│   ├── __init__.py

5. **Create helper folders**

   ```bash│   ├── file_handler.py             # File discovery and text extraction helpers- **File Processing**: PyPDF2, pdfplumber, python-docx

   mkdir data\cvs output logs

   ```│   └── cv_processor.py             # Batch processing and CSV persistence



## Running the App├── ui/- **Data Handling**: Pandas, Pydantic- **Structured Output**: Generates CSV files with timestamp and file location tracking-



- **Recommended**│   ├── __init__.py

  ```bash

  python app.py│   └── streamlit_app.py            # Streamlit interface implementation- **Configuration**: python-dotenv

  ```

  Launches Streamlit in headless mode and prints the local URL.├── models/                         # Placeholder for future local models



- **Direct Streamlit**├── data/- **Logging**: Loguru- **Comprehensive Data Extraction**:-

  ```bash

  streamlit run ui/streamlit_app.py│   └── cvs/                        # Default CV folder (create manually)

  ```

├── output/

Browse to `http://localhost:8501` (or the network URL shown in the terminal).

│   └── cv_extractions.csv          # Default CSV output path

## Using the UI

└── logs/                           # Rolling application logs## Project Structure  - Personal Information (Full Name)

1. Enter the CV folder path (defaults to `config/.env` value).

2. Provide or accept the CSV output location.```

3. Decide whether to append to the existing CSV.

4. Click **“Start Processing”** and watch progress updates.

5. Download the resulting CSV once processing finishes.

## Setup

## CSV Output Schema

```  - Professionalism Metrics (spelling, visual cleanliness, formatting)## Technology Stack

Each processed CV appends a row containing:

1. **Clone & enter the repo**

- `timestamp`

- `filename`   ```bashHireMind/

- `file_location`

- `status`   git clone https://github.com/alkashef/HireMind.git

- `error_message`

- `raw_output` (full markdown returned by the agent)   cd HireMind├── app.py                          # Main entry point (launches Streamlit UI)  - Experience Analysis (years since graduation, total experience)

- Extracted features (always present as columns):

  - `personal_information_full_name`   ```

  - `personal_information_first_name`

  - `personal_information_last_name`2. **Create a Conda environment**├── requirements.txt                # Project dependencies

  - `personal_information_email`

  - `personal_information_phone`   ```bash

  - `professionalism_misspelling_count`

  - `professionalism_misspelled_words`   conda create --name hiremind python=3.10├── README.md                       # Documentation  - Stability Indicators (employers, tenure)- **Frontend**: 

  - `professionalism_visual_cleanliness`

  - `professionalism_professional_look`   conda activate hiremind

  - `professionalism_formatting`

  - `experience_years_since_graduation`   ```├── LICENSE                         # License file

  - `experience_total_years`

  - `stability_number_of_employers`3. **Install dependencies**

  - `stability_employer_names`

  - `stability_average_years_per_employer`   ```bash├── config/  - Socioeconomic Standard (address, alma mater)- **Backend**: 

  - `stability_years_at_current_employer`

  - `socioeconomic_standard_address`   pip install -r requirements.txt

  - `socioeconomic_standard_alma_mater`

  - `flags_stem`   ```│   ├── .env                        # Environment variables (API keys, paths)

  - `flags_military_service`

  - `flags_worked_financial_institution`4. **Configure environment variables**

  - `flags_worked_egyptian_government`

   Edit `config/.env` with your own values:│   └── agent_config.py             # Agent configuration settings  - Important Flags (STEM degree, military service, industry experience)- **AI Model**: 

Columns are pre-created for every row, so downstream tooling can rely on a consistent schema even when the agent omits certain values.

   ```env

## Troubleshooting

   OPENAI_API_KEY=sk-your-actual-api-key-here├── prompts/                        # Prompt templates for agents

- **ImportError for `agents`**: ensure only the OpenAI SDK supplies the `agents` package. Local wrappers live in `app_agents/`.

- **Missing API key**: confirm `OPENAI_API_KEY` is populated and has access to the Agent SDK and `o1-pro`.   AGENT_MODEL=o1-pro

- **No CVs detected**: verify the folder path and that files have supported extensions (PDF, DOCX, TXT).

- **Unparsed or partial fields**: see `prompts/cv_extractor.md` for formatting guidance; adjust if your agent output changes structure.   AGENT_REASONING_EFFORT=high│   └── cv_extractor.md             # CV extraction prompt- **User-Friendly Interface**: Streamlit-based web UI for easy interaction- **Database**: 



## Contributing   WORKFLOW_ID=wf_68e60e3448f88190876d9d86fda0b37b0897b64fb74e981c



Pull requests are welcome. Please include tests or sample data where practical and keep prompts in `prompts/` for easy reuse.   DEBUG_MODE=false├── agents/



## License   LOG_LEVEL=INFO



Released under the license terms in `LICENSE`.   OUTPUT_CSV_PATH=output/cv_extractions.csv│   ├── __init__.py- **Append Mode**: Option to append new results to existing CSV files- **Model Optimization**: 



---   CV_FOLDER_PATH=data/cvs



**HireMind** — Intelligent CV Processing for Modern Hiring   MAX_CONCURRENT_PROCESSING=3│   └── cv_extractor_agent.py       # OpenAI Agent wrapper for CV extraction


   ```

5. **Create helper directories**├── services/- **Testing**:

   ```bash

   mkdir data\cvs output logs│   ├── __init__.py

   ```

│   ├── file_handler.py             # File reading and text extraction## Technology Stack- **Configuration**: 

## Running the App

│   └── cv_processor.py             # Batch processing and CSV generation

### Option A — via `app.py`

```bash├── ui/

python app.py

```│   ├── __init__.py

This starts Streamlit in headless mode and opens the HireMind UI.

│   └── streamlit_app.py            # Streamlit web interface- **AI Engine**: OpenAI Agent SDK (o1-pro model)## Important Files:

### Option B — direct Streamlit

```bash├── models/                         # Folder for local models (future use)

streamlit run ui/streamlit_app.py

```├── data/- **Frontend**: Streamlit



Access the UI at `http://localhost:8501` (network URL will also appear in the console).│   └── cvs/                        # Default folder for CV files



## Using the UI├── output/- **Backend**: Python 3.x with async support- Core Application: `app.py` - Main entry point with Streamlit interface



1. Enter the folder path containing CV files (or use the default from `.env`).│   └── cv_extractions.csv          # Default output CSV file

2. Provide the desired CSV output path (default `output/cv_extractions.csv`).

3. Choose whether to append results to the existing CSV.└── logs/                           # Application logs- **File Processing**: PyPDF2, pdfplumber, python-docx- Model Template: `prompt.txt` - Prompt engineering template for the LLM

4. Click **“Start Processing”**. Progress updates and per-file statuses appear live.

5. After completion, download the CSV directly from the interface.```



## CSV Output- **Data Handling**: Pandas, Pydantic



Each processed CV appends a row containing:## Setup for Development



- `timestamp`- **Configuration**: python-dotenv

- `filename`

- `file_location`### Prerequisites

- `status`

- `error_message`- **Logging**: Loguru## Setup for Development

- `raw_output` (full markdown generated by the agent)

- Parsed fields extracted from the markdown (e.g., `personal_information_full_name`)- Python 3.9 or higher



## Troubleshooting- OpenAI API Key with access to Agent SDK



- **Import errors for `RunContextWrapper`**: ensure the `agents` SDK package is installed (provided in `requirements.txt`) and that the local project folder is named `app_agents`, not `agents`.- Git (for cloning the repository)

- **API key issues**: confirm `OPENAI_API_KEY` is set and has access to the Agent SDK + `o1-pro`.

- **No CVs detected**: verify the folder path and supported extensions (.pdf, .docx, .txt).## Project Structure#### Conda Environment

- **Extraction failures**: scanned PDFs may require OCR conversion to text.

### Installation Steps

## Development Notes



- Code follows PEP 8 with type annotations and docstrings.

- Logging uses Loguru with daily rotation stored in `logs/`.1. Clone the repository:

- Future enhancements can include automated tests and additional agent prompts.

   ```bash```1. Create a new Conda environment:

## License

   git clone https://github.com/alkashef/HireMind.git

Distributed under the terms described in `LICENSE`.

   cd HireMindHireMind/

---

   ```

**HireMind** — Intelligent CV Processing for Modern Hiring

2. Create and activate a Conda environment:├── app.py                          # Main entry point (launches Streamlit UI)    ```bash

   ```bash

   conda create --name hiremind python=3.10├── requirements.txt                # Project dependencies	conda create --name select-ai 

   conda activate hiremind

   ```├── README.md                       # Documentation    ```

3. Install project dependencies:

   ```bash├── LICENSE                         # License file

   pip install -r requirements.txt

   ```├── config/2. Install pip:

4. Configure environment variables in `config/.env`:

   ```env│   ├── .env                        # Environment variables (API keys, paths)

   OPENAI_API_KEY=sk-your-actual-api-key-here

   AGENT_MODEL=o1-pro│   └── agent_config.py             # Agent configuration settings    ```bash

   AGENT_REASONING_EFFORT=high

   WORKFLOW_ID=wf_68e60e3448f88190876d9d86fda0b37b0897b64fb74e981c├── agents/	conda install pip

   DEBUG_MODE=false

   LOG_LEVEL=INFO│   ├── __init__.py    ```

   OUTPUT_CSV_PATH=output/cv_extractions.csv

   CV_FOLDER_PATH=data/cvs│   └── cv_extractor_agent.py       # OpenAI Agent wrapper for CV extraction

   MAX_CONCURRENT_PROCESSING=3

   ```├── services/3. Install project dependencies:

5. Create required directories:

   ```bash│   ├── __init__.py

   mkdir data\cvs output logs

   ```│   ├── file_handler.py             # File reading and text extraction    ```bash



## How to Run│   └── cv_processor.py             # Batch processing and CSV generation	pip install -r requirements.txt



### Method 1: Using Main Entry Point (Recommended)├── ui/    ```

```bash

python app.py│   ├── __init__.py

```

This launches the Streamlit web server and opens the HireMind CV Processing interface.│   └── streamlit_app.py            # Streamlit web interface



### Method 2: Direct Streamlit Launch├── models/                         # Folder for local models (future use)## How to Test

```bash

streamlit run ui/streamlit_app.py├── data/

```

│   └── cvs/                        # Default folder for CV filesRun tests to verify the application components are working correctly:

### Access the Application

- Local URL: `http://localhost:8501`├── output/

- Network URL: displayed in the terminal

│   └── cv_extractions.csv          # Default output CSV file

## Usage Workflow

└── logs/                           # Application logs

1. Place CV files (PDF, DOCX, TXT) in the target folder

2. Enter the CV folder path and output CSV path in the UI```

3. Choose whether to append to existing CSV or overwrite

4. Click "▶️ Start Processing" to begin batch processing## How to Run

5. Download the generated CSV containing extracted candidate information

## Setup for Development

## CSV Output Fields

The application can be run in two modes:

- `timestamp`: ISO 8601 timestamp of processing

- `filename`: Original CV filename### Prerequisites

- `file_location`: Full path to the source CV

- `status`: Success or error state of processing#### Web UI Mode (Default)

- `error_message`: Details if processing failed

- `raw_output`: Full markdown output generated by the agent- Python 3.9 or higher

- Other columns: Parsed fields extracted from the CV (e.g., personal_information_full_name)

- OpenAI API Key with access to Agent SDK```bash

## Troubleshooting

- Git (for cloning the repository)python app.py

- **Missing API Key**: Ensure `OPENAI_API_KEY` is set in `config/.env`

- **No CVs Found**: Verify folder path and supported extensions (.pdf, .docx, .txt)```

- **Extraction Errors**: Some PDFs may require OCR; convert to searchable text before processing

- **Timeouts**: Adjust `timeout_seconds` in `config/agent_config.py` if needed### Installation Steps



## Development NotesThis starts the web server on `http://localhost:5000`, where you can:



- Python code follows PEP 8 standards and uses type annotations#### 1. Clone the Repository1. Connect to the database

- Logging uses Loguru with daily rotation (stored in `logs/`)

- Future enhancements can include automated tests and additional agent prompts2. Load the AI model



## License```bash3. Enter natural language queries



See the [LICENSE](LICENSE) file for licensing details.git clone https://github.com/alkashef/HireMind.git4. Get translated SQL queries



## Contributingcd HireMind5. Execute queries and view results



Contributions are welcome! Please fork the repository, create a feature branch, and submit a pull request.```



## Acknowledgments#### Batch Mode



- OpenAI for the Agent SDK#### 2. Create Conda Environment

- Streamlit for the UI framework

```bash

---

```bashpython app.py --batch

**HireMind** — Intelligent CV Processing for Modern Hiring

conda create --name hiremind python=3.10```

conda activate hiremind

```This processes a batch of questions from the file specified in `QUESTIONS_PATH` in the `.env` file and outputs results to an Excel file.


#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Configure Environment Variables

Edit `config/.env` and add your OpenAI API key:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-your-actual-api-key-here

# Agent Configuration
AGENT_MODEL=o1-pro
AGENT_REASONING_EFFORT=high
WORKFLOW_ID=wf_68e60e3448f88190876d9d86fda0b37b0897b64fb74e981c

# Application Settings
DEBUG_MODE=false
LOG_LEVEL=INFO

# Output Configuration
OUTPUT_CSV_PATH=output/cv_extractions.csv
CV_FOLDER_PATH=data/cvs

# Processing Settings
MAX_CONCURRENT_PROCESSING=3
```

#### 5. Create Required Directories

```bash
mkdir data\cvs output logs
```

## How to Run

### Method 1: Using Main Entry Point (Recommended)

```bash
python app.py
```

This will:
1. Launch the Streamlit web server
2. Open the application in your default browser
3. Display the HireMind CV Processing interface

### Method 2: Direct Streamlit Launch

```bash
streamlit run ui/streamlit_app.py
```

### Access the Application

Once running, the application will be available at:
- **Local URL**: `http://localhost:8501`
- **Network URL**: (displayed in terminal)

## How to Use

### Step 1: Prepare Your CVs

1. Place all CV files (PDF, DOCX, or TXT) in a folder
2. Supported formats:
   - `.pdf` - Adobe PDF documents
   - `.docx` - Microsoft Word documents
   - `.txt` - Plain text files

### Step 2: Configure Processing

1. **Select CV Folder**: Enter or browse to the folder containing your CVs
2. **Set Output Path**: Specify where the CSV file should be saved
3. **Choose Append Mode**: 
   - ✅ Checked: Add new results to existing CSV
   - ❌ Unchecked: Create new CSV file (overwrites existing)

### Step 3: Process CVs

1. Click the **"▶️ Start Processing"** button
2. Monitor progress in real-time
3. View processing statistics as files are processed

### Step 4: Review Results

1. Check processing summary (total, successful, failed)
2. Download the CSV file using the **"📥 Download CSV"** button
3. Open the CSV in Excel or any spreadsheet application

## CSV Output Format

The generated CSV includes the following columns:

| Column | Description |
|--------|-------------|
| `timestamp` | ISO format timestamp of processing |
| `filename` | Name of the CV file |
| `file_location` | Full path to the CV file |
| `status` | Processing status (success/error) |
| `error_message` | Error details (if failed) |
| `raw_output` | Complete markdown output from agent |
| `personal_information_*` | Extracted personal data fields |
| `professionalism_*` | Professionalism metrics |
| `experience_*` | Experience-related fields |
| `stability_*` | Job stability indicators |
| `socioeconomic_standard_*` | Background information |
| `flags_*` | Boolean/categorical flags |

## Configuration

### Agent Configuration (`config/agent_config.py`)

```python
class AgentConfig(BaseModel):
    model: str = "o1-pro"
    reasoning_effort: Literal["low", "medium", "high"] = "high"
    workflow_id: str = "wf_68e60e3448f88190876d9d86fda0b37b0897b64fb74e981c"
    store_conversations: bool = True
    max_retries: int = 3
    timeout_seconds: int = 300
```

### Environment Variables (`config/.env`)

All configuration can be customized through environment variables. See the `.env` file for available options.

## Troubleshooting

### Common Issues

**Issue: API Key Error**
- **Solution**: Ensure your OpenAI API key is correctly set in `config/.env`
- Verify the key has access to the Agent SDK and o1-pro model

**Issue: No CVs Found**
- **Solution**: Check the folder path is correct
- Verify files have supported extensions (.pdf, .docx, .txt)
- Ensure files are not corrupted

**Issue: Text Extraction Fails**
- **Solution**: Some PDF files may be scanned images
- Try converting to searchable PDF or DOCX format
- Check file permissions

**Issue: Processing Hangs**
- **Solution**: Check your internet connection
- Verify OpenAI API status
- Increase timeout in `agent_config.py`

## Development

### Running Tests

```bash
# Tests will be added in future versions
pytest tests/
```

### Code Style

The project follows PEP 8 standards. Key conventions:
- Use f-strings for string formatting
- Employ context managers for file operations
- Use list comprehensions where appropriate
- Add type annotations to all functions
- Include docstrings for all classes and methods

### Logging

Logs are automatically saved to the `logs/` directory with daily rotation:
- Format: `hiremind_YYYY-MM-DD_HH-MM-SS.log`
- Retention: 7 days
- Levels: DEBUG, INFO, WARNING, ERROR

## License

See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Follow the coding standards
4. Add tests for new features
5. Submit a pull request

## Acknowledgments

- OpenAI for the Agent SDK and o1-pro model
- Streamlit for the excellent UI framework

## Contact

For questions or support, please open an issue on GitHub.

---

**HireMind** - Intelligent CV Processing for Modern Hiring
