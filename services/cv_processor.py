"""CV Processor service for batch processing CVs."""

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
from loguru import logger

from app_agents.cv_extractor_agent import CVExtractorAgent, WorkflowInput
from services.file_handler import FileHandler


def _normalize_text(value: str) -> str:
    """Lowercase and strip a string to an alphanumeric slug for matching."""
    if value is None:
        return ""
    cleaned = "".join(char if char.isalnum() or char.isspace() else " " for char in value.lower())
    return " ".join(cleaned.split())


SECTION_ALIASES = {
    "personal information": "personal information",
    "professionalism": "professionalism",
    "professionalism assessment": "professionalism",
    "experience": "experience",
    "work experience": "experience",
    "stability": "stability",
    "employment stability": "stability",
    "socioeconomic standard": "socioeconomic standard",
    "socioeconomic": "socioeconomic standard",
    "flags": "flags",
    "flag summary": "flags",
}


FIELD_MAPPING_DEFINITIONS = [
    ("personal information", ["full name"], "personal_information_full_name"),
    ("personal information", ["first name"], "personal_information_first_name"),
    ("personal information", ["last name"], "personal_information_last_name"),
    ("personal information", ["email", "email address"], "personal_information_email"),
    ("personal information", ["phone", "phone number"], "personal_information_phone"),
    (
        "professionalism",
        ["misspelling count"],
        "professionalism_misspelling_count",
    ),
    (
        "professionalism",
        ["list of misspelled words", "misspelled words"],
        "professionalism_misspelled_words",
    ),
    (
        "professionalism",
        ["visual cleanliness"],
        "professionalism_visual_cleanliness",
    ),
    (
        "professionalism",
        ["professional look"],
        "professionalism_professional_look",
    ),
    (
        "professionalism",
        ["formatting", "formatting consistency"],
        "professionalism_formatting",
    ),
    (
        "experience",
        ["years since graduation"],
        "experience_years_since_graduation",
    ),
    (
        "experience",
        ["total years of experience", "years of experience"],
        "experience_total_years",
    ),
    ("stability", ["number of employers"], "stability_number_of_employers"),
    (
        "stability",
        ["list of employer names", "employer names", "employers"],
        "stability_employer_names",
    ),
    (
        "stability",
        ["average number of years per employer", "average tenure per employer"],
        "stability_average_years_per_employer",
    ),
    (
        "stability",
        ["number of years at the current last employer", "years at current employer"],
        "stability_years_at_current_employer",
    ),
    (
        "socioeconomic standard",
        ["address"],
        "socioeconomic_standard_address",
    ),
    (
        "socioeconomic standard",
        ["alma mater"],
        "socioeconomic_standard_alma_mater",
    ),
    ("flags", ["stem", "stem degree"], "flags_stem"),
    ("flags", ["military service", "military service status"], "flags_military_service"),
    (
        "flags",
        [
            "worked for a financial institution previously",
            "financial institution experience",
            "worked at financial institution",
        ],
        "flags_worked_financial_institution",
    ),
    (
        "flags",
        [
            "worked for the egyptian government previously",
            "government experience",
            "worked for egyptian government",
        ],
        "flags_worked_egyptian_government",
    ),
]


FIELD_MAPPING = {}
FIELD_FALLBACK = {}
for section_name, field_aliases, column_name in FIELD_MAPPING_DEFINITIONS:
    normalized_section = SECTION_ALIASES.get(_normalize_text(section_name), _normalize_text(section_name))
    for alias in field_aliases:
        normalized_alias = _normalize_text(alias)
        FIELD_MAPPING[(normalized_section, normalized_alias)] = column_name
        FIELD_FALLBACK.setdefault(normalized_alias, column_name)

EXTRACTED_FIELD_COLUMNS = list(dict.fromkeys(definition[2] for definition in FIELD_MAPPING_DEFINITIONS))


class CVProcessor:
    """Service for processing multiple CVs and generating CSV output."""
    
    def __init__(self, agent: Optional[CVExtractorAgent] = None):
        """
        Initialize the CV Processor.
        
        Args:
            agent: CV Extractor Agent instance (creates new if None)
        """
        self.agent = agent or CVExtractorAgent()
        self.file_handler = FileHandler()
    
    async def process_single_cv(
        self, 
        file_path: Path
    ) -> Dict[str, Any]:
        """
        Process a single CV file.
        
        Args:
            file_path: Path to the CV file
            
        Returns:
            Dictionary containing processed CV data
        """
        try:
            logger.info(f"Processing CV: {file_path.name}")
            
            # Extract text from file
            cv_text = self.file_handler.extract_text(file_path)
            
            if not cv_text:
                response = {
                    'timestamp': datetime.now().isoformat(),
                    'filename': file_path.name,
                    'file_location': str(file_path.absolute()),
                    'status': 'error',
                    'error_message': 'Failed to extract text from file',
                    'raw_output': ''
                }
                response.update(self._empty_extraction_fields())
                return response
            
            # Run agent extraction
            workflow_input = WorkflowInput(input_as_text=cv_text)
            result = await self.agent.run_workflow(workflow_input)
            
            # Prepare result data
            cv_data = {
                'timestamp': datetime.now().isoformat(),
                'filename': file_path.name,
                'file_location': str(file_path.absolute()),
                'status': result.get('status', 'unknown'),
                'error_message': result.get('error_message', ''),
                'raw_output': result.get('output_text') or ''
            }
            cv_data.update(self._empty_extraction_fields())
            
            # Parse the markdown output to extract structured data
            parsed_data = self._parse_markdown_output(result.get('output_text', ''))
            cv_data.update(parsed_data)
            
            logger.info(f"Successfully processed CV: {file_path.name}")
            return cv_data
            
        except Exception as e:
            logger.error(f"Error processing CV {file_path.name}: {str(e)}")
            response = {
                'timestamp': datetime.now().isoformat(),
                'filename': file_path.name,
                'file_location': str(file_path.absolute()),
                'status': 'error',
                'error_message': str(e),
                'raw_output': ''
            }
            response.update(self._empty_extraction_fields())
            return response
    
    def _parse_markdown_output(self, output_text: str) -> Dict[str, Any]:
        """Parse the agent's markdown into a fixed set of CSV columns."""
        parsed = self._empty_extraction_fields()

        if not output_text:
            return parsed

        try:
            lines = output_text.splitlines()
            current_section = ""
            active_column = None

            for raw_line in lines:
                stripped_line = raw_line.strip()

                if not stripped_line:
                    active_column = None
                    continue

                if stripped_line.startswith('#'):
                    heading = stripped_line.lstrip('#').strip()
                    normalized_heading = _normalize_text(heading)
                    current_section = SECTION_ALIASES.get(normalized_heading, normalized_heading)
                    active_column = None
                    continue

                cleaned_line = stripped_line.lstrip('-* ').strip()
                if not cleaned_line:
                    continue

                if ':' in cleaned_line:
                    key_part, value_part = cleaned_line.split(':', 1)
                    normalized_key = _normalize_text(key_part)
                    column_name = self._resolve_column(current_section, normalized_key)
                    if column_name:
                        value = value_part.strip()
                        parsed[column_name] = self._merge_values(parsed[column_name], value)
                        active_column = column_name
                    else:
                        active_column = None
                    continue

                if active_column:
                    continuation_value = cleaned_line
                    parsed[active_column] = self._merge_values(parsed[active_column], continuation_value)

            logger.debug("Extracted {} structured fields", sum(1 for v in parsed.values() if v))

        except Exception as exc:
            logger.warning(f"Error parsing markdown output: {exc}")

        return parsed

    @staticmethod
    def _empty_extraction_fields() -> Dict[str, str]:
        """Return an empty dictionary for all tracked extraction columns."""
        return {column: "" for column in EXTRACTED_FIELD_COLUMNS}

    @staticmethod
    def _merge_values(existing: str, new_value: str) -> str:
        """Combine multiple values for the same column without duplication."""
        new_value = (new_value or "").strip()
        if not new_value:
            return existing

        if not existing:
            return new_value

        existing_parts = [part.strip() for part in existing.split('|') if part.strip()]
        if new_value in existing_parts:
            return existing

        existing_parts.append(new_value)
        return " | ".join(existing_parts)

    @staticmethod
    def _resolve_column(section: str, field_key: str) -> Optional[str]:
        """Map a section/field combination to a canonical CSV column name."""
        normalized_section = SECTION_ALIASES.get(section, section)
        if (normalized_section, field_key) in FIELD_MAPPING:
            return FIELD_MAPPING[(normalized_section, field_key)]
        return FIELD_FALLBACK.get(field_key)
    
    async def process_batch(
        self, 
        folder_path: str,
        output_csv_path: str
    ) -> Dict[str, Any]:
        """
        Process all CVs in a folder and save to CSV.
        
        Args:
            folder_path: Path to folder containing CV files
            output_csv_path: Path to output CSV file
            
        Returns:
            Dictionary with processing statistics
        """
        try:
            logger.info(f"Starting batch processing from folder: {folder_path}")
            
            # Get all CV files
            cv_files = self.file_handler.get_cv_files(folder_path)
            
            if not cv_files:
                logger.warning(f"No CV files found in {folder_path}")
                return {
                    'total_files': 0,
                    'successful': 0,
                    'failed': 0,
                    'output_file': None
                }
            
            # Process all CVs
            results = []
            for cv_file in cv_files:
                result = await self.process_single_cv(cv_file)
                results.append(result)
            
            # Save to CSV
            self._save_to_csv(results, output_csv_path)
            
            # Calculate statistics
            successful = sum(1 for r in results if r.get('status') == 'success')
            failed = len(results) - successful
            
            stats = {
                'total_files': len(results),
                'successful': successful,
                'failed': failed,
                'output_file': output_csv_path
            }
            
            logger.info(f"Batch processing complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}")
            raise
    
    def _save_to_csv(self, results: List[Dict[str, Any]], output_path: str) -> None:
        """
        Save processing results to CSV file.
        
        Args:
            results: List of CV processing results
            output_path: Path to output CSV file
        """
        try:
            # Create output directory if it doesn't exist
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to DataFrame for easier CSV handling
            df = pd.DataFrame(results)
            
            # Reorder columns to have key fields first
            priority_columns = [
                'timestamp', 
                'filename', 
                'file_location', 
                'status', 
                'error_message',
                'raw_output'
            ]

            # Ensure all expected extraction columns are present
            for column in EXTRACTED_FIELD_COLUMNS:
                if column not in df.columns:
                    df[column] = ""
            
            # Get all columns
            all_columns = df.columns.tolist()
            
            # Reorder: priority columns first, then rest
            ordered_columns = [col for col in priority_columns if col in all_columns]
            extraction_columns = [col for col in EXTRACTED_FIELD_COLUMNS if col in all_columns]
            remaining_columns = [
                col for col in all_columns 
                if col not in ordered_columns and col not in extraction_columns
            ]
            final_columns = ordered_columns + extraction_columns + remaining_columns
            
            df = df[final_columns]
            
            # Check if file exists to determine if we append or write
            file_exists = output_file.exists()
            
            if file_exists:
                # Append to existing file
                df.to_csv(output_path, mode='a', header=False, index=False, encoding='utf-8-sig')
                logger.info(f"Appended {len(results)} records to {output_path}")
            else:
                # Create new file
                df.to_csv(output_path, mode='w', header=True, index=False, encoding='utf-8-sig')
                logger.info(f"Created new CSV file with {len(results)} records: {output_path}")
                
        except Exception as e:
            logger.error(f"Error saving to CSV: {str(e)}")
            raise
    
    async def process_and_stream(
        self, 
        folder_path: str,
        output_csv_path: str,
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Process CVs with progress updates.
        
        Args:
            folder_path: Path to folder containing CV files
            output_csv_path: Path to output CSV file
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary with processing statistics
        """
        try:
            logger.info(f"Starting streaming batch processing from folder: {folder_path}")
            
            # Get all CV files
            cv_files = self.file_handler.get_cv_files(folder_path)
            
            if not cv_files:
                logger.warning(f"No CV files found in {folder_path}")
                return {
                    'total_files': 0,
                    'successful': 0,
                    'failed': 0,
                    'output_file': None
                }
            
            total_files = len(cv_files)
            successful = 0
            failed = 0
            
            # Process CVs one by one with progress updates
            for idx, cv_file in enumerate(cv_files, 1):
                result = await self.process_single_cv(cv_file)
                
                # Save individual result to CSV immediately
                self._save_to_csv([result], output_csv_path)
                
                # Update statistics
                if result.get('status') == 'success':
                    successful += 1
                else:
                    failed += 1
                
                # Call progress callback if provided
                if progress_callback:
                    progress_callback(
                        current=idx,
                        total=total_files,
                        filename=cv_file.name,
                        status=result.get('status')
                    )
            
            stats = {
                'total_files': total_files,
                'successful': successful,
                'failed': failed,
                'output_file': output_csv_path
            }
            
            logger.info(f"Streaming batch processing complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error in streaming batch processing: {str(e)}")
            raise
