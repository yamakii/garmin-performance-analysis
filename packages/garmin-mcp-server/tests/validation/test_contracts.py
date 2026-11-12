"""Tests for the run_note analysis contract."""

import json

import pytest

from garmin_mcp.validation.contracts import VALID_SECTION_TYPES, get_contract


@pytest.mark.unit
def test_contract_registry_is_run_note_only():
    """``run_note`` is the only section an agent writes (Issue #1256).

    A legacy section type is rejected exactly like any other unknown type: the
    five legacy contracts are gone, and nothing re-creates them.
    """
    assert set(VALID_SECTION_TYPES) == {"run_note"}

    for legacy in ("summary", "efficiency", "split", "phase", "environment"):
        with pytest.raises(ValueError, match="Unknown section_type") as legacy_err:
            get_contract(legacy)
        with pytest.raises(ValueError, match="Unknown section_type") as unknown_err:
            get_contract("nope")
        assert str(legacy_err.value).replace(legacy, "nope") == str(unknown_err.value)


@pytest.mark.unit
def test_contract_notes_allow_grouping():
    """The contract tells the agent how to fit outliers into 3 notes (#1492).

    The merge gate wants every adverse outlier explained exactly once and the
    schema caps notes at 3; without ``also`` in the contract the agent merges
    signals into prose the gate cannot see and the run_note is rejected.
    """
    contract = get_contract("run_note")

    assert "also" in contract["required_fields"]["notes"]["description"]
    policy = contract["evaluation_policy"]["notes"]
    assert "also" in policy
    assert "exactly once" in policy


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


@pytest.mark.unit
def test_run_note_never_write_covers_insufficient_signals():
    """An unjudged signal must not be folded into "all within range" (#1389)."""
    never_write = get_contract("run_note")["never_write"]

    assert any("insufficient" in item for item in never_write)


@pytest.mark.unit
def test_run_note_agent_does_not_copy_the_contract():
    """The contract is the single home of what a run note must do (Epic #1544).

    run-note-analyst.md used to restate never_write and the field rules, and the
    copies drifted (8 substantive drifts). It now points at the contract instead.
    """
    from pathlib import Path

    agent = Path(__file__).resolve().parents[4] / ".claude/agents/run-note-analyst.md"
    text = agent.read_text(encoding="utf-8")

    assert 'get_analysis_contract("run_note")' in text
    assert "never_write" in text  # named as living in the contract
    # no verbatim copy of contract items
    for item in get_contract("run_note")["never_write"]:
        assert item not in text


@pytest.mark.unit
def test_contract_run_note_lists_prose_roles():
    """The prose criterion travels with the contract (Epic #1247, #1251)."""
    contract = get_contract("run_note")

    assert contract["section_type"] == "run_note"
    assert len(contract["prose_roles"]) == 6
    assert len(contract["never_write"]) >= 5
    # The six roles are the whole job of the section.
    assert set(contract["prose_roles"]) == {
        "meaning",
        "causality",
        "flow",
        "weighting",
        "next_action",
        "recurrence_and_questions",
    }
    # Tone rules are referenced, not duplicated.
    assert "analysis-standards.md" in contract["evaluation_policy"]["tone"]
    # Every evidence prefix the grounding guard resolves is documented.
    assert set(contract["evidence_keys"]) == {
        "plan.<axis>",
        "plan.strides",
        "plan.continuity",
        "signals.<metric>",
        "moments.<id>",
        "recurrence.<kind>",
        "vs_previous.<field>",
        "conditions.<field>",
        "context.<field>",
    }


@pytest.mark.unit
def test_contract_describes_continuity_axis():
    """The purpose axis and the one-collapse-one-growth-point rule (#1353)."""
    contract = get_contract("run_note")

    assert "plan.continuity" in contract["evidence_keys"]
    policy = contract["evaluation_policy"]["growth_points"]
    assert "plan.continuity" in policy
    assert "ONE growth point" in policy


@pytest.mark.unit
def test_contract_run_note_next_challenge_carries_one_point():
    """持ち越す 1 点: one of today's points as a cue, not a next-session target.

    #1267 pointed the challenge at report.next_session, which made a single
    run prescribe the next session (2026-09-13). The session is the
    prescription's to set (#1358); the note carries one of today's points over.
    The rule lives in evaluation_policy.next_challenge only (Epic #1544).
    """
    contract = get_contract("run_note")

    policy = contract["evaluation_policy"]["next_challenge"]
    assert "good_points / growth_points" in policy
    assert "matters most" in policy
    assert "no numbers but the prescription's" in policy
    assert "next_challenge_evidence" in policy
    assert "are not its source" in policy
    assert "150 bpm を超えないように" in policy
    assert "next_challenge_evidence" in contract["required_fields"]
    assert (
        "next_session"
        not in contract["required_fields"]["next_challenge"]["description"]
    )


@pytest.mark.unit
def test_contract_principles_have_one_home():
    """Each principle is stated once; copies drifted before (Epic #1544)."""
    contract = get_contract("run_note")
    text = json.dumps(contract, ensure_ascii=False)

    # attribution order: prose_roles.causality only
    assert (
        "intensity -> terrain -> athlete_context"
        in contract["prose_roles"]["causality"]
    )
    assert text.count("intensity -> terrain") == 1
    # scene naming: never_write only
    assert any("lap" in r and "label_ja" in r for r in contract["never_write"])
    assert text.count("label_ja") == 1
    # the carried point: evaluation_policy.next_challenge only
    assert text.count("150 bpm を超えないように") == 1
    # instructions point at the sections instead of summarising them
    assert len(contract["instructions"]) <= 5


@pytest.mark.unit
def test_contract_timeline_narrates_sets_and_context():
    """Rep sessions are told as a set; acceptable / neutral scenes are context."""
    timeline = get_contract("run_note")["evaluation_policy"]["timeline"]

    for fact in ("pace_spread_s", "first_vs_last_s", "hr_drop_bpm"):
        assert fact in timeline
    assert "'acceptable'" in timeline and "'neutral'" in timeline
    assert "names the comparison it rests on" in timeline
    assert "attribution order" in timeline


@pytest.mark.unit
def test_contract_describes_strides_scene():
    """Strides are one set judged by reps, relaxed speed and recovery (#1294, #1298)."""
    contract = get_contract("run_note")

    assert "plan.strides" in contract["evidence_keys"]
    policy = contract["evaluation_policy"]["strides"]
    assert policy["kind"] == "strides"
    assert policy["evidence"] == "moments.<id>"
    assert policy["judge_by"] == ["reps", "relaxed_speed", "recovered_before_next"]
    assert policy["never"] == "ceiling_excursion"
    for fact in ("fastest_pace_s_per_km", "hr_at_next_start", "ceiling excursion"):
        assert fact in policy["description"]


@pytest.mark.unit
def test_contract_growth_points_match_the_gate():
    """The contract names the same three growth-point sources the gate accepts (#1314)."""
    policy = get_contract("run_note")["evaluation_policy"]["growth_points"]

    assert "outside its normal range AND adverse" in policy
    assert "off_plan / short / missing" in policy
    assert "policy.verdict == 'concern'" in policy
    for background in ("recurrence", "vs_previous", "conditions", "context"):
        assert background in policy


@pytest.mark.unit
def test_contract_describes_purpose():
    """The run is read against report.purpose, and an inferred one is hedged."""
    purpose = get_contract("run_note")["evaluation_policy"]["purpose"]

    assert purpose["source"] == "report.purpose"
    assert purpose["inferred"] == "hedge -- say the purpose was inferred"
    assert purpose["deviations"] == "acceptable/neutral are context, never a flaw"
    for fact in ("policy", "judged_share"):
        assert fact in purpose["description"]


@pytest.mark.unit
def test_contract_has_no_scene_conclusion_templates():
    """Scene-specific 'say X / never say Y' patches stay out (Epic #1544).

    The Nov patches (#1513 / #1517 / #1542) were removed first; the terminology,
    ceiling-wording, warm-up / progression / steady and backpack patches went in
    the second pass. Each is covered by a principle, the gate or run_policy.
    """
    text = json.dumps(get_contract("run_note"), ensure_ascii=False)

    for patch in (
        "fast_start whose HR stayed under the ceiling",
        "never carries a surge scene",
        "Blame a ceiling_touch on the start",
        "whatever the pace",
        "followed the pace",
        "a neutral moment the timeline does not narrate",
        "朝のレディネス",
        "never say the HR ceiling was not exceeded",
        "low-readiness morning",
        "backpack",
        "not filler",
        "shape of the build",
    ):
        assert patch not in text


@pytest.mark.unit
def test_contract_never_write_core_items():
    """The grounding bans that no gate can check stay in never_write."""
    never_write = get_contract("run_note")["never_write"]

    assert any("drink" in i and "traffic light" in i for i in never_write)  # #1329
    assert any("without the comparison" in i for i in never_write)  # #1542
    assert any("label alone" in i and "facts" in i for i in never_write)
    assert any("derived metric" in i and "confirmation" in i for i in never_write)


@pytest.mark.unit
def test_contract_good_points_rules():
    """good_points is 0-3 and never rests on a within-range or allowed scene (#1329)."""
    good = get_contract("run_note")["required_fields"]["good_points"]["description"]

    assert good.startswith("0-3 items")
    for rule in ("within-range", "acceptable", "timeline", "Leave it empty"):
        assert rule in good


@pytest.mark.unit
def test_contract_evaluation_policy_has_judgement_checklist():
    """One judgement checklist shared with conversation and skills (#1524)."""
    policy = get_contract("run_note")["evaluation_policy"]

    steps = policy["judgement"]["steps"]
    assert [step.split(":", 1)[0] for step in steps] == [
        "purpose",
        "facts",
        "applicability",
        "confidence",
    ]
    assert "achieved" in steps[0]
    for level in ("high", "medium", "low"):
        assert level in policy["confidence"]


@pytest.mark.unit
def test_contract_purpose_step_names_standing():
    """The purpose step says where the goals live (#1583)."""
    contract = get_contract("run_note")
    steps = contract["evaluation_policy"]["judgement"]["steps"]

    assert "context.standing" in steps[0]
    # The meaning role points at that step instead of restating it.
    assert "judgement step 1" in contract["prose_roles"]["meaning"]


@pytest.mark.unit
def test_contract_mentions_athlete_context_attribution():
    """A stated circumstance is a cause right after terrain (#1522)."""
    contract = get_contract("run_note")

    context_keys = contract["evidence_keys"]["context.<field>"]
    assert "athlete_context" in context_keys
    assert "prescription_for_run" in context_keys
    assert "never a growth point" in contract["evaluation_policy"]["athlete_context"]
    assert "instruction" in contract["evaluation_policy"]["coaching_rules"]
