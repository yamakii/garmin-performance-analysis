"""Analysis contract for the coach-review section.

``run_note`` is the only section an agent writes, and its contract is
retrieved via the get_analysis_contract MCP tool. Keeping the writing
criterion here rather than in the agent definition lets it be changed with a
reload_server() hot-reload instead of an agent edit.

Each principle lives in one place (Epic #1544): the attribution order in
``prose_roles.causality``, scene naming in ``never_write``, the carried point in
``evaluation_policy.next_challenge``. What the merge gate
(``validators.check_run_note_grounding``) and the section schema enforce is
stated briefly, not restated rule by rule.
"""

from __future__ import annotations

from typing import Any

_CONTRACTS: dict[str, dict[str, Any]] = {
    # The single LLM-written section of the redesigned single-run page
    # (Epic #1247). Everything a number can decide -- ranges, verdicts, star
    # scores -- is already computed and rendered as figures, so this section
    # writes only what a coach adds on top of them.
    "run_note": {
        "schema_version": "1.0",
        "section_type": "run_note",
        "required_fields": {
            "story": {
                "type": "string",
                "description": "2-3 sentences: evaluation_policy.judgement step 1",
            },
            "good_points": {
                "type": "array",
                "description": (
                    "0-3 items of {text, evidence}. A strength rests on a "
                    "favourable out-of-range signal, an on-plan axis (plan.hr_ceiling "
                    "only when pct_over <= 5), or "
                    "vs_previous / recurrence / conditions / context -- never on "
                    "a within-range signal, an 'acceptable' or 'concern' moment, "
                    "or a scene the timeline already tells. Leave it empty "
                    "rather than invent one"
                ),
            },
            "growth_points": {
                "type": "array",
                "description": (
                    "0-2 items of {text, evidence} that qualify under "
                    "evaluation_policy.growth_points, framed as room to grow, "
                    "never pass/fail"
                ),
            },
            "next_challenge": {
                "type": "string",
                "description": "持ち越す 1 点 -- see evaluation_policy.next_challenge",
            },
            "next_challenge_evidence": {
                "type": "string",
                "description": (
                    "The evidence key of the good / growth point next_challenge "
                    "carries over"
                ),
            },
            "timeline": {
                "type": "array",
                "description": "1-5 items of {moment_id, text}, 1-2 sentences each",
            },
            "notes": {
                "type": "array",
                "description": (
                    "<= 3 items of {signal, also?, text}, only for adverse "
                    "out-of-range signals. 'also' lists further outliers the "
                    "same explanation covers"
                ),
            },
            "question": {
                "type": "string",
                "description": (
                    "Optional, at most one, about something the sensors cannot "
                    "see (sleep, stress, how the legs felt, fuelling)"
                ),
            },
        },
        # The six roles the prose must play. Anything outside them is already
        # in the figures.
        "prose_roles": {
            "meaning": "evaluation_policy.judgement step 1",
            "causality": (
                "Connect a signal to its most likely cause in the attribution "
                "order intensity -> terrain -> athlete_context (stated load, "
                "commute, carried-over strides) -> weather + start time -> "
                "recovery -> form, and say when the cause is uncertain"
            ),
            "flow": "Narrate how the run unfolded scene by scene, not km by km",
            "weighting": (
                "Say which of the findings actually matters and which the "
                "athlete can ignore today"
            ),
            "next_action": "Carry ONE point over from today (next_challenge)",
            "recurrence_and_questions": (
                "Point out what keeps recurring across runs; ask only what the "
                "sensors cannot see"
            ),
        },
        "never_write": [
            "Numeric readouts already shown in the figures -- a number that "
            "carries a comparison or a prescription guard is not a readout",
            "Restated deterministic verdicts such as '接地時間は理想範囲内です'",
            "Generic criteria or textbook thresholds with no bearing on this run",
            "The same point in two places",
            "A cause the report does not carry -- a drink, a traffic light, how "
            "the legs felt -- filled in to explain a scene",
            "A cause named without the comparison it rests on -- say what was "
            "compared and that the earlier causes in the attribution order did "
            "not explain it",
            "A conclusion drawn from a label alone -- a scene's kind, its "
            "policy.verdict or a headline flag label -- without reading the "
            "facts behind it",
            "A derived metric (report.provenance device_derived / computed) "
            "cited as confirmation of the inputs it is derived from",
            "A blanket 'every signal is within range' when some signals are "
            "status insufficient -- those were not judged",
            "A lap / split number as a place in the run -- a scene is named by "
            "its label_ja ('3–5 km', '2本目')",
            "A bare English report key in Japanese prose",
        ],
        # How an ``evidence`` / ``moment_id`` / ``signal`` key is resolved by
        # ``validators.check_run_note_grounding`` at merge time.
        "evidence_keys": {
            "plan.<axis>": (
                "a row of report.plan.checks (status on_plan / off_plan / short "
                "/ missing / insufficient; insufficient = not judged). "
                "hr_ceiling is judged on the time above the ceiling "
                "(seconds_over / pct_over), not on the average"
            ),
            "plan.strides": "the strides row: reps done against the prescription",
            "plan.continuity": (
                "whether a run meant to hold an effort held it to the end"
            ),
            "signals.<metric>": "a metric of report.signals",
            "moments.<id>": "an id of report.moments",
            "recurrence.<kind>": "a kind of report.recurrence",
            "vs_previous.<field>": "a field of report.vs_previous",
            "conditions.<field>": "a field of report.conditions",
            "context.<field>": (
                "one of week_position / prescription_for_run / "
                "morning_wellness / gear / similar_workouts / athlete_context / "
                "standing. "
                "athlete_context.inferred.commute is a guess -- hedge it"
            ),
        },
        "evaluation_policy": {
            # Shared with conversation and the coaching skills
            # (.claude/rules/analysis/analysis-standards.md §3, #1524).
            "judgement": {
                "steps": [
                    "purpose: what the run was for (report.purpose), judged by "
                    "that purpose's own criteria -- start from what those "
                    "criteria count as achieved; place it in week / block / "
                    "goal via context.standing, purpose as yardstick",
                    "facts: what the report shows, and whether it is comparable "
                    "(a metric in comparability.excluded_metrics is not compared)",
                    "applicability: before a label, a rule or a recurring "
                    "pattern becomes advice, check that its precondition holds "
                    "in this run's facts",
                    "confidence: how sure the point is -- high, medium or low -- "
                    "and the one condition that would change it",
                ],
            },
            "confidence": (
                "State certainty in the prose: say a point plainly when the "
                "facts are direct (high), hedge it when it rests on one signal "
                "or an inferred purpose / commute (medium), and say it is "
                "uncertain, naming what would settle it, when the cause is not "
                "in the report (low)"
            ),
            "grounding": (
                "Every good point, growth point, timeline item and note carries "
                "the key of the datum behind it; a claim with no key is not "
                "written at all"
            ),
            "growth_points": (
                "Only a signal that is outside its normal range AND adverse, a "
                "plan axis that is off_plan / short / missing, or a moment whose "
                "policy.verdict == 'concern'. recurrence / vs_previous / "
                "conditions / context explain a growth point but never are one. "
                "A collapse on plan.continuity and its breakdown scene are ONE "
                "growth point"
            ),
            # What the run was *for* (#1312, #1314).
            "purpose": {
                "source": "report.purpose",
                "inferred": "hedge -- say the purpose was inferred",
                "deviations": "acceptable/neutral are context, never a flaw",
                "description": (
                    "Read the run against report.purpose. Each moment's policy "
                    "verdict is judged against it: 'concern' is a deviation, "
                    "'acceptable' / 'neutral' are context. When "
                    "report.judged_share is well below 1, say the verdict "
                    "covers only that part of the run"
                ),
            },
            "notes": (
                "Explain every adverse out-of-range signal exactly once, in the "
                "attribution order; signals with one cause share a note via "
                "'also'"
            ),
            "athlete_context": (
                "A stated circumstance explains a signal and is never a growth "
                "point; never ask what athlete_context already answers"
            ),
            "coaching_rules": (
                "Apply each context.coaching_rules rule_text as an instruction "
                "alongside this contract (the rationale is background). A rule "
                "never overrides the grounding gate or never_write"
            ),
            "timeline": (
                "One item per scene in report.moments, in order; an uneventful "
                "run gets one item on the 'steady' scene saying what held. A "
                "cause told for a scene names the comparison it rests on and "
                "walks the attribution order; what the report cannot separate "
                "is hedged. Narrate a rep session as a set (pace_spread_s, "
                "first_vs_last_s, hr_drop_bpm), not rep by rep. A scene whose "
                "policy.verdict is 'acceptable' or 'neutral' is context; only a "
                "'concern' scene is told as a deviation"
            ),
            # Strides are a few seconds of relaxed fast running inside an easy
            # run (#1294), judged by reps, relaxed speed and recovery.
            "strides": {
                "kind": "strides",
                "evidence": "moments.<id>",
                "judge_by": ["reps", "relaxed_speed", "recovered_before_next"],
                "never": "ceiling_excursion",
                "description": (
                    "A strides scene is one set: its HR peaks are not a ceiling "
                    "excursion. Judge it by reps done (plan.strides), relaxed "
                    "speed (fastest_pace_s_per_km) and whether HR came back "
                    "before the next rep (hr_at_next_start)"
                ),
            },
            "next_challenge": (
                "持ち越す 1 点 (10-120 chars). A single run cannot set the next "
                "session -- the prescription and the morning check-in do -- so "
                "choose the one of good_points / growth_points that matters most "
                "for what the run was for -- not a minor or on-plan detail -- and "
                "turn it into one behaviour cue (e.g. '後半も今日と同じリズムを"
                "保つ'); put "
                "its evidence key in next_challenge_evidence. No named or dated "
                "session, no numbers but the prescription's own values as a guard "
                "('150 bpm を超えないように'); report.next_session / "
                "next_run_target are not its source. A kept good point is a "
                "maintenance target, never pass/fail"
            ),
            "tone": (
                "Japanese coaching tone per "
                ".claude/rules/analysis/analysis-standards.md -- not duplicated here"
            ),
        },
        "instructions": [
            "Play the six prose_roles and nothing else",
            "Build each point through evaluation_policy.judgement",
            "Never write anything listed in never_write",
            "Attach an evidence key (evidence_keys) to every point; the merge "
            "gate rejects a key that does not resolve or a point that does not "
            "qualify",
        ],
    },
}

VALID_SECTION_TYPES = set(_CONTRACTS.keys())


def get_contract(section_type: str) -> dict[str, Any]:
    """Return the analysis contract for a given section type.

    Raises:
        ValueError: If section_type is not recognized.
    """
    if section_type not in _CONTRACTS:
        raise ValueError(
            f"Unknown section_type: {section_type}. "
            f"Valid types: {sorted(VALID_SECTION_TYPES)}"
        )
    return _CONTRACTS[section_type]
