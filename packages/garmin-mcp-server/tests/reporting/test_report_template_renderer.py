"""
Unit tests for ReportTemplateRenderer filter methods and path generation.

Tests _sort_splits_filter, _format_intensity_type_filter, and get_final_report_path.
Star rating filter tests are in test_report_generator_worker.py (TestExtractStarRating).
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from garmin_mcp.reporting.report_template_renderer import ReportTemplateRenderer


@pytest.mark.unit
class TestSortSplitsFilter:
    """Test _sort_splits_filter template filter."""

    def test_sorts_by_numeric_split_number(self) -> None:
        """Splits are sorted numerically, not lexicographically."""
        renderer = ReportTemplateRenderer()
        sort_splits = renderer.env.filters["sort_splits"]

        items = [
            ("split_12", {"pace": 400}),
            ("split_3", {"pace": 350}),
            ("split_1", {"pace": 380}),
            ("split_20", {"pace": 410}),
        ]

        result = sort_splits(items)

        assert [item[0] for item in result] == [
            "split_1",
            "split_3",
            "split_12",
            "split_20",
        ]

    def test_single_split(self) -> None:
        """Single split returns unchanged."""
        renderer = ReportTemplateRenderer()
        sort_splits = renderer.env.filters["sort_splits"]

        items = [("split_5", {"pace": 400})]
        result = sort_splits(items)

        assert len(result) == 1
        assert result[0][0] == "split_5"

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        renderer = ReportTemplateRenderer()
        sort_splits = renderer.env.filters["sort_splits"]

        result = sort_splits([])
        assert result == []

    def test_already_sorted(self) -> None:
        """Already sorted list remains in order."""
        renderer = ReportTemplateRenderer()
        sort_splits = renderer.env.filters["sort_splits"]

        items = [
            ("split_1", {"pace": 380}),
            ("split_2", {"pace": 390}),
            ("split_3", {"pace": 400}),
        ]

        result = sort_splits(items)

        assert [item[0] for item in result] == ["split_1", "split_2", "split_3"]

    def test_non_split_keys_sort_to_front(self) -> None:
        """Non-split keys get sort key 0 and appear before numbered splits."""
        renderer = ReportTemplateRenderer()
        sort_splits = renderer.env.filters["sort_splits"]

        items = [
            ("split_2", {"pace": 390}),
            ("summary", {"total": 100}),
            ("split_1", {"pace": 380}),
        ]

        result = sort_splits(items)

        assert result[0][0] == "summary"
        assert result[1][0] == "split_1"
        assert result[2][0] == "split_2"

    def test_preserves_values(self) -> None:
        """Sort preserves the associated values."""
        renderer = ReportTemplateRenderer()
        sort_splits = renderer.env.filters["sort_splits"]

        items = [
            ("split_3", {"pace": 400, "hr": 160}),
            ("split_1", {"pace": 380, "hr": 150}),
        ]

        result = sort_splits(items)

        assert result[0] == ("split_1", {"pace": 380, "hr": 150})
        assert result[1] == ("split_3", {"pace": 400, "hr": 160})

    def test_malformed_split_key(self) -> None:
        """Malformed split key (e.g., 'split_') gets sort key 0."""
        renderer = ReportTemplateRenderer()
        sort_splits = renderer.env.filters["sort_splits"]

        items = [
            ("split_2", {"pace": 390}),
            ("split_", {"pace": 0}),
            ("split_1", {"pace": 380}),
        ]

        result = sort_splits(items)

        # "split_" cannot parse number, gets 0
        assert result[0][0] == "split_"
        assert result[1][0] == "split_1"
        assert result[2][0] == "split_2"


@pytest.mark.unit
class TestFormatIntensityTypeFilter:
    """Test _format_intensity_type_filter template filter."""

    def test_warmup_returns_w_up(self) -> None:
        """Warmup intensity type returns 'W-up'."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [{"index": 1, "intensity_type": "warmup"}]
        assert fmt(splits, 1) == "W-up"

    def test_cooldown_returns_c_down(self) -> None:
        """Cooldown intensity type returns 'C-down'."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [{"index": 5, "intensity_type": "cooldown"}]
        assert fmt(splits, 5) == "C-down"

    def test_active_splits_numbered_sequentially(self) -> None:
        """Active splits are numbered W1, W2, W3, etc."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [
            {"index": 1, "intensity_type": "warmup"},
            {"index": 2, "intensity_type": "active"},
            {"index": 3, "intensity_type": "rest"},
            {"index": 4, "intensity_type": "active"},
            {"index": 5, "intensity_type": "rest"},
            {"index": 6, "intensity_type": "active"},
            {"index": 7, "intensity_type": "cooldown"},
        ]

        assert fmt(splits, 2) == "W1"
        assert fmt(splits, 4) == "W2"
        assert fmt(splits, 6) == "W3"

    def test_rest_splits_numbered_sequentially(self) -> None:
        """Rest splits are numbered R1, R2, etc."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [
            {"index": 1, "intensity_type": "warmup"},
            {"index": 2, "intensity_type": "active"},
            {"index": 3, "intensity_type": "rest"},
            {"index": 4, "intensity_type": "active"},
            {"index": 5, "intensity_type": "rest"},
            {"index": 6, "intensity_type": "cooldown"},
        ]

        assert fmt(splits, 3) == "R1"
        assert fmt(splits, 5) == "R2"

    def test_index_not_found_returns_na(self) -> None:
        """Non-existent index returns 'N/A'."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [{"index": 1, "intensity_type": "warmup"}]
        assert fmt(splits, 99) == "N/A"

    def test_empty_splits_returns_na(self) -> None:
        """Empty splits list returns 'N/A'."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        assert fmt([], 1) == "N/A"

    def test_missing_intensity_type_returns_na(self) -> None:
        """Split without intensity_type returns 'N/A'."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [{"index": 1}]
        assert fmt(splits, 1) == "N/A"

    def test_unknown_intensity_type_returns_raw(self) -> None:
        """Unknown intensity type returns the raw value."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [{"index": 1, "intensity_type": "other_type"}]
        assert fmt(splits, 1) == "other_type"

    def test_full_interval_workout(self) -> None:
        """Full interval workout with warmup, 3x work/rest, cooldown."""
        renderer = ReportTemplateRenderer()
        fmt = renderer.env.filters["format_intensity_type"]

        splits = [
            {"index": 1, "intensity_type": "warmup"},
            {"index": 2, "intensity_type": "active"},
            {"index": 3, "intensity_type": "rest"},
            {"index": 4, "intensity_type": "active"},
            {"index": 5, "intensity_type": "rest"},
            {"index": 6, "intensity_type": "active"},
            {"index": 7, "intensity_type": "rest"},
            {"index": 8, "intensity_type": "cooldown"},
        ]

        expected = ["W-up", "W1", "R1", "W2", "R2", "W3", "R3", "C-down"]
        for i, exp in enumerate(expected, start=1):
            assert fmt(splits, i) == exp, f"Split index {i}: expected {exp}"


@pytest.mark.unit
class TestGetFinalReportPath:
    """Test get_final_report_path method."""

    @patch("garmin_mcp.utils.paths.get_result_dir")
    def test_path_structure(self, mock_get_result_dir: Any) -> None:
        """Report path follows {result_dir}/individual/{YYYY}/{MM}/{date}_activity_{id}.md."""
        mock_get_result_dir.return_value = Path("/tmp/test_results")
        renderer = ReportTemplateRenderer()
        path = renderer.get_final_report_path("12345", "2025-10-15")

        assert path == Path(
            "/tmp/test_results/individual/2025/10/2025-10-15_activity_12345.md"
        )

    @patch("garmin_mcp.utils.paths.get_result_dir")
    def test_returns_path_object(self, mock_get_result_dir: Any) -> None:
        """Return type is a Path object."""
        mock_get_result_dir.return_value = Path("/tmp/test_results")
        renderer = ReportTemplateRenderer()
        path = renderer.get_final_report_path("99999", "2026-01-05")

        assert isinstance(path, Path)

    @patch("garmin_mcp.utils.paths.get_result_dir")
    def test_year_month_extraction(self, mock_get_result_dir: Any) -> None:
        """Year and month are correctly extracted from the date string."""
        mock_get_result_dir.return_value = Path("/tmp/results")
        renderer = ReportTemplateRenderer()
        path = renderer.get_final_report_path("11111", "2024-03-28")

        assert path.parts[-3] == "2024"
        assert path.parts[-2] == "03"

    @patch("garmin_mcp.utils.paths.get_result_dir")
    def test_filename_format(self, mock_get_result_dir: Any) -> None:
        """Filename follows {date}_activity_{id}.md format."""
        mock_get_result_dir.return_value = Path("/tmp/results")
        renderer = ReportTemplateRenderer()
        path = renderer.get_final_report_path("20594901208", "2025-10-05")

        assert path.name == "2025-10-05_activity_20594901208.md"
        assert path.suffix == ".md"
