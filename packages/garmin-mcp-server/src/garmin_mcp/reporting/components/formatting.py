"""Formatting utility functions extracted from ReportGeneratorWorker."""

import re
from typing import Any


def format_pace(pace_seconds_per_km: float) -> str:
    """Format pace as MM:SS/km.

    Args:
        pace_seconds_per_km: Pace in seconds per kilometer

    Returns:
        Formatted pace string (e.g., "4:30/km")
    """
    minutes = int(pace_seconds_per_km / 60)
    seconds = int(pace_seconds_per_km % 60)
    return f"{minutes}:{seconds:02d}/km"


def get_activity_type_display(training_type: str) -> dict[str, str]:
    """Map training_type to Japanese display name and English subtitle.

    Args:
        training_type: DuckDB training_type value

    Returns:
        dict with keys: "ja" (Japanese name), "en" (English name), "description"
    """
    mapping = {
        "recovery": {
            "ja": "リカバリーラン",
            "en": "Recovery Run",
            "description": "軽い有酸素運動で疲労回復を促進",
        },
        "aerobic_base": {
            "ja": "有酸素ベース走",
            "en": "Aerobic Base",
            "description": "心拍ゾーン2-3中心の中強度トレーニング。有酸素能力の基盤構築に最適な強度です。",
        },
        "tempo": {
            "ja": "テンポラン",
            "en": "Tempo Run",
            "description": "心拍ゾーン3-4の中高強度。閾値走より少し楽なペースで持久力を強化",
        },
        "lactate_threshold": {
            "ja": "乳酸閾値トレーニング",
            "en": "Lactate Threshold",
            "description": "3フェーズ構成（ウォームアップ-メイン-クールダウン）で、閾値ペースを維持する持久力強化トレーニング。Zone 4中心で乳酸処理能力を向上させることが目的です。",
        },
        "vo2max": {
            "ja": "VO2 Maxトレーニング",
            "en": "VO2 Max Training",
            "description": "最大酸素摂取量向上を目的とした高強度インターバル",
        },
        "anaerobic_capacity": {
            "ja": "無酸素容量トレーニング",
            "en": "Anaerobic Capacity",
            "description": "短時間高強度で無酸素能力を強化",
        },
        "speed": {
            "ja": "スピードトレーニング",
            "en": "Speed Training",
            "description": "短距離スプリントでスピードとパワーを強化",
        },
        "interval_training": {
            "ja": "インターバルトレーニング",
            "en": "Interval Training",
            "description": "1km×5本のWorkセグメントをZone 4-5（閾値〜最大心拍）で実施し、400mのRecoveryで回復する高強度トレーニング。VO2 max向上とスピード持久力の強化が目的です。",
        },
    }
    return mapping.get(
        training_type,
        {
            "ja": "その他のトレーニング",
            "en": "Other Training",
            "description": "分類不明のトレーニング",
        },
    )


def get_training_type_category(training_type: str) -> str:
    """Map training_type to template category for conditional logic.

    Args:
        training_type: DuckDB training_type value

    Returns:
        Category string:
        - "low_moderate": recovery, aerobic_base, aerobic_endurance, unknown
        - "tempo_threshold": tempo, lactate_threshold
        - "interval_sprint": vo2max, anaerobic_capacity, speed, interval_training

    This categorization is used for:
    - Showing/hiding physiological indicators summary
    - Selecting appropriate comparison pace (main_set vs overall)
    - Determining evaluation focus (overall vs specific phases)
    """
    interval_sprint = {
        "vo2max",
        "anaerobic_capacity",
        "speed",
        "interval_training",
    }
    tempo_threshold = {"tempo", "lactate_threshold"}

    if training_type in interval_sprint:
        return "interval_sprint"
    elif training_type in tempo_threshold:
        return "tempo_threshold"
    else:
        # Default to low_moderate for recovery, aerobic_base, and unknown types
        return "low_moderate"


def extract_phase_ratings(section_analyses: dict[str, Any]) -> dict[str, Any]:
    """Extract phase evaluation ratings from section analyses.

    Parses star ratings from phase evaluation texts like "(★★★★★)".

    Args:
        section_analyses: Section analyses dictionary containing phase evaluations

    Returns:
        Dictionary with warmup_rating, run_rating, recovery_rating, cooldown_rating.
        Each rating contains 'score' (float) and 'stars' (str).
    """

    def parse_rating(text: str | None) -> dict[str, Any]:
        """Parse star rating from text."""
        if not text:
            return {"score": 0, "stars": ""}

        # Extract (★...) pattern
        match = re.search(r"\(([★☆]+)\)", text)
        if not match:
            return {"score": 0, "stars": ""}

        stars_text = match.group(1)
        full_stars = stars_text.count("★")
        empty_stars = stars_text.count("☆")

        score = float(full_stars)
        stars = "★" * full_stars + "☆" * empty_stars

        return {"score": score, "stars": stars}

    # Get phase data from section_analyses
    phase_data = section_analyses.get("phase_evaluation") or section_analyses.get(
        "phase", {}
    )

    if not phase_data:
        return {
            "warmup_rating": {"score": 0, "stars": ""},
            "run_rating": {"score": 0, "stars": ""},
            "recovery_rating": {"score": 0, "stars": ""},
            "cooldown_rating": {"score": 0, "stars": ""},
        }

    # Extract ratings from evaluation texts
    warmup_text = phase_data.get("warmup_evaluation", "")
    run_text = phase_data.get("run_evaluation", "")
    recovery_text = phase_data.get("recovery_evaluation", "")
    cooldown_text = phase_data.get("cooldown_evaluation", "")

    return {
        "warmup_rating": parse_rating(warmup_text),
        "run_rating": parse_rating(run_text),
        "recovery_rating": parse_rating(recovery_text),
        "cooldown_rating": parse_rating(cooldown_text),
    }
