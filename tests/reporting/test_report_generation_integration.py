"""
Integration tests for report generation.

Tests complete workflow from DuckDB to final report.
"""

from pathlib import Path

import pytest

from tools.database.db_writer import GarminDBWriter
from tools.reporting.report_generator_worker import ReportGeneratorWorker


@pytest.fixture
def test_db(tmp_path):
    """Create test database with schema."""
    db_path = tmp_path / "test.duckdb"
    _writer = GarminDBWriter(str(db_path))  # Tables created by __init__
    return str(db_path)


@pytest.fixture
def test_activity_data():
    """Test activity data."""
    return {
        "activity_id": 12345,
        "activity_date": "2025-09-22",
        "activity_name": "Morning Run",
        "distance_km": 5.0,
        "duration_seconds": 1800,
        "avg_pace_seconds_per_km": 360,
        "avg_heart_rate": 155,
        "avg_cadence": 168,
        "avg_power": 250,
    }


@pytest.fixture
def test_section_analyses():
    """Test section analyses data."""
    return {
        "efficiency": {
            "metadata": {
                "activity_id": "12345",
                "date": "2025-09-22",
                "analyst": "efficiency-section-analyst",
                "version": "1.0",
            },
            "efficiency": {
                "form_efficiency": "GCT: 262ms (★★★☆☆), VO: 7.2cm (★★★★★)",
                "hr_efficiency": "Zone 1優位 (63.5%), aerobic_base型",
                "evaluation": "優秀な接地時間、効率的な地面反力利用",
            },
        },
        "environment": {
            "metadata": {
                "activity_id": "12345",
                "date": "2025-09-22",
                "analyst": "environment-section-analyst",
                "version": "1.0",
            },
            "environment_analysis": {
                "weather_conditions": "気温18.0°C、快適な条件",
                "terrain_impact": "平坦コース (標高変化+2m/-2m)",
                "gear": {
                    "shoes": "Nike Vaporfly Next% 2 (走行距離: 245km)",
                    "notes": "理想的なシューズ選択",
                },
                "evaluation": "理想的な環境条件、適切な機材選択",
            },
        },
        "phase": {
            "metadata": {
                "activity_id": "12345",
                "date": "2025-09-22",
                "analyst": "phase-section-analyst",
                "version": "1.0",
            },
            "phase_evaluation": {
                "warmup": {
                    "splits": [1],
                    "avg_pace": "6'15\"",
                    "evaluation": "適切なウォームアップ",
                },
                "main": {
                    "splits": [2, 3, 4],
                    "pace_stability": "高い安定性",
                    "evaluation": "一貫したペース維持",
                },
                "finish": {
                    "splits": [5],
                    "fatigue_level": "軽度",
                    "evaluation": "適切なペース配分",
                },
                "overall": "優れたペース配分",
            },
        },
        "split": {
            "metadata": {
                "activity_id": "12345",
                "date": "2025-09-22",
                "analyst": "split-section-analyst",
                "version": "1.0",
            },
            "split_analysis": {
                "splits": [
                    {"km": 1, "pace": "6'15\"", "hr": 152},
                    {"km": 2, "pace": "6'00\"", "hr": 158},
                ],
                "patterns": {"pace_trend": "安定", "hr_trend": "漸増"},
            },
        },
        "summary": {
            "metadata": {
                "activity_id": "12345",
                "date": "2025-09-22",
                "analyst": "summary-section-analyst",
                "version": "1.0",
            },
            "summary": {
                "activity_type": {"classification": "Easy Run", "confidence": "high"},
                "overall_rating": {"score": 4.5, "stars": "★★★★☆"},
                "key_strengths": ["フォーム効率", "ペース安定性"],
                "improvement_areas": ["心拍ドリフト管理"],
                "recommendations": "理想的なEasy Runテンポを維持",
            },
        },
    }


@pytest.mark.integration
def test_generate_report_full_workflow(
    test_db, test_activity_data, test_section_analyses, tmp_path
):
    """DuckDBからレポート生成までの完全なフローを確認."""
    # Setup: Insert test data
    writer = GarminDBWriter(test_db)

    # Insert activity
    writer.insert_activity(
        activity_id=test_activity_data["activity_id"],
        activity_date=test_activity_data["activity_date"],
        activity_name=test_activity_data["activity_name"],
        activity_type="running",
        distance_km=test_activity_data["distance_km"],
        duration_seconds=test_activity_data["duration_seconds"],
        avg_pace_seconds_per_km=test_activity_data["avg_pace_seconds_per_km"],
        avg_heart_rate=test_activity_data["avg_heart_rate"],
    )

    # Insert performance data
    performance_data = {"basic_metrics": test_activity_data}
    writer.insert_performance_data(
        activity_id=test_activity_data["activity_id"],
        activity_date=test_activity_data["activity_date"],
        performance_data=performance_data,
    )

    # Insert section analyses
    for section_type, analysis_data in test_section_analyses.items():
        writer.insert_section_analysis(
            activity_id=test_activity_data["activity_id"],
            activity_date=test_activity_data["activity_date"],
            section_type=section_type,
            analysis_data=analysis_data,
        )

    # Generate report
    worker = ReportGeneratorWorker(test_db)
    result = worker.generate_report(
        test_activity_data["activity_id"], test_activity_data["activity_date"]
    )

    # Assertions
    assert result["success"] is True
    assert result["activity_id"] == test_activity_data["activity_id"]
    assert Path(result["report_path"]).exists()

    # Verify report content
    report_content = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "# アクティビティ詳細分析レポート" in report_content
    assert "## 🎯 効率分析" in report_content
    assert "## ✅ 総合評価" in report_content
    assert "Nike Vaporfly" in report_content  # Gear info


@pytest.mark.integration
def test_generate_report_partial_sections(test_db, test_activity_data, tmp_path):
    """一部のセクション分析のみでもレポート生成できることを確認."""
    # Setup: Insert only efficiency and summary sections
    writer = GarminDBWriter(test_db)

    writer.insert_activity(
        activity_id=test_activity_data["activity_id"],
        activity_date=test_activity_data["activity_date"],
        activity_name=test_activity_data["activity_name"],
        activity_type="running",
        distance_km=test_activity_data["distance_km"],
        duration_seconds=test_activity_data["duration_seconds"],
        avg_pace_seconds_per_km=test_activity_data["avg_pace_seconds_per_km"],
        avg_heart_rate=test_activity_data["avg_heart_rate"],
    )

    performance_data = {"basic_metrics": test_activity_data}
    writer.insert_performance_data(
        activity_id=test_activity_data["activity_id"],
        activity_date=test_activity_data["activity_date"],
        performance_data=performance_data,
    )

    # Insert only efficiency section
    efficiency_data = {
        "metadata": {"analyst": "efficiency-section-analyst"},
        "efficiency": {"form_efficiency": "GCT: 262ms"},
    }
    writer.insert_section_analysis(
        activity_id=test_activity_data["activity_id"],
        activity_date=test_activity_data["activity_date"],
        section_type="efficiency",
        analysis_data=efficiency_data,
    )

    # Generate report
    worker = ReportGeneratorWorker(test_db)
    result = worker.generate_report(
        test_activity_data["activity_id"], test_activity_data["activity_date"]
    )

    assert result["success"] is True
    report_content = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "GCT: 262ms" in report_content
    assert "データがありません" in report_content  # Missing sections


@pytest.mark.integration
def test_generate_report_activity_not_found(test_db):
    """存在しないactivity_idでValueErrorがraiseされることを確認."""
    worker = ReportGeneratorWorker(test_db)

    with pytest.raises(ValueError, match="No performance data found"):
        worker.generate_report(99999, "2025-09-22")


@pytest.mark.integration
def test_report_japanese_encoding(
    test_db, test_activity_data, test_section_analyses, tmp_path
):
    """日本語テキストが正しくUTF-8でエンコードされることを確認."""
    # Setup
    writer = GarminDBWriter(test_db)

    writer.insert_activity(
        activity_id=test_activity_data["activity_id"],
        activity_date=test_activity_data["activity_date"],
        activity_name=test_activity_data["activity_name"],
        activity_type="running",
        distance_km=test_activity_data["distance_km"],
        duration_seconds=test_activity_data["duration_seconds"],
        avg_pace_seconds_per_km=test_activity_data["avg_pace_seconds_per_km"],
        avg_heart_rate=test_activity_data["avg_heart_rate"],
    )

    performance_data = {"basic_metrics": test_activity_data}
    writer.insert_performance_data(
        activity_id=test_activity_data["activity_id"],
        activity_date=test_activity_data["activity_date"],
        performance_data=performance_data,
    )

    for section_type, analysis_data in test_section_analyses.items():
        writer.insert_section_analysis(
            activity_id=test_activity_data["activity_id"],
            activity_date=test_activity_data["activity_date"],
            section_type=section_type,
            analysis_data=analysis_data,
        )

    # Generate report
    worker = ReportGeneratorWorker(test_db)
    result = worker.generate_report(
        test_activity_data["activity_id"], test_activity_data["activity_date"]
    )

    report_content = Path(result["report_path"]).read_text(encoding="utf-8")

    # Verify Japanese text
    assert "優秀な接地時間" in report_content
    assert "適切なペース配分" in report_content
    assert "理想的な環境条件" in report_content
