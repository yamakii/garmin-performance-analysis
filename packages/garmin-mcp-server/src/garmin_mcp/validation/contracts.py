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
            "warmup_criteria": {
                "excellent": "Gradual HR rise to Zone 2, 10-15 min",
                "good": "Adequate preparation, minor inconsistency",
                "poor": "Too short (<5 min) or too intense (Zone 3+)",
            },
            "cooldown_criteria": {
                "excellent": "Gradual HR descent, 5-10 min",
                "good": "Present but brief",
                "poor": "Absent or abrupt stop",
            },
        },
        "instructions": [
            "Evaluate each phase independently",
            "Include star rating on its own line in parentheses",
            "Base evaluation on training_type from prefetch context",
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
            "gct": {
                "excellent": "220-260ms",
                "good": "260-280ms",
                "needs_improvement": ">280ms",
            },
            "vertical_oscillation": {
                "excellent": "6-8cm",
                "good": "8-10cm",
                "needs_improvement": ">10cm",
            },
            "vertical_ratio": {
                "ideal": "8-10%",
                "acceptable": "7-11%",
                "needs_improvement": ">11%",
            },
            "cadence": {
                "ideal": ">=180 spm",
                "acceptable": "175-179 spm",
                "needs_improvement": "<175 spm",
            },
            "integrated_score_stars": {
                "5_stars": "95-100",
                "4_stars": "85-94",
                "3_stars": "70-84",
                "2_stars": "50-69",
                "1_star": "<50",
            },
        },
        "instructions": [
            "Use form_evaluations MCP data as primary source",
            "Report integrated_score with star rating",
            "Compare baseline coefficients with 1-month prior",
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
            "temperature": {
                "optimal": "10-15°C",
                "good": "5-10°C or 15-20°C",
                "challenging": "0-5°C or 20-25°C",
                "severe": "<0°C or >25°C",
            },
            "humidity": {
                "optimal": "40-60%",
                "acceptable": "30-40% or 60-70%",
                "challenging": "<30% or >70%",
            },
            "wind": {
                "calm": "0-10 km/h",
                "moderate": "10-20 km/h",
                "strong": "20-30 km/h",
                "severe": ">30 km/h",
            },
            "terrain_classification": {
                "flat": "<10m/km",
                "undulating": "10-20m/km",
                "hilly": "20-40m/km",
                "mountainous": ">40m/km",
            },
        },
        "instructions": [
            "Use weather.json data (not device temperature)",
            "Evaluate combined impact of temperature + humidity + wind",
            "Include terrain classification from elevation data",
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
            "star_rating_scale": {
                "5.0": "Exceptional",
                "4.0-4.9": "Strong",
                "3.0-3.9": "Adequate",
                "2.0-2.9": "Below expectations",
                "1.0-1.9": "Poor",
            },
            "next_run_target_variants": {
                "easy_recovery": [
                    "recommended_type",
                    "target_hr_low",
                    "target_hr_high",
                    "reference_pace_low_formatted",
                    "reference_pace_high_formatted",
                    "success_criterion",
                    "adjustment_tip",
                    "summary_ja",
                ],
                "tempo_threshold": [
                    "recommended_type",
                    "target_pace_low_formatted",
                    "target_pace_high_formatted",
                    "target_hr",
                    "success_criterion",
                    "adjustment_tip",
                    "summary_ja",
                ],
                "interval": [
                    "recommended_type",
                    "target_pace_low_formatted",
                    "target_pace_high_formatted",
                    "success_criterion",
                    "adjustment_tip",
                    "summary_ja",
                ],
                "data_insufficient": [
                    "insufficient_data",
                    "summary_ja",
                ],
            },
            "recommendations_max": 2,
            "next_action_count": 1,
        },
        "instructions": [
            "Exactly 1 next_action with numeric target and success condition",
            "Maximum 2 recommendations with specific numbers",
            "Easy run suggestions use HR range, not pace",
            "Include plan_achievement only when planned_workout exists",
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
