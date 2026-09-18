"""Analysis contracts for centralized evaluation policies.

Each section type has a contract that agents can retrieve via
get_analysis_contract MCP tool. This centralizes changeable parameters
(thresholds, star rating logic) in the MCP server, enabling hot-reload
via reload_server() without agent definition changes.
"""

from __future__ import annotations

from typing import Any

from garmin_mcp.database.inserters.hr_efficiency import ZONE_BAND_CUTS

# Index into a ZONE_BAND_CUTS tuple: (excellent_cut, good_cut, fair_cut).
_ZONE_CUT_INDEX = {"excellent": 0, "good": 1, "fair": 2}


def _zone_target(category: str, grade: str = "good") -> str:
    """Return one HR-zone target string from the inserter's ZONE_BAND_CUTS.

    The easy-run target used to be written out three times with three different
    numbers (the inserter cut at 75, this contract at 70, the summary contract
    at 80), so an analysis could quote a guideline the rating was never judged
    against (#1235). Both contracts now read the cut that decides the rating.
    """
    return f">={ZONE_BAND_CUTS[category][_ZONE_CUT_INDEX[grade]]:.0f}%"


# Pace coefficient-of-variation bands, shared by the phase and summary
# contracts (#973). Easy / long / LSD runs are HR-governed and run on 1 km
# auto-laps, so hills, signals and walk breaks make their CV structurally
# larger than a tempo run held at a target pace. Every low_moderate band must
# therefore be >= the corresponding tempo_threshold band.
CV_THRESHOLDS: dict[str, dict[str, str]] = {
    "low_moderate": {
        "excellent": "<5%",
        "good": "<8%",
        "fair": "<12%",
        "poor": ">=12%",
    },
    "tempo_threshold": {
        "excellent": "<3%",
        "good": "<5%",
        "fair": "<7%",
        "poor": ">=7%",
    },
    # A prescribed build-up spans Zone2 to Zone4 on purpose, so its pace CV is
    # structurally the largest of any continuous session -- a Z2->Z4 ramp over
    # 5km moves ~60-90 sec/km by design (#1086). Judging it with the
    # steady-tempo band penalised the athlete for executing the prescription,
    # so the band is separated by category rather than loosened for everyone.
    "progression": {
        "excellent": "<8%",
        "good": "<12%",
        "fair": "<18%",
        "poor": ">=18%",
    },
    "interval_sprint": {
        "work": "<5%",
        "recovery": "<10%",
    },
}


def _cv_band(category: str, grade: str) -> str:
    """Return one pace-CV band string from the shared CV_THRESHOLDS table."""
    return CV_THRESHOLDS[category][grade]


_CONTRACTS: dict[str, dict[str, Any]] = {
    "split": {
        "schema_version": "1.0",
        "section_type": "split",
        "required_fields": {
            "highlights": {
                "type": "string",
                "description": "1 sentence summary, 10-500 chars",
            },
            "analyses": {
                "type": "object",
                "description": "Keys: split_1..split_N, values: Japanese markdown per split",
            },
        },
        "evaluation_policy": {
            "hr_drift": {
                "excellent": "<5%",
                "normal": "5-10%",
                "fatigue": ">10%",
            },
            "pace_stability": {
                "easy": "±10 sec/km",
                "tempo": "±5 sec/km",
            },
            "form_degradation_triggers": {
                "gct": "+10ms above first-half average",
                "vo": "+0.5cm above first-half average",
                "vr": "+0.3% above first-half average",
            },
            "anomaly_thresholds": {
                "pace_too_fast": "< 3:00/km (180 sec/km)",
                "hr_too_high": "> 200 bpm",
            },
            # The split agent holds no HR-zone tool of its own, so a zone label
            # it writes unaided is inference. It said "HR164bpm(Zone4)" and
            # "max171bpm is near LTHR170" with nothing behind it (Issue #1093);
            # correct that day, silently wrong after the next zone revision.
            "hr_zone_labeling": (
                "Name a zone ONLY from the boundaries in CONTEXT.hr_zones_detail "
                "(Garmin native zones). Without those boundaries, state the bpm "
                "and say nothing about zones, LTHR or thresholds -- never infer "
                "a zone from the number"
            ),
            # Splits are where a prescribed ramp is actually visible, so this is
            # the section that should say whether each kilometre answered the
            # step prescribed for it.
            "prescription_alignment": (
                "With CONTEXT.prescription_for_run present, judge each split "
                "against the step prescribed for it (its HR band / target) and "
                "say whether it answered that step -- description alone is not "
                "an evaluation. Axes in prescription_verdict.on_plan came out on "
                "plan and must never be written as deviations. With no "
                "prescription, fall back to describing the splits on their own"
            ),
        },
        "instructions": [
            "Analyze every 1km split without exception",
            "Compare first-half vs second-half metrics for drift detection",
            "Flag measurement anomalies (pace < 3:00/km, HR > 200)",
            "Follow prescription_alignment when the CONTEXT carries a "
            "prescription, and hr_zone_labeling whenever naming a zone",
            "Use Japanese coaching tone with specific numbers",
        ],
    },
    "phase": {
        "schema_version": "1.0",
        "section_type": "phase",
        "required_fields": {
            "warmup_evaluation": {
                "type": "string",
                "description": "Warmup evaluation with star rating",
            },
            "run_evaluation": {
                "type": "string",
                "description": "Main run evaluation with star rating",
            },
            "cooldown_evaluation": {
                "type": "string",
                "description": "Cooldown evaluation with star rating",
            },
            "recovery_evaluation": {
                "type": "string",
                "description": "Recovery evaluation (interval only)",
                "optional": True,
            },
            "evaluation_criteria": {
                "type": "string",
                "description": "Evaluation basis category",
            },
        },
        "evaluation_policy": {
            "star_rating_format": "(★★★★☆ N.N/5.0)",
            "evaluation_criteria": {
                "low_moderate": {
                    "hr_target": "Zone 1-2",
                    "pace_focus": "even pace",
                    "weights": {
                        "hr_control": 0.40,
                        "pace_stability": 0.30,
                        "form": 0.30,
                    },
                },
                "tempo_threshold": {
                    "hr_target": "Zone 3-4",
                    "pace_focus": "negative split allowed",
                    "weights": {
                        "target_pace": 0.40,
                        "hr_control": 0.30,
                        "pace_stability": 0.30,
                    },
                },
                "progression": {
                    "hr_target": "the prescribed ramp (e.g. Z2->Z3->Z4)",
                    "pace_focus": (
                        "monotonic build: each segment at or faster than the "
                        "previous one, fastest at the end. High pace CV is the "
                        "design, not a defect"
                    ),
                    "weights": {
                        "target_pace": 0.40,
                        "hr_control": 0.30,
                        "progression_quality": 0.30,
                    },
                    "progression_quality": (
                        "Score the ramp itself: did HR step through the "
                        "prescribed zones in order and stop at the prescribed "
                        "ceiling? Do NOT score pace stability for this category"
                    ),
                },
                "interval_sprint": {
                    "hr_target": "Zone 4-5",
                    "pace_focus": "work/recovery consistency",
                    "weights": {
                        "work_intensity": 0.40,
                        "recovery_quality": 0.30,
                        "structure": 0.30,
                    },
                },
            },
            "cv_thresholds": CV_THRESHOLDS,
            "warmup_criteria": {
                "low_moderate": {
                    "not_needed": "Warmup not required for low intensity",
                    "star_if_absent": "5.0",
                },
                "tempo_threshold": {
                    "5_star": (
                        "1-2km, main pace +15-30sec/km, " "gradual HR rise to Zone 2"
                    ),
                    "4_star": "Pace diff +10-40sec/km",
                    "3_star": "Present but HR spikes or too short",
                    "star_if_absent": "3.0",
                },
                # A build-up starts easy by design, so its opening segment IS
                # the warmup: a large pace gap to the (fast) closing segment is
                # expected and is not a warmup defect (#1086).
                "progression": {
                    "5_star": (
                        "Opens in the prescribed starting zone with no HR spike"
                    ),
                    "4_star": "Opens one zone off the prescribed start",
                    "3_star": "Starts above the prescribed zone (skipped the ramp)",
                    "star_if_absent": "4.0",
                },
                "interval_sprint": {
                    "5_star": (
                        "2km+, HR to Zone 2 gradually, " "dynamic stretching implied"
                    ),
                    "4_star": "1-2km, adequate pace progression",
                    "3_star": "<1km or HR spikes",
                    "star_if_absent": "1.0",
                },
            },
            "cooldown_criteria": {
                "low_moderate": {
                    "not_needed": "Cooldown not required for low intensity",
                    "star_if_absent": "5.0",
                },
                "tempo_threshold": {
                    "5_star": (
                        "Last 1km at main +20-40sec/km, " "HR drops to Zone 1-2"
                    ),
                    "4_star": "Pace drops but HR stays elevated",
                    "3_star": "Abrupt stop or absent",
                    "star_if_absent": "3.0",
                },
                "progression": {
                    "5_star": (
                        "Cooldown follows the peak segment, HR drops to Zone 1-2"
                    ),
                    "4_star": "Pace drops but HR stays elevated",
                    "3_star": "Abrupt stop or absent",
                    "star_if_absent": "3.0",
                },
                "interval_sprint": {
                    "5_star": (
                        "Last 1km at main +20-40sec/km, " "HR drops to Zone 1-2"
                    ),
                    "4_star": "Pace drops but HR stays elevated",
                    "3_star": "Abrupt stop or absent",
                    "star_if_absent": "1.0",
                },
            },
            "hr_drift_by_type": {
                "definition": (
                    "hr_drift_percentage is now a Pa:HR decoupling metric: "
                    "run-phase laps are split into first/second halves and the "
                    "% drop in speed:HR efficiency is reported. Positive = "
                    "efficiency declined (same pace costs higher HR in the "
                    "second half). <5% indicates good aerobic coupling."
                ),
                "low_moderate": {
                    "good_coupling": "<5%",
                    "mild": "5-8%",
                    "excessive": ">8%",
                },
                "tempo_threshold": {
                    "good_coupling": "<8%",
                    "mild": "8-12%",
                    "excessive": ">12%",
                },
                # Intensity rises through the session by design, so the first /
                # second half comparison overstates decoupling. Only a large
                # positive value is informative.
                "progression": {
                    "good_coupling": "<12%",
                    "mild": "12-18%",
                    "excessive": ">18%",
                },
                "interval_sprint": ("N/A (not applicable for interval structure)"),
            },
            "phase_structures": {
                "normal_run": ["warmup", "run", "cooldown"],
                "interval": ["warmup", "work", "recovery", "cooldown"],
                "detection": (
                    "recovery_splits present → 4-phase, " "otherwise → 3-phase"
                ),
            },
        },
        "instructions": [
            "Evaluate each phase independently using criteria from " "this contract",
            "Include star rating on its own line in parentheses",
            "Base evaluation on CONTEXT.phase_category (already mapped from "
            "training_type / prescription; 'progression' means a prescribed "
            "build-up -- score the ramp, never pace stability)",
            "Use cv_thresholds for pace stability assessment " "per training type",
            "Apply warmup/cooldown criteria based on " "training type category",
            "Use hr_drift_by_type for HR drift assessment " "(skip for interval)",
            "Detect phase structure using " "phase_structures.detection rule",
        ],
    },
    "efficiency": {
        "schema_version": "1.0",
        "section_type": "efficiency",
        "required_fields": {
            "efficiency": {
                "type": "string",
                "description": "5-9 sentences: GCT/VO/VR + power + cadence + integrated_score",
            },
            "evaluation": {
                "type": "string",
                "description": "3-5 sentences: HR zone distribution + training_type",
            },
            "form_trend": {
                "type": "string",
                "description": "2-4 sentences: 1-month baseline comparison",
            },
        },
        "evaluation_policy": {
            "form_ranges": {
                "_note": (
                    "Absolute bands with NO pace term. The same runner reads "
                    "worse at slow paces purely because ground contact and "
                    "vertical ratio scale with speed, so a 'standard' label on "
                    "a slow long run is a pace artifact, not a form flaw. The "
                    "authoritative judgement is the pace-corrected "
                    "form_evaluation.{metric}.star_rating / evaluation_text "
                    "(deviation from the runner's own speed-matched baseline); "
                    "use these bands only as supplementary absolute context and "
                    "never call a band label a weakness on its own."
                ),
                "gct": {
                    "excellent": "<220ms",
                    "good": "220-260ms",
                    "standard": "260-280ms",
                    "needs_improvement": ">280ms",
                },
                "vo": {
                    "excellent": "<6.0cm",
                    "good": "6.0-8.0cm",
                    "standard": "8.0-10.0cm",
                    "needs_improvement": ">10.0cm",
                },
                "vr": {
                    "excellent": "<6.0%",
                    "good": "6.0-8.0%",
                    "standard": "8.0-10.0%",
                    "needs_improvement": ">10.0%",
                },
            },
            "cadence_ranges": {
                "_note": (
                    "Pace-dependent cadence evaluation. "
                    "Do NOT use an absolute 180 spm target."
                ),
                "method": (
                    "Compare form_evaluation.cadence.actual against "
                    "form_evaluation.cadence.expected (pace-dependent baseline "
                    "from the trained model)."
                ),
                "star_rating": (
                    "Use form_evaluation.cadence.star_rating as-is; never "
                    "recompute from a fixed spm threshold."
                ),
                "evaluation_text": (
                    "When narrating cadence, use "
                    "form_evaluation.cadence.evaluation_text "
                    "(already pace-dependent)."
                ),
                "needs_improvement": (
                    "Use the form_evaluation.cadence.needs_improvement flag; "
                    "do not derive needs_improvement from an absolute spm cutoff."
                ),
            },
            # Band tables make the star jump a whole step at an edge, and the
            # LLM mapped the bands itself. The continuous value is computed
            # upstream (#1233), so point at it instead (#1235).
            "integrated_score_stars": {
                "formula": (
                    "stars = 5.0 - (100 - integrated_score) / 20, clamped to 1.0-5.0"
                ),
                "source": (
                    "form_scores.integrated_star_score "
                    "(pre-computed; transcribe, do not recompute)"
                ),
            },
            "power_efficiency_stars": {
                "5_stars": "+5% or more (highly efficient)",
                "4_stars": "+2% to +5% (efficient)",
                "3_stars": "±2% (normal pattern)",
                "2_stars": "-2% to -5% (slightly inefficient)",
                "1_star": "-5% or less (inefficient)",
            },
            "baseline_comparison": {
                "daily_variation_normal": "±5%",
                "baseline_improved": ">+10%",
                "baseline_normal": "±10%",
                "baseline_attention": "<-10%",
            },
            # target_pct is the cut at which the data layer rates the
            # distribution "Good", read from ZONE_BAND_CUTS so the guideline
            # quoted to the athlete is the one the rating used (#1235).
            "zone_targets": {
                "base_easy_recovery": {
                    "primary_zones": "Zone 1-2",
                    "target_pct": _zone_target("easy"),
                },
                "tempo_threshold": {
                    "primary_zones": "Zone 3-4",
                    "target_pct": _zone_target("tempo"),
                },
                "interval_sprint": {
                    "primary_zones": "Zone 4-5",
                    "target_pct": _zone_target("vo2max"),
                },
            },
        },
        "instructions": [
            "Use form_evaluations MCP data as primary source",
            "Retrieve form ranges, cadence, and star rating scales from this contract",
            "Report integrated_score with star rating using integrated_score_stars scale",
            "Compare baseline coefficients with 1-month prior using baseline_comparison thresholds",
            "Evaluate HR zone distribution against zone_targets for the training_type",
            "Use Garmin native HR zones only",
        ],
    },
    "environment": {
        "schema_version": "1.0",
        "section_type": "environment",
        "required_fields": {
            "environmental": {
                "type": "string",
                "description": "4-7 sentences + star rating at end",
            },
        },
        "evaluation_policy": {
            "temperature_by_training_type": {
                "recovery": {
                    "ideal": "<15",
                    "good": "15-22",
                    "acceptable": "22-28",
                    "warm": ">28",
                },
                "base_moderate": {
                    "cold": "<10",
                    "ideal": "10-18",
                    "ok": "18-23",
                    "hot": "23-28",
                    "severe": ">28",
                },
                "tempo_threshold": {
                    "cold": "<8",
                    "ideal": "8-15",
                    "good": "15-20",
                    "warm": "20-25",
                    "hot": ">25",
                },
                "interval_sprint": {
                    "ideal": "8-15",
                    "good": "15-20",
                    "warm": "20-23",
                    "dangerous": "23-28",
                    "extreme": ">28",
                },
            },
            "humidity": {
                "good": "<60%",
                "acceptable": "60-75%",
                "challenging": ">75%",
            },
            "wind_speed_ms": {
                "minimal": "<2",
                "light": "2-4",
                "moderate": "4-6",
                "strong": ">6",
            },
            "terrain_classification": {
                "flat": "<10m/km",
                "undulating": "10-30m/km",
                "hilly": "30-50m/km",
                "mountainous": ">50m/km",
                "note": (
                    "平均が flat 域でも単一区間 gain+loss >=15m なら "
                    "undulating に昇格 (局所の丘を拾う, Issue #473)"
                ),
            },
            "star_rating": {
                "weights": {
                    "temperature": 0.40,
                    "humidity": 0.25,
                    "terrain": 0.20,
                    "wind": 0.15,
                },
                "scale": [
                    {
                        "stars": "5.0",
                        "description": "All conditions optimal",
                    },
                    {
                        "stars": "4.5-4.9",
                        "description": "1 factor slightly suboptimal",
                    },
                    {
                        "stars": "4.0-4.4",
                        "description": "Multiple minor issues",
                    },
                    {
                        "stars": "3.5-3.9",
                        "description": "Noticeable environmental burden",
                    },
                    {
                        "stars": "≤3.0",
                        "description": "Multiple challenging factors",
                    },
                ],
            },
        },
        "instructions": [
            "Use weather.json data (not device temperature)",
            "Retrieve training_type and evaluate temperature using "
            "temperature_by_training_type[category]",
            "Evaluate humidity, wind (m/s), and terrain using thresholds "
            "from this contract",
            "Compute weighted star rating using star_rating.weights",
            "Star rating reflects overall environmental favorability",
        ],
    },
    "summary": {
        "schema_version": "1.0",
        "section_type": "summary",
        "required_fields": {
            "star_rating": {
                "type": "string",
                "description": "Format: ★★★★☆ N.N/5.0",
            },
            "integrated_score": {
                "type": "number",
                "description": "0-100, null if unavailable",
                "optional": True,
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence assessment",
            },
            "key_strengths": {
                "type": "array",
                "description": "3-5 items with numbers",
            },
            "improvement_areas": {
                "type": "array",
                "description": "Max 2 items",
            },
            "next_action": {
                "type": "string",
                "description": "1 action with numeric target + success condition",
            },
            "next_run_target": {
                "type": "object",
                "description": "Target varying by training type",
            },
            "recommendations": {
                "type": "string",
                "description": "Max 2 in structured markdown",
            },
            "prescription_verdict": {
                "type": "object",
                "description": (
                    "Transcribe CONTEXT.prescription_verdict verbatim "
                    "({verdict, prescription_title, reasons}); omit when the "
                    "day had no prescription. Never recompute the verdict"
                ),
                "optional": True,
            },
            "vs_previous": {
                "type": "object",
                "description": (
                    "Transcribe CONTEXT.vs_previous verbatim (deltas vs the "
                    "last same-type run); omit when no comparable run exists"
                ),
                "optional": True,
            },
        },
        "evaluation_policy": {
            "prescription_vs_actual": {
                "verdicts": {
                    "✅": "ran the prescribed session",
                    "🟡": "one deviation (volume, HR or a lower intensity class)",
                    "🔴": "risk-side deviation (higher intensity, rest day run, "
                    "HR over ceiling by >10bpm, volume >1.50x)",
                },
                "rules": [
                    "Transcribe prescription_verdict / vs_previous; never "
                    "recompute or soften them",
                    "Axes named in prescription_verdict.on_plan (intensity_class"
                    " / volume / hr_ceiling / rest) came out ON PLAN: never list"
                    " them in improvement_areas or recommendations, never call "
                    "them a shortfall, and never invent a cause for them -- a "
                    "volume of 89% inside the 85-130% band is the plan met, not "
                    "a distance the athlete failed to finish",
                    "A ✅ verdict must appear in key_strengths, and next_action "
                    "builds on the plan (the next prescribed step) instead of "
                    "correcting a session that was executed as prescribed",
                    "next_run_target is deterministic: transcribe its HR band "
                    "and paces verbatim and never restate the run's own average "
                    "HR as the next target",
                    "next_action must follow week_position.ladder_step.next "
                    "when it exists (never propose extending distance on top "
                    "of the ladder)",
                    "A 🔴 verdict is addressed by next_action first",
                    "Mention morning_wellness when readiness < 50 or rhr_z > 1.0",
                    "vs_previous form deltas within noise (|gct| < 5ms, "
                    "|cadence| < 2spm) are not problems",
                ],
                "form_delta_noise": {"gct_ms": 5, "cadence_spm": 2},
                "wellness_mention_thresholds": {"readiness": 50, "rhr_z": 1.0},
            },
            "star_rating": {
                "weights": {
                    "form_efficiency": 0.30,
                    "pace_consistency": 0.25,
                    "hr_management": 0.25,
                    "execution_quality": 0.20,
                },
                "scale": [
                    {"stars": "5.0", "min": 4.5, "description": "Exceptional"},
                    {"stars": "4.0-4.9", "min": 3.5, "description": "Strong"},
                    {"stars": "3.0-3.9", "min": 2.5, "description": "Adequate"},
                    {
                        "stars": "2.0-2.9",
                        "min": 1.5,
                        "description": "Below expectations",
                    },
                    {"stars": "1.0-1.9", "min": 0, "description": "Poor"},
                ],
            },
            "next_run_target_variants": {
                "base_easy": {
                    "distance": "±10%",
                    "pace": "±5sec/km (reference only)",
                    "hr_cap": "avg+5bpm, ≤Zone2 upper",
                    "focus": "HR range primary, pace secondary",
                },
                "tempo": {
                    "distance": "same or +1km",
                    "pace": "-3sec/km (gradual improvement)",
                    "hr_band": (
                        "transcribe next_run_target.target_hr_low/high "
                        "(prescription > Garmin Zone3-4 > recent average); "
                        "never the run's own avg_hr"
                    ),
                },
                "interval": {
                    "sets": "same or +1 rep",
                    "pace": "±3sec/km",
                    "recovery": "HR drops to Zone 2 before next set",
                },
                "long_run": {
                    "distance": "+1-2km (≤30% weekly volume)",
                    "pace": "Easy pace (HR Zone 1-2)",
                    "nutrition": "Plan fueling if >60min",
                },
            },
            "recommendations": {
                "max_count": 2,
                "format": {
                    "heading": "### N. Title ⭐ 重要度: 高/中/低",
                    "sections": [
                        "**現状:**",
                        "**推奨アクション:**",
                        "**期待効果:**",
                    ],
                    "separator": "---",
                },
                "rules": [
                    "Specific numbers required (no generic advice)",
                    "Easy run suggestions use HR range, not pace",
                    "Each recommendation must include measurable target",
                ],
            },
            "training_type_criteria": {
                "base": {
                    "hr_zone_1_2": _zone_target("easy"),
                    "pace_cv": _cv_band("low_moderate", "good"),
                },
                "tempo": {
                    "hr_zone_3_4": _zone_target("tempo"),
                    "pace_cv": _cv_band("tempo_threshold", "good"),
                    "hr_drift": "10-15% allowed",
                },
                # A prescribed build-up spends its opening kilometres in Zone2
                # on purpose and carries the warmup / cooldown its registered
                # workout adds, so the whole-run Zone3-4 share is the wrong
                # test: what matters is that the peak segment reached the
                # prescribed zone (#1086).
                "progression": {
                    "hr_zone_3_4": (
                        "not applicable -- judge whether the peak segment "
                        "reached the prescribed zone"
                    ),
                    "pace_cv": _cv_band("progression", "good"),
                    "hr_drift": "10-15% allowed",
                },
                "interval": {
                    "work_recovery_contrast": "clear HR amplitude",
                    "hr_drift": "N/A",
                },
                # Recovery asks for the "Excellent" easy cut, not the "Good"
                # one a base run is judged on.
                "recovery": {
                    "hr_zone_1_2": _zone_target("easy", "excellent"),
                    "form_eval": "not required",
                },
                "race": {
                    "pacing": "negative split or even",
                    "hr_drift": "expected",
                },
            },
            "summary_structure": {
                "line_1": "training_type + distance + overall rating (1 sentence)",
                "line_2": "Best aspect with specific number",
                "line_3": "Improvement point with number (optional if none)",
            },
            "next_action_count": 1,
        },
        "instructions": [
            "Retrieve star_rating weights and training_type_criteria from this contract",
            "Exactly 1 next_action with numeric target and success condition",
            "Maximum recommendations per recommendations.max_count",
            "Follow recommendations.format for structured markdown",
            "Easy run suggestions use HR range, not pace",
            "Use summary_structure for summary text format",
            "Use next_run_target_variants[type] for target calculation",
            "Transcribe CONTEXT.prescription_verdict and CONTEXT.vs_previous "
            "verbatim; follow prescription_vs_actual.rules for next_action, "
            "wellness mentions and form-delta noise",
        ],
    },
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
                    "1-2 sentences; numbers transcribed from next_run_target. An "
                    "HR ceiling is written as a guard "
                    "('150 bpm を超えないように') together with where HR should settle"
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
                "not kilometre by kilometre"
            ),
            "weighting": (
                "Say which of the findings actually matters and which the "
                "athlete can ignore today"
            ),
            "next_action": (
                "One concrete next step, with the numbers transcribed from "
                "next_run_target and an HR ceiling written as a guard"
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
            "point, or a note that repeats the timeline)",
            "A pass/fail judgement of the athlete -- growth points are room to "
            "grow or a maintenance target",
            "A scene, cause or comparison that no evidence key supports",
        ],
        # How an ``evidence`` / ``moment_id`` / ``signal`` key is resolved by
        # ``validators.check_run_note_grounding`` at merge time.
        "evidence_keys": {
            "plan.<axis>": "an axis of report.plan.checks (rejected when plan is null)",
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
                "run gets exactly one item on the 'steady' scene. Never invent a "
                "scene the moments do not contain"
            ),
            "next_challenge": (
                "Transcribe the numbers from next_run_target. An HR ceiling is a "
                "guard ('150 bpm を超えないように') plus where HR should settle, "
                "never a pass/fail target"
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
            "Transcribe next_challenge numbers from next_run_target and write an "
            "HR ceiling as a guard with its settling range",
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
