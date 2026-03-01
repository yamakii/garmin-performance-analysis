"""Analysis contracts for centralized evaluation policies.

Each section type has a contract that agents can retrieve via
get_analysis_contract MCP tool. This centralizes changeable parameters
(thresholds, star rating logic) in the MCP server, enabling hot-reload
via reload_server() without agent definition changes.
"""

from __future__ import annotations

from typing import Any

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
        },
        "instructions": [
            "Analyze every 1km split without exception",
            "Compare first-half vs second-half metrics for drift detection",
            "Flag measurement anomalies (pace < 3:00/km, HR > 200)",
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
            "cv_thresholds": {
                "low_moderate": {
                    "excellent": "<2%",
                    "good": "<3%",
                    "fair": "<5%",
                    "poor": ">=5%",
                },
                "tempo_threshold": {
                    "excellent": "<3%",
                    "good": "<5%",
                    "fair": "<7%",
                    "poor": ">=7%",
                },
                "interval_sprint": {
                    "work": "<5%",
                    "recovery": "<10%",
                },
            },
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
                "low_moderate": {
                    "normal": "<5%",
                    "mild": "5-8%",
                    "excessive": ">8%",
                },
                "tempo_threshold": {
                    "normal": "<8%",
                    "mild": "8-12%",
                    "excessive": ">12%",
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
            "Base evaluation on training_type mapped to "
            "evaluation_criteria category",
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
                "ideal": ">=180 spm",
                "near_target": "178-179 spm",
                "acceptable": "175-177 spm",
                "needs_improvement": "<175 spm",
            },
            "integrated_score_stars": {
                "5_stars": "95-100",
                "4_stars": "85-94",
                "3_stars": "70-84",
                "2_stars": "50-69",
                "1_star": "<50",
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
            "zone_targets": {
                "base_easy_recovery": {
                    "primary_zones": "Zone 1-2",
                    "target_pct": ">=70%",
                },
                "tempo_threshold": {
                    "primary_zones": "Zone 3-4",
                    "target_pct": ">=60%",
                },
                "interval_sprint": {
                    "primary_zones": "Zone 4-5",
                    "target_pct": ">=50%",
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
            "plan_achievement": {
                "type": "object",
                "description": "Plan vs actual (if planned_workout exists)",
                "optional": True,
            },
        },
        "evaluation_policy": {
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
                    "hr_zone": "Zone 3-4 time +5%",
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
            "plan_achievement": {
                "weights": {"pace": 0.40, "hr": 0.30, "distance": 0.30},
                "scale": [
                    {"stars": 5, "min_pct": 95},
                    {"stars": 4, "min_pct": 85},
                    {"stars": 3, "min_pct": 75},
                    {"stars": 2, "min_pct": 60},
                    {"stars": 1, "min_pct": 0},
                ],
            },
            "training_type_criteria": {
                "base": {
                    "hr_zone_1_2": ">=80%",
                    "pace_cv": "<3%",
                },
                "tempo": {
                    "hr_zone_3_4": ">=60%",
                    "pace_cv": "<5%",
                    "hr_drift": "10-15% allowed",
                },
                "interval": {
                    "work_recovery_contrast": "clear HR amplitude",
                    "hr_drift": "N/A",
                },
                "recovery": {
                    "hr_zone_1_2": ">=90%",
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
            "Include plan_achievement only when planned_workout exists",
            "Use plan_achievement.weights and scale for achievement scoring",
            "Use summary_structure for summary text format",
            "Use next_run_target_variants[type] for target calculation",
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
