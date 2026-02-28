"""Migration script to remove foreign key constraints from DuckDB schema.

This script migrates existing databases from FK-constrained schema to
FK-free schema using CTAS (CREATE TABLE AS SELECT) backup strategy.

Migration strategy:
1. Backup: CREATE TABLE <table>_backup_fk AS SELECT * FROM <table>
2. Drop: DROP TABLE <table>
3. Create: CREATE TABLE <table> (...) -- without FOREIGN KEY
4. Restore: INSERT INTO <table> SELECT * FROM <table>_backup_fk
5. Verify: Check row counts match
6. Cleanup: DROP TABLE <table>_backup_fk

All operations run within a transaction for safety (ROLLBACK on error).
"""

from typing import Any

import duckdb


def _backup_tables(conn: duckdb.DuckDBPyConnection, tables: list[str]) -> None:
    """Create backup tables using CTAS (CREATE TABLE AS SELECT).

    Args:
        conn: DuckDB connection
        tables: List of table names to backup

    Creates:
        <table>_backup_fk: Backup table with all data from <table>
    """
    for table in tables:
        backup_table = f"{table}_backup_fk"
        conn.execute(f"CREATE TABLE {backup_table} AS SELECT * FROM {table}")


def _drop_old_tables(conn: duckdb.DuckDBPyConnection, tables: list[str]) -> None:
    """Drop old tables with FK constraints.

    Args:
        conn: DuckDB connection
        tables: List of table names to drop
    """
    for table in tables:
        conn.execute(f"DROP TABLE {table}")


def _restore_data(conn: duckdb.DuckDBPyConnection, tables: list[str]) -> None:
    """Restore data from backup tables.

    Args:
        conn: DuckDB connection
        tables: List of table names to restore

    Note:
        Uses column-wise INSERT to handle schema differences between
        backup (4-col test) and new table (28-col production).
    """
    for table in tables:
        backup_table = f"{table}_backup_fk"

        # Get column names from backup table
        backup_columns = conn.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{backup_table}' ORDER BY ordinal_position"
        ).fetchall()
        backup_col_names = [col[0] for col in backup_columns]

        # Get column names from new table
        new_columns = conn.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position"
        ).fetchall()
        new_col_names = [col[0] for col in new_columns]

        # Find common columns
        common_columns = [col for col in backup_col_names if col in new_col_names]

        if not common_columns:
            raise ValueError(f"No common columns between {table} and {backup_table}")

        # Build INSERT with explicit column names
        cols_str = ", ".join(common_columns)
        conn.execute(
            f"INSERT INTO {table} ({cols_str}) SELECT {cols_str} FROM {backup_table}"
        )


def _verify_data_integrity(
    conn: duckdb.DuckDBPyConnection, tables: list[str]
) -> dict[str, dict[str, int]]:
    """Verify data integrity by comparing row counts.

    Args:
        conn: DuckDB connection
        tables: List of table names to verify

    Returns:
        Dict mapping table names to {original: count, backup: count}

    Raises:
        AssertionError: If row counts don't match
    """
    results = {}
    for table in tables:
        backup_table = f"{table}_backup_fk"

        count_new_result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        count_backup_result = conn.execute(
            f"SELECT COUNT(*) FROM {backup_table}"
        ).fetchone()

        if count_new_result is None or count_backup_result is None:
            raise ValueError(f"Failed to get row counts for {table}")

        count_new = count_new_result[0]
        count_backup = count_backup_result[0]

        results[table] = {"new": count_new, "backup": count_backup}

        if count_new != count_backup:
            raise AssertionError(
                f"Data integrity check failed for {table}: "
                f"new={count_new}, backup={count_backup}"
            )

    return results


def _cleanup_backup_tables(conn: duckdb.DuckDBPyConnection, tables: list[str]) -> None:
    """Drop backup tables after successful migration.

    Args:
        conn: DuckDB connection
        tables: List of table names whose backups should be dropped
    """
    for table in tables:
        backup_table = f"{table}_backup_fk"
        conn.execute(f"DROP TABLE {backup_table}")


def migrate_remove_fk_constraints(
    db_path: str, dry_run: bool = False
) -> dict[str, Any]:
    """Execute FK removal migration with transaction safety.

    Args:
        db_path: Path to DuckDB database
        dry_run: If True, show SQL only without execution

    Returns:
        Migration result dict with status, tables migrated, errors

    Raises:
        Exception: If migration fails (triggers ROLLBACK)
    """
    tables_to_migrate = [
        "splits",
        "form_efficiency",
        "heart_rate_zones",
        "hr_efficiency",
        "performance_trends",
        "vo2_max",
        "lactate_threshold",
        "form_evaluations",
        "section_analyses",
    ]

    if dry_run:
        print("DRY RUN MODE - No changes will be made")
        print(f"\nTables to migrate: {tables_to_migrate}")
        print("\nSteps:")
        print("1. BEGIN TRANSACTION")
        for table in tables_to_migrate:
            print(f"2. CREATE TABLE {table}_backup_fk AS SELECT * FROM {table}")
            print(f"3. DROP TABLE {table}")
            print(f"4. CREATE TABLE {table} (...) -- without FK")
            print(f"5. INSERT INTO {table} SELECT * FROM {table}_backup_fk")
            print("6. Verify COUNT(*) matches")
            print(f"7. DROP TABLE {table}_backup_fk")
        print("8. COMMIT")
        return {"status": "dry_run", "tables": tables_to_migrate}

    # This function is deprecated. The migration runner uses _wrap_remove_fk
    # (no-op) instead. DDL schemas are centralized in db_writer._ensure_tables().
    raise NotImplementedError(
        "migrate_remove_fk_constraints is deprecated. "
        "DDL is now centralized in db_writer._ensure_tables(). "
        "The migration runner uses _wrap_remove_fk (no-op) instead."
    )
