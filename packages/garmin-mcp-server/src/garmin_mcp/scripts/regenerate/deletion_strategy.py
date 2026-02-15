"""Deletion strategies for DuckDB regeneration.

Handles activity-specific and table-wide deletion of records.
"""

import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def delete_activity_records(
    activity_ids: list[int],
    tables: list[str],
    db_path: Path,
) -> None:
    """
    Delete existing records for specified activities from filtered tables.

    Deletion is atomic (uses transaction). body_composition is skipped
    (no activity_id column).

    Args:
        activity_ids: List of activity IDs to delete
        tables: List of table names to delete from
        db_path: Path to DuckDB database
    """
    tables_to_delete = [t for t in tables if t != "body_composition"]

    if not tables_to_delete:
        logger.debug("No tables to delete (body_composition only)")
        return

    logger.info(
        f"🗑️  Deletion strategy: Activity-specific ({len(activity_ids)} activities)"
    )
    logger.info(f"   Tables: {', '.join(tables_to_delete)}")
    logger.info("   Reason: --activity-ids specified with --tables")

    with duckdb.connect(str(db_path)) as conn:
        try:
            conn.execute("BEGIN TRANSACTION")

            for table in tables_to_delete:
                try:
                    placeholders = ",".join("?" * len(activity_ids))
                    sql = f"DELETE FROM {table} WHERE activity_id IN ({placeholders})"
                    logger.debug(f"Deleting {len(activity_ids)} records from {table}")
                    conn.execute(sql, tuple(activity_ids))
                except Exception as table_error:
                    if "does not exist" in str(table_error):
                        logger.debug(
                            f"Table {table} does not exist yet, skipping deletion"
                        )
                    else:
                        raise

            conn.execute("COMMIT")
            logger.info(
                f"Deleted records for {len(activity_ids)} activities "
                f"from {len(tables_to_delete)} tables"
            )

        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"Error deleting records: {e}")
            raise


def delete_table_all_records(
    tables: list[str],
    db_path: Path,
) -> None:
    """
    Delete all records from specified tables (table-wide deletion).

    Used when regenerating entire tables without --activity-ids filter.
    Gracefully handles missing tables.

    Args:
        tables: List of table names to delete all records from
        db_path: Path to DuckDB database
    """
    tables_to_delete = [t for t in tables if t != "body_composition"]

    if not tables_to_delete:
        logger.debug("No tables to delete (body_composition only)")
        return

    logger.warning("⚠️  Deletion strategy: Table-wide (all records)")
    logger.warning(f"   Tables: {', '.join(tables_to_delete)}")
    logger.warning("   Reason: --tables specified without --activity-ids")

    with duckdb.connect(str(db_path)) as conn:
        conn.execute("BEGIN TRANSACTION")
        deleted_tables = []
        try:
            for table in tables_to_delete:
                try:
                    sql = f"DELETE FROM {table}"
                    logger.debug(f"Deleting all records from {table}")
                    conn.execute(sql)
                    deleted_tables.append(table)
                    logger.info(f"Deleted all records from {table}")
                except duckdb.CatalogException as e:
                    logger.warning(
                        f"Table {table} does not exist, skipping deletion: {e}"
                    )
                    continue

            conn.execute("COMMIT")
            logger.info(
                f"Successfully deleted records from {len(deleted_tables)} tables"
            )
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Error during table deletion, rolled back: {e}")
            raise
