"""File handler service for processing CV files."""

import os
from pathlib import Path
from typing import Optional, List
import PyPDF2
import pdfplumber
from docx import Document
from loguru import logger


class FileHandler:
    """Handle file operations for CV processing."""
    
    SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.txt']
    
    @staticmethod
    def get_cv_files(folder_path: str) -> List[Path]:
        """
        Get all supported CV files from a folder.
        
        Args:
            folder_path: Path to the folder containing CV files
            
        Returns:
            List of Path objects for supported CV files
        """
        try:
            folder = Path(folder_path)
            if not folder.exists():
                logger.error(f"Folder does not exist: {folder_path}")
                return []
            
            cv_files = []
            for file_path in folder.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in FileHandler.SUPPORTED_EXTENSIONS:
                    cv_files.append(file_path)
            
            logger.info(f"Found {len(cv_files)} CV files in {folder_path}")
            return sorted(cv_files)
            
        except Exception as e:
            logger.error(f"Error reading folder {folder_path}: {str(e)}")
            return []
    
    @staticmethod
    def extract_text_from_pdf(file_path: Path) -> Optional[str]:
        """
        Extract text from a PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text or None if extraction fails
        """
        try:
            # Try pdfplumber first (better text extraction)
            with pdfplumber.open(file_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                
                if text.strip():
                    logger.info(f"Successfully extracted text from {file_path.name} using pdfplumber")
                    return text.strip()
            
            # Fallback to PyPDF2
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                
                if text.strip():
                    logger.info(f"Successfully extracted text from {file_path.name} using PyPDF2")
                    return text.strip()
            
            logger.warning(f"No text extracted from {file_path.name}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path.name}: {str(e)}")
            return None
    
    @staticmethod
    def extract_text_from_docx(file_path: Path) -> Optional[str]:
        """
        Extract text from a DOCX file.
        
        Args:
            file_path: Path to the DOCX file
            
        Returns:
            Extracted text or None if extraction fails
        """
        try:
            doc = Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            
            if text.strip():
                logger.info(f"Successfully extracted text from {file_path.name}")
                return text.strip()
            
            logger.warning(f"No text extracted from {file_path.name}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path.name}: {str(e)}")
            return None
    
    @staticmethod
    def extract_text_from_txt(file_path: Path) -> Optional[str]:
        """
        Extract text from a TXT file.
        
        Args:
            file_path: Path to the TXT file
            
        Returns:
            Extracted text or None if extraction fails
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
            
            if text.strip():
                logger.info(f"Successfully extracted text from {file_path.name}")
                return text.strip()
            
            logger.warning(f"No text extracted from {file_path.name}")
            return None
            
        except UnicodeDecodeError:
            # Try different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    text = file.read()
                if text.strip():
                    logger.info(f"Successfully extracted text from {file_path.name} using latin-1 encoding")
                    return text.strip()
            except Exception as e:
                logger.error(f"Error extracting text from TXT {file_path.name}: {str(e)}")
                return None
        except Exception as e:
            logger.error(f"Error extracting text from TXT {file_path.name}: {str(e)}")
            return None
    
    @staticmethod
    def extract_text(file_path: Path) -> Optional[str]:
        """
        Extract text from a file based on its extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Extracted text or None if extraction fails
        """
        extension = file_path.suffix.lower()
        
        if extension == '.pdf':
            return FileHandler.extract_text_from_pdf(file_path)
        elif extension == '.docx':
            return FileHandler.extract_text_from_docx(file_path)
        elif extension == '.txt':
            return FileHandler.extract_text_from_txt(file_path)
        else:
            logger.error(f"Unsupported file format: {extension}")
            return None
