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
    # one point carried over from today. The prose criterion is carried here verbatim so the agent
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
                    "0-3 items of {text, evidence}: one sentence each with the "
                    "evidence key of the number that supports it. A strength "
                    "rests on a signal outside its normal range on the "
                    "favourable side, an on-plan axis, a neutral moment the "
                    "timeline does not narrate, or vs_previous / recurrence / "
                    "conditions / context. Never a within-range signal, an "
                    "'acceptable' or 'concern' moment, or a scene the timeline "
                    "already tells. Leave it empty rather than invent one"
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
                    "持ち越す 1 点: ONE sentence, 10-120 chars -- one of "
                    "today's growth_points (or, with none, a good point to keep) "
                    "turned into one behaviour cue for the runs ahead "
                    "('最初の 2 km は上限の 150 に近づく前に抑える'). Not a "
                    "restatement of the point, not a target for a named or "
                    "dated session, and no numbers except the prescription's "
                    "own values quoted as a guard"
                ),
            },
            "next_challenge_evidence": {
                "type": "string",
                "description": (
                    "The evidence key of the good point or growth point the "
                    "next_challenge carries over -- it must equal the evidence "
                    "of one of today's good_points / growth_points"
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
                "Carry ONE point over from today: pick one growth point (or a "
                "good point to keep) and turn it into one behaviour cue. The "
                "next session itself is the prescription's and the morning "
                "check-in's to set -- never target it from a single run"
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
            "A cause the report does not carry -- a drink, a traffic light, how "
            "the legs felt -- filled in to explain a scene",
            "A lap / split number as a place in the run -- a scene is placed "
            "by distance ('3–5 km') or by step ('2本目'), which is what its "
            "label_ja already says",
            "A bare English context key in Japanese prose -- readiness is "
            "「朝のレディネス（回復スコア）」 on first use and 「レディネス」 "
            "afterwards, HRV is 「心拍変動」 and RHR is 「安静時心拍」",
            "Every rep's pace and heart rate one by one -- the steps table "
            "shows them; a rep session is narrated as a set",
            "A blanket 'every signal is within range' when some signals are "
            "status insufficient -- those were not judged; say the judged "
            "ones are within range, or name which were judged",
        ],
        # How an ``evidence`` / ``moment_id`` / ``signal`` key is resolved by
        # ``validators.check_run_note_grounding`` at merge time.
        "evidence_keys": {
            "plan.<axis>": (
                "an axis of report.plan.checks (rejected when plan is null). "
                "hr_ceiling is judged on the steady time above the ceiling "
                "(plan.hr_ceiling.seconds_over / pct_over), not the average: "
                "off plan when more than 5% of it AND at least 5 minutes sat "
                "above, so an average under the ceiling does not mean "
                "the ceiling was kept"
            ),
            "plan.strides": (
                "the strides row of report.plan.checks -- strides run against the "
                "prescribed reps ('4本'); present only when the prescription "
                "carries strides"
            ),
            "plan.continuity": (
                "the continuity row of report.plan.checks -- whether the run "
                "delivered the prescription's purpose by holding its effort to "
                "the end ('保てた' / '18 km から崩れ'); present only with a "
                "prescription whose purpose is one of holding an effort"
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
                "its normal range AND adverse, on a plan axis that came out "
                "off plan, or on a moment whose policy.verdict == 'concern' "
                "(a deviation from what the run was for, see "
                "evaluation_policy.purpose). A within-range or favourable "
                "signal is never a weakness, an on_plan axis is never an "
                "improvement area, and a moment judged 'acceptable' or "
                "'neutral' is never a flaw. recurrence / vs_previous / "
                "conditions / context explain a growth point but never are one. "
                "A run that came apart on a prescribed day is off plan on "
                "plan.continuity AND carries a breakdown scene: that is one "
                "collapse, so it is ONE growth point on plan.continuity, and "
                "the breakdown scene is told in the timeline"
            ),
            # What the run was *for* (#1312, #1314). The report resolves the
            # purpose and judges every scene against it, so the same walk break
            # is context on an aerobic long run and a real miss on a goal-pace
            # rehearsal.
            "purpose": {
                "source": "report.purpose",
                "inferred": "hedge -- say the purpose was inferred",
                "deviations": "acceptable/neutral are context, never a flaw",
                "description": (
                    "report.purpose = {id, label_ja, source} names what the run "
                    "was for; story and meaning read the run against it. source "
                    "is 'prescription' / 'session_default' (the plan said so), "
                    "'inferred' (read from the run's own data) or 'default' "
                    "(unknown). When source == 'inferred', hedge it -- say the "
                    "purpose was read from the run ('データからは有酸素のロングと"
                    "見られます') rather than stating it as the plan. Every "
                    "moment carries policy = {verdict, reason} judged against "
                    "the purpose: 'concern' is a deviation from what the run "
                    "asks for and may become a growth point; 'acceptable' "
                    "(expected or allowed, e.g. a walk break on an aerobic long "
                    "run) and 'neutral' (descriptive) are narrated as context in "
                    "the timeline, never as a flaw or a note. report.judged_share "
                    "= {hr, form} is the share of the run's time (0-1) the HR "
                    "ceiling and the form signals were judged on; when it is "
                    "well below 1 (stops, walk breaks, strides excluded), say "
                    "the verdict covers only that part of the run"
                ),
            },
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
                "without listing every kilometre. A scene whose policy.verdict "
                "is 'acceptable' or 'neutral' is context -- say what it was "
                "and why it fits the purpose, never frame it as a flaw; only a "
                "'concern' scene is told as a deviation. Never invent a scene "
                "the moments do not contain"
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
                "持ち越す 1 点. A single run cannot set the next "
                "session -- the prescription and the morning check-in do -- so "
                "carry ONE point over from today instead: choose one of "
                "good_points / growth_points (a growth point when there is "
                "one, otherwise a good point to keep, as a maintenance target) "
                "and turn it into one behaviour cue that holds whatever the "
                "next run is. Put that point's evidence key in "
                "next_challenge_evidence. Do not restate the point's facts, do "
                "not name or date a session, and quote no numbers but the "
                "prescription's own values as a guard ('150 bpm を超えないよう"
                "に'). report.next_session / next_run_target are not its "
                "source. Never a pass/fail target"
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
            "Only an outside + adverse signal, an off-plan axis or a moment with "
            "policy.verdict == 'concern' may become a growth point; an "
            "'acceptable' or 'neutral' moment is context, never a flaw",
            "A good point rests on a favourable out-of-range signal, an on-plan "
            "axis, a neutral moment the timeline does not narrate, or a "
            "background source; write none rather than praise a within-range "
            "value or an allowed scene",
            "When plan.hr_ceiling.seconds_over > 0, never say the HR ceiling "
            "was not exceeded; when plan.hr_ceiling.pct_over > 5, plan.hr_ceiling "
            "is not a good point either (a few minutes over a short run can "
            "leave the axis on plan -- it is judged on > 5% AND >= 5 min -- "
            "and still not be a strength)",
            "Read the run against report.purpose; when purpose.source == "
            "'inferred', hedge it -- say the purpose was inferred from the run, "
            "not prescribed",
            "Acknowledge judged_share: when the HR ceiling or the form signals "
            "were judged on only part of the run, say the verdict covers that "
            "part",
            "Write a note for every adverse out-of-range signal and for no other",
            "Write next_challenge as ONE point carried over from today: one of "
            "good_points / growth_points turned into one behaviour cue, with "
            "that point's evidence key in next_challenge_evidence; no named "
            "session and no numbers but the prescription's",
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
