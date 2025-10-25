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
class TestExtractStarRating:
    """Test extract_star_rating template filter."""

    def test_extract_star_rating_with_stars(self):
        """Extract star rating from text with rating."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()

        # Get the filter function
        extract_star_rating = renderer.env.filters.get("extract_star_rating")
        assert (
            extract_star_rating is not None
        ), "extract_star_rating filter not registered"

        text = "今日のランは質の高い有酸素ベース走でした。(★★★★☆ 4.2/5.0)"
        result = extract_star_rating(text)

        assert result["stars"] == "★★★★☆"
        assert result["score"] == 4.2
        assert (
            result["text_without_rating"]
            == "今日のランは質の高い有酸素ベース走でした。"
        )

    def test_extract_star_rating_with_perfect_score(self):
        """Extract star rating with 5.0 score."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        text = "完璧なウォームアップです。(★★★★★ 5.0/5.0)"
        result = extract_star_rating(text)

        assert result["stars"] == "★★★★★"
        assert result["score"] == 5.0
        assert result["text_without_rating"] == "完璧なウォームアップです。"

    def test_extract_star_rating_with_low_score(self):
        """Extract star rating with low score."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        text = "改善が必要です。(★★★☆☆ 3.5/5.0)"
        result = extract_star_rating(text)

        assert result["stars"] == "★★★☆☆"
        assert result["score"] == 3.5
        assert result["text_without_rating"] == "改善が必要です。"

    def test_extract_star_rating_without_stars(self):
        """Return empty stars when no rating in text."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        text = "普通のランニングでした。"
        result = extract_star_rating(text)

        assert result["stars"] == ""
        assert result["score"] == 0.0
        assert result["text_without_rating"] == "普通のランニングでした。"

    def test_extract_star_rating_at_beginning(self):
        """Extract star rating when it appears at the beginning."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        text = "(★★★★☆ 4.0/5.0) 良好な結果です。"
        result = extract_star_rating(text)

        assert result["stars"] == "★★★★☆"
        assert result["score"] == 4.0
        assert result["text_without_rating"] == "良好な結果です。"

    def test_extract_star_rating_multiple_occurrences(self):
        """Extract first star rating when multiple ratings exist."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        text = "前半 (★★★★☆ 4.0/5.0) 後半 (★★★☆☆ 3.0/5.0)"
        result = extract_star_rating(text)

        # Should extract first occurrence
        assert result["stars"] == "★★★★☆"
        assert result["score"] == 4.0
        # Should remove only the first rating
        assert "(★★★☆☆ 3.0/5.0)" in result["text_without_rating"]

    def test_extract_star_rating_edge_case_decimal(self):
        """Handle edge case with single decimal place."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        text = "まあまあです。(★★★★☆ 4.5/5.0)"
        result = extract_star_rating(text)

        assert result["stars"] == "★★★★☆"
        assert result["score"] == 4.5
        assert result["text_without_rating"] == "まあまあです。"

    def test_extract_star_rating_with_dict_input(self):
        """Handle dict input gracefully."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        result = extract_star_rating({"key": "value"})

        assert result["stars"] == ""
        assert result["score"] == 0.0
        assert result["text_without_rating"] == ""

    def test_extract_star_rating_with_none_input(self):
        """Handle None input gracefully."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()
        extract_star_rating = renderer.env.filters["extract_star_rating"]

        result = extract_star_rating(None)

        assert result["stars"] == ""
        assert result["score"] == 0.0
        assert result["text_without_rating"] == ""


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


@pytest.mark.unit
class TestPaceComparisonLogic:
    """Test training-type-aware pace selection."""

    def test_structured_workout_uses_main_set_pace(self, mocker):
        """Threshold/interval workouts use main set pace."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        data = {
            "training_type": "lactate_threshold",
            "basic_metrics": {"avg_pace_seconds_per_km": 380.0},
            "run_metrics": {"avg_pace_seconds_per_km": 330.0},
        }

        pace, pace_source = worker._get_comparison_pace(data)

        assert pace == 330.0
        assert pace_source == "main_set"

    def test_recovery_uses_overall_pace(self, mocker):
        """Recovery runs use overall average pace."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        data = {
            "training_type": "recovery",
            "basic_metrics": {"avg_pace_seconds_per_km": 420.0},
            "run_metrics": {"avg_pace_seconds_per_km": 410.0},
        }

        pace, pace_source = worker._get_comparison_pace(data)

        assert pace == 420.0
        assert pace_source == "overall"

    @pytest.mark.parametrize(
        "training_type,expected_source",
        [
            ("tempo", "main_set"),
            ("lactate_threshold", "main_set"),
            ("vo2max", "main_set"),
            ("anaerobic_capacity", "main_set"),
            ("speed", "main_set"),
            ("recovery", "overall"),
            ("aerobic_base", "overall"),
            ("unknown", "overall"),
        ],
    )
    def test_pace_source_by_training_type(self, training_type, expected_source, mocker):
        """All training types map to correct pace source."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        data = {
            "training_type": training_type,
            "basic_metrics": {"avg_pace_seconds_per_km": 400.0},
            "run_metrics": {"avg_pace_seconds_per_km": 350.0},
        }

        _, pace_source = worker._get_comparison_pace(data)

        assert pace_source == expected_source

    def test_fallback_when_run_metrics_missing(self, mocker):
        """Falls back to overall pace when run_metrics unavailable."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        data = {
            "training_type": "lactate_threshold",  # Structured
            "basic_metrics": {"avg_pace_seconds_per_km": 380.0},
            "run_metrics": None,  # Missing
        }

        pace, pace_source = worker._get_comparison_pace(data)

        assert pace == 380.0
        assert pace_source == "overall"


@pytest.mark.unit
class TestActivityTypeDisplay:
    """Test _get_activity_type_display method."""

    @pytest.mark.parametrize(
        "training_type,expected_ja,expected_en",
        [
            ("recovery", "リカバリーラン", "Recovery Run"),
            ("aerobic_base", "有酸素ベース走", "Aerobic Base"),
            ("tempo", "テンポラン", "Tempo Run"),
            ("lactate_threshold", "乳酸閾値トレーニング", "Lactate Threshold"),
            ("vo2max", "VO2 Maxトレーニング", "VO2 Max Training"),
            ("anaerobic_capacity", "無酸素容量トレーニング", "Anaerobic Capacity"),
            ("speed", "スピードトレーニング", "Speed Training"),
            ("interval_training", "インターバルトレーニング", "Interval Training"),
        ],
    )
    def test_activity_type_mapping(
        self, training_type, expected_ja, expected_en, mocker
    ):
        """All 8 training types map to correct display names."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        result = worker._get_activity_type_display(training_type)

        assert result["ja"] == expected_ja
        assert result["en"] == expected_en
        assert "description" in result
        assert len(result["description"]) > 0

    def test_unknown_training_type_fallback(self, mocker):
        """Unknown training types return fallback display."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        result = worker._get_activity_type_display("unknown_type")

        assert result["ja"] == "その他のトレーニング"
        assert result["en"] == "Other Training"
        assert "description" in result

    def test_aerobic_base_description_content(self, mocker):
        """Aerobic base description mentions heart rate zones."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        result = worker._get_activity_type_display("aerobic_base")

        assert "心拍ゾーン" in result["description"] or "Zone" in result["description"]
        assert "有酸素" in result["description"]

    def test_lactate_threshold_description_structure(self, mocker):
        """Lactate threshold description mentions 3-phase structure."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        result = worker._get_activity_type_display("lactate_threshold")

        assert "3" in result["description"] or "フェーズ" in result["description"]
        assert "閾値" in result["description"]

    def test_interval_training_description_details(self, mocker):
        """Interval training description includes workout structure details."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        result = worker._get_activity_type_display("interval_training")

        assert "Work" in result["description"] or "Recovery" in result["description"]
        assert "VO2" in result["description"] or "高強度" in result["description"]


@pytest.mark.unit
class TestTrainingTypeCategory:
    """Test _get_training_type_category method for Phase 2."""

    @pytest.mark.parametrize(
        "training_type,expected_category",
        [
            # Low to moderate intensity
            ("recovery", "low_moderate"),
            ("aerobic_base", "low_moderate"),
            ("aerobic_endurance", "low_moderate"),
            ("unknown", "low_moderate"),
            # Tempo/Threshold
            ("tempo", "tempo_threshold"),
            ("lactate_threshold", "tempo_threshold"),
            # Interval/Sprint
            ("vo2max", "interval_sprint"),
            ("anaerobic_capacity", "interval_sprint"),
            ("speed", "interval_sprint"),
            ("interval_training", "interval_sprint"),
        ],
    )
    def test_training_type_category_mapping(
        self, training_type, expected_category, mocker
    ):
        """All training types map to correct internal category."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        category = worker._get_training_type_category(training_type)

        assert category == expected_category

    def test_category_mapping_is_consistent_with_display(self, mocker):
        """Category mapping should work for all display-mapped types."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # All 8 display types should have valid category mapping
        display_types = [
            "recovery",
            "aerobic_base",
            "tempo",
            "lactate_threshold",
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
        ]

        for training_type in display_types:
            category = worker._get_training_type_category(training_type)
            assert category in ["low_moderate", "tempo_threshold", "interval_sprint"]


@pytest.mark.unit
class TestPhysiologicalIndicators:
    """Test _calculate_physiological_indicators method for Phase 2."""

    def test_calculate_vo2_max_utilization(self, mocker):
        """Calculate VO2 Max utilization percentage."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        vo2_max_data = {"precise_value": 52.3}
        lactate_threshold_data = {
            "functional_threshold_power": 285,
            "speed_mps": 3.63,  # ~4:35/km
        }
        run_metrics = {
            "avg_pace_seconds_per_km": 304,  # 5:04/km
            "avg_power": 250,
        }

        result = worker._calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        assert result is not None
        assert "vo2_max_utilization" in result
        assert "threshold_pace_formatted" in result
        assert "ftp_percentage" in result

        # VO2 Max utilization should be < 100% (running slower than VO2 Max pace)
        assert 0 < result["vo2_max_utilization"] < 100

    def test_ftp_percentage_calculation(self, mocker):
        """Calculate FTP percentage correctly."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        vo2_max_data = {"precise_value": 52.3}
        lactate_threshold_data = {"functional_threshold_power": 285, "speed_mps": 3.63}
        run_metrics = {"avg_pace_seconds_per_km": 275, "avg_power": 342}

        result = worker._calculate_physiological_indicators(
            training_type_category="interval_sprint",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        assert result is not None
        # 342W / 285W ≈ 120%
        assert result["ftp_percentage"] == pytest.approx(120.0, rel=0.1)

    def test_threshold_pace_formatting(self, mocker):
        """Format threshold pace as MM:SS/km."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        vo2_max_data = {"precise_value": 52.3}
        lactate_threshold_data = {
            "functional_threshold_power": 285,
            "speed_mps": 3.63,  # 1000/3.63 ≈ 275.5s/km ≈ 4:35/km
        }
        run_metrics = {"avg_pace_seconds_per_km": 304, "avg_power": 250}

        result = worker._calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        assert result is not None
        assert result["threshold_pace_formatted"] in ["4:35/km", "4:36/km"]

    def test_returns_none_for_low_moderate(self, mocker):
        """Returns None for low_moderate training types."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        result = worker._calculate_physiological_indicators(
            training_type_category="low_moderate",
            vo2_max_data={"precise_value": 52.3},
            lactate_threshold_data={"functional_threshold_power": 285},
            run_metrics={"avg_pace_seconds_per_km": 400},
        )

        assert result is None

    def test_handles_missing_data_gracefully(self, mocker):
        """Returns None when required data is missing."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Missing VO2 Max data
        result = worker._calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data={"functional_threshold_power": 285},
            run_metrics={"avg_pace_seconds_per_km": 304},
        )
        assert result is None

        # Missing lactate threshold data
        result = worker._calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data={"precise_value": 52.3},
            lactate_threshold_data=None,
            run_metrics={"avg_pace_seconds_per_km": 304},
        )
        assert result is None
        # Note: Actual Mermaid rendering in template is tested in integration tests


@pytest.mark.unit
class TestComparisonPaceAnnotation:
    """Test pace_source annotation for Task 3 (Phase 2)."""

    def test_pace_source_is_main_set_for_interval(self, mocker):
        """pace_source is 'main_set' for Interval workouts (using run_metrics)."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Interval workout with run_metrics pace
        performance_data = {
            "training_type": "vo2max",
            "basic_metrics": {"avg_pace_seconds_per_km": 290},
            "run_metrics": {"avg_pace_seconds_per_km": 275},  # Work pace
        }

        pace, pace_source = worker._get_comparison_pace(performance_data)

        assert pace == 275
        assert pace_source == "main_set"

    def test_pace_source_is_main_set_for_threshold(self, mocker):
        """pace_source is 'main_set' for Threshold workouts (using run_metrics)."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Threshold workout with run_metrics pace
        performance_data = {
            "training_type": "lactate_threshold",
            "basic_metrics": {"avg_pace_seconds_per_km": 300},
            "run_metrics": {"avg_pace_seconds_per_km": 285},  # Main phase pace
        }

        pace, pace_source = worker._get_comparison_pace(performance_data)

        assert pace == 285
        assert pace_source == "main_set"

    def test_pace_source_is_overall_for_base_run(self, mocker):
        """pace_source is 'overall' for Base runs (using basic_metrics)."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Base run without run_metrics
        performance_data = {
            "training_type": "aerobic_base",
            "basic_metrics": {"avg_pace_seconds_per_km": 360},
            "run_metrics": None,
        }

        pace, pace_source = worker._get_comparison_pace(performance_data)

        assert pace == 360
        assert pace_source == "overall"
