"""Form baseline evaluator module.

Evaluates activity form metrics against pace-adjusted baselines and stores results.
"""

import json
from pathlib import Path
from typing import Any

import duckdb

from .scorer import compute_star_rating, score_observation
from .text_generator import generate_evaluation_text, generate_overall_text
from .trainer import GCTPowerModel, LinearModel


def _load_models_from_file(model_file: Path) -> dict[str, GCTPowerModel | LinearModel]:
    """Load trained models from JSON file.

    Args:
        model_file: Path to JSON file with model coefficients

    Returns:
        Dictionary of models: {'gct': GCTPowerModel, 'vo': LinearModel, 'vr': LinearModel}

    Raises:
        FileNotFoundError: If model file doesn't exist
        ValueError: If JSON format is invalid
    """
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found: {model_file}")

    with open(model_file) as f:
        data = json.load(f)

    # Create GCT power model
    gct_data = data["gct"]
    gct_model = GCTPowerModel(
        alpha=gct_data["alpha"],
        d=gct_data["d"],
        rmse=gct_data["rmse"],
        n_samples=gct_data["n_samples"],
        speed_range=(gct_data["speed_range"]["min"], gct_data["speed_range"]["max"]),
    )

    # Create VO linear model
    vo_data = data["vo"]
    vo_model = LinearModel(
        a=vo_data["a"],
        b=vo_data["b"],
        rmse=vo_data["rmse"],
        n_samples=vo_data["n_samples"],
        speed_range=(vo_data["speed_range"]["min"], vo_data["speed_range"]["max"]),
    )

    # Create VR linear model
    vr_data = data["vr"]
    vr_model = LinearModel(
        a=vr_data["a"],
        b=vr_data["b"],
        rmse=vr_data["rmse"],
        n_samples=vr_data["n_samples"],
        speed_range=(vr_data["speed_range"]["min"], vr_data["speed_range"]["max"]),
    )

    return {
        "gct": gct_model,
        "vo": vo_model,
        "vr": vr_model,
    }


def _get_splits_data(
    db_path: str,
    activity_id: int,
) -> dict[str, float]:
    """Get average splits data from DuckDB.

    Args:
        db_path: Path to DuckDB database
        activity_id: Activity ID

    Returns:
        Dictionary with average form metrics:
            - pace_s_per_km: Average pace (seconds per km)
            - gct_ms: Average ground contact time (ms)
            - vo_cm: Average vertical oscillation (cm)
            - vr_pct: Average vertical ratio (%)
            - cadence: Average cadence (spm)

    Raises:
        ValueError: If no splits found for activity
    """
    conn = duckdb.connect(db_path, read_only=True)

    try:
        result = conn.execute(
            """
            SELECT
                AVG(pace_seconds_per_km) as pace_s_per_km,
                AVG(ground_contact_time) as gct_ms,
                AVG(vertical_oscillation) as vo_cm,
                AVG(vertical_ratio) as vr_pct,
                AVG(cadence) as cadence
            FROM splits
            WHERE activity_id = ?
              AND ground_contact_time IS NOT NULL
              AND vertical_oscillation IS NOT NULL
              AND vertical_ratio IS NOT NULL
        """,
            [activity_id],
        ).fetchone()

        if not result or result[0] is None:
            raise ValueError(f"No splits found for activity {activity_id}")

        pace_s_per_km, gct_ms, vo_cm, vr_pct, cadence = result

        return {
            "pace_s_per_km": float(pace_s_per_km),
            "gct_ms": float(gct_ms),
            "vo_cm": float(vo_cm),
            "vr_pct": float(vr_pct),
            "cadence": float(cadence) if cadence is not None else 0.0,
        }
    finally:
        conn.close()


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

    Example:
        >>> result = evaluate_and_store(
        ...     activity_id=20790040925,
        ...     activity_date="2025-10-25",
        ...     db_path="data/database/garmin_performance.duckdb"
        ... )
        >>> print(result['gct']['star_rating'])
        ★★★★★
    """
    # Load models
    if model_file is None:
        # Default location: tools/form_baseline/models/flat_road.json
        model_file = Path(__file__).parent / "models" / f"{condition_group}.json"

    models = _load_models_from_file(model_file)

    # Get actual data from splits
    splits_data = _get_splits_data(db_path, activity_id)

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
            penalty=(5.0 - overall_score) * 20.0,  # Convert 0-5 score to penalty
            delta_pct=0.0,  # Not used for overall
        )["star_rating"],
    }

    # Generate overall text
    overall_text = generate_overall_text(evaluation)
    evaluation["overall_text"] = overall_text

    # Store evaluation results in DuckDB
    import duckdb

    conn = duckdb.connect(db_path)
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
                overall_score, overall_star_rating
            ) VALUES (
                nextval('form_evaluations_seq'),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
            ],
        )
        conn.close()
    except Exception as e:
        conn.close()
        raise RuntimeError(f"Failed to store evaluation results: {e}") from e

    return evaluation
