"""
SectionAnalysisInserter - Insert section analysis data to DuckDB

Inserts section analysis data into section_analyses table.
Supports both file-based and dict-based insertion.
"""

import json
import logging
from pathlib import Path
from typing import Any

from tools.database.db_writer import GarminDBWriter

logger = logging.getLogger(__name__)


def insert_section_analysis(
    activity_id: int,
    activity_date: str,
    section_type: str,
    analysis_file: str | None = None,
    analysis_data: dict[str, Any] | None = None,
    agent_name: str | None = None,
    agent_version: str = "1.0",
    db_path: str | None = None,
) -> bool:
    """
    Insert section analysis data into DuckDB with auto-generated metadata.

    Supports two modes:
    1. File-based: Load from analysis_file JSON
    2. Dict-based: Use analysis_data directly (RECOMMENDED - no file creation)

    Metadata will be auto-generated if not present in the data.

    Args:
        activity_id: Activity ID
        activity_date: Activity date (YYYY-MM-DD)
        section_type: Section type (efficiency/environment/phase/split/summary)
        analysis_file: Optional path to section analysis JSON file
        analysis_data: Optional dict containing analysis data
        agent_name: Optional agent name (defaults to {section_type}-section-analyst)
        agent_version: Agent version (defaults to "1.0")
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate inputs
        if analysis_file is None and analysis_data is None:
            logger.error("Either analysis_file or analysis_data must be provided")
            return False

        if analysis_file is not None and analysis_data is not None:
            logger.error("Cannot provide both analysis_file and analysis_data")
            return False

        # Load analysis data
        if analysis_file is not None:
            # File-based mode
            analysis_path = Path(analysis_file)
            if not analysis_path.exists():
                logger.error(f"Analysis file not found: {analysis_file}")
                return False

            with open(analysis_path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            # Dict-based mode (RECOMMENDED)
            data = analysis_data

        # Initialize DB writer
        writer = GarminDBWriter(db_path=db_path) if db_path else GarminDBWriter()

        # Insert section analysis (metadata will be auto-generated)
        success = writer.insert_section_analysis(
            activity_id=activity_id,
            activity_date=activity_date,
            section_type=section_type,
            analysis_data=data,
            agent_name=agent_name,
            agent_version=agent_version,
        )

        if not success:
            logger.error(
                f"Failed to insert section analysis for {activity_id} ({section_type})"
            )
            return False

        logger.info(
            f"Successfully inserted section analysis for activity {activity_id} ({section_type})"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting section analysis: {e}")
        return False
