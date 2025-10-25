"""Unit tests for splits loading and Mermaid data generation.

Tests the _load_splits() method and its integration with _generate_mermaid_data().
"""

from tools.reporting.report_generator_worker import ReportGeneratorWorker


class TestSplitsLoading:
    """Test suite for splits loading functionality."""

    def test_load_splits_success(self):
        """Test successful splits loading from DuckDB."""
        worker = ReportGeneratorWorker()
        splits = worker._load_splits(activity_id=20625808856)

        assert len(splits) == 7
        assert splits[0]["index"] == 1
        assert "pace_seconds_per_km" in splits[0]
        assert "heart_rate" in splits[0]
        assert splits[0]["pace_seconds_per_km"] > 0

    def test_load_splits_no_data(self):
        """Test graceful handling when no splits exist."""
        worker = ReportGeneratorWorker()
        splits = worker._load_splits(activity_id=99999999)

        assert splits == []

    def test_mermaid_data_generation(self):
        """Test mermaid data generation from splits."""
        worker = ReportGeneratorWorker()

        # Load real splits
        splits = worker._load_splits(activity_id=20625808856)
        mermaid_data = worker._generate_mermaid_data(splits)

        assert mermaid_data is not None
        assert len(mermaid_data["x_axis_labels"]) == 7
        assert len(mermaid_data["pace_data"]) == 7
        assert len(mermaid_data["heart_rate_data"]) == 7
        assert mermaid_data["pace_min"] > 0
        assert mermaid_data["pace_max"] > mermaid_data["pace_min"]

    def test_load_performance_data_includes_mermaid(self):
        """Test that load_performance_data includes mermaid_data."""
        worker = ReportGeneratorWorker()
        data = worker.load_performance_data(activity_id=20625808856)

        assert data is not None
        assert "splits" in data
        assert "mermaid_data" in data
        assert data["mermaid_data"] is not None
        assert "x_axis_labels" in data["mermaid_data"]
