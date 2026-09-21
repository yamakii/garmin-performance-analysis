"""Test integrated score calculation with mode-specific weights."""

import pytest


@pytest.mark.unit
def test_calculate_integrated_score_interval_mode():
    """interval_sprint mode: w_power=0.40 (power efficiency重視)."""
    from garmin_mcp.form_baseline.integrated_score import calculate_integrated_score

    penalties: dict[str, float | None] = {
        "gct": 0.1,
        "vo": 0.05,
        "vr": -0.02,
        "power": 0.08,
    }

    score = calculate_integrated_score(penalties, training_mode="interval_sprint")

    # 100 - (0.30*10 + 0.15*5 + 0.15*2 + 0.40*8) = 100 - 6.95 = 93.05
    assert 92.0 < score < 94.0, f"Expected ~93.05, got {score}"


@pytest.mark.unit
def test_calculate_integrated_score_tempo_mode():
    """tempo_threshold mode: w_power=0.35."""
    from garmin_mcp.form_baseline.integrated_score import calculate_integrated_score

    penalties: dict[str, float | None] = {
        "gct": 0.1,
        "vo": 0.05,
        "vr": -0.02,
        "power": 0.08,
    }

    score = calculate_integrated_score(penalties, training_mode="tempo_threshold")

    # 100 - (0.25*0.1 + 0.20*0.05 + 0.20*(-0.02) + 0.35*0.08) * 100 = 100 - 5.9 = 94.1
    assert 93.5 < score < 94.5, f"Expected ~94.1, got {score}"


@pytest.mark.unit
def test_calculate_integrated_score_recovery_mode():
    """low_moderate mode: w_power=0.20 (power efficiency軽視)."""
    from garmin_mcp.form_baseline.integrated_score import calculate_integrated_score

    penalties: dict[str, float | None] = {
        "gct": 0.1,
        "vo": 0.05,
        "vr": -0.02,
        "power": 0.08,
    }

    score = calculate_integrated_score(penalties, training_mode="low_moderate")

    # 100 - (0.30*0.1 + 0.25*0.05 + 0.25*(-0.02) + 0.20*0.08) * 100 = 100 - 5.35 = 94.65
    assert 94.0 < score < 95.0, f"Expected ~94.65, got {score}"


@pytest.mark.unit
def test_calculate_integrated_score_no_power_data():
    """パワーデータなしの場合、powerペナルティ0で計算."""
    from garmin_mcp.form_baseline.integrated_score import calculate_integrated_score

    penalties = {"gct": 0.1, "vo": 0.05, "vr": -0.02, "power": None}

    score = calculate_integrated_score(penalties, training_mode="interval_sprint")

    # powerペナルティ除外、他の重みを正規化
    # w_gct = 0.30 / (0.30 + 0.15 + 0.15) = 0.5
    # w_vo = 0.15 / 0.60 = 0.25
    # w_vr = 0.15 / 0.60 = 0.25
    # 100 - (0.5*0.1 + 0.25*0.05 + 0.25*(-0.02)) * 100 = 100 - 5.75 = 94.25
    assert 93.5 < score < 95.0, f"Expected ~94.25, got {score}"


@pytest.mark.unit
def test_calculate_integrated_score_all_zero_penalties():
    """全ペナルティ0の場合、スコアは100点."""
    from garmin_mcp.form_baseline.integrated_score import calculate_integrated_score

    penalties: dict[str, float | None] = {
        "gct": 0.0,
        "vo": 0.0,
        "vr": 0.0,
        "power": 0.0,
    }

    score = calculate_integrated_score(penalties, training_mode="interval_sprint")

    assert score == 100.0


@pytest.mark.unit
def test_calculate_integrated_score_negative_penalties():
    """負のペナルティ(改善)の場合、スコアが100点を超える."""
    from garmin_mcp.form_baseline.integrated_score import calculate_integrated_score

    penalties: dict[str, float | None] = {
        "gct": -0.05,
        "vo": -0.03,
        "vr": -0.02,
        "power": -0.04,
    }

    score = calculate_integrated_score(penalties, training_mode="interval_sprint")

    # 100 - (0.30*-5 + 0.15*-3 + 0.15*-2 + 0.40*-4) = 100 - (-3.85) = 103.85
    assert 103.0 < score < 105.0, f"Expected ~103.85, got {score}"


@pytest.mark.unit
def test_calculate_integrated_score_invalid_mode_defaults_to_low_moderate():
    """無効なトレーニングモードの場合、low_moderateにフォールバック."""
    from garmin_mcp.form_baseline.integrated_score import calculate_integrated_score

    penalties: dict[str, float | None] = {
        "gct": 0.1,
        "vo": 0.05,
        "vr": -0.02,
        "power": 0.08,
    }

    score = calculate_integrated_score(penalties, training_mode="invalid_mode")

    # low_moderate の重みで計算される
    assert 94.0 < score < 95.0


@pytest.mark.unit
def test_calculate_integrated_score_weights_sum_to_one():
    """各モードの重みが合計1.0になることを確認."""
    from garmin_mcp.form_baseline.integrated_score import TRAINING_MODE_WEIGHTS

    for mode, weights in TRAINING_MODE_WEIGHTS.items():
        total = sum(weights.values())
        assert (
            abs(total - 1.0) < 0.01
        ), f"Mode {mode} weights sum to {total}, expected 1.0"
