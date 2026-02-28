"""Tests for section analysis data validation schemas."""

import pytest

from garmin_mcp.validation.section_schemas import validate_section_data


@pytest.mark.unit
def test_split_valid_data():
    data = {
        "highlights": "テストハイライト文章です。",
        "analyses": {"split_1": "分析テキスト"},
    }
    valid, errors = validate_section_data("split", data)
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_split_missing_highlights():
    data = {"analyses": {"split_1": "分析テキスト"}}
    valid, errors = validate_section_data("split", data)
    assert valid is False
    assert len(errors) > 0
    assert any("highlights" in e for e in errors)


@pytest.mark.unit
def test_split_empty_analyses():
    data = {"highlights": "テストハイライト文章です。", "analyses": {}}
    valid, errors = validate_section_data("split", data)
    assert valid is False
    assert len(errors) > 0


@pytest.mark.unit
def test_split_invalid_key_format():
    data = {
        "highlights": "テストハイライト文章です。",
        "analyses": {"bad_key": "分析テキスト"},
    }
    valid, errors = validate_section_data("split", data)
    assert valid is False
    assert len(errors) > 0
    assert any("split_N" in e or "bad_key" in e for e in errors)


@pytest.mark.unit
def test_phase_valid_3phase():
    data = {
        "warmup_evaluation": "ウォームアップの評価テキストです。",
        "run_evaluation": "ランニング本体の評価テキストです。",
        "cooldown_evaluation": "クールダウンの評価テキストです。",
        "evaluation_criteria": "基準テキスト",
    }
    valid, errors = validate_section_data("phase", data)
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_phase_valid_4phase():
    data = {
        "warmup_evaluation": "ウォームアップの評価テキストです。",
        "run_evaluation": "ランニング本体の評価テキストです。",
        "cooldown_evaluation": "クールダウンの評価テキストです。",
        "recovery_evaluation": "リカバリーの評価テキストです。",
        "evaluation_criteria": "基準テキスト",
    }
    valid, errors = validate_section_data("phase", data)
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_phase_missing_run():
    data = {
        "warmup_evaluation": "ウォームアップの評価テキストです。",
        "cooldown_evaluation": "クールダウンの評価テキストです。",
        "evaluation_criteria": "基準テキスト",
    }
    valid, errors = validate_section_data("phase", data)
    assert valid is False
    assert len(errors) > 0
    assert any("run_evaluation" in e for e in errors)


@pytest.mark.unit
def test_efficiency_valid():
    data = {
        "efficiency": "効率性の分析結果を詳細に記述します。ペースに対するHR効率が良好です。",
        "evaluation": "総合評価の結果を詳細に記述します。全体的にバランスの取れた走りでした。",
        "form_trend": "フォームトレンドの分析です。安定傾向にあります。",
    }
    valid, errors = validate_section_data("efficiency", data)
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_environment_valid():
    data = {
        "environmental": "天候は晴れで気温20度、走りやすい環境でした。",
    }
    valid, errors = validate_section_data("environment", data)
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_summary_valid_minimal():
    data = {
        "star_rating": "★★★★☆ 4.2/5.0",
        "integrated_score": 78.5,
        "summary": "全体的に良いランニングでした。",
        "key_strengths": ["安定したペース配分"],
        "improvement_areas": [],
        "next_action": "次回はHR Zone 2を維持して走りましょう。",
        "next_run_target": {"recommended_type": "easy_run"},
        "recommendations": "週3回のランニングを継続してください。",
    }
    valid, errors = validate_section_data("summary", data)
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_summary_with_plan_achievement():
    data = {
        "star_rating": "★★★★☆ 4.0/5.0",
        "integrated_score": 80.0,
        "summary": "プラン通りのトレーニングができました。",
        "key_strengths": ["目標HR達成"],
        "improvement_areas": ["ペース安定性"],
        "next_action": "次回もHR Zone 2を意識して走りましょう。",
        "next_run_target": {"recommended_type": "easy_run"},
        "recommendations": "引き続きプランに沿ったトレーニングを推奨します。",
        "plan_achievement": {
            "workout_type": "easy_run",
            "description_ja": "イージーラン",
            "targets": {"hr_zone": "Zone 2", "pace": "5:30-6:00/km"},
            "actuals": {"hr_zone": "Zone 2", "pace": "5:35/km"},
            "hr_achieved": True,
            "pace_achieved": True,
            "evaluation": "目標を達成しました。",
        },
    }
    valid, errors = validate_section_data("summary", data)
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_summary_missing_star_rating():
    data = {
        "integrated_score": 78.5,
        "summary": "全体的に良いランニングでした。",
        "key_strengths": ["安定したペース配分"],
        "improvement_areas": [],
        "next_action": "次回はHR Zone 2を維持して走りましょう。",
        "next_run_target": {},
        "recommendations": "週3回のランニングを継続してください。",
    }
    valid, errors = validate_section_data("summary", data)
    assert valid is False
    assert len(errors) > 0
    assert any("star_rating" in e for e in errors)


@pytest.mark.unit
def test_unknown_section_type():
    valid, errors = validate_section_data("unknown", {"foo": "bar"})
    assert valid is False
    assert len(errors) > 0
    assert any("Unknown section_type: unknown" in e for e in errors)
