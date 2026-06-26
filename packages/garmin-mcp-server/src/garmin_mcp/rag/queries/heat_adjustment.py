"""Heat-adjustment model for Garmin running data.

Fits a multivariate OLS regression::

    HR ~ pace + heat_hinge(temp) + days_since_start

to estimate the temperature-hinge coefficient ``beta_heat`` (extra bpm per °C
above a reference temperature), then derives, for each run, the ``heat_cost``
(extra bpm attributable to heat) and a *climate-neutral HR* (``raw_hr -
heat_cost``) reprojected onto the reference temperature.

This is the single-source calculation module reused by the MCP tool and the
Web app. Regression inputs (avg_heart_rate / avg_pace_seconds_per_km /
temp_celsius / activity_date) come from the ``activities`` table via
``GarminDBReader.get_bulk_activity_fields`` + ``get_activity_dates``.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression

from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)

REF_TEMP_C: float = 15.0
"""Hinge breakpoint in °C (spike-derived; subject to tuning)."""

MIN_FIT_ACTIVITIES: int = 10
"""Minimum number of complete rows required to fit the model."""


def heat_hinge(temp_c: float, ref_temp_c: float = REF_TEMP_C) -> float:
    """Return ``max(temp_c - ref_temp_c, 0.0)``.

    Below the reference temperature the hinge is 0 (no heat penalty); the
    function never returns a negative value.
    """
    return max(temp_c - ref_temp_c, 0.0)


@dataclass(frozen=True)
class HeatModelCoefficients:
    """Fitted coefficients of the heat-adjustment regression."""

    intercept: float
    beta_pace: float
    beta_heat: float  # bpm / °C (temp > ref)
    beta_days: float  # bpm / day (time trend = fitness change)
    ref_temp_c: float
    n: int  # number of complete rows used to fit
    r_squared: float


class HeatAdjustmentModel:
    """Fit the heat-adjustment model and compute climate-neutral HR trends."""

    def __init__(
        self,
        db_path: str | None = None,
        ref_temp_c: float = REF_TEMP_C,
    ) -> None:
        """Initialize the model.

        Args:
            db_path: Optional path to the DuckDB database.
            ref_temp_c: Hinge breakpoint in °C.
        """
        self.db_reader = GarminDBReader(db_path)
        self.ref_temp_c = ref_temp_c

    def fit(self, activity_ids: list[int]) -> HeatModelCoefficients:
        """Fit a multivariate OLS via sklearn ``LinearRegression``.

        Rows missing any of temp / HR / pace are dropped. Raises
        ``ValueError`` when fewer than ``MIN_FIT_ACTIVITIES`` complete rows
        remain.

        Args:
            activity_ids: Activity IDs to include.

        Returns:
            Fitted :class:`HeatModelCoefficients`.

        Raises:
            ValueError: If complete rows < ``MIN_FIT_ACTIVITIES``.
        """
        observations = self._load_observations(activity_ids)
        return self._fit_observations(observations)

    @staticmethod
    def heat_cost(temp_c: float, coeffs: HeatModelCoefficients) -> float:
        """Return the heat-induced HR uplift in bpm.

        ``coeffs.beta_heat * heat_hinge(temp_c, coeffs.ref_temp_c)``.
        """
        return coeffs.beta_heat * heat_hinge(temp_c, coeffs.ref_temp_c)

    @classmethod
    def climate_neutral_hr(
        cls,
        raw_hr: float,
        temp_c: float,
        coeffs: HeatModelCoefficients,
    ) -> float:
        """Return ``raw_hr - heat_cost(temp_c, coeffs)``.

        The HR reprojected onto the reference temperature (e.g. 15 °C).
        """
        return raw_hr - cls.heat_cost(temp_c, coeffs)

    def compute_trend(
        self,
        activity_ids: list[int],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Fit the model and return per-run climate-neutral HR points.

        Each point is ``{date, temp_c, raw_hr, heat_cost, neutral_hr}`` in
        ascending date order, together with the time trend (slope, p_value) of
        the climate-neutral HR. When fewer than ``MIN_FIT_ACTIVITIES`` complete
        rows fall in ``[start_date, end_date]`` the result is
        ``{"status": "insufficient_data", ...}``. All numeric values are
        ``json.dumps``-serializable (``datetime.date`` is rendered via
        ``isoformat``).

        Args:
            activity_ids: Activity IDs to include.
            start_date: Inclusive lower date bound (YYYY-MM-DD).
            end_date: Inclusive upper date bound (YYYY-MM-DD).

        Returns:
            Result dict (see module docstring / Issue for the exact shape).
        """
        observations = self._filter_by_date_range(
            self._load_observations(activity_ids), start_date, end_date
        )

        if len(observations) < MIN_FIT_ACTIVITIES:
            return {
                "status": "insufficient_data",
                "n": len(observations),
                "required": MIN_FIT_ACTIVITIES,
                "start_date": start_date,
                "end_date": end_date,
            }

        coeffs = self._fit_observations(observations)

        points: list[dict[str, Any]] = []
        for obs_date, _pace, raw_hr, temp_c in observations:
            cost = self.heat_cost(temp_c, coeffs)
            neutral = self.climate_neutral_hr(raw_hr, temp_c, coeffs)
            points.append(
                {
                    "date": obs_date.isoformat(),
                    "temp_c": temp_c,
                    "raw_hr": raw_hr,
                    "heat_cost": cost,
                    "neutral_hr": neutral,
                }
            )

        # Time trend of the climate-neutral HR (days since earliest run).
        base = observations[0][0].toordinal()
        x = np.array([obs[0].toordinal() - base for obs in observations], dtype=float)
        y = np.array([p["neutral_hr"] for p in points], dtype=float)
        slope, _intercept, _r, p_value, _std_err = stats.linregress(x, y)

        return {
            "status": "ok",
            "coefficients": {
                "intercept": coeffs.intercept,
                "beta_pace": coeffs.beta_pace,
                "beta_heat": coeffs.beta_heat,
                "beta_days": coeffs.beta_days,
                "ref_temp_c": coeffs.ref_temp_c,
                "n": coeffs.n,
                "r_squared": coeffs.r_squared,
            },
            "neutral_hr_slope": float(slope),
            "neutral_hr_p_value": float(p_value),
            "points": points,
            "start_date": start_date,
            "end_date": end_date,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load_observations(
        self, activity_ids: list[int]
    ) -> list[tuple[date, float, float, float]]:
        """Load complete ``(date, pace, hr, temp)`` rows, sorted by date.

        Rows missing a parseable date or any of HR / pace / temp are dropped.
        """
        if not activity_ids:
            return []

        dates_by_id = self.db_reader.get_activity_dates(activity_ids)
        fields_by_id = self.db_reader.get_bulk_activity_fields(
            activity_ids,
            ["avg_heart_rate", "avg_pace_seconds_per_km", "temp_celsius"],
        )

        observations: list[tuple[date, float, float, float]] = []
        for activity_id in activity_ids:
            date_str = dates_by_id.get(activity_id)
            fields = fields_by_id.get(activity_id)
            if date_str is None or fields is None:
                continue

            hr = fields.get("avg_heart_rate")
            pace = fields.get("avg_pace_seconds_per_km")
            temp = fields.get("temp_celsius")
            if hr is None or pace is None or temp is None:
                continue

            try:
                obs_date = date.fromisoformat(str(date_str)[:10])
            except ValueError:
                logger.warning(
                    "Skipping activity %s: unparseable date %r",
                    activity_id,
                    date_str,
                )
                continue

            observations.append((obs_date, float(pace), float(hr), float(temp)))

        observations.sort(key=lambda o: o[0])
        return observations

    @staticmethod
    def _filter_by_date_range(
        observations: list[tuple[date, float, float, float]],
        start_date: str,
        end_date: str,
    ) -> list[tuple[date, float, float, float]]:
        """Keep observations whose date falls within ``[start_date, end_date]``."""
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            logger.warning(
                "Unparseable date range %r..%r; using all observations",
                start_date,
                end_date,
            )
            return observations
        return [obs for obs in observations if start <= obs[0] <= end]

    def _fit_observations(
        self, observations: list[tuple[date, float, float, float]]
    ) -> HeatModelCoefficients:
        """Fit the OLS regression on pre-loaded complete observations."""
        if len(observations) < MIN_FIT_ACTIVITIES:
            raise ValueError(
                f"Need at least {MIN_FIT_ACTIVITIES} complete activities to fit "
                f"the heat-adjustment model, got {len(observations)}."
            )

        base = observations[0][0].toordinal()
        design = np.array(
            [
                [
                    pace,
                    heat_hinge(temp, self.ref_temp_c),
                    obs_date.toordinal() - base,
                ]
                for obs_date, pace, _hr, temp in observations
            ],
            dtype=float,
        )
        target = np.array([hr for _d, _pace, hr, _temp in observations], dtype=float)

        model = LinearRegression().fit(design, target)
        return HeatModelCoefficients(
            intercept=float(model.intercept_),
            beta_pace=float(model.coef_[0]),
            beta_heat=float(model.coef_[1]),
            beta_days=float(model.coef_[2]),
            ref_temp_c=self.ref_temp_c,
            n=len(observations),
            r_squared=float(model.score(design, target)),
        )
