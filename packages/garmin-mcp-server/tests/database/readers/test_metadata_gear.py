"""Tests for the gear usage helpers in the metadata reader (Issue #1207).

Shoes are identified by ``gear_uuid``, not by name: Garmin's newer gear form
leaves ``gear_model`` as the base model, so a replacement pair of the same shoe
reuses the string. ``gear_model`` remains the fallback for rows ingested before
``gear_uuid`` existed.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.metadata import (
    collect_activity_gear,
    collect_gear_roster,
    collect_week_gear_usage,
)


def _insert(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    activity_date: str,
    distance_km: float,
    gear_model: str | None = None,
    gear_nickname: str | None = None,
    gear_uuid: str | None = None,
    gear_type: str | None = "Shoes",
    gear_max_km: float | None = None,
    gear_status: str | None = None,
    gear_since_date: str | None = None,
    gear_retired_date: str | None = None,
) -> None:
    """Insert one activity row with the gear columns under test."""
    conn.execute(
        """
        INSERT INTO activities (
            activity_id, activity_date, total_distance_km,
            gear_type, gear_model, gear_nickname, gear_uuid,
            gear_max_km, gear_status, gear_since_date, gear_retired_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            activity_id,
            activity_date,
            distance_km,
            gear_type if gear_model else None,
            gear_model,
            gear_nickname,
            gear_uuid,
            gear_max_km,
            gear_status,
            gear_since_date,
            gear_retired_date,
        ],
    )


@pytest.fixture
def gear_conn(reader_db_path: Path) -> duckdb.DuckDBPyConnection:
    """Connection holding one shoe used three times, plus a second shoe."""
    conn = duckdb.connect(str(reader_db_path))
    _insert(conn, 1, "2026-09-01", 10.0, "Test Shoe A", "v1", "uuid-a")
    _insert(conn, 2, "2026-09-03", 12.0, "Test Shoe A", "v1", "uuid-a")
    _insert(conn, 3, "2026-09-05", 8.0, "Test Shoe A", "v1", "uuid-a")
    # 40 km in one outing, so Shoe B outranks Shoe A's 30 km without a tie.
    _insert(conn, 4, "2026-09-03", 40.0, "Test Shoe B", None, "uuid-b")
    return conn


@pytest.mark.integration
class TestCollectActivityGear:
    """Tests for collect_activity_gear()."""

    def test_collect_activity_gear_returns_cumulative_counts(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Counts are as of the given run, not as of today."""
        result = collect_activity_gear(gear_conn, 2)

        assert result is not None
        assert result["gear_model"] == "Test Shoe A"
        assert result["gear_nickname"] == "v1"
        assert result["gear_label"] == "Test Shoe A (v1)"
        assert result["gear_type"] == "Shoes"
        assert result["first_use_date"] == "2026-09-01"
        assert result["runs_on_gear"] == 2
        assert result["km_on_gear"] == 22.0
        assert result["is_new_gear"] is True

    def test_collect_activity_gear_excludes_other_models(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """A different shoe on the same day does not inflate the total."""
        result = collect_activity_gear(gear_conn, 4)

        assert result is not None
        assert result["gear_model"] == "Test Shoe B"
        assert result["runs_on_gear"] == 1
        assert result["km_on_gear"] == 40.0

    def test_collect_activity_gear_separates_pairs_sharing_a_model_name(
        self, reader_db_path: Path
    ) -> None:
        """Two generations of one model must not share a mileage total.

        This is the collision Garmin's newer gear form creates: both pairs
        carry ``customMakeModel = "NB 1080"`` and differ only by nickname and
        uuid.
        """
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-01", 10.0, "NB 1080", "v14", "uuid-v14")
        _insert(conn, 2, "2026-09-03", 12.0, "NB 1080", "v14", "uuid-v14")
        _insert(conn, 3, "2026-09-08", 8.0, "NB 1080", "v15", "uuid-v15")

        result = collect_activity_gear(conn, 3)

        assert result is not None
        assert result["gear_label"] == "NB 1080 (v15)"
        assert result["runs_on_gear"] == 1
        assert result["km_on_gear"] == 8.0
        assert result["first_use_date"] == "2026-09-08"

    def test_collect_activity_gear_falls_back_to_model_without_uuid(
        self, reader_db_path: Path
    ) -> None:
        """Rows ingested before gear_uuid existed still aggregate by name."""
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-01", 10.0, "Legacy Shoe")
        _insert(conn, 2, "2026-09-03", 12.0, "Legacy Shoe")

        result = collect_activity_gear(conn, 2)

        assert result is not None
        assert result["runs_on_gear"] == 2
        assert result["km_on_gear"] == 22.0
        assert result["gear_label"] == "Legacy Shoe"

    def test_collect_activity_gear_returns_none_without_gear(
        self, reader_db_path: Path
    ) -> None:
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-01", 10.0)

        assert collect_activity_gear(conn, 1) is None

    def test_collect_activity_gear_returns_none_for_unknown_activity(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        assert collect_activity_gear(gear_conn, 999999) is None


@pytest.mark.integration
class TestCollectWeekGearUsage:
    """Tests for collect_week_gear_usage()."""

    def test_collect_week_gear_usage_orders_by_km_desc(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        result = collect_week_gear_usage(gear_conn, "2026-09-01", "2026-09-07")

        assert len(result) == 2
        assert result[0]["gear_model"] == "Test Shoe B"
        assert result[0]["km"] == 40.0
        assert result[0]["runs"] == 1
        assert result[1]["gear_model"] == "Test Shoe A"
        assert result[1]["km"] == 30.0
        assert result[1]["runs"] == 3

    def test_collect_week_gear_usage_window_is_inclusive(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Only the runs inside the window count toward runs / km."""
        result = collect_week_gear_usage(gear_conn, "2026-09-01", "2026-09-03")

        by_model = {row["gear_model"]: row for row in result}
        assert by_model["Test Shoe A"]["runs"] == 2
        assert by_model["Test Shoe A"]["km"] == 22.0

    def test_collect_week_gear_usage_totals_are_cumulative(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """runs_on_gear_total spans the shoe's life through the window end."""
        result = collect_week_gear_usage(gear_conn, "2026-09-05", "2026-09-07")

        assert len(result) == 1
        assert result[0]["gear_model"] == "Test Shoe A"
        assert result[0]["runs"] == 1
        assert result[0]["runs_on_gear_total"] == 3
        assert result[0]["is_new_gear"] is True

    def test_collect_week_gear_usage_empty_window(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        assert collect_week_gear_usage(gear_conn, "2020-01-01", "2020-01-07") == []


@pytest.fixture
def wear_conn(reader_db_path: Path) -> duckdb.DuckDBPyConnection:
    """A worn pair, a brand-new one sharing its model name, and a retired one.

    Mirrors the real rotation: the v14 sits at 552.5 / 643.7 km while the v15
    stores under the same ``gear_model`` string.
    """
    conn = duckdb.connect(str(reader_db_path))
    _insert(
        conn,
        1,
        "2026-01-10",
        300.0,
        "NB 1080",
        "v14",
        "u-v14",
        gear_max_km=643.7,
        gear_status="active",
        gear_since_date="2025-12-26",
    )
    _insert(
        conn,
        2,
        "2026-09-06",
        252.5,
        "NB 1080",
        "v14",
        "u-v14",
        gear_max_km=643.7,
        gear_status="active",
        gear_since_date="2025-12-26",
    )
    _insert(
        conn,
        3,
        "2026-09-08",
        37.6,
        "NB 1080",
        "v15",
        "u-v15",
        gear_max_km=650.0,
        gear_status="active",
        gear_since_date="2026-09-08",
    )
    # Status flips across this shoe's own rows: active, then retired.
    _insert(
        conn,
        4,
        "2025-06-01",
        400.0,
        "skechers",
        None,
        "u-sk",
        gear_max_km=643.7,
        gear_status="active",
        gear_since_date="2022-11-11",
    )
    _insert(
        conn,
        5,
        "2025-11-17",
        287.9,
        "skechers",
        None,
        "u-sk",
        gear_max_km=643.7,
        gear_status="retired",
        gear_since_date="2022-11-11",
        gear_retired_date="2025-12-26",
    )
    return conn


@pytest.mark.integration
class TestGearWearAndAge:
    """Wear / age enrichment on the collectors (Issue #1209)."""

    def test_collect_activity_gear_includes_wear_and_age(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        result = collect_activity_gear(wear_conn, 2)

        assert result is not None
        assert result["km_on_gear"] == 552.5
        assert result["max_km"] == 643.7
        assert result["wear_pct"] == 85.8
        assert result["wear_status"] == "due_soon"
        assert result["since_date"] == "2025-12-26"
        assert result["age_status"] == "ok"
        assert result["is_retired"] is False
        assert result["replace_recommended"] is True

    def test_collect_activity_gear_wear_is_as_of_that_run(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Re-analyzing the earlier run reports the verdict that applied then."""
        earlier = collect_activity_gear(wear_conn, 1)

        assert earlier is not None
        assert earlier["km_on_gear"] == 300.0
        assert earlier["wear_pct"] == 46.6
        assert earlier["wear_status"] == "ok"
        assert earlier["replace_recommended"] is False

    def test_collect_activity_gear_separates_wear_across_one_model_name(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """The v15 must not inherit the v14's wear despite the shared name."""
        result = collect_activity_gear(wear_conn, 3)

        assert result is not None
        assert result["gear_label"] == "NB 1080 (v15)"
        assert result["max_km"] == 650.0
        assert result["wear_pct"] == 5.8
        assert result["wear_status"] == "ok"

    def test_collect_activity_gear_uses_latest_lifecycle_row(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Status comes from the shoe's newest row, so the flip is seen.

        Queried via the OLD row, which still says 'active'.
        """
        result = collect_activity_gear(wear_conn, 4)

        assert result is not None
        assert result["is_retired"] is True

    def test_collect_activity_gear_flags_age_and_over_wear(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """The retired pair trips both axes: 106.9% and 36 months."""
        result = collect_activity_gear(wear_conn, 5)

        assert result is not None
        assert result["wear_pct"] == 106.9
        assert result["wear_status"] == "over"
        assert result["age_months"] == 36
        assert result["age_status"] == "aged"
        assert result["replace_recommended"] is True

    def test_collect_activity_gear_null_wear_without_max(
        self, reader_db_path: Path
    ) -> None:
        """No limit recorded -> wear fields null, existing fields unchanged."""
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-10", 50.0, "Mystery Shoe", None, "u-my")

        result = collect_activity_gear(conn, 1)

        assert result is not None
        assert result["gear_model"] == "Mystery Shoe"
        assert result["km_on_gear"] == 50.0
        assert result["max_km"] is None
        assert result["wear_pct"] is None
        assert result["wear_status"] is None
        assert result["replace_recommended"] is False
        # A row predating the lifecycle columns is unknown, never "retired".
        assert result["is_retired"] is False

    def test_collect_week_gear_usage_includes_wear(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Weekly wear covers the shoe's whole life, not the window's mileage."""
        result = collect_week_gear_usage(wear_conn, "2026-09-06", "2026-09-12")

        by_label = {row["gear_label"]: row for row in result}
        assert by_label["NB 1080 (v14)"]["km"] == 252.5
        assert by_label["NB 1080 (v14)"]["km_on_gear_total"] == 552.5
        assert by_label["NB 1080 (v14)"]["wear_status"] == "due_soon"
        assert by_label["NB 1080 (v15)"]["wear_status"] == "ok"


@pytest.mark.integration
class TestCollectGearRoster:
    """Tests for collect_gear_roster() -- the alert surface (Issue #1209)."""

    def test_roster_excludes_retired_by_default(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        roster = collect_gear_roster(wear_conn, as_of="2026-09-16")

        assert [r["gear_label"] for r in roster] == [
            "NB 1080 (v14)",
            "NB 1080 (v15)",
        ]

    def test_roster_includes_retired_when_asked(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        roster = collect_gear_roster(
            wear_conn, include_retired=True, as_of="2026-09-16"
        )

        assert len(roster) == 3
        assert any(r["is_retired"] for r in roster)

    def test_roster_orders_by_wear_desc(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        roster = collect_gear_roster(
            wear_conn, include_retired=True, as_of="2026-09-16"
        )

        assert [r["wear_pct"] for r in roster] == [106.9, 85.8, 5.8]

    def test_roster_flags_replacement_and_carries_last_used(
        self, wear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        roster = collect_gear_roster(wear_conn, as_of="2026-09-16")
        v14 = roster[0]

        assert v14["replace_recommended"] is True
        assert v14["runs"] == 2
        assert v14["km"] == 552.5
        assert v14["last_used"] == "2026-09-06"
        assert v14["first_use_date"] == "2026-01-10"
        assert v14["gear_uuid"] == "u-v14"

    def test_roster_sorts_unknown_wear_last(self, reader_db_path: Path) -> None:
        """A shoe with no limit cannot be ranked, so it must not lead."""
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-10", 50.0, "Mystery Shoe", None, "u-my")
        _insert(
            conn,
            2,
            "2026-09-11",
            300.0,
            "Known Shoe",
            None,
            "u-kn",
            gear_max_km=643.7,
            gear_status="active",
        )

        roster = collect_gear_roster(conn, as_of="2026-09-16")

        assert [r["gear_label"] for r in roster] == ["Known Shoe", "Mystery Shoe"]
        assert roster[-1]["wear_pct"] is None

    def test_roster_empty_without_gear(self, reader_db_path: Path) -> None:
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-10", 50.0)

        assert collect_gear_roster(conn) == []
