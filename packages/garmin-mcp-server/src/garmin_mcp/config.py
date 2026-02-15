"""Centralized configuration for Garmin Performance Analysis.

Consolidates environment variables, magic numbers, and default values
that were previously scattered across 10+ files.

Usage:
    from garmin_mcp.config import get_config

    config = get_config()
    db_path = config.db_path
    max_size = config.max_output_size
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Default values (previously magic numbers scattered across the codebase)
DEFAULT_MAX_OUTPUT_SIZE = 10240
DEFAULT_DB_NAME = "garmin_performance.duckdb"
DEFAULT_DATA_DIR_FALLBACK = "data"
DEFAULT_HOME_DATA_DIR = "~/garmin_data"


@dataclass(frozen=True)
class GarminConfig:
    """Immutable configuration for the Garmin analysis system.

    All settings are resolved at creation time. Use `from_env()` to
    create from environment variables, or construct directly for testing.
    """

    data_dir: Path
    result_dir: Path
    db_path: Path
    max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE
    garmin_email: str | None = None
    garmin_password: str | None = None

    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings.

        Returns:
            List of warning messages (empty if all OK).
        """
        warnings: list[str] = []
        if not self.data_dir.exists():
            warnings.append(f"Data directory does not exist: {self.data_dir}")
        if not self.db_path.parent.exists():
            warnings.append(f"Database directory does not exist: {self.db_path.parent}")
        if self.max_output_size <= 0:
            warnings.append(f"Invalid max_output_size: {self.max_output_size}")
        return warnings

    @staticmethod
    def from_env() -> GarminConfig:
        """Create config from environment variables.

        Environment variables:
            GARMIN_DATA_DIR: Override default data directory
            GARMIN_RESULT_DIR: Override default result directory
            GARMIN_EMAIL: Garmin Connect email
            GARMIN_PASSWORD: Garmin Connect password
        """
        # Use paths.py logic for project root detection
        from garmin_mcp.utils.paths import get_data_base_dir, get_result_dir

        data_dir = get_data_base_dir()
        result_dir = get_result_dir()
        db_path = data_dir / "database" / DEFAULT_DB_NAME

        return GarminConfig(
            data_dir=data_dir,
            result_dir=result_dir,
            db_path=db_path,
            max_output_size=DEFAULT_MAX_OUTPUT_SIZE,
            garmin_email=os.getenv("GARMIN_EMAIL"),
            garmin_password=os.getenv("GARMIN_PASSWORD"),
        )


@lru_cache(maxsize=1)
def get_config() -> GarminConfig:
    """Get the singleton config instance.

    Returns:
        GarminConfig instance created from environment variables.
    """
    return GarminConfig.from_env()
