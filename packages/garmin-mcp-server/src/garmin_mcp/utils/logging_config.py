"""Logging configuration for Garmin MCP Server.

Configures stderr and optional file logging. MCP uses stdout for JSON-RPC,
so all log output goes to stderr or rotating log files.
"""

import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from garmin_mcp.utils.paths import get_data_base_dir

# 10 MB per file, keep 5 backups
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


def setup_mcp_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
) -> None:
    """Configure logging for the MCP server.

    Always adds a stderr handler. Optionally adds a rotating file handler.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Directory for log files. Defaults to $GARMIN_DATA_DIR/logs/.
            Pass a Path to enable file logging; the directory is created if needed.
    """
    root_logger = logging.getLogger("garmin_mcp")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on repeated calls
    root_logger.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT)

    # stderr handler (always)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root_logger.addHandler(stderr_handler)

    # File handler (rotating)
    if log_dir is None:
        log_dir = get_data_base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "mcp_server.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    session_id = uuid.uuid4().hex[:8]
    root_logger.info("session_start session_id=%s", session_id)
