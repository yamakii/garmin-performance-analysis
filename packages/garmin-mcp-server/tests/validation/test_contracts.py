"""Tests for analysis contracts."""

import pytest

from garmin_mcp.validation.contracts import VALID_SECTION_TYPES, get_contract


@pytest.mark.unit
def test_get_contract_split():
    contract = get_contract("split")
    assert contract["schema_version"] == "1.0"
    assert "highlights" in contract["required_fields"]
    assert "analyses" in contract["required_fields"]
    assert "hr_drift" in contract["evaluation_policy"]
    assert isinstance(contract["instructions"], list)


@pytest.mark.unit
def test_get_contract_phase():
    contract = get_contract("phase")
    assert "warmup_criteria" in contract["evaluation_policy"]
    assert "cooldown_criteria" in contract["evaluation_policy"]
    assert "star_rating_format" in contract["evaluation_policy"]


@pytest.mark.unit
def test_get_contract_efficiency():
    contract = get_contract("efficiency")
    policy = contract["evaluation_policy"]
    assert "form_ranges" in policy
    assert "cadence_ranges" in policy
    assert "integrated_score_stars" in policy
    assert "power_efficiency_stars" in policy
    assert "baseline_comparison" in policy
    assert "zone_targets" in policy


@pytest.mark.unit
def test_efficiency_contract_has_form_ranges():
    contract = get_contract("efficiency")
    form = contract["evaluation_policy"]["form_ranges"]
    assert len(form) == 3
    for metric in ["gct", "vo", "vr"]:
        assert metric in form
        assert "excellent" in form[metric]
        assert "needs_improvement" in form[metric]


@pytest.mark.unit
def test_efficiency_contract_has_integrated_score():
    contract = get_contract("efficiency")
    score = contract["evaluation_policy"]["integrated_score_stars"]
    assert "5_stars" in score
    assert "1_star" in score


@pytest.mark.unit
def test_efficiency_contract_has_zone_targets():
    contract = get_contract("efficiency")
    zones = contract["evaluation_policy"]["zone_targets"]
    assert len(zones) == 3
    for category in ["base_easy_recovery", "tempo_threshold", "interval_sprint"]:
        assert category in zones


@pytest.mark.unit
def test_efficiency_contract_has_baseline_thresholds():
    contract = get_contract("efficiency")
    baseline = contract["evaluation_policy"]["baseline_comparison"]
    assert "daily_variation_normal" in baseline
    assert "baseline_improved" in baseline
    assert "baseline_attention" in baseline


@pytest.mark.unit
def test_get_contract_environment():
    contract = get_contract("environment")
    policy = contract["evaluation_policy"]
    assert "temperature_by_training_type" in policy
    assert "humidity" in policy
    assert "wind_speed_ms" in policy
    assert "terrain_classification" in policy


@pytest.mark.unit
def test_environment_contract_has_temperature_by_type():
    contract = get_contract("environment")
    temp = contract["evaluation_policy"]["temperature_by_training_type"]
    assert len(temp) == 4
    for category in [
        "recovery",
        "base_moderate",
        "tempo_threshold",
        "interval_sprint",
    ]:
        assert category in temp


@pytest.mark.unit
def test_environment_contract_has_humidity_thresholds():
    contract = get_contract("environment")
    humidity = contract["evaluation_policy"]["humidity"]
    assert "good" in humidity
    assert "challenging" in humidity


@pytest.mark.unit
def test_environment_contract_has_wind_thresholds():
    contract = get_contract("environment")
    wind = contract["evaluation_policy"]["wind_speed_ms"]
    assert len(wind) == 4


@pytest.mark.unit
def test_environment_contract_has_terrain_classification():
    contract = get_contract("environment")
    terrain = contract["evaluation_policy"]["terrain_classification"]
    assert len(terrain) == 4


@pytest.mark.unit
def test_environment_contract_has_star_rating_weights():
    contract = get_contract("environment")
    weights = contract["evaluation_policy"]["star_rating"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 0.01


@pytest.mark.unit
def test_get_contract_summary():
    contract = get_contract("summary")
    policy = contract["evaluation_policy"]
    assert "star_rating_scale" in policy
    assert "next_run_target_variants" in policy
    assert policy["recommendations_max"] == 2
    assert policy["next_action_count"] == 1


@pytest.mark.unit
def test_get_contract_unknown_type():
    with pytest.raises(ValueError, match="Unknown section_type"):
        get_contract("unknown")


@pytest.mark.unit
def test_contract_has_required_keys():
    required_keys = {
        "schema_version",
        "section_type",
        "required_fields",
        "evaluation_policy",
        "instructions",
    }
    for section_type in VALID_SECTION_TYPES:
        contract = get_contract(section_type)
        assert required_keys.issubset(
            contract.keys()
        ), f"{section_type} missing keys: {required_keys - contract.keys()}"
