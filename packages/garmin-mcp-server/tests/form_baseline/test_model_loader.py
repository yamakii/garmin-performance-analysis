"""Tests for form_baseline.model_loader module."""

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.form_baseline.model_loader import (
    load_models_from_db,
    load_models_from_file,
)
from garmin_mcp.form_baseline.trainer import GCTPowerModel, LinearModel


def _make_model_json() -> dict:
    """Create a valid model JSON structure."""
    return {
        "gct": {
            "alpha": 5.0,
            "d": -0.8,
            "rmse": 0.02,
            "n_samples": 100,
            "speed_range": {"min": 2.5, "max": 4.5},
        },
        "vo": {
            "a": 12.0,
            "b": -0.5,
            "rmse": 0.3,
            "n_samples": 100,
            "speed_range": {"min": 2.5, "max": 4.5},
        },
        "vr": {
            "a": 10.0,
            "b": -0.3,
            "rmse": 0.2,
            "n_samples": 100,
            "speed_range": {"min": 2.5, "max": 4.5},
        },
    }


def _create_baseline_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create form_baseline_history table for testing."""
    conn.execute("""
        CREATE TABLE form_baseline_history (
            user_id VARCHAR,
            condition_group VARCHAR,
            metric VARCHAR,
            period_start DATE,
            period_end DATE,
            coef_alpha DOUBLE,
            coef_d DOUBLE,
            coef_a DOUBLE,
            coef_b DOUBLE,
            n_samples INTEGER,
            rmse DOUBLE,
            speed_range_min DOUBLE,
            speed_range_max DOUBLE,
            model_type VARCHAR
        )
    """)


def _insert_baseline_row(
    conn: duckdb.DuckDBPyConnection,
    metric: str,
    period_end: str,
    *,
    user_id: str = "default",
    condition_group: str = "flat_road",
    alpha: float = 5.0,
    d: float = -0.8,
    a: float = 12.0,
    b: float = -0.5,
    rmse: float = 0.02,
    n_samples: int = 100,
    speed_min: float = 2.5,
    speed_max: float = 4.5,
    model_type: str = "linear",
    period_start: str = "2025-01-01",
) -> None:
    """Insert a single baseline row."""
    conn.execute(
        """
        INSERT INTO form_baseline_history
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            user_id,
            condition_group,
            metric,
            period_start,
            period_end,
            alpha,
            d,
            a,
            b,
            n_samples,
            rmse,
            speed_min,
            speed_max,
            model_type,
        ],
    )


# ============================================================
# Tests for load_models_from_file
# ============================================================


@pytest.mark.unit
class TestLoadModelsFromFileValid:
    """Test load_models_from_file with valid JSON."""

    def test_load_valid_json(self, tmp_path: Path) -> None:
        """Valid JSON should produce correct model types."""
        model_file = tmp_path / "models.json"
        model_file.write_text(json.dumps(_make_model_json()))

        result = load_models_from_file(Path(model_file))

        assert set(result.keys()) == {"gct", "vo", "vr"}
        assert isinstance(result["gct"], GCTPowerModel)
        assert isinstance(result["vo"], LinearModel)
        assert isinstance(result["vr"], LinearModel)

        # Verify specific values
        assert result["gct"].alpha == 5.0
        assert result["gct"].d == -0.8
        assert result["vo"].a == 12.0
        assert result["vo"].b == -0.5
        assert result["vr"].a == 10.0
        assert result["vr"].b == -0.3


@pytest.mark.unit
class TestLoadModelsFromFileNotFound:
    """Test load_models_from_file with non-existent file."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Non-existent path should raise FileNotFoundError."""
        bad_path = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError, match="Model file not found"):
            load_models_from_file(Path(bad_path))


@pytest.mark.unit
class TestLoadModelsFromFileInvalidStructure:
    """Test load_models_from_file with invalid JSON structure."""

    def test_invalid_structure(self, tmp_path: Path) -> None:
        """JSON missing required keys should raise KeyError."""
        model_file = tmp_path / "bad_models.json"
        # Missing 'gct' key entirely
        bad_data = {"vo": {"a": 1, "b": 2}, "vr": {"a": 1, "b": 2}}
        model_file.write_text(json.dumps(bad_data))

        with pytest.raises(KeyError):
            load_models_from_file(Path(model_file))


# ============================================================
# Tests for load_models_from_db
# ============================================================


@pytest.mark.integration
class TestLoadModelsFromDbBaselineExists:
    """Test load_models_from_db when baseline rows exist."""

    def test_baseline_exists(self, tmp_path: Path) -> None:
        """Should return 3 models when all baseline rows exist."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        _insert_baseline_row(conn, "gct", "2025-10-01")
        _insert_baseline_row(conn, "vo", "2025-10-01", a=11.0, b=-0.4)
        _insert_baseline_row(conn, "vr", "2025-10-01", a=9.0, b=-0.2)
        conn.close()

        result = load_models_from_db(db_path, "2025-10-15")

        assert set(result.keys()) == {"gct", "vo", "vr"}
        assert isinstance(result["gct"], GCTPowerModel)
        assert isinstance(result["vo"], LinearModel)
        assert isinstance(result["vr"], LinearModel)
        assert result["gct"].alpha == 5.0
        assert result["vo"].a == 11.0
        assert result["vr"].a == 9.0


@pytest.mark.integration
class TestLoadModelsFromDbNoBaseline:
    """Test load_models_from_db when no baseline exists."""

    def test_no_baseline_raises(self, tmp_path: Path) -> None:
        """Empty table should raise ValueError."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)
        conn.close()

        with pytest.raises(ValueError, match="No baseline found"):
            load_models_from_db(db_path, "2025-10-15")


@pytest.mark.integration
class TestLoadModelsFromDbIncompleteBaseline:
    """Test load_models_from_db when baseline is incomplete."""

    def test_incomplete_baseline_raises(self, tmp_path: Path) -> None:
        """Only gct row present should raise ValueError about incomplete data."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        # Insert only gct, missing vo and vr
        _insert_baseline_row(conn, "gct", "2025-10-01")
        conn.close()

        with pytest.raises(ValueError, match="Incomplete baseline data"):
            load_models_from_db(db_path, "2025-10-15")


@pytest.mark.integration
class TestLoadModelsFromDbDegenerateFlag:
    """Test load_models_from_db restores the degenerate (flat model) flag."""

    def test_load_models_from_db_restores_degenerate_flag(self, tmp_path: Path) -> None:
        """model_type='linear_flat' should come back as degenerate=True (#873)."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        _insert_baseline_row(conn, "gct", "2025-10-01", model_type="power")
        _insert_baseline_row(conn, "vo", "2025-10-01", a=11.0, b=-0.4)
        _insert_baseline_row(conn, "vr", "2025-10-01", a=9.0, b=-0.2)
        _insert_baseline_row(
            conn,
            "cadence",
            "2025-10-01",
            a=178.0,
            b=0.0,
            model_type="linear_flat",
        )
        conn.close()

        result = load_models_from_db(db_path, "2025-10-15")

        cadence = result["cadence"]
        assert isinstance(cadence, LinearModel)
        assert cadence.degenerate is True
        assert cadence.predict(3.33) == 178.0

        # Healthy 'linear' rows keep degenerate=False
        vo = result["vo"]
        assert isinstance(vo, LinearModel)
        assert vo.degenerate is False


@pytest.mark.integration
class TestLoadModelsFromDbSelectsLatest:
    """Test load_models_from_db selects the latest baseline."""

    def test_selects_latest_baseline(self, tmp_path: Path) -> None:
        """When multiple baselines exist, the latest period_end should be used."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        # Older baseline (period_end=2025-09-01) with alpha=3.0
        _insert_baseline_row(conn, "gct", "2025-09-01", alpha=3.0)
        _insert_baseline_row(conn, "vo", "2025-09-01", a=10.0, b=-0.3)
        _insert_baseline_row(conn, "vr", "2025-09-01", a=8.0, b=-0.1)

        # Newer baseline (period_end=2025-10-01) with alpha=5.0
        _insert_baseline_row(conn, "gct", "2025-10-01", alpha=5.0)
        _insert_baseline_row(conn, "vo", "2025-10-01", a=12.0, b=-0.5)
        _insert_baseline_row(conn, "vr", "2025-10-01", a=10.0, b=-0.3)

        conn.close()

        result = load_models_from_db(db_path, "2025-10-15")

        # Should use the newer baseline (period_end=2025-10-01)
        assert result["gct"].alpha == 5.0  # type: ignore[union-attr]
        assert result["vo"].a == 12.0  # type: ignore[union-attr]
        assert result["vr"].a == 10.0  # type: ignore[union-attr]

    def test_selects_covering_period_over_earlier_period(self, tmp_path: Path) -> None:
        """A baseline whose window contains the activity date wins (#1088).

        Reproduces the real 2026-09-09 case: an ended Jul-Aug window and a
        still-open Jul31-Sep30 window. The old ``period_end <= date`` rule
        could only ever pick the midsummer one.
        """
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        for metric, kwargs in (
            ("gct", {"alpha": 10.49}),
            ("vo", {"a": 4.45, "b": 1.17}),
            ("vr", {"a": 15.41, "b": -2.61}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-08-31",
                period_start="2026-07-01",
                **kwargs,  # type: ignore[arg-type]
            )

        for metric, kwargs in (
            ("gct", {"alpha": 13.42}),
            ("vo", {"a": 6.51, "b": 0.28}),
            ("vr", {"a": 16.85, "b": -3.25}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-09-30",
                period_start="2026-07-31",
                **kwargs,  # type: ignore[arg-type]
            )

        conn.close()

        result = load_models_from_db(db_path, "2026-09-09")

        assert result["gct"].alpha == 13.42  # type: ignore[union-attr]
        assert result["vo"].a == 6.51  # type: ignore[union-attr]
        assert result["vr"].a == 16.85  # type: ignore[union-attr]

    def test_falls_back_to_latest_ended_period_when_none_covers(
        self, tmp_path: Path
    ) -> None:
        """With no covering window, the newest ended one is used as before."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        for metric, kwargs in (
            ("gct", {"alpha": 3.0}),
            ("vo", {"a": 10.0, "b": -0.3}),
            ("vr", {"a": 8.0, "b": -0.1}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-06-30",
                period_start="2026-05-01",
                **kwargs,  # type: ignore[arg-type]
            )

        for metric, kwargs in (
            ("gct", {"alpha": 7.0}),
            ("vo", {"a": 12.0, "b": -0.5}),
            ("vr", {"a": 10.0, "b": -0.3}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-08-31",
                period_start="2026-07-01",
                **kwargs,  # type: ignore[arg-type]
            )

        conn.close()

        result = load_models_from_db(db_path, "2026-09-09")

        assert result["gct"].alpha == 7.0  # type: ignore[union-attr]

    def test_selects_most_recent_when_multiple_cover(self, tmp_path: Path) -> None:
        """Among covering windows, the most recent period_start wins."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        for metric, kwargs in (
            ("gct", {"alpha": 4.0}),
            ("vo", {"a": 10.0, "b": -0.3}),
            ("vr", {"a": 8.0, "b": -0.1}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-09-30",
                period_start="2026-06-01",
                **kwargs,  # type: ignore[arg-type]
            )

        for metric, kwargs in (
            ("gct", {"alpha": 9.0}),
            ("vo", {"a": 12.0, "b": -0.5}),
            ("vr", {"a": 10.0, "b": -0.3}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-09-30",
                period_start="2026-08-01",
                **kwargs,  # type: ignore[arg-type]
            )

        conn.close()

        result = load_models_from_db(db_path, "2026-09-09")

        assert result["gct"].alpha == 9.0  # type: ignore[union-attr]

    def test_ignores_power_window_when_selecting_period(self, tmp_path: Path) -> None:
        """The power baseline's own window must not drive the form-model pick.

        power is trained on a window whose period_start can differ by a day
        (2026-08-01 vs 2026-07-31). It used to win the covering sort and leave
        the loader with no form metrics at all (#1092).
        """
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        for metric, kwargs in (
            ("gct", {"alpha": 13.42}),
            ("vo", {"a": 6.51, "b": 0.28}),
            ("vr", {"a": 16.85, "b": -3.25}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-09-30",
                period_start="2026-07-31",
                **kwargs,  # type: ignore[arg-type]
            )
        _insert_baseline_row(
            conn, "power", "2026-09-30", period_start="2026-08-01", alpha=99.0
        )

        conn.close()

        result = load_models_from_db(db_path, "2026-09-09")

        assert set(result.keys()) == {"gct", "vo", "vr"}
        assert result["gct"].alpha == 13.42  # type: ignore[union-attr]

    def test_returns_consistent_period_pair_with_duplicate_period_end(
        self, tmp_path: Path
    ) -> None:
        """All returned models come from one and the same training window.

        Two windows share period_end 2026-02-28. Resolving period_start and
        period_end through separate scalar subqueries could pick different
        rows and match nothing (#1092).
        """
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_baseline_table(conn)

        for metric, kwargs in (
            ("gct", {"alpha": 1.0}),
            ("vo", {"a": 1.0, "b": -0.1}),
            ("vr", {"a": 1.0, "b": -0.1}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-02-28",
                period_start="2025-12-29",
                **kwargs,  # type: ignore[arg-type]
            )

        for metric, kwargs in (
            ("gct", {"alpha": 2.0}),
            ("vo", {"a": 2.0, "b": -0.2}),
            ("vr", {"a": 2.0, "b": -0.2}),
        ):
            _insert_baseline_row(
                conn,
                metric,
                "2026-02-28",
                period_start="2026-01-01",
                **kwargs,  # type: ignore[arg-type]
            )

        conn.close()

        result = load_models_from_db(db_path, "2026-02-15")

        assert set(result.keys()) == {"gct", "vo", "vr"}
        # Every model must come from the same window, not a mix of the two
        assert result["gct"].alpha == 2.0  # type: ignore[union-attr]
        assert result["vo"].a == 2.0  # type: ignore[union-attr]
        assert result["vr"].a == 2.0  # type: ignore[union-attr]
