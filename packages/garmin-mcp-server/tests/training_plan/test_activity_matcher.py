"""Tests for ActivityMatcher."""

import duckdb
import pytest

from garmin_mcp.training_plan.activity_matcher import ActivityMatcher


def _setup_db(conn: duckdb.DuckDBPyConnection) -> None:
    """Create tables and seed test data."""
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE,
            total_distance_km DOUBLE,
            total_time_seconds DOUBLE,
            avg_pace_seconds_per_km DOUBLE,
            activity_name VARCHAR
        )
    """)
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


def _insert_plan(conn: duckdb.DuckDBPyConnection, plan_id: str = "plan-1") -> None:
    """Insert a minimal training plan."""
    conn.execute(
        """
        INSERT INTO training_plans (plan_id, version, goal_type, vdot, pace_zones_json,
            total_weeks, start_date, weekly_volume_start_km, weekly_volume_peak_km,
            runs_per_week, status)
        VALUES (?, 1, 'fitness', 45.0, '{}', 4, '2026-03-02', 30.0, 40.0, 4, 'active')
        """,
        [plan_id],
    )


def _insert_workout(
    conn: duckdb.DuckDBPyConnection,
    workout_id: str,
    plan_id: str,
    version: int,
    week_number: int,
    day_of_week: int,
    workout_date: str,
    workout_type: str = "easy",
) -> None:
    """Insert a planned workout."""
    conn.execute(
        """
        INSERT INTO planned_workouts
            (workout_id, plan_id, version, week_number, day_of_week,
             workout_date, workout_type, phase)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'base')
        """,
        [
            workout_id,
            plan_id,
            version,
            week_number,
            day_of_week,
            workout_date,
            workout_type,
        ],
    )


def _insert_activity(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    activity_date: str,
    distance_km: float = 5.0,
) -> None:
    """Insert an activity."""
    conn.execute(
        """
        INSERT INTO activities (activity_id, activity_date, total_distance_km,
            total_time_seconds, avg_pace_seconds_per_km)
        VALUES (?, ?, ?, 1800, 360.0)
        """,
        [activity_id, activity_date, distance_km],
    )


@pytest.mark.unit
class TestActivityMatcher:
    @pytest.fixture
    def db_path(self, tmp_path):
        path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(path)
        _setup_db(conn)
        _insert_plan(conn, "plan-1")
        conn.close()
        return path

    def test_match_exact_date(self, db_path):
        """Activity on same date as workout matches."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_activity(conn, 1001, "2026-03-03")
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        assert len(matches) == 1
        assert matches[0].workout_id == "w1"
        assert matches[0].actual_activity_id == 1001

    def test_match_plus_one_day(self, db_path):
        """Activity one day after workout date matches."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_activity(conn, 1001, "2026-03-04")  # +1 day
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        assert len(matches) == 1
        assert matches[0].actual_activity_id == 1001

    def test_match_minus_one_day(self, db_path):
        """Activity one day before workout date matches."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_activity(conn, 1001, "2026-03-02")  # -1 day
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        assert len(matches) == 1

    def test_no_match_two_days_away(self, db_path):
        """Activity two days away does not match."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_activity(conn, 1001, "2026-03-05")  # +2 days
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        assert len(matches) == 0

    def test_no_double_match(self, db_path):
        """Each activity can only match one workout."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_workout(conn, "w2", "plan-1", 1, 1, 3, "2026-03-03")
        _insert_activity(conn, 1001, "2026-03-03")
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        # Only one workout should match this single activity
        assert len(matches) == 1

    def test_closest_date_preferred(self, db_path):
        """When multiple activities are within range, closest date wins."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_activity(conn, 1001, "2026-03-02")  # -1 day
        _insert_activity(conn, 1002, "2026-03-03")  # exact match
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        assert len(matches) == 1
        assert matches[0].actual_activity_id == 1002  # exact match preferred

    def test_rest_days_excluded(self, db_path):
        """Rest day workouts are excluded from matching."""
        conn = duckdb.connect(db_path)
        _insert_workout(
            conn, "w1", "plan-1", 1, 1, 2, "2026-03-03", workout_type="rest"
        )
        _insert_activity(conn, 1001, "2026-03-03")
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        assert len(matches) == 0

    def test_multiple_weeks(self, db_path):
        """Matching works across multiple weeks."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_workout(conn, "w2", "plan-1", 1, 2, 4, "2026-03-12")
        _insert_activity(conn, 1001, "2026-03-03")
        _insert_activity(conn, 1002, "2026-03-12")
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches = matcher.match_activities("plan-1", version=1)

        assert len(matches) == 2

    def test_get_completed_weeks_empty(self, db_path):
        """No matches means no completed weeks."""
        matcher = ActivityMatcher(db_path=db_path)
        completed, last = matcher.get_completed_weeks("plan-1", version=1)

        assert completed == set()
        assert last == 0

    def test_get_completed_weeks(self, db_path):
        """Weeks with at least one match are completed."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_workout(conn, "w2", "plan-1", 1, 2, 4, "2026-03-12")
        _insert_activity(conn, 1001, "2026-03-03")
        _insert_activity(conn, 1002, "2026-03-12")
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        completed, last = matcher.get_completed_weeks("plan-1", version=1)

        assert 1 in completed
        assert 2 in completed
        assert last == 2

    def test_version_isolation(self, db_path):
        """Workouts from different versions are not mixed."""
        conn = duckdb.connect(db_path)
        _insert_workout(conn, "w1", "plan-1", 1, 1, 2, "2026-03-03")
        _insert_workout(conn, "w2", "plan-1", 2, 1, 2, "2026-03-03")
        _insert_activity(conn, 1001, "2026-03-03")
        conn.close()

        matcher = ActivityMatcher(db_path=db_path)
        matches_v1 = matcher.match_activities("plan-1", version=1)
        matches_v2 = matcher.match_activities("plan-1", version=2)

        assert len(matches_v1) == 1
        assert len(matches_v2) == 1
        # Both match the same activity to different versioned workouts
        assert matches_v1[0].workout_id == "w1"
        assert matches_v2[0].workout_id == "w2"
