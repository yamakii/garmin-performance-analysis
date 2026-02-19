"""Tests for PhysiologyHandler."""

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.physiology_handler import PhysiologyHandler

# ---------------------------------------------------------------------------
# handles() tests
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = [
    "get_form_efficiency_summary",
    "get_form_evaluations",
    "get_form_baseline_trend",
    "get_hr_efficiency_analysis",
    "get_heart_rate_zones_detail",
    "get_vo2_max_data",
    "get_lactate_threshold_data",
]


@pytest.mark.unit
class TestHandles:
    """Test PhysiologyHandler.handles() for each known tool and unknown names."""

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_handles_known_tools(
        self, mock_db_reader: MagicMock, tool_name: str
    ) -> None:
        handler = PhysiologyHandler(mock_db_reader)
        assert handler.handles(tool_name) is True

    @pytest.mark.parametrize(
        "tool_name",
        ["unknown_tool", "get_splits_pace_hr", "get_performance_trends", ""],
    )
    def test_handles_unknown_tools(
        self, mock_db_reader: MagicMock, tool_name: str
    ) -> None:
        handler = PhysiologyHandler(mock_db_reader)
        assert handler.handles(tool_name) is False


# ---------------------------------------------------------------------------
# Simple method tests (6 methods, all same db_reader delegation pattern)
# ---------------------------------------------------------------------------

SIMPLE_METHODS = [
    ("get_form_efficiency_summary", "get_form_efficiency_summary"),
    ("get_form_evaluations", "get_form_evaluations"),
    ("get_hr_efficiency_analysis", "get_hr_efficiency_analysis"),
    ("get_heart_rate_zones_detail", "get_heart_rate_zones_detail"),
    ("get_vo2_max_data", "get_vo2_max_data"),
    ("get_lactate_threshold_data", "get_lactate_threshold_data"),
]

SAMPLE_DATA = {
    "get_form_efficiency_summary": {
        "activity_id": 12345,
        "gct_mean": 245.3,
        "vo_mean": 8.2,
        "vr_mean": 7.1,
    },
    "get_form_evaluations": {
        "activity_id": 12345,
        "evaluations": [
            {"metric": "GCT", "score": 4, "stars": "****"},
        ],
    },
    "get_hr_efficiency_analysis": {
        "activity_id": 12345,
        "training_type": "base_run",
        "zone_distribution": {"zone1": 10, "zone2": 50, "zone3": 30},
    },
    "get_heart_rate_zones_detail": {
        "activity_id": 12345,
        "zones": [
            {"zone": 1, "low": 100, "high": 130, "time_seconds": 120},
        ],
    },
    "get_vo2_max_data": {
        "activity_id": 12345,
        "vo2_max": 52.3,
        "fitness_age": 28,
        "category": "Excellent",
    },
    "get_lactate_threshold_data": {
        "activity_id": 12345,
        "lt_heart_rate": 168,
        "lt_speed": 3.8,
        "lt_power": 320,
    },
}


@pytest.mark.unit
class TestSimpleMethods:
    """Test the 6 simple delegation methods that call db_reader and return JSON."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,reader_method", SIMPLE_METHODS)
    async def test_returns_data(
        self,
        mock_db_reader: MagicMock,
        tool_name: str,
        reader_method: str,
    ) -> None:
        expected = SAMPLE_DATA[tool_name]
        getattr(mock_db_reader, reader_method).return_value = expected

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle(tool_name, {"activity_id": 12345})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed == expected
        getattr(mock_db_reader, reader_method).assert_called_once_with(12345)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,reader_method", SIMPLE_METHODS)
    async def test_returns_none(
        self,
        mock_db_reader: MagicMock,
        tool_name: str,
        reader_method: str,
    ) -> None:
        getattr(mock_db_reader, reader_method).return_value = None

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle(tool_name, {"activity_id": 99999})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,reader_method", SIMPLE_METHODS)
    async def test_returns_empty_dict(
        self,
        mock_db_reader: MagicMock,
        tool_name: str,
        reader_method: str,
    ) -> None:
        getattr(mock_db_reader, reader_method).return_value = {}

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle(tool_name, {"activity_id": 12345})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed == {}


@pytest.mark.unit
class TestUnknownTool:
    """Test that an unknown tool name raises ValueError."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self, mock_db_reader: MagicMock) -> None:
        handler = PhysiologyHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {"activity_id": 1})


# ---------------------------------------------------------------------------
# _get_form_baseline_trend tests (complex, direct DuckDB queries)
# ---------------------------------------------------------------------------


def _make_mock_conn(mocker: pytest.fixture, side_effects: list) -> MagicMock:
    """Create a mock duckdb connection with sequential execute().fetchall() results.

    Args:
        mocker: pytest-mock mocker fixture.
        side_effects: List of return values for successive fetchall() calls.

    Returns:
        The patched duckdb.connect mock.
    """
    mock_conn = MagicMock()

    # Build chained execute().fetchall() side effects
    mock_results = []
    for data in side_effects:
        mock_result = MagicMock()
        mock_result.fetchall.return_value = data
        mock_results.append(mock_result)

    mock_conn.execute.side_effect = mock_results

    # duckdb is imported locally inside _get_form_baseline_trend,
    # so we patch the top-level duckdb module's connect function.
    mocker.patch("duckdb.connect", return_value=mock_conn)
    return mock_conn


@pytest.mark.unit
class TestFormBaselineTrend:
    """Test _get_form_baseline_trend with mocked DuckDB connection."""

    BASE_ARGS = {
        "activity_id": 12345,
        "activity_date": "2025-10-15",
    }

    CURRENT_BASELINES = [
        # (metric, coef_d, coef_b, period_start, period_end)
        ("GCT", -0.15, 260.0, "2025-10-01", "2025-10-31"),
        ("VO", 0.02, 8.0, "2025-10-01", "2025-10-31"),
        ("VR", 0.01, 7.0, "2025-10-01", "2025-10-31"),
    ]

    PREVIOUS_BASELINES = [
        ("GCT", -0.12, 265.0, "2025-09-01", "2025-09-30"),
        ("VO", 0.025, 8.5, "2025-09-01", "2025-09-30"),
        ("VR", 0.015, 7.5, "2025-09-01", "2025-09-30"),
    ]

    @pytest.mark.asyncio
    async def test_success_both_periods(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/fake/db.duckdb"
        _make_mock_conn(mocker, [self.CURRENT_BASELINES, self.PREVIOUS_BASELINES])

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle("get_form_baseline_trend", self.BASE_ARGS)

        parsed = json.loads(result[0].text)
        assert parsed["success"] is True
        assert parsed["activity_id"] == 12345
        assert parsed["activity_date"] == "2025-10-15"

        metrics = parsed["metrics"]
        assert "GCT" in metrics
        assert "VO" in metrics
        assert "VR" in metrics

        # Verify GCT deltas
        gct = metrics["GCT"]
        assert gct["current"]["coef_d"] == -0.15
        assert gct["current"]["coef_b"] == 260.0
        assert gct["previous"]["coef_d"] == -0.12
        assert gct["previous"]["coef_b"] == 265.0
        assert gct["delta_d"] == pytest.approx(-0.15 - (-0.12))
        assert gct["delta_b"] == pytest.approx(260.0 - 265.0)

    @pytest.mark.asyncio
    async def test_no_current_baseline(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/fake/db.duckdb"
        _make_mock_conn(mocker, [[]])  # Empty current baselines

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle("get_form_baseline_trend", self.BASE_ARGS)

        parsed = json.loads(result[0].text)
        assert parsed["success"] is False
        assert "No baseline found" in parsed["error"]

    @pytest.mark.asyncio
    async def test_no_previous_baseline(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/fake/db.duckdb"
        _make_mock_conn(mocker, [self.CURRENT_BASELINES, []])

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle("get_form_baseline_trend", self.BASE_ARGS)

        parsed = json.loads(result[0].text)
        assert parsed["success"] is False
        assert "No previous baseline found" in parsed["error"]

    @pytest.mark.asyncio
    async def test_exception_handling(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/fake/db.duckdb"
        mocker.patch(
            "duckdb.connect",
            side_effect=RuntimeError("DB connection failed"),
        )

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle("get_form_baseline_trend", self.BASE_ARGS)

        parsed = json.loads(result[0].text)
        assert parsed["success"] is False
        assert "DB connection failed" in parsed["error"]

    @pytest.mark.asyncio
    async def test_custom_user_id_and_condition_group(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/fake/db.duckdb"
        mock_conn = _make_mock_conn(
            mocker, [self.CURRENT_BASELINES, self.PREVIOUS_BASELINES]
        )

        args = {
            **self.BASE_ARGS,
            "user_id": "runner1",
            "condition_group": "hilly",
        }

        handler = PhysiologyHandler(mock_db_reader)
        await handler.handle("get_form_baseline_trend", args)

        # Verify the first execute call used custom user_id and condition_group
        first_call_args = mock_conn.execute.call_args_list[0]
        params = first_call_args[0][1]
        assert params[0] == "runner1"
        assert params[1] == "hilly"

    @pytest.mark.asyncio
    async def test_default_user_id_and_condition_group(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/fake/db.duckdb"
        mock_conn = _make_mock_conn(
            mocker, [self.CURRENT_BASELINES, self.PREVIOUS_BASELINES]
        )

        handler = PhysiologyHandler(mock_db_reader)
        await handler.handle("get_form_baseline_trend", self.BASE_ARGS)

        # Verify defaults: user_id="default", condition_group="flat_road"
        first_call_args = mock_conn.execute.call_args_list[0]
        params = first_call_args[0][1]
        assert params[0] == "default"
        assert params[1] == "flat_road"

    @pytest.mark.asyncio
    async def test_delta_with_none_coef(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        """When coef_d or coef_b is None, deltas should not be computed."""
        mock_db_reader.db_path = "/fake/db.duckdb"
        current = [("GCT", None, 260.0, "2025-10-01", "2025-10-31")]
        previous = [("GCT", -0.12, 265.0, "2025-09-01", "2025-09-30")]
        _make_mock_conn(mocker, [current, previous])

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle("get_form_baseline_trend", self.BASE_ARGS)

        parsed = json.loads(result[0].text)
        assert parsed["success"] is True
        gct = parsed["metrics"]["GCT"]
        # delta_d should not be present because current coef_d is None
        assert "delta_d" not in gct
        # delta_b should still be computed
        assert gct["delta_b"] == pytest.approx(260.0 - 265.0)

    @pytest.mark.asyncio
    async def test_metric_in_current_but_not_previous(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        """Metrics that exist in current but not previous should have no 'previous' or deltas."""
        mock_db_reader.db_path = "/fake/db.duckdb"
        current = [
            ("GCT", -0.15, 260.0, "2025-10-01", "2025-10-31"),
            ("NEW_METRIC", 0.5, 100.0, "2025-10-01", "2025-10-31"),
        ]
        previous = [("GCT", -0.12, 265.0, "2025-09-01", "2025-09-30")]
        _make_mock_conn(mocker, [current, previous])

        handler = PhysiologyHandler(mock_db_reader)
        result = await handler.handle("get_form_baseline_trend", self.BASE_ARGS)

        parsed = json.loads(result[0].text)
        assert parsed["success"] is True
        # NEW_METRIC should have current but no previous or deltas
        nm = parsed["metrics"]["NEW_METRIC"]
        assert "current" in nm
        assert "previous" not in nm
        assert "delta_d" not in nm
