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
    assert "gct" in policy
    assert "vertical_oscillation" in policy
    assert "vertical_ratio" in policy
    assert "cadence" in policy
    assert "integrated_score_stars" in policy


@pytest.mark.unit
def test_get_contract_environment():
    contract = get_contract("environment")
    policy = contract["evaluation_policy"]
    assert "temperature" in policy
    assert "humidity" in policy
    assert "wind" in policy
    assert "terrain_classification" in policy


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
