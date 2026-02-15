"""Intensity type to phase mapping and estimation."""


class PhaseMapper:
    """Map Garmin intensity types to training phases."""

    @staticmethod
    def map_intensity_to_phase(intensity_type: str | None) -> str | None:
        """
        Map Garmin intensityType to role_phase.

        Args:
            intensity_type: Garmin intensityType (e.g., "WARMUP", "INTERVAL", "RECOVERY", "COOLDOWN")

        Returns:
            role_phase string or None
        """
        if not intensity_type:
            return None

        intensity_upper = intensity_type.upper()

        if intensity_upper == "WARMUP":
            return "warmup"
        elif intensity_upper in ("INTERVAL", "ACTIVE"):
            return "run"
        elif intensity_upper == "RECOVERY":
            return "recovery"
        elif intensity_upper == "COOLDOWN":
            return "cooldown"
        else:
            return None

    @staticmethod
    def estimate_intensity_type(splits: list[dict]) -> list[str]:
        """
        Estimate intensity_type for splits based on HR and pace patterns.

        Algorithm (validated - 92.7% accuracy):
        - Calculate average HR and pace across all splits
        - For each split in order:
            1. WARMUP: First 2 splits (1 split if total <= 6)
            2. COOLDOWN: Last 2 splits (1 split if total <= 6)
            3. RECOVERY: pace > 400 sec/km AND previous split was INTERVAL/RECOVERY
            4. INTERVAL: pace < avg_pace * 0.90 OR hr > avg_hr * 1.1
            5. ACTIVE: Everything else (default)

        Args:
            splits: List of split dictionaries with 'avg_heart_rate' and 'pace_seconds_per_km' keys

        Returns:
            List of estimated intensity_type strings (same length as splits)
        """
        total_splits = len(splits)

        if total_splits == 0:
            return []

        if total_splits == 1:
            return ["ACTIVE"]

        # Calculate averages (skip splits with missing values)
        hrs: list[float] = [
            float(hr) for s in splits if (hr := s.get("avg_heart_rate")) is not None
        ]
        paces: list[float] = [
            float(pace)
            for s in splits
            if (pace := s.get("pace_seconds_per_km")) is not None
        ]

        avg_hr = sum(hrs) / len(hrs) if hrs else 0.0
        avg_pace = sum(paces) / len(paces) if paces else 0.0

        if avg_hr == 0 and avg_pace == 0:
            return ["ACTIVE"] * total_splits

        warmup_count = 2 if total_splits > 6 else 1
        cooldown_count = 2 if total_splits > 6 else 1

        estimated_types = []
        for idx, split in enumerate(splits):
            split_hr = split.get("avg_heart_rate")
            split_pace = split.get("pace_seconds_per_km")

            position = idx + 1  # 1-based position

            if position <= warmup_count:
                estimated_types.append("WARMUP")
            elif position > total_splits - cooldown_count:
                estimated_types.append("COOLDOWN")
            elif (
                split_pace is not None
                and split_pace > 400
                and idx > 0
                and estimated_types[idx - 1] in ["INTERVAL", "RECOVERY"]
            ):
                estimated_types.append("RECOVERY")
            elif (split_pace is not None and split_pace < avg_pace * 0.90) or (
                split_hr is not None and split_hr > avg_hr * 1.1
            ):
                estimated_types.append("INTERVAL")
            else:
                estimated_types.append("ACTIVE")

        return estimated_types
