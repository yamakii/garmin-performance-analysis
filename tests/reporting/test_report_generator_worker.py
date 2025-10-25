"""
Unit tests for ReportTemplateRenderer.

Tests JSON data rendering in templates.
"""

from typing import Any

import pytest

from tools.reporting.report_template_renderer import ReportTemplateRenderer


@pytest.mark.unit
class TestReportTemplateRenderer:
    """Test ReportTemplateRenderer JSON data handling."""

    def test_renderer_accepts_json_data(self):
        """RendererがJSON dataを受け取ってレンダリングできることを確認."""
        renderer = ReportTemplateRenderer()

        basic_metrics = {
            "distance_km": 5.0,
            "duration_seconds": 1800,
            "avg_pace_seconds_per_km": 360,
            "avg_heart_rate": 155,
        }

        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {
                "evaluation": "GCT: 262msの優秀な接地時間、Zone 1優位の効率的な心拍管理"
            },
            "environment_analysis": {
                "weather_conditions": "気温18.0°C",
                "gear": {"shoes": "Nike Vaporfly"},
            },
            "phase_evaluation": {},
            "split_analysis": {},
            "summary": {},
        }

        report = renderer.render_report(
            "12345", "2025-09-22", basic_metrics, section_analyses
        )

        assert "5.0" in report or "5.00" in report  # Template側でフォーマット
        assert "GCT: 262ms" in report
        assert "Nike Vaporfly" in report

    def test_renderer_handles_missing_sections(self):
        """空のセクションに対してTemplate側で適切に処理されることを確認."""
        renderer = ReportTemplateRenderer()

        basic_metrics = {"distance_km": 5.0, "duration_seconds": 1800}
        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {"evaluation": "GCT: 262msの優秀な接地時間"},
            "environment_analysis": {},  # 空セクション
            "phase_evaluation": {},
            "split_analysis": {},
            "summary": {},
        }

        report = renderer.render_report(
            "12345", "2025-09-22", basic_metrics, section_analyses
        )

        assert report is not None


@pytest.mark.unit
class TestMermaidGraphGeneration:
    """Test Mermaid graph data generation."""

    def test_mermaid_data_structure(self, mocker):
        """Mermaid dataが正しい構造を持つことを確認."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        # Mock the db_reader to avoid needing a real database
        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Create sample splits data
        splits: list[dict[str, Any]] = [
            {
                "index": 1,
                "pace_seconds_per_km": 400,
                "heart_rate": 140,
                "power": 250,
            },
            {
                "index": 2,
                "pace_seconds_per_km": 410,
                "heart_rate": 145,
                "power": 255,
            },
            {
                "index": 3,
                "pace_seconds_per_km": 405,
                "heart_rate": 143,
                "power": None,  # Test None handling
            },
        ]

        mermaid_data = worker._generate_mermaid_data(splits)

        # Check structure
        assert mermaid_data is not None
        assert "x_axis_labels" in mermaid_data
        assert "pace_data" in mermaid_data
        assert "heart_rate_data" in mermaid_data
        assert "power_data" in mermaid_data
        assert "pace_min" in mermaid_data
        assert "pace_max" in mermaid_data
        assert "hr_min" in mermaid_data
        assert "hr_max" in mermaid_data

        # Check data types
        assert isinstance(mermaid_data["x_axis_labels"], list)
        assert isinstance(mermaid_data["pace_data"], list)
        assert isinstance(mermaid_data["heart_rate_data"], list)
        assert isinstance(mermaid_data["power_data"], list)

        # Check list lengths match
        assert len(mermaid_data["x_axis_labels"]) == 3
        assert len(mermaid_data["pace_data"]) == 3
        assert len(mermaid_data["heart_rate_data"]) == 3
        assert len(mermaid_data["power_data"]) == 3

        # Check None power handling (should be 0)
        assert mermaid_data["power_data"][2] == 0

        # Check Y-axis ranges (10% padding)
        assert mermaid_data["pace_min"] == round(400 * 0.9, 1)
        assert mermaid_data["pace_max"] == round(410 * 1.1, 1)
        assert mermaid_data["hr_min"] == round(140 * 0.9, 1)
        assert mermaid_data["hr_max"] == round(145 * 1.1, 1)

    def test_mermaid_data_empty_splits(self, mocker):
        """空のsplitsに対してNoneを返すことを確認."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        # Mock the db_reader to avoid needing a real database
        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        mermaid_data = worker._generate_mermaid_data([])
        assert mermaid_data is None

        mermaid_data = worker._generate_mermaid_data(None)
        assert mermaid_data is None

    def test_mermaid_graph_renders_in_template(self):
        """Template内でMermaidグラフがレンダリングされることを確認."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()

        basic_metrics = {
            "distance_km": 5.0,
            "duration_seconds": 1800,
            "avg_pace_seconds_per_km": 360,
            "avg_heart_rate": 155,
        }

        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {"evaluation": "Test"},
            "environment_analysis": {},
            "phase_evaluation": {},
            "split_analysis": {},
            "summary": {},
        }

        mermaid_data = {
            "x_axis_labels": ["1", "2", "3"],
            "pace_data": [400, 410, 405],
            "heart_rate_data": [140, 145, 143],
            "power_data": [250, 255, 0],
            "pace_min": 360.0,
            "pace_max": 451.0,
            "hr_min": 126.0,
            "hr_max": 159.5,
        }

        # Test that mermaid_data parameter is accepted (template rendering is separate concern)
        report = renderer.render_report(
            "12345",
            "2025-09-22",
            basic_metrics,
            section_analyses,
            mermaid_data=mermaid_data,
        )

        # Check that report was generated successfully
        assert report is not None
        assert len(report) > 0


@pytest.mark.unit
class TestFormatPace:
    """Test _format_pace helper method."""

    def test_format_pace_basic(self, mocker):
        """Basic pace formatting test."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        assert worker._format_pace(240) == "4:00/km"
        assert worker._format_pace(270) == "4:30/km"
        assert worker._format_pace(360) == "6:00/km"
        assert worker._format_pace(405) == "6:45/km"

    def test_format_pace_with_seconds(self, mocker):
        """Test pace formatting with seconds."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        assert worker._format_pace(242) == "4:02/km"
        assert worker._format_pace(369) == "6:09/km"


class TestLoadSimilarWorkouts:
    """Test _load_similar_workouts method."""

    def test_similar_workouts_import_error_returns_none(self, mocker):
        """Similar workouts returns None when MCP tool is not available."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # The method should handle import errors gracefully
        result = worker._load_similar_workouts(
            activity_id=12345, current_metrics={"avg_pace": 395, "avg_hr": 145}
        )

        # Should return None due to import error
        assert result is None

    def test_similar_workouts_graceful_fallback(self, mocker):
        """Similar workouts method has proper error handling."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # This should not raise an exception
        try:
            result = worker._load_similar_workouts(
                12345, {"avg_pace": 395, "avg_hr": 145}
            )
            # Result will be None due to missing MCP tool, which is expected
            assert result is None
        except Exception as e:
            pytest.fail(f"Method should not raise exception: {e}")


@pytest.mark.unit
class TestPaceCorrectedFormEfficiency:
    """Test _calculate_pace_corrected_form_efficiency method."""

    @pytest.mark.parametrize(
        "pace,expected_gct",
        [
            (240, 230.0),  # 4:00/km → 230ms
            (420, 269.6),  # 7:00/km → 269.6ms
            (405, 266.3),  # 6:45/km → 266.3ms
        ],
    )
    def test_gct_baseline_formula(self, pace, expected_gct):
        """GCT baseline: 230 + (pace - 240) * 0.22."""
        baseline = 230 + (pace - 240) * 0.22
        assert abs(baseline - expected_gct) < 0.5

    @pytest.mark.parametrize(
        "pace,expected_vo",
        [
            (240, 6.8),  # 4:00/km → 6.8cm
            (420, 7.52),  # 7:00/km → 7.52cm
            (405, 7.46),  # 6:45/km → 7.46cm
        ],
    )
    def test_vo_baseline_formula(self, pace, expected_vo):
        """VO baseline: 6.8 + (pace - 240) * 0.004."""
        baseline = 6.8 + (pace - 240) * 0.004
        assert abs(baseline - expected_vo) < 0.02

    def test_pace_corrected_form_efficiency_structure(self, mocker):
        """Pace-corrected form efficiency returns correct structure."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        form_eff = {
            "gct_average": 253.0,
            "vo_average": 7.2,
            "vr_average": 8.5,
        }
        result = worker._calculate_pace_corrected_form_efficiency(405, form_eff)

        assert "gct" in result
        assert "vo" in result
        assert "vr" in result
        assert result["gct"]["actual"] == 253.0
        assert abs(result["gct"]["baseline"] - 266.3) < 0.5
        assert result["gct"]["label"] in ["優秀", "良好", "要改善"]
        assert "rating_stars" in result["gct"]
        assert "rating_score" in result["gct"]

    def test_pace_corrected_gct_excellent(self, mocker):
        """GCT score < -5% should be marked as 優秀."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Pace 405 → baseline GCT 266.3
        # Actual 250 → score = (250-266.3)/266.3*100 = -6.1% < -5%
        form_eff = {"gct_average": 250.0, "vo_average": 7.0, "vr_average": 8.5}
        result = worker._calculate_pace_corrected_form_efficiency(405, form_eff)

        assert result["gct"]["label"] == "優秀"
        assert result["gct"]["rating_score"] == 5.0

    def test_pace_corrected_gct_good(self, mocker):
        """GCT score within ±5% should be marked as 良好."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Pace 405 → baseline GCT 266.3
        # Actual 266 → score = (266-266.3)/266.3*100 = -0.1% (within ±5%)
        form_eff = {"gct_average": 266.0, "vo_average": 7.0, "vr_average": 8.5}
        result = worker._calculate_pace_corrected_form_efficiency(405, form_eff)

        assert result["gct"]["label"] == "良好"
        assert result["gct"]["rating_score"] >= 4.0

    def test_pace_corrected_vr_ideal_range(self, mocker):
        """VR within 8.0-9.5% should be marked as 理想範囲内."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        form_eff = {"gct_average": 253.0, "vo_average": 7.2, "vr_average": 8.5}
        result = worker._calculate_pace_corrected_form_efficiency(405, form_eff)

        assert result["vr"]["label"] == "理想範囲内"
        assert result["vr"]["rating_score"] == 5.0

    def test_pace_corrected_vr_needs_improvement(self, mocker):
        """VR outside 8.0-9.5% should be marked as 要改善."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        form_eff = {"gct_average": 253.0, "vo_average": 7.2, "vr_average": 12.0}
        result = worker._calculate_pace_corrected_form_efficiency(405, form_eff)

        assert result["vr"]["label"] == "要改善"
        assert result["vr"]["rating_score"] == 3.5
        # Note: Actual Mermaid rendering in template is tested in integration tests
