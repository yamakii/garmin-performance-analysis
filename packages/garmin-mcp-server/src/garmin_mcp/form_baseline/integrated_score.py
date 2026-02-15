"""Integrated score calculation with training mode-specific weights."""

# Training mode weights (must sum to 1.0)
TRAINING_MODE_WEIGHTS = {
    "interval_sprint": {
        "w_gct": 0.30,
        "w_vo": 0.15,
        "w_vr": 0.15,
        "w_power": 0.40,  # Power efficiency重視
    },
    "tempo_threshold": {
        "w_gct": 0.25,
        "w_vo": 0.20,
        "w_vr": 0.20,
        "w_power": 0.35,
    },
    "low_moderate": {
        "w_gct": 0.30,
        "w_vo": 0.25,
        "w_vr": 0.25,
        "w_power": 0.20,  # Power efficiency軽視
    },
}


def calculate_integrated_score(
    penalties: dict[str, float | None], training_mode: str = "low_moderate"
) -> float:
    """Calculate 100-point integrated score with mode-specific weights.

    Args:
        penalties: Dictionary with keys 'gct', 'vo', 'vr', 'power'
                   Values are penalty ratios (positive = worse than expected, negative = better)
                   Example: {'gct': 0.1, 'vo': 0.05, 'vr': -0.02, 'power': 0.08}
                   Power can be None if no power data available
        training_mode: Training mode for weight selection
                       ('interval_sprint', 'tempo_threshold', 'low_moderate')

    Returns:
        Score (0-100+, higher is better)
        Can exceed 100 if all penalties are negative (better than expected)

    Formula:
        score = 100 - (w_gct * |penalty_gct| + w_vo * |penalty_vo| +
                       w_vr * |penalty_vr| + w_power * |penalty_power|) * 100

    Notes:
        - If power is None, power penalty is excluded and other weights are normalized
        - Negative penalties (improvements) increase the score above 100
    """
    # Get weights for training mode (fallback to low_moderate)
    weights = TRAINING_MODE_WEIGHTS.get(
        training_mode, TRAINING_MODE_WEIGHTS["low_moderate"]
    )

    # Extract penalties (ensure float type for non-None values)
    penalty_gct: float = penalties.get("gct") or 0.0
    penalty_vo: float = penalties.get("vo") or 0.0
    penalty_vr: float = penalties.get("vr") or 0.0
    penalty_power: float | None = penalties.get("power")

    # Calculate weighted penalty sum
    if penalty_power is None:
        # No power data: exclude power penalty and normalize other weights
        total_weight = weights["w_gct"] + weights["w_vo"] + weights["w_vr"]
        normalized_w_gct = weights["w_gct"] / total_weight
        normalized_w_vo = weights["w_vo"] / total_weight
        normalized_w_vr = weights["w_vr"] / total_weight

        weighted_penalty = (
            normalized_w_gct * penalty_gct
            + normalized_w_vo * penalty_vo
            + normalized_w_vr * penalty_vr
        )
    else:
        # With power data: use all weights
        weighted_penalty = (
            weights["w_gct"] * penalty_gct
            + weights["w_vo"] * penalty_vo
            + weights["w_vr"] * penalty_vr
            + weights["w_power"] * penalty_power
        )

    # Convert to 100-point scale
    score = 100.0 - (weighted_penalty * 100.0)

    return score
