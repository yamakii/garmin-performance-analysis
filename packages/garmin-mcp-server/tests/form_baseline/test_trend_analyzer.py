"""Tests for trend_analyzer module."""

from pathlib import Path

import pytest

from garmin_mcp.form_baseline.trend_analyzer import analyze_form_trend


@pytest.mark.unit
class TestAnalyzeFormTrend:
    """Test cases for analyze_form_trend function."""

    @pytest.mark.performance
    def test_analyze_form_trend_with_real_data(self, tmp_path):
        """Test trend analysis with real database (if available)."""
        db_path = Path.home() / "garmin_data/data/database/garmin_performance.duckdb"

        if not db_path.exists():
            pytest.skip("Real database not available")

        result = analyze_form_trend(
            db_path=str(db_path),
            activity_date="2025-10-25",
            comparison_months_back=3,
        )

        # Should have data available for recent months
        assert result["data_available"] is True
        assert result["current_period"] is not None
        assert result["past_period"] is not None
        assert result["interpretation_text"] != ""

        # Periods should be different
        assert result["current_period"] != result["past_period"]

        # Current period should end in 2025-10
        assert result["current_period"][1] == "2025-10-31"

        # Past period should end 3 months earlier (2025-07)
        assert result["past_period"][1] == "2025-07-31"

    def test_analyze_form_trend_with_mocked_data(self, mocker):
        """Test trend analysis with mocked database connection."""
        # Mock database connection
        mock_conn = mocker.MagicMock()

        # Mock current period data (Oct 2025: improved form)
        mock_conn.execute.return_value.fetchall.side_effect = [
            # First call: current period
            [
                ("2025-05-01", "2025-10-31", "gct", -3.0, None),
                ("2025-05-01", "2025-10-31", "vo", None, 0.7),
                ("2025-05-01", "2025-10-31", "vr", None, -2.0),
            ],
            # Second call: past period
            [
                ("2025-02-01", "2025-07-31", "gct", -2.8, None),
                ("2025-02-01", "2025-07-31", "vo", None, 0.8),
                ("2025-02-01", "2025-07-31", "vr", None, -2.2),
            ],
        ]

        mocker.patch("duckdb.connect", return_value=mock_conn)

        result = analyze_form_trend(
            db_path=":memory:",
            activity_date="2025-10-25",
            comparison_months_back=3,
        )

        assert result["data_available"] is True
        assert result["gct_improvement"] is True  # -3.0 - (-2.8) = -0.2 < -0.1 ✓
        assert result["vo_improvement"] is True  # 0.7 - 0.8 = -0.1 < -0.05 ✓
        assert (
            result["vr_improvement"] is False
        )  # -2.0 - (-2.2) = 0.2 > -0.1 (no improvement)

    def test_analyze_form_trend_no_current_data(self, mocker):
        """Test when current period has no data."""
        mock_conn = mocker.MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        mocker.patch("duckdb.connect", return_value=mock_conn)

        result = analyze_form_trend(
            db_path=":memory:",
            activity_date="2020-01-01",
            comparison_months_back=3,
        )

        assert result["data_available"] is False
        assert result["gct_improvement"] is None
        assert result["current_period"] is None
        assert "データ不足" in result["interpretation_text"]

    def test_analyze_form_trend_no_past_data(self, mocker):
        """Test when past period has no data."""
        mock_conn = mocker.MagicMock()

        # First call returns current data, second call returns empty
        mock_conn.execute.return_value.fetchall.side_effect = [
            [
                ("2025-05-01", "2025-10-31", "gct", -3.0, None),
                ("2025-05-01", "2025-10-31", "vo", None, 0.7),
                ("2025-05-01", "2025-10-31", "vr", None, -2.0),
            ],
            [],  # No past data
        ]

        mocker.patch("duckdb.connect", return_value=mock_conn)

        result = analyze_form_trend(
            db_path=":memory:",
            activity_date="2025-10-25",
            comparison_months_back=3,
        )

        assert result["data_available"] is False
        assert result["current_period"] == ("2025-05-01", "2025-10-31")
        assert result["past_period"] is None
        assert "3ヶ月前のデータがない" in result["interpretation_text"]

    def test_analyze_form_trend_invalid_date_format(self):
        """Test with invalid date format."""
        with pytest.raises(ValueError, match="Invalid activity_date format"):
            analyze_form_trend(
                db_path=":memory:",
                activity_date="2025/10/25",  # Wrong format
                comparison_months_back=3,
            )

    def test_analyze_form_trend_improvement_thresholds(self, mocker):
        """Test improvement threshold logic."""
        # Test borderline cases
        test_cases = [
            # (gct_delta_d, vo_delta_b, vr_delta_b, expected_gct, expected_vo, expected_vr)
            (-0.11, -0.06, -0.11, True, True, True),  # All improved (past threshold)
            (
                -0.09,
                -0.04,
                -0.09,
                False,
                False,
                False,
            ),  # None improved (below threshold)
            (
                -0.1,
                -0.05,
                -0.1,
                True,
                True,
                True,
            ),  # At threshold (floating point makes it slightly < threshold)
            (-0.15, 0.01, -0.05, True, False, False),  # Mixed
        ]

        for gct_d, vo_b, vr_b, exp_gct, exp_vo, exp_vr in test_cases:
            current_gct = -3.0
            current_vo = 0.7
            current_vr = -2.0

            past_gct = current_gct - gct_d
            past_vo = current_vo - vo_b
            past_vr = current_vr - vr_b

            # Create new mock for each test case
            mock_conn = mocker.MagicMock()
            mock_conn.execute.return_value.fetchall.side_effect = [
                [
                    ("2025-05-01", "2025-10-31", "gct", current_gct, None),
                    ("2025-05-01", "2025-10-31", "vo", None, current_vo),
                    ("2025-05-01", "2025-10-31", "vr", None, current_vr),
                ],
                [
                    ("2025-02-01", "2025-07-31", "gct", past_gct, None),
                    ("2025-02-01", "2025-07-31", "vo", None, past_vo),
                    ("2025-02-01", "2025-07-31", "vr", None, past_vr),
                ],
            ]

            mocker.patch("duckdb.connect", return_value=mock_conn)

            result = analyze_form_trend(
                db_path=":memory:",
                activity_date="2025-10-25",
                comparison_months_back=3,
            )

            assert result["gct_improvement"] == exp_gct, f"GCT failed for delta={gct_d}"
            assert result["vo_improvement"] == exp_vo, f"VO failed for delta={vo_b}"
            assert result["vr_improvement"] == exp_vr, f"VR failed for delta={vr_b}"


@pytest.mark.unit
class TestGenerateTrendInterpretation:
    """Test cases for trend interpretation text generation."""

    def test_interpretation_all_improved(self, mocker):
        """Test interpretation when all metrics improved."""
        mock_conn = mocker.MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [
                ("2025-05-01", "2025-10-31", "gct", -3.0, None),
                ("2025-05-01", "2025-10-31", "vo", None, 0.6),
                ("2025-05-01", "2025-10-31", "vr", None, -2.2),
            ],
            [
                ("2025-02-01", "2025-07-31", "gct", -2.8, None),
                ("2025-02-01", "2025-07-31", "vo", None, 0.7),
                ("2025-02-01", "2025-07-31", "vr", None, -2.0),
            ],
        ]

        mocker.patch("duckdb.connect", return_value=mock_conn)

        result = analyze_form_trend(
            db_path=":memory:",
            activity_date="2025-10-25",
            comparison_months_back=3,
        )

        # All three improved
        assert "接地時間" in result["interpretation_text"]
        assert "上下動" in result["interpretation_text"]
        assert "上下動比" in result["interpretation_text"]
        assert "進化" in result["interpretation_text"]

    def test_interpretation_one_improved(self, mocker):
        """Test interpretation when only one metric improved."""
        mock_conn = mocker.MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [
                ("2025-05-01", "2025-10-31", "gct", -3.0, None),
                ("2025-05-01", "2025-10-31", "vo", None, 0.7),
                ("2025-05-01", "2025-10-31", "vr", None, -2.0),
            ],
            [
                ("2025-02-01", "2025-07-31", "gct", -2.8, None),
                ("2025-02-01", "2025-07-31", "vo", None, 0.7),
                ("2025-02-01", "2025-07-31", "vr", None, -2.0),
            ],
        ]

        mocker.patch("duckdb.connect", return_value=mock_conn)

        result = analyze_form_trend(
            db_path=":memory:",
            activity_date="2025-10-25",
            comparison_months_back=3,
        )

        # Only GCT improved
        assert "接地時間が改善" in result["interpretation_text"]
        assert "進化" in result["interpretation_text"]

    def test_interpretation_stable(self, mocker):
        """Test interpretation when metrics are stable."""
        mock_conn = mocker.MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [
                ("2025-05-01", "2025-10-31", "gct", -2.8, None),
                ("2025-05-01", "2025-10-31", "vo", None, 0.7),
                ("2025-05-01", "2025-10-31", "vr", None, -2.0),
            ],
            [
                ("2025-02-01", "2025-07-31", "gct", -2.8, None),
                ("2025-02-01", "2025-07-31", "vo", None, 0.7),
                ("2025-02-01", "2025-07-31", "vr", None, -2.0),
            ],
        ]

        mocker.patch("duckdb.connect", return_value=mock_conn)

        result = analyze_form_trend(
            db_path=":memory:",
            activity_date="2025-10-25",
            comparison_months_back=3,
        )

        # No significant changes
        assert "同水準を維持" in result["interpretation_text"]

    def test_interpretation_deteriorated(self, mocker):
        """Test interpretation when metrics deteriorated."""
        mock_conn = mocker.MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [
                ("2025-05-01", "2025-10-31", "gct", -2.6, None),
                ("2025-05-01", "2025-10-31", "vo", None, 0.9),
                ("2025-05-01", "2025-10-31", "vr", None, -1.8),
            ],
            [
                ("2025-02-01", "2025-07-31", "gct", -2.8, None),
                ("2025-02-01", "2025-07-31", "vo", None, 0.7),
                ("2025-02-01", "2025-07-31", "vr", None, -2.0),
            ],
        ]

        mocker.patch("duckdb.connect", return_value=mock_conn)

        result = analyze_form_trend(
            db_path=":memory:",
            activity_date="2025-10-25",
            comparison_months_back=3,
        )

        # All deteriorated
        assert "悪化" in result["interpretation_text"]
        assert "見直し" in result["interpretation_text"]
