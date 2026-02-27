"""Validation logic for DuckDB regeneration.

Validates table names, dependencies, and argument combinations.
"""

import logging
from pathlib import Path

import duckdb

from garmin_mcp.database.connection import get_connection

logger = logging.getLogger(__name__)

# All available DuckDB tables
AVAILABLE_TABLES: list[str] = [
    "activities",
    "splits",
    "form_efficiency",
    "hr_efficiency",
    "heart_rate_zones",
    "performance_trends",
    "vo2_max",
    "lactate_threshold",
    "time_series_metrics",
    "section_analyses",
    "body_composition",
]


def filter_tables(tables: list[str] | None) -> list[str]:
    """
    Filter and validate table list.

    Args:
        tables: List of table names (None = all tables)

    Returns:
        Validated list of table names

    Raises:
        ValueError: If invalid table names are provided
    """
    if tables is None:
        return list(AVAILABLE_TABLES)

    invalid_tables = set(tables) - set(AVAILABLE_TABLES)
    if invalid_tables:
        raise ValueError(f"Invalid table names: {invalid_tables}")

    return tables


def validate_table_dependencies(
    tables: list[str] | None,
    activity_ids: list[int],
    db_path: Path,
) -> None:
    """
    Validate that parent activities exist before regenerating child tables.

    Prevents orphaned records in child tables when FK constraints are removed.

    Args:
        tables: List of table names (None = all tables, validation skipped)
        activity_ids: List of activity IDs to regenerate
        db_path: Path to DuckDB database

    Raises:
        ValueError: If child tables specified without parent activities existing
    """
    # Skip validation if regenerating all tables
    if tables is None:
        logger.debug(
            "Validation skipped: Full regeneration (all tables, activities will be created)"
        )
        return

    # Skip validation if activities table is being regenerated
    if "activities" in tables:
        logger.debug(
            "Validation skipped: activities table included (parent will be created)"
        )
        return

    # Child-only regeneration: validate parent activities exist
    logger.debug(f"Validating {len(activity_ids)} parent activities exist...")

    missing_ids = _find_missing_activity_ids(activity_ids, db_path)

    if missing_ids:
        shown_ids = missing_ids[:5]
        shown_str = ", ".join(map(str, shown_ids))
        more_str = f" (and {len(missing_ids) - 5} more)" if len(missing_ids) > 5 else ""

        raise ValueError(
            f"Cannot regenerate child tables without parent activities. "
            f"Missing activity IDs: [{shown_str}]{more_str}. "
            f"Solution: Either (1) include 'activities' in --tables, "
            f"or (2) regenerate these activities first without --tables filter."
        )

    logger.info(
        f"✅ Validation passed: All {len(activity_ids)} parent activities exist"
    )


def _find_missing_activity_ids(activity_ids: list[int], db_path: Path) -> list[int]:
    """Find activity IDs that don't exist in DuckDB."""
    if not db_path.exists():
        return list(activity_ids)

    try:
        with get_connection(db_path) as conn:
            try:
                missing = []
                for activity_id in activity_ids:
                    query = "SELECT COUNT(*) FROM activities WHERE activity_id = ?"
                    result = conn.execute(query, (activity_id,)).fetchone()
                    if not result or result[0] == 0:
                        missing.append(activity_id)
                return missing
            except duckdb.CatalogException:
                return list(activity_ids)
    except Exception:
        return list(activity_ids)
