"""Path configuration utilities for Garmin Performance Analysis.

This module provides centralized path configuration that can be
customized via environment variables for privacy and data separation.
"""

import os
from pathlib import Path


def get_data_base_dir() -> Path:
    """Get the base data directory from environment or default.

    Returns:
        Path: Base data directory (default: project_root/data)

    Environment:
        GARMIN_DATA_DIR: Override default data directory path
    """
    env_path = os.getenv("GARMIN_DATA_DIR")
    if env_path:
        return Path(env_path).resolve()
    # Default: project_root/data
    project_root = Path(__file__).parent.parent.parent
    return project_root / "data"


def get_result_dir() -> Path:
    """Get the result directory from environment or default.

    Returns:
        Path: Result directory (default: project_root/result)

    Environment:
        GARMIN_RESULT_DIR: Override default result directory path
    """
    env_path = os.getenv("GARMIN_RESULT_DIR")
    if env_path:
        return Path(env_path).resolve()
    # Default: project_root/result
    project_root = Path(__file__).parent.parent.parent
    return project_root / "result"


def get_raw_dir() -> Path:
    """Get the raw data directory."""
    return get_data_base_dir() / "raw"


def get_performance_dir() -> Path:
    """Get the performance data directory."""
    return get_data_base_dir() / "performance"


def get_precheck_dir() -> Path:
    """Get the precheck data directory."""
    return get_data_base_dir() / "precheck"


def get_database_dir() -> Path:
    """Get the database directory."""
    return get_data_base_dir() / "database"


def get_default_db_path() -> str:
    """Get the default DuckDB database file path.

    Returns:
        str: Default database path (database_dir/garmin_performance.duckdb)

    This function centralizes the default database path logic,
    used by GarminIngestWorker, inserters, and other components.
    """
    return str(get_database_dir() / "garmin_performance.duckdb")


def get_weight_raw_dir() -> Path:
    """Get the weight raw data directory."""
    return get_data_base_dir() / "raw" / "weight"
