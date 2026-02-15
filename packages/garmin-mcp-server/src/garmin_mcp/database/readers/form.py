"""
Form efficiency reader for DuckDB.

Handles queries to form_efficiency and form_evaluations tables.
"""

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class FormReader(BaseDBReader):
    """Reader for form efficiency and evaluation metrics."""

    def get_form_efficiency_summary(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get form efficiency summary from form_efficiency table.

        Args:
            activity_id: Activity ID

        Returns:
            Form efficiency data with GCT, VO, VR metrics and ratings.
            Format: {
                "gct": {"average": float, "min": float, "max": float, "std": float,
                        "variability": float, "rating": str, "evaluation": str},
                "vo": {"average": float, "min": float, "max": float, "std": float,
                       "trend": str, "rating": str, "evaluation": str},
                "vr": {"average": float, "min": float, "max": float, "std": float,
                       "rating": str, "evaluation": str}
            }
            None if activity not found.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        gct_average, gct_min, gct_max, gct_std, gct_variability,
                        gct_rating, gct_evaluation,
                        vo_average, vo_min, vo_max, vo_std, vo_trend,
                        vo_rating, vo_evaluation,
                        vr_average, vr_min, vr_max, vr_std,
                        vr_rating, vr_evaluation
                    FROM form_efficiency
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    return None

                return {
                    "gct": {
                        "average": result[0],
                        "min": result[1],
                        "max": result[2],
                        "std": result[3],
                        "variability": result[4],
                        "rating": result[5],
                        "evaluation": result[6],
                    },
                    "vo": {
                        "average": result[7],
                        "min": result[8],
                        "max": result[9],
                        "std": result[10],
                        "trend": result[11],
                        "rating": result[12],
                        "evaluation": result[13],
                    },
                    "vr": {
                        "average": result[14],
                        "min": result[15],
                        "max": result[16],
                        "std": result[17],
                        "rating": result[18],
                        "evaluation": result[19],
                    },
                }

        except Exception as e:
            logger.error(f"Error getting form efficiency summary: {e}")
            return None

    def get_form_evaluations(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get form evaluation results from form_evaluations table.

        Args:
            activity_id: Activity ID

        Returns:
            Form evaluation data with expected values, actual values, scores,
            and evaluation texts for GCT, VO, VR, cadence, power efficiency,
            and overall.
            None if activity not found or not evaluated.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        gct_ms_expected, gct_ms_actual, gct_delta_pct,
                        gct_star_rating, gct_score, gct_needs_improvement,
                        gct_evaluation_text,
                        vo_cm_expected, vo_cm_actual, vo_delta_cm,
                        vo_star_rating, vo_score, vo_needs_improvement,
                        vo_evaluation_text,
                        vr_pct_expected, vr_pct_actual, vr_delta_pct,
                        vr_star_rating, vr_score, vr_needs_improvement,
                        vr_evaluation_text,
                        cadence_actual, cadence_minimum, cadence_achieved,
                        overall_score, overall_star_rating,
                        power_avg_w, power_wkg, speed_actual_mps, speed_expected_mps,
                        power_efficiency_score, power_efficiency_rating,
                        power_efficiency_needs_improvement,
                        integrated_score, training_mode
                    FROM form_evaluations
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    return None

                # Calculate vo_delta_pct from vo_delta_cm and vo_cm_expected
                vo_delta_pct = (
                    (result[9] / result[7]) * 100.0 if result[7] != 0 else 0.0
                )

                return {
                    "activity_id": activity_id,
                    "gct": {
                        "actual": result[1],
                        "expected": result[0],
                        "delta_pct": result[2],
                        "star_rating": result[3],
                        "score": result[4],
                        "needs_improvement": result[5],
                        "evaluation_text": result[6],
                    },
                    "vo": {
                        "actual": result[8],
                        "expected": result[7],
                        "delta_cm": result[9],
                        "delta_pct": vo_delta_pct,
                        "star_rating": result[10],
                        "score": result[11],
                        "needs_improvement": result[12],
                        "evaluation_text": result[13],
                    },
                    "vr": {
                        "actual": result[15],
                        "expected": result[14],
                        "delta_pct": result[16],
                        "star_rating": result[17],
                        "score": result[18],
                        "needs_improvement": result[19],
                        "evaluation_text": result[20],
                    },
                    "cadence": {
                        "actual": result[21],
                        "minimum": result[22],
                        "achieved": result[23],
                    },
                    "power": {
                        "avg_w": result[26],
                        "wkg": result[27],
                        "speed_actual_mps": result[28],
                        "speed_expected_mps": result[29],
                        "efficiency_score": result[30],
                        "star_rating": result[31],
                        "needs_improvement": result[32],
                    },
                    "integrated_score": result[33],
                    "training_mode": result[34],
                    "overall_score": result[24],
                    "overall_star_rating": result[25],
                }

        except Exception as e:
            logger.debug(f"Form evaluations not available: {e}")
            return None
