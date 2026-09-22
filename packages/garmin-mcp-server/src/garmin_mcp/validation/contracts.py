"""Analysis contract for the coach-review section.

``run_note`` is the only section an agent writes, and its contract is
retrieved via the get_analysis_contract MCP tool. Keeping the writing
criterion here rather than in the agent definition lets it be changed with a
reload_server() hot-reload instead of an agent edit.
"""

from __future__ import annotations

from typing import Any

_CONTRACTS: dict[str, dict[str, Any]] = {
    # The single LLM-written section of the redesigned single-run page
    # (Epic #1247). Everything a number can decide -- ranges, verdicts, star
    # scores -- is already computed and rendered as figures, so this section
    # writes only what a coach adds on top of them: meaning, causality and the
    # next step. The prose criterion is carried here verbatim so the agent
    # definition and this contract cannot drift apart.
    "run_note": {
        "schema_version": "1.0",
        "section_type": "run_note",
        "required_fields": {
            "story": {
                "type": "string",
                "description": (
                    "2-3 sentences, 20-400 chars: what the run was for (week / "
                    "block / goal) and whether it served that. May tell the "
                    "athlete what NOT to worry about"
                ),
            },
            "good_points": {
                "type": "array",
                "description": (
                    "1-3 items of {text, evidence}: one sentence each with the "
                    "evidence key of the number that supports it"
                ),
            },
            "growth_points": {
                "type": "array",
                "description": (
                    "0-2 items of {text, evidence}, framed as room to grow or a "
                    "maintenance target, never pass/fail"
                ),
            },
            "next_challenge": {
                "type": "string",
                "description": (
                    "1-2 sentences about the session in next_session -- name it "
                    "and date it ('9/20 の 16 km ロング走'). Its numbers come from "
                    "next_session; next_run_target's pace / HR bands may be "
                    "quoted only when it is the same kind of run. An HR ceiling "
                    "is written as a guard ('150 bpm を超えないように') together "
                    "with where HR should settle"
                ),
            },
            "timeline": {
                "type": "array",
                "description": (
                    "1-5 items of {moment_id, text}, 1-2 sentences each. An "
                    "uneventful run has exactly one item on the 'steady' scene"
                ),
            },
            "notes": {
                "type": "array",
                "description": (
                    "Only for adverse out-of-range signals, <= 2 sentences each: "
                    "{signal, text}"
                ),
            },
            "question": {
                "type": "string",
                "description": (
                    "Optional, at most one question, about something the sensors "
                    "cannot see (omit it when there is nothing to ask)"
                ),
            },
        },
        # The six roles the prose must play. Anything outside them is already
        # in the figures.
        "prose_roles": {
            "meaning": (
                "Say what the run was for in this week / block / goal and "
                "whether it served that purpose"
            ),
            "causality": (
                "Connect a signal to its most likely cause in the attribution "
                "order intensity -> terrain -> weather + start time -> recovery "
                "-> form, and say when the cause is uncertain"
            ),
            "flow": (
                "Narrate how the run unfolded scene by scene (the moments), "
                "not kilometre by kilometre. Place each scene by its own "
                "label_ja: a unit='km' scene is a stretch of road ('3–5 km'), "
                "a unit='step' scene is a step of the session ('1本目', "
                "'レスト1') -- never a lap or split number"
            ),
            "weighting": (
                "Say which of the findings actually matters and which the "
                "athlete can ignore today"
            ),
            "next_action": (
                "One concrete next step for the session in next_session -- the "
                "run the athlete actually does next, named and dated -- with an "
                "HR ceiling written as a guard"
            ),
            "recurrence_and_questions": (
                "Point out what keeps recurring across runs, and ask at most "
                "one question about what the sensors cannot see"
            ),
        },
        # Deterministic output already covers these, so writing them again is
        # noise at best and a contradiction at worst.
        "never_write": [
            "Numeric readouts already shown in the figures (pace / HR / GCT "
            "tables repeated as prose)",
            "Restated deterministic verdicts such as '接地時間は理想範囲内です' "
            "-- the range badge already says it",
            "Generic criteria or textbook thresholds with no bearing on this run",
            "A within-range deviation dressed up as a strength or a weakness",
            "The same point in two places (a good point that is also a growth "
            "point, a note that repeats the timeline, or a low-readiness "
            "morning stated in story and again in good_points)",
            "A pass/fail judgement of the athlete -- growth points are room to "
            "grow or a maintenance target",
            "A scene, cause or comparison that no evidence key supports",
            "A lap / split number as a place in the run -- a scene is placed "
            "by distance ('3–5 km') or by step ('2本目'), which is what its "
            "label_ja already says",
            "A bare English context key in Japanese prose -- readiness is "
            "「朝のレディネス（回復スコア）」 on first use and 「レディネス」 "
            "afterwards, HRV is 「心拍変動」 and RHR is 「安静時心拍」",
            "Every rep's pace and heart rate one by one -- the steps table "
            "shows them; a rep session is narrated as a set",
        ],
        # How an ``evidence`` / ``moment_id`` / ``signal`` key is resolved by
        # ``validators.check_run_note_grounding`` at merge time.
        "evidence_keys": {
            "plan.<axis>": "an axis of report.plan.checks (rejected when plan is null)",
            "plan.strides": (
                "the strides row of report.plan.checks -- strides run against the "
                "prescribed reps ('4本'); present only when the prescription "
                "carries strides"
            ),
            "signals.<metric>": "a metric of report.signals",
            "moments.<id>": "an id of report.moments",
            "recurrence.<kind>": "a kind of report.recurrence",
            "vs_previous.<field>": (
                "a field of report.vs_previous (rejected when vs_previous is null)"
            ),
            "conditions.<field>": "a field of report.conditions",
            "context.<field>": (
                "one of week_position / ladder_step / prescription / "
                "morning_wellness / gear / similar_workouts"
            ),
        },
        "evaluation_policy": {
            "grounding": (
                "Every good point, growth point, timeline item and note carries "
                "the key of the datum behind it; a claim with no key is not "
                "written at all"
            ),
            "growth_points": (
                "A growth point may only rest on a signal that is BOTH outside "
                "its normal range AND adverse, or on a plan axis that came out "
                "off plan. A within-range or favourable signal is never a "
                "weakness, and an on_plan axis is never an improvement area"
            ),
            "notes": (
                "Write one note for every adverse out-of-range signal and for no "
                "other signal. Attribute the cause in the order intensity -> "
                "terrain -> weather + start time -> recovery -> form"
            ),
            "timeline": (
                "One item per scene in report.moments, in order; an uneventful "
                "run gets exactly one item on the 'steady' scene. Refer to a "
                "scene by its label_ja and by nothing else -- never by "
                "split_from / split_to, and never by an 'N km 目' worked out "
                "from a lap number. A unit='km' label is a stretch of road "
                "('3–5 km', '本編 0.9–5.9 km'), a unit='step' label is the name "
                "of the step ('ウォームアップ', '1本目', 'レスト1'). kind is "
                "start / fast_start / surge / ceiling_touch / walk_break / "
                "climb / fade / strong_finish / progression / steady for "
                "unit='km' scenes, and warmup / rep / rest / main / cooldown / "
                "work_set / strides for unit='step' scenes. A strides scene "
                "('流し（4本）') is the whole set of strides and their jogs -- "
                "narrate it as one item (see evaluation_policy.strides). On a "
                "rep session "
                "(flow.axis == 'time') narrate the reps as a set -- how "
                "consistent they were (pace_vs_first_s, pace_spread_s), how the "
                "last compares with the first (first_vs_last_s, max_hr_vs_first) "
                "and whether the rests brought heart rate down (hr_drop_bpm) -- "
                "instead of listing each rep; warm-up and cool-down items are "
                "one sentence and say only what a table cannot. A progression "
                "scene describes the shape of the build (which step broke the "
                "order, where the biggest jump was) from its per_km facts "
                "without listing every kilometre. Never invent a scene the "
                "moments do not contain"
            ),
            # Strides are a few seconds of relaxed fast running inside an easy
            # run (#1294). Their HR peaks are the set doing its job, so they
            # are judged by reps, relaxed speed and recovery -- never by HR.
            "strides": {
                "kind": "strides",
                "evidence": "moments.<id>",
                "judge_by": ["reps", "relaxed_speed", "recovered_before_next"],
                "never": "ceiling_excursion",
                "description": (
                    "Strides are a neuromuscular set: a stride's HR peak "
                    "(peak_hr) and the jog HR after it are not a ceiling "
                    "excursion and never a note or growth point. Judge the set "
                    "by reps done (plan.strides), relaxed speed "
                    "(fastest_pace_s_per_km / median_pace_s_per_km, "
                    "median_cadence_spm) and whether HR came back before the "
                    "next rep (hr_at_next_start). Only the easy running outside "
                    "the set is read against the HR ceiling. A strides axis "
                    "that is short / missing is off plan like any other axis"
                ),
            },
            "next_challenge": (
                "Write it for report.next_session -- the session the athlete "
                "actually does next -- saying which session it is and when "
                "('9/20 の 16 km ロング走'), with its target_km / "
                "target_minutes / hr_high. next_run_target describes the next "
                "run *of today's kind*, so its pace and HR bands may be quoted "
                "only when next_session.source == 'same_type' or its "
                "session_type is the same kind as today's run. With "
                "next_session == null, carry today's main finding over without "
                "naming a type or quoting numbers ('次のランでも…'). An HR "
                "ceiling is a guard ('150 bpm を超えないように') plus where HR "
                "should settle, never a pass/fail target"
            ),
            "question": (
                "At most one, and only about something the sensors cannot see "
                "(sleep, stress, how the legs felt, fuelling)"
            ),
            "tone": (
                "Japanese coaching tone per "
                ".claude/rules/analysis/analysis-standards.md (natural sentences, "
                "no 体言止め, 1-2 sentences per point) -- not duplicated here"
            ),
        },
        "instructions": [
            "Play the six prose_roles and nothing else -- the figures already "
            "carry the numbers",
            "Never write anything listed in never_write",
            "Attach an evidence key from evidence_keys to every good point and "
            "growth point; timeline items carry a moment_id and notes carry a "
            "signal name",
            "Only an outside + adverse signal (or an off-plan axis) may become a "
            "growth point",
            "Write a note for every adverse out-of-range signal and for no other",
            "Write next_challenge for next_session (named and dated); quote "
            "next_run_target's bands only when it is the same kind of run, and "
            "write an HR ceiling as a guard with its settling range",
            "Refer to a scene by its label_ja -- a distance range for unit='km' "
            "and the step's name for unit='step' -- never by a lap number",
            "Strides are a neuromuscular set; do not read stride or recovery HR "
            "as a ceiling excursion; judge a set by reps done, relaxed speed and "
            "whether HR came back before the next rep",
            "Ask at most one question, about something the sensors cannot see",
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
