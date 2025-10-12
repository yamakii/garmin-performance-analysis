"""Activity type classification based on HR zones, distance, and power.

This module provides the ActivityClassifier class for classifying running activities
into 6 training types based on heart rate zone distribution, distance, and power metrics.
"""

from typing import Any


class ActivityClassifier:
    """Classify running activities into training types.

    Classifies activities into 6 types based on HR zones, distance, and power:
    - Base Run (有酸素ベース走): HR Zone 1-2 is 60%+
    - Threshold Run (閾値走): HR Zone 4 is 30%+
    - Sprint/Interval (スプリント/インターバル): HR Zone 5 is 20%+
    - Anaerobic (無酸素走): power > 300W or HR Zone 5 is 50%+
    - Long Run (ロング走): distance > 15km and Base Run criteria
    - Recovery (リカバリー走): HR Zone 1 is 70%+

    Priority order (highest to lowest):
    1. Recovery (most specific)
    2. Anaerobic
    3. Sprint/Interval
    4. Threshold Run
    5. Long Run
    6. Base Run (most general)
    """

    # Training type definitions
    TRAINING_TYPES = {
        "recovery": {
            "en": "Recovery",
            "ja": "リカバリー走",
            "description": "Very easy recovery run in HR Zone 1",
        },
        "anaerobic": {
            "en": "Anaerobic",
            "ja": "無酸素走",
            "description": "High-intensity anaerobic effort",
        },
        "sprint_interval": {
            "en": "Sprint/Interval",
            "ja": "スプリント/インターバル",
            "description": "Sprint or interval training with HR Zone 5",
        },
        "threshold": {
            "en": "Threshold Run",
            "ja": "閾値走",
            "description": "Lactate threshold training in HR Zone 4",
        },
        "long_run": {
            "en": "Long Run",
            "ja": "ロング走",
            "description": "Long distance aerobic base run",
        },
        "base": {
            "en": "Base Run",
            "ja": "有酸素ベース走",
            "description": "Aerobic base building in HR Zone 1-2",
        },
        "unknown": {
            "en": "Unknown",
            "ja": "不明",
            "description": "Unable to classify activity type",
        },
    }

    def __init__(self) -> None:
        """Initialize ActivityClassifier."""
        pass

    def classify(
        self,
        hr_zones_data: dict[str, Any] | None,
        distance_km: float,
        avg_power: float | None,
    ) -> dict[str, Any]:
        """Classify activity type based on HR zones, distance, and power.

        Args:
            hr_zones_data: Heart rate zones data with zone distribution.
                Format: {"zones": [{"zone_number": int, "zone_percentage": float}, ...]}
            distance_km: Total distance in kilometers.
            avg_power: Average power in watts (optional).

        Returns:
            Dictionary containing:
                - type_en: Training type in English
                - type_ja: Training type in Japanese
                - confidence: Classification confidence (high/medium/low)
                - description: Brief description

        Examples:
            >>> classifier = ActivityClassifier()
            >>> hr_data = {"zones": [
            ...     {"zone_number": 1, "zone_percentage": 35.0},
            ...     {"zone_number": 2, "zone_percentage": 35.0},
            ...     {"zone_number": 3, "zone_percentage": 20.0},
            ...     {"zone_number": 4, "zone_percentage": 7.0},
            ...     {"zone_number": 5, "zone_percentage": 3.0},
            ... ]}
            >>> result = classifier.classify(hr_data, 10.0, None)
            >>> print(result["type_en"])
            Base Run
        """
        # Handle missing or invalid HR zones data
        if (
            not hr_zones_data
            or "zones" not in hr_zones_data
            or not hr_zones_data["zones"]
        ):
            return {
                "type_en": self.TRAINING_TYPES["unknown"]["en"],
                "type_ja": self.TRAINING_TYPES["unknown"]["ja"],
                "confidence": "low",
                "description": self.TRAINING_TYPES["unknown"]["description"],
            }

        # Extract zone percentages
        zone_percentages = self._extract_zone_percentages(hr_zones_data["zones"])

        # Classify by HR zones and distance/power
        training_type = self._classify_by_hr_zones(
            zone_percentages, distance_km, avg_power
        )

        # Assess confidence
        confidence = self._assess_confidence(zone_percentages, training_type)

        return {
            "type_en": self.TRAINING_TYPES[training_type]["en"],
            "type_ja": self.TRAINING_TYPES[training_type]["ja"],
            "confidence": confidence,
            "description": self.TRAINING_TYPES[training_type]["description"],
        }

    def _extract_zone_percentages(
        self, zones: list[dict[str, Any]]
    ) -> dict[int, float]:
        """Extract zone percentages from zones data.

        Args:
            zones: List of zone dictionaries with zone_number and zone_percentage.

        Returns:
            Dictionary mapping zone number to percentage.
        """
        zone_percentages = {}
        for zone in zones:
            zone_num = zone.get("zone_number")
            zone_pct = zone.get("zone_percentage", 0.0)
            if zone_num is not None:
                zone_percentages[zone_num] = zone_pct
        return zone_percentages

    def _classify_by_hr_zones(
        self,
        zone_percentages: dict[int, float],
        distance_km: float,
        avg_power: float | None,
    ) -> str:
        """Classify training type by HR zones, distance, and power.

        Priority order (highest to lowest):
        1. Recovery (HR Zone 1 >= 70%)
        2. Anaerobic (power > 300W or HR Zone 5 >= 50%)
        3. Sprint/Interval (HR Zone 5 >= 20%)
        4. Threshold Run (HR Zone 4 >= 30%)
        5. Long Run (distance > 15km and Zone 1+2 >= 60%)
        6. Base Run (HR Zone 1+2 >= 60%)
        7. Unknown (default)

        Args:
            zone_percentages: Dictionary mapping zone number to percentage.
            distance_km: Total distance in kilometers.
            avg_power: Average power in watts (optional).

        Returns:
            Training type key.
        """
        # Get zone percentages (default to 0.0 if not present)
        zone1 = zone_percentages.get(1, 0.0)
        zone2 = zone_percentages.get(2, 0.0)
        zone4 = zone_percentages.get(4, 0.0)
        zone5 = zone_percentages.get(5, 0.0)

        # Priority 1: Recovery (HR Zone 1 >= 70%)
        if zone1 >= 70.0:
            return "recovery"

        # Priority 2: Anaerobic (power > 300W or HR Zone 5 >= 50%)
        if avg_power is not None and avg_power > 300.0:
            return "anaerobic"
        if zone5 >= 50.0:
            return "anaerobic"

        # Priority 3: Sprint/Interval (HR Zone 5 >= 20%)
        if zone5 >= 20.0:
            return "sprint_interval"

        # Priority 4: Threshold Run (HR Zone 4 >= 30%)
        if zone4 >= 30.0:
            return "threshold"

        # Priority 5: Long Run (distance > 15km and Zone 1+2 >= 60%)
        if distance_km > 15.0 and (zone1 + zone2) >= 60.0:
            return "long_run"

        # Priority 6: Base Run (HR Zone 1+2 >= 60%)
        if (zone1 + zone2) >= 60.0:
            return "base"

        # Default: Unknown
        return "unknown"

    def _assess_confidence(
        self,
        zone_percentages: dict[int, float],
        training_type: str,
    ) -> str:
        """Assess classification confidence based on zone distribution.

        High confidence:
            - Recovery: Zone 1 >= 70%
            - Anaerobic: Zone 5 >= 50% or power > 300W
            - Threshold: Zone 4 >= 30%
            - Sprint: Zone 5 >= 20%
            - Base/Long Run: Zone 1+2 >= 60%
        Medium confidence: Moderate distribution (20-30% spread across zones)
        Low confidence: Very distributed (<20% in any zone) or unknown type

        Args:
            zone_percentages: Dictionary mapping zone number to percentage.
            training_type: Classified training type.

        Returns:
            Confidence level: "high", "medium", or "low".
        """
        if training_type == "unknown":
            return "low"

        # Get zone percentages
        zone1 = zone_percentages.get(1, 0.0)
        zone2 = zone_percentages.get(2, 0.0)
        zone4 = zone_percentages.get(4, 0.0)
        zone5 = zone_percentages.get(5, 0.0)

        # Type-specific confidence assessment
        if training_type == "recovery":
            # Recovery: High if Zone 1 >= 70%
            return "high" if zone1 >= 70.0 else "medium"

        elif training_type == "anaerobic":
            # Anaerobic: High if Zone 5 >= 50% (or power > 300W, assumed high)
            return "high" if zone5 >= 50.0 else "high"  # Power-based is always high

        elif training_type == "sprint_interval":
            # Sprint: High if Zone 5 >= 20%
            return "high" if zone5 >= 20.0 else "medium"

        elif training_type == "threshold":
            # Threshold: High if Zone 4 >= 30%
            return "high" if zone4 >= 30.0 else "medium"

        elif training_type in ["base", "long_run"]:
            # Base/Long: High if Zone 1+2 >= 60%
            return "high" if (zone1 + zone2) >= 60.0 else "medium"

        # For other cases, use max zone percentage
        if not zone_percentages:
            return "low"

        max_zone_pct = max(zone_percentages.values())

        if max_zone_pct >= 30.0:
            return "medium"
        else:
            return "low"
