"""Streamlit UI for HireMind CV Processing Application."""

import os
import asyncio
from pathlib import Path
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv
from loguru import logger

from app_agents.cv_extractor_agent import CVExtractorAgent
from services.cv_processor import CVProcessor


# Load environment variables
load_dotenv('config/.env')

# Configure logger
logger.add("logs/hiremind_{time}.log", rotation="1 day", retention="7 days")


def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if 'processor' not in st.session_state:
        st.session_state.processor = None
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'results' not in st.session_state:
        st.session_state.results = None


def setup_page():
    """Configure Streamlit page settings."""
    st.set_page_config(
        page_title="HireMind - CV Processor",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🧠 HireMind - CV Processing System")
    st.markdown("""
    This application processes CVs using OpenAI's Agent SDK to extract structured information.
    
    **Features:**
    - Batch process multiple CVs from a folder
    - Extract comprehensive candidate information
    - Export results to CSV with timestamps
    """)


def sidebar_configuration():
    """Render sidebar configuration options."""
    st.sidebar.header("⚙️ Configuration")
    
    # Check for API key
    api_key = os.getenv('OPENAI_API_KEY', '')
    if api_key and api_key != 'your_openai_api_key_here':
        st.sidebar.success("✅ OpenAI API Key configured")
    else:
        st.sidebar.error("❌ OpenAI API Key not configured")
        st.sidebar.info("Please set your OPENAI_API_KEY in config/.env")
    
    st.sidebar.markdown("---")
    
    # Agent settings
    st.sidebar.subheader("Agent Settings")
    model = os.getenv('AGENT_MODEL', 'o1-pro')
    reasoning = os.getenv('AGENT_REASONING_EFFORT', 'high')
    
    st.sidebar.text(f"Model: {model}")
    st.sidebar.text(f"Reasoning: {reasoning}")
    
    st.sidebar.markdown("---")
    
    # System info
    st.sidebar.subheader("System Info")
    st.sidebar.text(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    st.sidebar.text(f"Time: {datetime.now().strftime('%H:%M:%S')}")


def main_interface():
    """Render main application interface."""
    
    # Folder selection
    st.header("📁 Select CV Folder")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        default_folder = os.getenv('CV_FOLDER_PATH', 'data/cvs')
        folder_path = st.text_input(
            "CV Folder Path",
            value=default_folder,
            help="Enter the path to the folder containing CV files (PDF, DOCX, TXT)"
        )
    
    with col2:
        st.write("")
        st.write("")
        if st.button("📂 Browse", use_container_width=True):
            st.info("Use the text input to enter folder path")
    
    # Validate folder
    folder_exists = Path(folder_path).exists() if folder_path else False
    
    if folder_path:
        if folder_exists:
            cv_count = len([f for f in Path(folder_path).iterdir() 
                          if f.is_file() and f.suffix.lower() in ['.pdf', '.docx', '.txt']])
            st.success(f"✅ Folder found: {cv_count} CV file(s) detected")
        else:
            st.warning(f"⚠️ Folder not found: {folder_path}")
    
    st.markdown("---")
    
    # Output configuration
    st.header("💾 Output Configuration")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        default_output = os.getenv('OUTPUT_CSV_PATH', 'output/cv_extractions.csv')
        output_path = st.text_input(
            "Output CSV Path",
            value=default_output,
            help="Path where the CSV file will be saved"
        )
    
    with col2:
        append_mode = st.checkbox("Append to existing", value=True)
    
    st.markdown("---")
    
    # Processing section
    st.header("🚀 Process CVs")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        process_button = st.button(
            "▶️ Start Processing",
            type="primary",
            use_container_width=True,
            disabled=not folder_exists or st.session_state.processing
        )
    
    with col2:
        if st.session_state.results:
            st.download_button(
                label="📥 Download CSV",
                data=open(output_path, 'rb').read() if Path(output_path).exists() else b"",
                file_name=Path(output_path).name,
                mime="text/csv",
                use_container_width=True,
                disabled=not Path(output_path).exists()
            )
    
    with col3:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.results = None
            st.rerun()
    
    # Process CVs
    if process_button:
        process_cvs(folder_path, output_path, append_mode)
    
    # Display results
    if st.session_state.results:
        display_results(st.session_state.results)


def process_cvs(folder_path: str, output_path: str, append_mode: bool):
    """
    Process CVs from the specified folder.
    
    Args:
        folder_path: Path to folder containing CVs
        output_path: Path to output CSV file
        append_mode: Whether to append to existing CSV
    """
    st.session_state.processing = True
    
    try:
        # Create processor
        with st.spinner("Initializing CV Processor..."):
            agent = CVExtractorAgent()
            processor = CVProcessor(agent)
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Get CV files
        cv_files = [f for f in Path(folder_path).iterdir() 
                   if f.is_file() and f.suffix.lower() in ['.pdf', '.docx', '.txt']]
        total_files = len(cv_files)
        
        if total_files == 0:
            st.error("No CV files found in the specified folder.")
            st.session_state.processing = False
            return
        
        # Delete output file if not in append mode
        if not append_mode and Path(output_path).exists():
            Path(output_path).unlink()
            st.info(f"Cleared existing output file: {output_path}")
        
        # Process callback
        def progress_callback(current, total, filename, status):
            progress = current / total
            progress_bar.progress(progress)
            status_emoji = "✅" if status == "success" else "❌"
            status_text.text(f"Processing {current}/{total}: {filename} {status_emoji}")
        
        # Run processing
        status_text.text("Starting batch processing...")
        
        # Run async processing
        results = asyncio.run(
            processor.process_and_stream(
                folder_path=folder_path,
                output_csv_path=output_path,
                progress_callback=progress_callback
            )
        )
        
        # Store results
        st.session_state.results = results
        
        # Complete
        progress_bar.progress(1.0)
        status_text.text("Processing complete!")
        
        # Show success message
        st.success(f"""
        ✅ **Processing Complete!**
        - Total files: {results['total_files']}
        - Successful: {results['successful']}
        - Failed: {results['failed']}
        - Output file: {results['output_file']}
        """)
        
    except Exception as e:
        logger.error(f"Error processing CVs: {str(e)}")
        st.error(f"❌ Error: {str(e)}")
    
    finally:
        st.session_state.processing = False


def display_results(results: dict):
    """
    Display processing results.
    
    Args:
        results: Dictionary containing processing statistics
    """
    st.markdown("---")
    st.header("📊 Processing Results")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Files", results['total_files'])
    
    with col2:
        st.metric("Successful", results['successful'], delta_color="normal")
    
    with col3:
        st.metric("Failed", results['failed'], delta_color="inverse")
    
    with col4:
        success_rate = (results['successful'] / results['total_files'] * 100) if results['total_files'] > 0 else 0
        st.metric("Success Rate", f"{success_rate:.1f}%")
    
    # Display output file info
    if results.get('output_file') and Path(results['output_file']).exists():
        st.info(f"📄 Output saved to: `{results['output_file']}`")
        
        # Show file size
        file_size = Path(results['output_file']).stat().st_size / 1024  # KB
        st.text(f"File size: {file_size:.2f} KB")


def main():
    """Main application entry point."""
    # Initialize
    initialize_session_state()
    setup_page()
    
    # Render UI
    sidebar_configuration()
    main_interface()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: gray;'>
        <p>HireMind CV Processing System | Powered by OpenAI Agent SDK</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
