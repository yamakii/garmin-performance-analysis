"""Tests for the run_note analysis contract."""

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
    run prescribe the next session and put a long run's HR band on a Z2 jog
    (2026-09-13). The session is the prescription's to set (#1358); the note
    carries one of today's points over instead.
    """
    contract = get_contract("run_note")

    policy = contract["evaluation_policy"]["next_challenge"]
    assert "good_points / growth_points" in policy
    assert "no numbers but the prescription's" in policy
    assert "next_challenge_evidence" in policy
    # next_session is named only to say it is not the source.
    assert "are not its source" in policy
    assert "same_type" not in policy
    required = contract["required_fields"]
    assert "next_challenge_evidence" in required
    assert "next_session" not in required["next_challenge"]["description"]
    assert any("next_challenge_evidence" in line for line in contract["instructions"])
    # The ceiling is still quoted as a guard.
    assert "150 bpm を超えないように" in policy


@pytest.mark.unit
def test_contract_run_note_scenes_referenced_by_label():
    """A scene is named by its label, never by the lap it was recorded under.

    Since #1268 every scene carries ``label_ja`` + ``unit``; step scenes
    (``rep`` / ``rest`` / ``work_set``) have no kilometre to be numbered by at
    all, so a lap-derived 「N km 目」 is simply wrong (#1267).
    """
    contract = get_contract("run_note")

    timeline = contract["evaluation_policy"]["timeline"]
    assert "label_ja" in timeline
    for kind in ("rep", "rest", "work_set", "progression"):
        assert kind in timeline
    # The facts a rep session is narrated from, rather than rep-by-rep numbers.
    for fact in ("pace_spread_s", "first_vs_last_s", "hr_drop_bpm"):
        assert fact in timeline
    # Placing a scene by a lap number is called out as forbidden.
    assert any("lap" in rule and "label_ja" in rule for rule in contract["never_write"])
    assert any("label_ja" in line for line in contract["instructions"])


@pytest.mark.unit
def test_contract_describes_strides_scene():
    """The strides scene and the strides plan axis are documented (#1298)."""
    contract = get_contract("run_note")

    timeline = contract["evaluation_policy"]["timeline"]
    assert "strides" in timeline
    assert "plan.strides" in contract["evidence_keys"]

    policy = contract["evaluation_policy"]["strides"]
    assert policy["kind"] == "strides"
    assert policy["evidence"] == "moments.<id>"
    assert policy["judge_by"] == ["reps", "relaxed_speed", "recovered_before_next"]
    # The facts the set is judged from are the ones the strides scene carries.
    for fact in ("fastest_pace_s_per_km", "hr_at_next_start", "peak_hr"):
        assert fact in policy["description"]


@pytest.mark.unit
def test_contract_growth_points_allow_concern_moments():
    """A scene may carry a growth point only when its purpose calls it a concern.

    The merge gate accepts ``moments.<id>`` as growth-point evidence only for a
    moment whose ``policy.verdict`` is ``concern`` (#1314); the contract has to
    say the same thing or the agent writes notes the gate then rejects.
    """
    contract = get_contract("run_note")

    policy = contract["evaluation_policy"]["growth_points"]
    assert "policy.verdict == 'concern'" in policy
    # Acceptable / neutral scenes are context, and background sources explain a
    # growth point without being one.
    assert "'acceptable'" in policy
    assert "'neutral'" in policy
    for background in ("recurrence", "vs_previous", "conditions", "context"):
        assert background in policy
    assert any(
        "policy.verdict == 'concern'" in line and "growth point" in line
        for line in contract["instructions"]
    )
    # The timeline narrates acceptable / neutral scenes as context.
    timeline = contract["evaluation_policy"]["timeline"]
    assert "policy.verdict" in timeline
    assert "context" in timeline


@pytest.mark.unit
def test_contract_describes_purpose():
    """The run is read against report.purpose, and an inferred one is hedged."""
    contract = get_contract("run_note")

    purpose = contract["evaluation_policy"]["purpose"]
    assert purpose["source"] == "report.purpose"
    assert purpose["inferred"] == "hedge -- say the purpose was inferred"
    assert purpose["deviations"] == "acceptable/neutral are context, never a flaw"
    for fact in ("label_ja", "source == 'inferred'", "policy", "judged_share"):
        assert fact in purpose["description"]

    rule = next(line for line in contract["instructions"] if "purpose" in line)
    assert "inferred" in rule
    assert "hedge" in rule
    assert any("judged_share" in line for line in contract["instructions"])


@pytest.mark.unit
def test_contract_strides_not_ceiling_excursion():
    """Stride HR peaks are the set doing its job, not an HR-ceiling breach."""
    contract = get_contract("run_note")

    assert contract["evaluation_policy"]["strides"]["never"] == "ceiling_excursion"
    rule = next(
        line for line in contract["instructions"] if "neuromuscular" in line.lower()
    )
    assert "ceiling excursion" in rule
    assert "stride or recovery HR" in rule
    assert "relaxed speed" in rule
    assert "HR came back before the next rep" in rule


@pytest.mark.unit
def test_contract_has_no_scene_conclusion_templates():
    """Scene-specific 'say X / never say Y' patches are gone (Epic #1544).

    The fast_start-under-ceiling verdict is computed by run_policy (#1513) and a
    surge on an easy run is a neutral verdict there; the ceiling-touch
    templates of #1517 / #1542 are subsumed by the timeline's general demand
    that a cause names its comparison.
    """
    import json

    text = json.dumps(get_contract("run_note"), ensure_ascii=False)

    for patch in (
        "fast_start whose HR stayed under the ceiling",
        "never carries a surge scene",
        "Blame a ceiling_touch on the start",
        "whatever the pace",
        "followed the pace",
        "a neutral moment the timeline does not narrate",
    ):
        assert patch not in text
    timeline = get_contract("run_note")["evaluation_policy"]["timeline"]
    assert "names the comparison it rests on" in timeline
    assert "attribution order" in timeline


@pytest.mark.unit
def test_contract_never_write_bans_cause_without_comparison():
    """A cause must name the comparison it rests on (#1542)."""
    contract = get_contract("run_note")

    assert any("without the comparison" in line for line in contract["never_write"])


@pytest.mark.unit
def test_contract_good_points_rules():
    """good_points is 0-3 with gated evidence, and invented causes are banned (#1329)."""
    contract = get_contract("run_note")

    good = contract["required_fields"]["good_points"]["description"]
    assert good.startswith("0-3 items")
    for rule in ("within-range", "acceptable", "timeline", "Leave it empty"):
        assert rule in good
    assert any(
        "drink" in line and "traffic light" in line for line in contract["never_write"]
    )
    assert any("seconds_over > 0" in line for line in contract["instructions"])
    # A run far over its ceiling cannot praise keeping it (#1332).
    assert any("pct_over > 5" in line for line in contract["instructions"])


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
def test_contract_never_write_forbids_label_only_conclusion():
    never_write = get_contract("run_note")["never_write"]

    assert any("label alone" in item and "facts" in item for item in never_write)
    assert any(
        "derived metric" in item and "confirmation" in item for item in never_write
    )


@pytest.mark.unit
def test_contract_mentions_athlete_context_attribution():
    """A stated circumstance is a cause right after terrain (#1522)."""
    contract = get_contract("run_note")

    context_keys = contract["evidence_keys"]["context.<field>"]
    assert "athlete_context" in context_keys
    assert "prescription_for_run" in context_keys
    assert "ladder_step" not in context_keys

    order = "intensity -> terrain -> athlete_context"
    assert order in contract["prose_roles"]["causality"]
    assert order in contract["evaluation_policy"]["notes"]
    assert "never a growth point" in contract["evaluation_policy"]["athlete_context"]
    assert "instruction" in contract["evaluation_policy"]["coaching_rules"]
