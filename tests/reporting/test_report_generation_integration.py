"""
Integration tests for report generation.

Tests complete workflow from DuckDB to final report.
"""

from pathlib import Path

import pytest

from tools.reporting.report_generator_worker import ReportGeneratorWorker


@pytest.fixture
def test_db(tmp_path):
    """Create test database with production schema."""
    import duckdb

    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create activities table with complete production schema
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE,
            activity_name VARCHAR,
            start_time_local TIMESTAMP,
            start_time_gmt TIMESTAMP,
            location_name VARCHAR,
            total_distance_km DOUBLE,
            total_time_seconds INTEGER,
            avg_speed_ms DOUBLE,
            avg_pace_seconds_per_km DOUBLE,
            avg_heart_rate INTEGER,
            max_heart_rate INTEGER,
            temp_celsius DOUBLE,
            relative_humidity_percent DOUBLE,
            wind_speed_kmh DOUBLE,
            wind_direction VARCHAR,
            gear_type VARCHAR,
            gear_model VARCHAR
        )
    """
    )

    # Create form_efficiency table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS form_efficiency (
            activity_id BIGINT PRIMARY KEY,
            gct_average DOUBLE,
            gct_std DOUBLE,
            gct_rating VARCHAR,
            vo_average DOUBLE,
            vo_std DOUBLE,
            vo_rating VARCHAR,
            vr_average DOUBLE,
            vr_std DOUBLE,
            vr_rating VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create performance_trends table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_trends (
            activity_id BIGINT PRIMARY KEY,
            pace_consistency DOUBLE,
            hr_drift_percentage DOUBLE,
            cadence_consistency VARCHAR,
            fatigue_pattern VARCHAR,
            warmup_avg_pace_seconds_per_km DOUBLE,
            warmup_avg_hr DOUBLE,
            main_avg_pace_seconds_per_km DOUBLE,
            main_avg_hr DOUBLE,
            finish_avg_pace_seconds_per_km DOUBLE,
            finish_avg_hr DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create hr_efficiency table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_efficiency (
            activity_id BIGINT PRIMARY KEY,
            training_type VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create section_analyses table
    conn.execute(
        """
        CREATE SEQUENCE IF NOT EXISTS section_analyses_seq START 1;
        CREATE TABLE IF NOT EXISTS section_analyses (
            analysis_id INTEGER PRIMARY KEY DEFAULT nextval('section_analyses_seq'),
            activity_id BIGINT NOT NULL,
            activity_date DATE NOT NULL,
            section_type VARCHAR NOT NULL,
            analysis_data VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            agent_name VARCHAR,
            agent_version VARCHAR
        )
    """
    )

    conn.close()
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
            "environmental": {
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
            "warmup_evaluation": "適切なウォームアップ",
            "main_evaluation": "一貫したペース維持",
            "finish_evaluation": "適切なペース配分",
        },
        "split": {
            "metadata": {
                "activity_id": "12345",
                "date": "2025-09-22",
                "analyst": "split-section-analyst",
                "version": "1.0",
            },
            "analyses": {
                "split_1": "1km目: ペース6'15\", 心拍152",
                "split_2": "2km目: ペース6'00\", 心拍158",
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
    import json

    import duckdb

    # Setup: Insert test data using production schema
    conn = duckdb.connect(test_db)

    # Insert activity with complete production schema
    conn.execute(
        """
        INSERT INTO activities (
            activity_id, activity_date, activity_name, location_name,
            total_distance_km, total_time_seconds, avg_pace_seconds_per_km,
            avg_heart_rate, temp_celsius, relative_humidity_percent,
            wind_speed_kmh, gear_type, gear_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            test_activity_data["activity_date"],
            test_activity_data["activity_name"],
            "",  # location_name
            test_activity_data["distance_km"],
            test_activity_data["duration_seconds"],
            test_activity_data["avg_pace_seconds_per_km"],
            test_activity_data["avg_heart_rate"],
            18.0,  # temp_celsius
            65.0,  # relative_humidity_percent
            9.0,  # wind_speed_kmh (2.5 m/s * 3.6)
            "Nike",  # gear_type
            "Vaporfly Next% 2",  # gear_model
        ],
    )

    # Insert form efficiency data
    conn.execute(
        """
        INSERT INTO form_efficiency (
            activity_id, gct_average, gct_std, gct_rating,
            vo_average, vo_std, vo_rating,
            vr_average, vr_std, vr_rating
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            262.0,
            5.0,
            "★★★★★",
            7.2,
            0.3,
            "★★★★☆",
            9.3,
            0.4,
            "★★★★★",
        ],
    )

    # Insert performance trends data
    conn.execute(
        """
        INSERT INTO performance_trends (
            activity_id, pace_consistency, hr_drift_percentage,
            cadence_consistency, fatigue_pattern,
            warmup_avg_pace_seconds_per_km, warmup_avg_hr,
            main_avg_pace_seconds_per_km, main_avg_hr,
            finish_avg_pace_seconds_per_km, finish_avg_hr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            0.05,
            3.5,
            "高い安定性",
            "適切な疲労管理",
            365,
            145,
            355,
            152,
            350,
            158,
        ],
    )

    # Insert HR efficiency data
    conn.execute(
        """
        INSERT INTO hr_efficiency (
            activity_id, training_type
        ) VALUES (?, ?)
    """,
        [
            test_activity_data["activity_id"],
            "aerobic_base",
        ],
    )

    # Insert section analyses
    for section_type, analysis_data in test_section_analyses.items():
        conn.execute(
            """
            INSERT INTO section_analyses (
                activity_id, activity_date, section_type, analysis_data
            ) VALUES (?, ?, ?, ?)
        """,
            [
                test_activity_data["activity_id"],
                test_activity_data["activity_date"],
                section_type,
                json.dumps(analysis_data, ensure_ascii=False),
            ],
        )

    conn.close()

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
    assert "# ランニングパフォーマンス分析レポート" in report_content
    assert "## 基本情報" in report_content
    assert "## パフォーマンス指標" in report_content
    assert "## 総合評価" in report_content
    assert "Nike Vaporfly" in report_content  # Gear info


@pytest.mark.integration
def test_generate_report_partial_sections(test_db, test_activity_data, tmp_path):
    """一部のセクション分析のみでもレポート生成できることを確認."""
    import json

    import duckdb

    # Setup: Insert only efficiency section
    conn = duckdb.connect(test_db)

    # Insert activity with minimal required data
    conn.execute(
        """
        INSERT INTO activities (
            activity_id, activity_date, activity_name, location_name,
            total_distance_km, total_time_seconds, avg_pace_seconds_per_km,
            avg_heart_rate, temp_celsius, relative_humidity_percent,
            wind_speed_kmh, gear_type, gear_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            test_activity_data["activity_date"],
            test_activity_data["activity_name"],
            "",
            test_activity_data["distance_km"],
            test_activity_data["duration_seconds"],
            test_activity_data["avg_pace_seconds_per_km"],
            test_activity_data["avg_heart_rate"],
            None,  # temp_celsius (optional)
            None,  # relative_humidity_percent (optional)
            None,  # wind_speed_kmh (optional)
            None,  # gear_type (optional)
            None,  # gear_model (optional)
        ],
    )

    # Insert only efficiency section
    efficiency_data = {
        "metadata": {"analyst": "efficiency-section-analyst"},
        "efficiency": "GCT: 262msの優秀な接地時間を維持できています。",
    }
    conn.execute(
        """
        INSERT INTO section_analyses (
            activity_id, activity_date, section_type, analysis_data
        ) VALUES (?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            test_activity_data["activity_date"],
            "efficiency",
            json.dumps(efficiency_data, ensure_ascii=False),
        ],
    )

    conn.close()

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
    import json

    import duckdb

    # Setup
    conn = duckdb.connect(test_db)

    # Insert activity with complete data
    conn.execute(
        """
        INSERT INTO activities (
            activity_id, activity_date, activity_name, location_name,
            total_distance_km, total_time_seconds, avg_pace_seconds_per_km,
            avg_heart_rate, temp_celsius, relative_humidity_percent,
            wind_speed_kmh, gear_type, gear_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            test_activity_data["activity_date"],
            test_activity_data["activity_name"],
            "",
            test_activity_data["distance_km"],
            test_activity_data["duration_seconds"],
            test_activity_data["avg_pace_seconds_per_km"],
            test_activity_data["avg_heart_rate"],
            18.0,  # temp_celsius
            65.0,  # relative_humidity_percent
            9.0,  # wind_speed_kmh (2.5 m/s * 3.6)
            "Nike",  # gear_type
            "Vaporfly Next% 2",  # gear_model
        ],
    )

    # Insert form efficiency data
    conn.execute(
        """
        INSERT INTO form_efficiency (
            activity_id, gct_average, gct_std, gct_rating,
            vo_average, vo_std, vo_rating,
            vr_average, vr_std, vr_rating
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            262.0,
            5.0,
            "★★★★★",
            7.2,
            0.3,
            "★★★★☆",
            9.3,
            0.4,
            "★★★★★",
        ],
    )

    # Insert performance trends data
    conn.execute(
        """
        INSERT INTO performance_trends (
            activity_id, pace_consistency, hr_drift_percentage,
            cadence_consistency, fatigue_pattern,
            warmup_avg_pace_seconds_per_km, warmup_avg_hr,
            main_avg_pace_seconds_per_km, main_avg_hr,
            finish_avg_pace_seconds_per_km, finish_avg_hr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            test_activity_data["activity_id"],
            0.05,
            3.5,
            "高い安定性",
            "適切な疲労管理",
            365,
            145,
            355,
            152,
            350,
            158,
        ],
    )

    # Insert HR efficiency data
    conn.execute(
        """
        INSERT INTO hr_efficiency (
            activity_id, training_type
        ) VALUES (?, ?)
    """,
        [
            test_activity_data["activity_id"],
            "aerobic_base",
        ],
    )

    # Insert section analyses
    for section_type, analysis_data in test_section_analyses.items():
        conn.execute(
            """
            INSERT INTO section_analyses (
                activity_id, activity_date, section_type, analysis_data
            ) VALUES (?, ?, ?, ?)
        """,
            [
                test_activity_data["activity_id"],
                test_activity_data["activity_date"],
                section_type,
                json.dumps(analysis_data, ensure_ascii=False),
            ],
        )

    conn.close()

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
