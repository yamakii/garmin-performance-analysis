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


def _create_new_tables(conn: duckdb.DuckDBPyConnection, tables: list[str]) -> None:
    """Create new tables without FK constraints.

    Args:
        conn: DuckDB connection
        tables: List of table names to create
    """
    # Table schemas without FK constraints
    schemas = _get_table_schemas_without_fk()

    for table in tables:
        if table not in schemas:
            raise ValueError(f"Unknown table: {table}")
        conn.execute(schemas[table])


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


def _get_table_schemas_without_fk() -> dict[str, str]:
    """Return CREATE TABLE statements without FK constraints.

    Returns:
        Dict mapping table names to CREATE TABLE SQL
    """
    return {
        "splits": """
            CREATE TABLE splits (
                activity_id BIGINT,
                split_index INTEGER,
                distance DOUBLE,
                duration_seconds DOUBLE,
                start_time_gmt VARCHAR,
                start_time_s INTEGER,
                end_time_s INTEGER,
                intensity_type VARCHAR,
                role_phase VARCHAR,
                pace_str VARCHAR,
                pace_seconds_per_km DOUBLE,
                heart_rate INTEGER,
                hr_zone VARCHAR,
                cadence DOUBLE,
                cadence_rating VARCHAR,
                power DOUBLE,
                power_efficiency VARCHAR,
                stride_length DOUBLE,
                ground_contact_time DOUBLE,
                vertical_oscillation DOUBLE,
                vertical_ratio DOUBLE,
                elevation_gain DOUBLE,
                elevation_loss DOUBLE,
                terrain_type VARCHAR,
                environmental_conditions VARCHAR,
                wind_impact VARCHAR,
                temp_impact VARCHAR,
                environmental_impact VARCHAR,
                PRIMARY KEY (activity_id, split_index)
            )
        """,
        "form_efficiency": """
            CREATE TABLE form_efficiency (
                activity_id BIGINT PRIMARY KEY,
                gct_average DOUBLE,
                gct_min DOUBLE,
                gct_max DOUBLE,
                gct_std DOUBLE,
                gct_variability DOUBLE,
                gct_rating VARCHAR,
                gct_evaluation VARCHAR,
                vo_average DOUBLE,
                vo_min DOUBLE,
                vo_max DOUBLE,
                vo_std DOUBLE,
                vo_trend VARCHAR,
                vo_rating VARCHAR,
                vo_evaluation VARCHAR,
                vr_average DOUBLE,
                vr_min DOUBLE,
                vr_max DOUBLE,
                vr_std DOUBLE,
                vr_rating VARCHAR,
                vr_evaluation VARCHAR
            )
        """,
        "heart_rate_zones": """
            CREATE TABLE heart_rate_zones (
                activity_id BIGINT,
                zone_number INTEGER,
                zone_low_boundary INTEGER,
                zone_high_boundary INTEGER,
                time_in_zone_seconds DOUBLE,
                zone_percentage DOUBLE,
                PRIMARY KEY (activity_id, zone_number)
            )
        """,
        "hr_efficiency": """
            CREATE TABLE hr_efficiency (
                activity_id BIGINT PRIMARY KEY,
                primary_zone VARCHAR,
                zone_distribution_rating VARCHAR,
                hr_stability VARCHAR,
                aerobic_efficiency VARCHAR,
                training_quality VARCHAR,
                zone2_focus BOOLEAN,
                zone4_threshold_work BOOLEAN,
                training_type VARCHAR,
                zone1_percentage DOUBLE,
                zone2_percentage DOUBLE,
                zone3_percentage DOUBLE,
                zone4_percentage DOUBLE,
                zone5_percentage DOUBLE
            )
        """,
        "performance_trends": """
            CREATE TABLE performance_trends (
                activity_id BIGINT PRIMARY KEY,
                pace_consistency DOUBLE,
                hr_drift_percentage DOUBLE,
                cadence_consistency VARCHAR,
                fatigue_pattern VARCHAR,
                warmup_splits VARCHAR,
                warmup_avg_pace_seconds_per_km DOUBLE,
                warmup_avg_pace_str VARCHAR,
                warmup_avg_hr DOUBLE,
                warmup_avg_cadence DOUBLE,
                warmup_avg_power DOUBLE,
                warmup_evaluation VARCHAR,
                run_splits VARCHAR,
                run_avg_pace_seconds_per_km DOUBLE,
                run_avg_pace_str VARCHAR,
                run_avg_hr DOUBLE,
                run_avg_cadence DOUBLE,
                run_avg_power DOUBLE,
                run_evaluation VARCHAR,
                recovery_splits VARCHAR,
                recovery_avg_pace_seconds_per_km DOUBLE,
                recovery_avg_pace_str VARCHAR,
                recovery_avg_hr DOUBLE,
                recovery_avg_cadence DOUBLE,
                recovery_avg_power DOUBLE,
                recovery_evaluation VARCHAR,
                cooldown_splits VARCHAR,
                cooldown_avg_pace_seconds_per_km DOUBLE,
                cooldown_avg_pace_str VARCHAR,
                cooldown_avg_hr DOUBLE,
                cooldown_avg_cadence DOUBLE,
                cooldown_avg_power DOUBLE,
                cooldown_evaluation VARCHAR
            )
        """,
        "vo2_max": """
            CREATE TABLE vo2_max (
                activity_id BIGINT PRIMARY KEY,
                precise_value DOUBLE,
                value DOUBLE,
                date DATE,
                category INTEGER
            )
        """,
        "lactate_threshold": """
            CREATE TABLE lactate_threshold (
                activity_id BIGINT PRIMARY KEY,
                heart_rate INTEGER,
                speed_mps DOUBLE,
                date_hr TIMESTAMP,
                functional_threshold_power INTEGER,
                power_to_weight DOUBLE,
                weight DOUBLE,
                date_power TIMESTAMP
            )
        """,
        "form_evaluations": """
            CREATE TABLE form_evaluations (
                eval_id INTEGER PRIMARY KEY,
                activity_id BIGINT UNIQUE,

                gct_ms_expected FLOAT,
                vo_cm_expected FLOAT,
                vr_pct_expected FLOAT,

                gct_ms_actual FLOAT,
                vo_cm_actual FLOAT,
                vr_pct_actual FLOAT,

                gct_delta_pct FLOAT,
                vo_delta_cm FLOAT,
                vr_delta_pct FLOAT,

                gct_penalty FLOAT,
                gct_star_rating VARCHAR,
                gct_score FLOAT,
                gct_needs_improvement BOOLEAN,
                gct_evaluation_text TEXT,

                vo_penalty FLOAT,
                vo_star_rating VARCHAR,
                vo_score FLOAT,
                vo_needs_improvement BOOLEAN,
                vo_evaluation_text TEXT,

                vr_penalty FLOAT,
                vr_star_rating VARCHAR,
                vr_score FLOAT,
                vr_needs_improvement BOOLEAN,
                vr_evaluation_text TEXT,

                cadence_actual FLOAT,
                cadence_minimum INTEGER DEFAULT 180,
                cadence_achieved BOOLEAN,

                overall_score FLOAT,
                overall_star_rating VARCHAR,

                power_avg_w FLOAT,
                power_wkg FLOAT,
                speed_actual_mps FLOAT,
                speed_expected_mps FLOAT,
                power_efficiency_score FLOAT,
                power_efficiency_rating VARCHAR,
                power_efficiency_needs_improvement BOOLEAN,
                integrated_score FLOAT,
                training_mode VARCHAR,

                evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "section_analyses": """
            CREATE TABLE section_analyses (
                analysis_id INTEGER PRIMARY KEY,
                activity_id BIGINT NOT NULL,
                activity_date DATE NOT NULL,
                section_type VARCHAR NOT NULL,
                analysis_data VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                agent_name VARCHAR,
                agent_version VARCHAR
            )
        """,
    }


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

    conn = duckdb.connect(db_path)

    try:
        conn.execute("BEGIN TRANSACTION")

        # 1. Backup
        _backup_tables(conn, tables_to_migrate)

        # 2. Drop old tables
        _drop_old_tables(conn, tables_to_migrate)

        # 3. Create new tables without FK
        _create_new_tables(conn, tables_to_migrate)

        # 4. Restore data
        _restore_data(conn, tables_to_migrate)

        # 5. Verify data integrity
        verification_results = _verify_data_integrity(conn, tables_to_migrate)

        # 6. Cleanup backup tables
        _cleanup_backup_tables(conn, tables_to_migrate)

        conn.execute("COMMIT")

        conn.close()

        return {
            "status": "success",
            "tables": tables_to_migrate,
            "verification": verification_results,
        }

    except Exception as e:
        conn.execute("ROLLBACK")
        conn.close()
        raise Exception(f"Migration failed: {e}") from e
