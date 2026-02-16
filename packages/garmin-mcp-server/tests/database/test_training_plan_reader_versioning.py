"""Tests for versioned training plan reader."""

import duckdb
import pytest

from garmin_mcp.database.readers.training_plans import TrainingPlanReader


def _setup_db(conn: duckdb.DuckDBPyConnection) -> None:
    """Create tables with version columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS training_plans (
            plan_id VARCHAR,
            version INTEGER DEFAULT 1,
            goal_type VARCHAR NOT NULL,
            target_race_date DATE,
            target_time_seconds INTEGER,
            vdot DOUBLE NOT NULL,
            pace_zones_json VARCHAR NOT NULL,
            total_weeks INTEGER NOT NULL,
            start_date DATE NOT NULL,
            weekly_volume_start_km DOUBLE NOT NULL,
            weekly_volume_peak_km DOUBLE NOT NULL,
            runs_per_week INTEGER NOT NULL,
            frequency_progression_json VARCHAR,
            personalization_notes VARCHAR,
            status VARCHAR DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS planned_workouts (
            workout_id VARCHAR PRIMARY KEY,
            plan_id VARCHAR NOT NULL,
            version INTEGER DEFAULT 1,
            week_number INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            workout_date DATE,
            workout_type VARCHAR NOT NULL,
            description_ja VARCHAR,
            target_distance_km DOUBLE,
            target_duration_minutes DOUBLE,
            target_pace_low DOUBLE,
            target_pace_high DOUBLE,
            target_hr_low INTEGER,
            target_hr_high INTEGER,
            intervals_json VARCHAR,
            phase VARCHAR NOT NULL,
            garmin_workout_id BIGINT,
            uploaded_at TIMESTAMP,
            actual_activity_id BIGINT,
            adherence_score DOUBLE,
            completed_at TIMESTAMP
        )
    """)


def _insert_plan(
    conn: duckdb.DuckDBPyConnection,
    plan_id: str,
    version: int,
    status: str = "active",
) -> None:
    conn.execute(
        """
        INSERT INTO training_plans (plan_id, version, goal_type, vdot,
            pace_zones_json, total_weeks, start_date,
            weekly_volume_start_km, weekly_volume_peak_km,
            runs_per_week, status)
        VALUES (?, ?, 'fitness', 45.0, '{"easy_low":360}', 4,
                '2026-03-02', 30.0, 40.0, 4, ?)
        """,
        [plan_id, version, status],
    )


def _insert_workout(
    conn: duckdb.DuckDBPyConnection,
    workout_id: str,
    plan_id: str,
    version: int,
    week_number: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO planned_workouts
            (workout_id, plan_id, version, week_number, day_of_week,
             workout_type, phase)
        VALUES (?, ?, ?, ?, 2, 'easy', 'base')
        """,
        [workout_id, plan_id, version, week_number],
    )


@pytest.mark.unit
class TestTrainingPlanReaderVersioning:
    @pytest.fixture
    def db_path(self, tmp_path):
        path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(path)
        _setup_db(conn)
        conn.close()
        return path

    def test_get_latest_active_version(self, db_path):
        """version=None should return the latest active version."""
        conn = duckdb.connect(db_path)
        _insert_plan(conn, "plan-1", 1, "superseded")
        _insert_plan(conn, "plan-1", 2, "active")
        _insert_workout(conn, "w1", "plan-1", 1)
        _insert_workout(conn, "w2", "plan-1", 2)
        conn.close()

        reader = TrainingPlanReader(db_path=db_path)
        result = reader.get_training_plan("plan-1")

        assert result.get("version") == 2
        assert len(result.get("workouts", [])) == 1
        assert result["workouts"][0]["workout_id"] == "w2"

    def test_get_specific_version(self, db_path):
        """Specifying version returns that exact version."""
        conn = duckdb.connect(db_path)
        _insert_plan(conn, "plan-1", 1, "superseded")
        _insert_plan(conn, "plan-1", 2, "active")
        _insert_workout(conn, "w1", "plan-1", 1)
        _insert_workout(conn, "w2", "plan-1", 2)
        conn.close()

        reader = TrainingPlanReader(db_path=db_path)
        result = reader.get_training_plan("plan-1", version=1)

        assert result.get("version") == 1
        assert len(result.get("workouts", [])) == 1
        assert result["workouts"][0]["workout_id"] == "w1"

    def test_summary_includes_version(self, db_path):
        """Summary mode also includes version."""
        conn = duckdb.connect(db_path)
        _insert_plan(conn, "plan-1", 1, "active")
        _insert_workout(conn, "w1", "plan-1", 1)
        conn.close()

        reader = TrainingPlanReader(db_path=db_path)
        result = reader.get_training_plan("plan-1", summary_only=True)

        assert result.get("version") == 1
        assert "workouts" not in result

    def test_not_found(self, db_path):
        """Non-existent plan returns error."""
        reader = TrainingPlanReader(db_path=db_path)
        result = reader.get_training_plan("nonexistent")

        assert "error" in result

    def test_workouts_filtered_by_version(self, db_path):
        """Workouts are filtered by the selected version."""
        conn = duckdb.connect(db_path)
        _insert_plan(conn, "plan-1", 1, "superseded")
        _insert_plan(conn, "plan-1", 2, "active")
        # 2 workouts for v1, 3 for v2
        _insert_workout(conn, "w1a", "plan-1", 1, week_number=1)
        _insert_workout(conn, "w1b", "plan-1", 1, week_number=2)
        _insert_workout(conn, "w2a", "plan-1", 2, week_number=1)
        _insert_workout(conn, "w2b", "plan-1", 2, week_number=2)
        _insert_workout(conn, "w2c", "plan-1", 2, week_number=3)
        conn.close()

        reader = TrainingPlanReader(db_path=db_path)

        # Latest (v2) has 3 workouts
        result_latest = reader.get_training_plan("plan-1")
        assert len(result_latest["workouts"]) == 3

        # v1 has 2 workouts
        result_v1 = reader.get_training_plan("plan-1", version=1)
        assert len(result_v1["workouts"]) == 2

    def test_week_filter_with_version(self, db_path):
        """Week filter works together with version filter."""
        conn = duckdb.connect(db_path)
        _insert_plan(conn, "plan-1", 2, "active")
        _insert_workout(conn, "w2a", "plan-1", 2, week_number=1)
        _insert_workout(conn, "w2b", "plan-1", 2, week_number=2)
        conn.close()

        reader = TrainingPlanReader(db_path=db_path)
        result = reader.get_training_plan("plan-1", version=2, week_number=1)

        assert len(result["workouts"]) == 1
        assert result["workouts"][0]["week_number"] == 1
