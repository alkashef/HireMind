"""
HireMind - CV Processing Application

This is the main entry point for the HireMind application.
It launches the Streamlit UI for batch processing CVs using OpenAI's Agent SDK.

Original Agent SDK code moved to: agents/cv_extractor_agent.py

Usage:
    python app.py
    
Or with Streamlit directly:
    streamlit run ui/streamlit_app.py
"""

import sys
import subprocess
from pathlib import Path


def main():
    """Launch the Streamlit application."""
    
    # Path to the Streamlit UI
    ui_path = Path(__file__).parent / "ui" / "streamlit_app.py"
    
    print("🧠 Starting HireMind CV Processing System...")
    print(f"📂 UI Location: {ui_path}")
    print("-" * 50)
    
    # Launch Streamlit
    try:
        subprocess.run([
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ui_path),
            "--server.headless=true"
        ])
    except KeyboardInterrupt:
        print("\n\n👋 HireMind application stopped.")
    except Exception as e:
        print(f"\n❌ Error launching application: {str(e)}")
        print("\nTry running directly with:")
        print(f"  streamlit run {ui_path}")


if __name__ == "__main__":
    main()
