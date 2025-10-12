"""Garmin Performance Analysis Tools Package.

This package automatically loads environment variables from .env file
at the project root when any module from this package is imported.
"""

from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent.parent
dotenv_path = project_root / ".env"

if dotenv_path.exists():
    load_dotenv(dotenv_path)
else:
    # Fallback: search for .env in current directory
    load_dotenv()
