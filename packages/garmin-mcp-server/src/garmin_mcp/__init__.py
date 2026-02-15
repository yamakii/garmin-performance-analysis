"""Garmin MCP Server - Performance analysis tools via MCP protocol.

This package automatically loads environment variables from .env file
at the project root when any module from this package is imported.
"""

__version__ = "0.1.0"

from pathlib import Path

from dotenv import load_dotenv

# Load .env file - search upward from package location
# Supports both development (monorepo root) and installed modes
_pkg_root = Path(__file__).parent
for _candidate in [
    _pkg_root.parent.parent.parent.parent / ".env",  # monorepo root
    Path.cwd() / ".env",  # current directory
]:
    if _candidate.exists():
        load_dotenv(_candidate)
        break
else:
    load_dotenv()  # fallback: search default locations
