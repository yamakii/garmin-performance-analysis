"""Tests for PerformanceReader.

Covers get_performance_trends (phase parsing, recovery_phase presence),
get_weather_data (unit conversions, NULL handling),
and get_section_analysis (deprecation, size limit).
"""

import json
import warnings
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.performance import PerformanceReader

ACTIVITY_ID = 66660001
MISSING_ID = 99999999


@pytest.fixture
def perf_reader(reader_db_path: Path) -> PerformanceReader:
    """PerformanceReader with seeded performance + weather + section data."""
    conn = duckdb.connect(str(reader_db_path))

    # Parent activity with weather data
    conn.execute(
        """INSERT INTO activities (activity_id, activity_date,
           temp_celsius, relative_humidity_percent, wind_speed_kmh, wind_direction)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [ACTIVITY_ID, "2025-06-15", 25.0, 60.0, 18.0, "NW"],
    )

    # performance_trends — 3-phase (no recovery)
    conn.execute(
        """INSERT INTO performance_trends (
            activity_id, pace_consistency, hr_drift_percentage,
            cadence_consistency, fatigue_pattern,
            warmup_splits, warmup_avg_pace_seconds_per_km, warmup_avg_hr,
            run_splits, run_avg_pace_seconds_per_km, run_avg_hr,
            recovery_splits, recovery_avg_pace_seconds_per_km, recovery_avg_hr,
            cooldown_splits, cooldown_avg_pace_seconds_per_km, cooldown_avg_hr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ACTIVITY_ID,
            0.92,
            2.5,
            "安定",
            "negative_split",
            "1",
            360.0,
            130.0,
            "2,3,4,5,6,7",
            300.0,
            155.0,
            None,
            None,
            None,
            "8",
            420.0,
            125.0,
        ],
    )

    # section_analyses
    analysis_json = json.dumps({"rating": "****", "summary": "良好なペース"})
    conn.execute(
        """INSERT INTO section_analyses
           (analysis_id, activity_id, activity_date, section_type, analysis_data)
           VALUES (?, ?, ?, ?, ?)""",
        [1, ACTIVITY_ID, "2025-06-15", "phase", analysis_json],
    )

    conn.close()
    return PerformanceReader(db_path=str(reader_db_path))


# ---------------------------------------------------------------------------
# get_performance_trends
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPerformanceTrends:
    """Tests for PerformanceReader.get_performance_trends()."""

    def test_returns_data(self, perf_reader: PerformanceReader):
        result = perf_reader.get_performance_trends(ACTIVITY_ID)
        assert result is not None
        assert result["pace_consistency"] == 0.92

    def test_no_recovery_phase_when_null(self, perf_reader: PerformanceReader):
        """3-phase activity should NOT have recovery_phase key."""
        result = perf_reader.get_performance_trends(ACTIVITY_ID)
        assert result is not None
        assert "recovery_phase" not in result

    def test_recovery_phase_when_present(self, reader_db_path: Path):
        """4-phase interval training includes recovery_phase."""
        conn = duckdb.connect(str(reader_db_path))
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
            [ACTIVITY_ID + 1, "2025-06-16"],
        )
        conn.execute(
            """INSERT INTO performance_trends (
                activity_id, pace_consistency, hr_drift_percentage,
                cadence_consistency, fatigue_pattern,
                warmup_splits, warmup_avg_pace_seconds_per_km, warmup_avg_hr,
                run_splits, run_avg_pace_seconds_per_km, run_avg_hr,
                recovery_splits, recovery_avg_pace_seconds_per_km, recovery_avg_hr,
                cooldown_splits, cooldown_avg_pace_seconds_per_km, cooldown_avg_hr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ACTIVITY_ID + 1,
                0.88,
                3.0,
                "やや不安定",
                "even",
                "1",
                360.0,
                130.0,
                "2,3,4",
                280.0,
                165.0,
                "5,6",
                350.0,
                140.0,
                "7",
                420.0,
                125.0,
            ],
        )
        conn.close()

        reader = PerformanceReader(db_path=str(reader_db_path))
        result = reader.get_performance_trends(ACTIVITY_ID + 1)
        assert result is not None
        assert "recovery_phase" in result
        assert result["recovery_phase"]["avg_pace"] == 350.0

    def test_missing_activity(self, perf_reader: PerformanceReader):
        assert perf_reader.get_performance_trends(MISSING_ID) is None


# ---------------------------------------------------------------------------
# get_weather_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetWeatherData:
    """Tests for PerformanceReader.get_weather_data()."""

    def test_wind_speed_kmh_to_ms(self, perf_reader: PerformanceReader):
        """18.0 km/h → 5.0 m/s."""
        result = perf_reader.get_weather_data(ACTIVITY_ID)
        assert result is not None
        assert abs(result["wind_speed_ms"] - 5.0) < 0.01

    def test_celsius_to_fahrenheit(self, perf_reader: PerformanceReader):
        """25.0°C → 77.0°F."""
        result = perf_reader.get_weather_data(ACTIVITY_ID)
        assert result is not None
        assert result["temperature_c"] == 25.0
        assert abs(result["temperature_f"] - 77.0) < 0.01

    def test_null_temp_handling(self, reader_db_path: Path):
        """NULL temperature → None in both C and F."""
        conn = duckdb.connect(str(reader_db_path))
        conn.execute(
            """INSERT INTO activities (activity_id, activity_date,
               temp_celsius, wind_speed_kmh)
               VALUES (?, ?, NULL, NULL)""",
            [ACTIVITY_ID + 10, "2025-07-01"],
        )
        conn.close()

        reader = PerformanceReader(db_path=str(reader_db_path))
        result = reader.get_weather_data(ACTIVITY_ID + 10)
        assert result is not None
        assert result["temperature_c"] is None
        assert result["temperature_f"] is None
        assert result["wind_speed_ms"] is None

    def test_missing_activity(self, perf_reader: PerformanceReader):
        assert perf_reader.get_weather_data(MISSING_ID) is None


# ---------------------------------------------------------------------------
# get_section_analysis
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSectionAnalysis:
    """Tests for PerformanceReader.get_section_analysis()."""

    def test_deprecation_warning(self, perf_reader: PerformanceReader):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            perf_reader.get_section_analysis(ACTIVITY_ID, "phase")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_returns_parsed_json(self, perf_reader: PerformanceReader):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = perf_reader.get_section_analysis(ACTIVITY_ID, "phase")
        assert result is not None
        assert result["rating"] == "****"

    def test_max_output_size_exceeded(self, perf_reader: PerformanceReader):
        with (
            pytest.raises(ValueError, match="exceeds max_output_size"),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", DeprecationWarning)
            perf_reader.get_section_analysis(ACTIVITY_ID, "phase", max_output_size=5)

    def test_missing_section(self, perf_reader: PerformanceReader):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = perf_reader.get_section_analysis(ACTIVITY_ID, "nonexistent")
        assert result is None

    def test_reader_returns_latest_version(self, reader_db_path: Path):
        """With multiple versions of a section, the newest one is returned.

        Append-only storage (#720) keeps every version; the reader resolves the
        canonical result via ORDER BY created_at DESC.
        """
        conn = duckdb.connect(str(reader_db_path))
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
            [ACTIVITY_ID, "2025-06-15"],
        )
        # Two versions of the same section, created 1 minute apart.
        conn.execute(
            """INSERT INTO section_analyses
               (analysis_id, activity_id, activity_date, section_type,
                analysis_data, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                10,
                ACTIVITY_ID,
                "2025-06-15",
                "efficiency",
                json.dumps({"summary": "old"}),
                "2025-06-15 12:00:00",
            ],
        )
        conn.execute(
            """INSERT INTO section_analyses
               (analysis_id, activity_id, activity_date, section_type,
                analysis_data, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                11,
                ACTIVITY_ID,
                "2025-06-15",
                "efficiency",
                json.dumps({"summary": "new"}),
                "2025-06-15 12:01:00",
            ],
        )
        conn.close()

        reader = PerformanceReader(db_path=str(reader_db_path))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = reader.get_section_analysis(ACTIVITY_ID, "efficiency")

        assert result is not None
        assert result["summary"] == "new"


# ---------------------------------------------------------------------------
# find_unanalyzed_activities
# ---------------------------------------------------------------------------

_ALL_SECTIONS = ["efficiency", "phase", "environment", "summary", "split"]


def _seed_activity(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    date: str,
    section_count: int,
) -> None:
    """Insert an activity plus ``section_count`` distinct section analyses."""
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
        [activity_id, date],
    )
    for i, section in enumerate(_ALL_SECTIONS[:section_count]):
        conn.execute(
            """INSERT INTO section_analyses
               (analysis_id, activity_id, activity_date, section_type,
                analysis_data)
               VALUES (?, ?, ?, ?, ?)""",
            [
                activity_id * 10 + i,
                activity_id,
                date,
                section,
                json.dumps({"summary": section}),
            ],
        )


@pytest.mark.unit
class TestFindUnanalyzedActivities:
    """Tests for PerformanceReader.find_unanalyzed_activities()."""

    def test_find_unanalyzed_returns_incomplete(self, reader_db_path: Path):
        """3 activities (5/3/0 sections) -> 2 incomplete with counts 3 and 0."""
        conn = duckdb.connect(str(reader_db_path))
        _seed_activity(conn, 70000001, "2025-06-01", 5)  # complete
        _seed_activity(conn, 70000002, "2025-06-02", 3)  # incomplete
        _seed_activity(conn, 70000003, "2025-06-03", 0)  # never analyzed
        conn.close()

        reader = PerformanceReader(db_path=str(reader_db_path))
        result = reader.find_unanalyzed_activities("2025-06-01", "2025-06-30")

        assert [r["activity_id"] for r in result] == [70000002, 70000003]
        assert [r["section_count"] for r in result] == [3, 0]
        assert [r["date"] for r in result] == ["2025-06-02", "2025-06-03"]

    def test_find_unanalyzed_empty_when_complete(self, reader_db_path: Path):
        """Every activity has 5 sections -> no incomplete activities."""
        conn = duckdb.connect(str(reader_db_path))
        _seed_activity(conn, 70000010, "2025-06-01", 5)
        _seed_activity(conn, 70000011, "2025-06-02", 5)
        conn.close()

        reader = PerformanceReader(db_path=str(reader_db_path))
        result = reader.find_unanalyzed_activities("2025-06-01", "2025-06-30")

        assert result == []

    def test_find_unanalyzed_respects_date_range(self, reader_db_path: Path):
        """An unanalyzed activity outside the range is excluded."""
        conn = duckdb.connect(str(reader_db_path))
        _seed_activity(conn, 70000020, "2025-06-15", 0)  # in range
        _seed_activity(conn, 70000021, "2025-08-01", 0)  # out of range
        conn.close()

        reader = PerformanceReader(db_path=str(reader_db_path))
        result = reader.find_unanalyzed_activities("2025-06-01", "2025-06-30")

        assert [r["activity_id"] for r in result] == [70000020]
