"""Form baseline evaluator module.

Evaluates activity form metrics against pace-adjusted baselines and stores results.

Helper logic has been extracted to:
- model_loader: Load trained models from file or DuckDB
- data_fetcher: Fetch splits data from DuckDB
- power_calculator: Power efficiency scoring
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

from .data_fetcher import get_splits_data
from .model_loader import load_models_from_db, load_models_from_file
from .power_calculator import (
    calculate_power_efficiency_internal,
)
from .scorer import compute_star_rating, score_observation
from .text_generator import generate_evaluation_text, generate_overall_text


def evaluate_and_store(
    activity_id: int,
    activity_date: str,
    db_path: str,
    condition_group: str = "flat_road",
    model_file: Path | None = None,
) -> dict[str, Any]:
    """Evaluate activity form metrics and store results.

    This is the main entry point for form evaluation. It loads trained models,
    fetches actual form data from splits, predicts expected values, scores
    the observations, generates Japanese evaluation text, and returns the
    complete evaluation result.

    Args:
        activity_id: Garmin activity ID
        activity_date: Activity date (YYYY-MM-DD format)
        db_path: Path to DuckDB database
        condition_group: Condition group name (default: 'flat_road')
        model_file: Path to trained model file (optional, uses default location)

    Returns:
        Evaluation dictionary containing:
            - activity_id: int
            - gct: {actual, expected, delta_pct, star_rating, score,
                    needs_improvement, evaluation_text}
            - vo: {same structure as gct}
            - vr: {same structure as gct}
            - cadence: {actual, minimum, achieved}
            - overall_score: float (0-5.0)
            - overall_star_rating: str

    Raises:
        FileNotFoundError: If model file doesn't exist
        ValueError: If no splits found for activity
    """
    # Load models
    if model_file is None:
        models = load_models_from_db(
            db_path=db_path,
            activity_date=activity_date,
            user_id="default",
            condition_group=condition_group,
        )
    else:
        models = load_models_from_file(model_file)

    # Get actual data from splits
    splits_data = get_splits_data(db_path, activity_id)

    # Build observation dict for scorer
    obs = {
        "pace_s_per_km": splits_data["pace_s_per_km"],
        "gct_ms": splits_data["gct_ms"],
        "vo_cm": splits_data["vo_cm"],
        "vr_pct": splits_data["vr_pct"],
    }

    # Predict expectations and score
    score_result = score_observation(models, obs)

    # Compute star ratings
    gct_rating = compute_star_rating(
        penalty=score_result["gct_penalty"],
        delta_pct=score_result["gct_delta_pct"],
    )
    vo_rating = compute_star_rating(
        penalty=score_result["vo_penalty"],
        delta_pct=score_result["vo_delta_pct"],
    )
    vr_rating = compute_star_rating(
        penalty=score_result["vr_penalty"],
        delta_pct=score_result["vr_delta_pct"],
    )

    # Generate evaluation text for each metric
    gct_text = generate_evaluation_text(
        metric="gct",
        actual=score_result["gct_ms_actual"],
        expected=score_result["gct_ms_exp"],
        delta_pct=score_result["gct_delta_pct"],
        pace_s_per_km=splits_data["pace_s_per_km"],
        star_rating=gct_rating["star_rating"],
        score=gct_rating["score"],
    )

    vo_text = generate_evaluation_text(
        metric="vo",
        actual=score_result["vo_cm_actual"],
        expected=score_result["vo_cm_exp"],
        delta_pct=score_result["vo_delta_pct"],
        pace_s_per_km=splits_data["pace_s_per_km"],
        star_rating=vo_rating["star_rating"],
        score=vo_rating["score"],
    )

    vr_text = generate_evaluation_text(
        metric="vr",
        actual=score_result["vr_pct_actual"],
        expected=score_result["vr_pct_exp"],
        delta_pct=score_result["vr_delta_pct"],
        pace_s_per_km=splits_data["pace_s_per_km"],
        star_rating=vr_rating["star_rating"],
        score=vr_rating["score"],
    )

    # Compute overall score (average of 3 metrics)
    overall_score = (
        gct_rating["score"] + vo_rating["score"] + vr_rating["score"]
    ) / 3.0

    # Cadence evaluation
    cadence_achieved = splits_data["cadence"] >= 180.0

    # Build result dictionary
    evaluation = {
        "activity_id": activity_id,
        "gct": {
            "actual": score_result["gct_ms_actual"],
            "expected": score_result["gct_ms_exp"],
            "delta_pct": score_result["gct_delta_pct"],
            "star_rating": gct_rating["star_rating"],
            "score": gct_rating["score"],
            "needs_improvement": score_result["gct_needs_improvement"],
            "evaluation_text": gct_text,
        },
        "vo": {
            "actual": score_result["vo_cm_actual"],
            "expected": score_result["vo_cm_exp"],
            "delta_cm": score_result["vo_delta_cm"],
            "delta_pct": (score_result["vo_delta_cm"] / score_result["vo_cm_exp"])
            * 100.0,
            "star_rating": vo_rating["star_rating"],
            "score": vo_rating["score"],
            "needs_improvement": score_result["vo_needs_improvement"],
            "evaluation_text": vo_text,
        },
        "vr": {
            "actual": score_result["vr_pct_actual"],
            "expected": score_result["vr_pct_exp"],
            "delta_pct": score_result["vr_delta_pct"],
            "star_rating": vr_rating["star_rating"],
            "score": vr_rating["score"],
            "needs_improvement": score_result["vr_needs_improvement"],
            "evaluation_text": vr_text,
        },
        "cadence": {
            "actual": splits_data["cadence"],
            "minimum": 180,
            "achieved": cadence_achieved,
        },
        "overall_score": overall_score,
        "overall_star_rating": compute_star_rating(
            penalty=(5.0 - overall_score) * 20.0,
            delta_pct=0.0,
        )["star_rating"],
    }

    # Generate overall text
    overall_text = generate_overall_text(evaluation)
    evaluation["overall_text"] = overall_text

    # Store evaluation results in DuckDB
    conn = duckdb.connect(db_path)

    # Check baseline freshness and auto-retrain if needed (all metrics)
    from garmin_mcp.form_baseline.trainer import train_form_baselines

    # Get newest baseline end date across all metrics
    baseline_check = conn.execute(
        """
        SELECT MAX(period_end) as newest_end
        FROM form_baseline_history
        WHERE user_id = 'default'
          AND condition_group = ?
          AND metric IN ('gct', 'vo', 'vr', 'power')
        """,
        [condition_group],
    ).fetchone()

    if (
        baseline_check
        and baseline_check[0]
        and isinstance(baseline_check[0], date | datetime)
    ):
        baseline_age_days = (
            datetime.strptime(activity_date, "%Y-%m-%d").date() - baseline_check[0]
        ).days

        if baseline_age_days > 7:
            print(
                f"Form baselines are {baseline_age_days} days old. Auto-retraining all metrics..."
            )
            # Close connection before retraining (trainer opens its own)
            conn.close()
            retrain_result = train_form_baselines(
                db_path=db_path,
                user_id="default",
                condition_group=condition_group,
                window_months=2,
            )
            if retrain_result:
                print(
                    f"  ✓ Retrained baselines: {retrain_result['period_start']} ~ {retrain_result['period_end']}"
                )
                print(
                    f"    GCT: n={retrain_result['gct']['n_samples']}, RMSE={retrain_result['gct']['rmse']:.2f}"
                )
                print(
                    f"    VO:  n={retrain_result['vo']['n_samples']}, RMSE={retrain_result['vo']['rmse']:.2f}"
                )
                print(
                    f"    VR:  n={retrain_result['vr']['n_samples']}, RMSE={retrain_result['vr']['rmse']:.2f}"
                )
                if "power" in retrain_result:
                    print(
                        f"    Power: n={retrain_result['power']['n_samples']}, RMSE={retrain_result['power']['power_rmse']:.2f}"
                    )
            # Reconnect
            conn = duckdb.connect(db_path)

    # Evaluate power efficiency (if available)
    form_penalties = {
        "gct": score_result["gct_penalty"],
        "vo": score_result["vo_penalty"],
        "vr": score_result["vr_penalty"],
    }
    power_result = calculate_power_efficiency_internal(
        conn, activity_id, activity_date, "default", condition_group, form_penalties
    )

    if power_result:
        evaluation["power"] = {
            "avg_w": power_result["avg_w"],
            "wkg": power_result["wkg"],
            "speed_actual_mps": power_result["speed_actual_mps"],
            "speed_expected_mps": power_result["speed_expected_mps"],
            "efficiency_score": power_result["efficiency_score"],
            "star_rating": power_result["star_rating"],
            "needs_improvement": power_result["needs_improvement"],
        }
        evaluation["integrated_score"] = power_result["integrated_score"]
        evaluation["training_mode"] = power_result["training_mode"]
    try:
        conn.execute(
            """
            INSERT INTO form_evaluations (
                eval_id, activity_id,
                gct_ms_expected, vo_cm_expected, vr_pct_expected,
                gct_ms_actual, vo_cm_actual, vr_pct_actual,
                gct_delta_pct, vo_delta_cm, vr_delta_pct,
                gct_penalty, gct_star_rating, gct_score, gct_needs_improvement, gct_evaluation_text,
                vo_penalty, vo_star_rating, vo_score, vo_needs_improvement, vo_evaluation_text,
                vr_penalty, vr_star_rating, vr_score, vr_needs_improvement, vr_evaluation_text,
                cadence_actual, cadence_minimum, cadence_achieved,
                overall_score, overall_star_rating,
                power_avg_w, power_wkg, speed_actual_mps, speed_expected_mps,
                power_efficiency_score, power_efficiency_rating, power_efficiency_needs_improvement,
                integrated_score, training_mode
            ) VALUES (
                nextval('form_evaluations_seq'),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT (activity_id) DO UPDATE SET
                gct_ms_expected = EXCLUDED.gct_ms_expected,
                vo_cm_expected = EXCLUDED.vo_cm_expected,
                vr_pct_expected = EXCLUDED.vr_pct_expected,
                gct_ms_actual = EXCLUDED.gct_ms_actual,
                vo_cm_actual = EXCLUDED.vo_cm_actual,
                vr_pct_actual = EXCLUDED.vr_pct_actual,
                gct_delta_pct = EXCLUDED.gct_delta_pct,
                vo_delta_cm = EXCLUDED.vo_delta_cm,
                vr_delta_pct = EXCLUDED.vr_delta_pct,
                gct_penalty = EXCLUDED.gct_penalty,
                gct_star_rating = EXCLUDED.gct_star_rating,
                gct_score = EXCLUDED.gct_score,
                gct_needs_improvement = EXCLUDED.gct_needs_improvement,
                gct_evaluation_text = EXCLUDED.gct_evaluation_text,
                vo_penalty = EXCLUDED.vo_penalty,
                vo_star_rating = EXCLUDED.vo_star_rating,
                vo_score = EXCLUDED.vo_score,
                vo_needs_improvement = EXCLUDED.vo_needs_improvement,
                vo_evaluation_text = EXCLUDED.vo_evaluation_text,
                vr_penalty = EXCLUDED.vr_penalty,
                vr_star_rating = EXCLUDED.vr_star_rating,
                vr_score = EXCLUDED.vr_score,
                vr_needs_improvement = EXCLUDED.vr_needs_improvement,
                vr_evaluation_text = EXCLUDED.vr_evaluation_text,
                cadence_actual = EXCLUDED.cadence_actual,
                cadence_minimum = EXCLUDED.cadence_minimum,
                cadence_achieved = EXCLUDED.cadence_achieved,
                overall_score = EXCLUDED.overall_score,
                overall_star_rating = EXCLUDED.overall_star_rating,
                power_avg_w = EXCLUDED.power_avg_w,
                power_wkg = EXCLUDED.power_wkg,
                speed_actual_mps = EXCLUDED.speed_actual_mps,
                speed_expected_mps = EXCLUDED.speed_expected_mps,
                power_efficiency_score = EXCLUDED.power_efficiency_score,
                power_efficiency_rating = EXCLUDED.power_efficiency_rating,
                power_efficiency_needs_improvement = EXCLUDED.power_efficiency_needs_improvement,
                integrated_score = EXCLUDED.integrated_score,
                training_mode = EXCLUDED.training_mode,
                evaluated_at = now()
            """,
            [
                activity_id,
                # Expected values
                evaluation["gct"]["expected"],
                evaluation["vo"]["expected"],
                evaluation["vr"]["expected"],
                # Actual values
                evaluation["gct"]["actual"],
                evaluation["vo"]["actual"],
                evaluation["vr"]["actual"],
                # Deltas
                evaluation["gct"]["delta_pct"],
                evaluation["vo"]["delta_cm"],
                evaluation["vr"]["delta_pct"],
                # GCT evaluation
                score_result["gct_penalty"],
                evaluation["gct"]["star_rating"],
                evaluation["gct"]["score"],
                evaluation["gct"]["needs_improvement"],
                evaluation["gct"]["evaluation_text"],
                # VO evaluation
                score_result["vo_penalty"],
                evaluation["vo"]["star_rating"],
                evaluation["vo"]["score"],
                evaluation["vo"]["needs_improvement"],
                evaluation["vo"]["evaluation_text"],
                # VR evaluation
                score_result["vr_penalty"],
                evaluation["vr"]["star_rating"],
                evaluation["vr"]["score"],
                evaluation["vr"]["needs_improvement"],
                evaluation["vr"]["evaluation_text"],
                # Cadence
                evaluation["cadence"]["actual"],
                evaluation["cadence"]["minimum"],
                evaluation["cadence"]["achieved"],
                # Overall
                evaluation["overall_score"],
                evaluation["overall_star_rating"],
                # Power efficiency
                evaluation.get("power", {}).get("avg_w"),
                evaluation.get("power", {}).get("wkg"),
                evaluation.get("power", {}).get("speed_actual_mps"),
                evaluation.get("power", {}).get("speed_expected_mps"),
                evaluation.get("power", {}).get("efficiency_score"),
                evaluation.get("power", {}).get("star_rating"),
                evaluation.get("power", {}).get("needs_improvement"),
                evaluation.get("integrated_score"),
                evaluation.get("training_mode"),
            ],
        )
        conn.close()
    except Exception as e:
        conn.close()
        raise RuntimeError(f"Failed to store evaluation results: {e}") from e

    return evaluation
