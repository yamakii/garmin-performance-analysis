"""Power efficiency calculation for form baseline evaluation.

Handles power efficiency scoring and star ratings.
"""


def calculate_power_efficiency_rating(score: float) -> str:
    """Calculate star rating from power efficiency score.

    Args:
        score: Power efficiency score (actual - expected) / expected

    Returns:
        Star rating string
    """
    if score >= 0.05:
        return "★★★★★"
    elif score >= 0.02:
        return "★★★★☆"
    elif -0.02 <= score < 0.02:
        return "★★★☆☆"
    elif -0.05 <= score < -0.02:
        return "★★☆☆☆"
    else:
        return "★☆☆☆☆"


def calculate_power_efficiency_internal(
    conn,
    activity_id: int,
    activity_date: str,
    user_id: str = "default",
    condition_group: str = "flat_road",
    form_penalties: dict | None = None,
) -> dict | None:
    """Calculate power efficiency (internal function, no DB write).

    Args:
        conn: DuckDB connection
        activity_id: Activity ID
        activity_date: Activity date (YYYY-MM-DD)
        user_id: User ID
        condition_group: Condition group
        form_penalties: Optional dict with gct/vo/vr penalties for integrated score

    Returns:
        Dict with power efficiency evaluation or None if no power data
    """
    from .integrated_score import calculate_integrated_score

    try:
        # Get training mode from hr_efficiency table
        training_mode_row = conn.execute(
            """
            SELECT training_type
            FROM hr_efficiency
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        # Default to low_moderate if not found or NULL
        training_mode = (
            training_mode_row[0]
            if (training_mode_row and training_mode_row[0])
            else "low_moderate"
        )

        # Get baseline (use latest available baseline)
        baseline = conn.execute(
            """
            SELECT power_a, power_b, power_rmse, period_end
            FROM form_baseline_history
            WHERE user_id = ?
              AND condition_group = ?
              AND metric = 'power'
              AND period_start <= ?
            ORDER BY period_end DESC
            LIMIT 1
            """,
            [user_id, condition_group, activity_date],
        ).fetchone()

        if not baseline:
            return None

        power_a, power_b, power_rmse, baseline_period_end = baseline

        # Get average power and speed from splits
        splits_data = conn.execute(
            """
            SELECT AVG(power) as power_avg, AVG(average_speed) as speed_avg
            FROM splits
            WHERE activity_id = ?
              AND power IS NOT NULL
            """,
            [activity_id],
        ).fetchone()

        if not splits_data or splits_data[0] is None:
            return None

        power_avg, speed_actual = splits_data

        # Get base weight (7-day median)
        body_mass_row = conn.execute(
            "SELECT base_weight_kg FROM activities WHERE activity_id = ?",
            [activity_id],
        ).fetchone()

        if not body_mass_row:
            return None

        body_mass = body_mass_row[0]

        if not body_mass or body_mass <= 0:
            return None

        # Calculate power efficiency
        power_wkg = power_avg / body_mass
        speed_expected = power_a + power_b * power_wkg
        score = (speed_actual - speed_expected) / speed_expected
        rating = calculate_power_efficiency_rating(score)
        needs_improvement = score < -0.02

        # Calculate integrated score if form penalties provided
        integrated_score = None
        if form_penalties and all(
            p is not None
            for p in [
                form_penalties.get("gct"),
                form_penalties.get("vo"),
                form_penalties.get("vr"),
            ]
        ):
            # Convert penalties from 0-100 scale to ratio (0-1)
            gct_penalty_ratio = form_penalties["gct"] / 100.0
            vo_penalty_ratio = form_penalties["vo"] / 100.0
            vr_penalty_ratio = form_penalties["vr"] / 100.0

            # Power penalty: negative score means better than expected
            power_penalty_ratio = -score

            penalties = {
                "gct": gct_penalty_ratio,
                "vo": vo_penalty_ratio,
                "vr": vr_penalty_ratio,
                "power": power_penalty_ratio,
            }

            integrated_score = calculate_integrated_score(penalties, training_mode)

        return {
            "avg_w": power_avg,
            "wkg": power_wkg,
            "speed_actual_mps": speed_actual,
            "speed_expected_mps": speed_expected,
            "efficiency_score": score,
            "star_rating": rating,
            "needs_improvement": needs_improvement,
            "integrated_score": integrated_score,
            "training_mode": training_mode,
        }

    except Exception as e:
        import traceback

        print(f"Error in calculate_power_efficiency_internal: {e}")
        traceback.print_exc()
        return None
