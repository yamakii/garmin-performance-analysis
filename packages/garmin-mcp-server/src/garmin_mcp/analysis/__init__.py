"""Pure analysis helpers (no I/O).

Modules here hold side-effect-free computations used by readers and tools.
``body_composition`` decomposes a weight change into fat / lean components and
derives lean-mass power-to-weight. ``recovery`` derives RHR / HRV recovery
signals from daily wellness rows. ``running_economy`` couples runs with body
weight (nearest measurement), derives efficiency-factor metrics and fits a
longitudinal ``EF ~ weight + days (+ fitness)`` OLS (with a VIF collinearity
flag).
"""

from garmin_mcp.analysis.body_composition import (
    decompose_weight_change,
    lean_power_to_weight,
)
from garmin_mcp.analysis.recovery import (
    compute_hrv_recovery,
    compute_rhr_trend,
)
from garmin_mcp.analysis.running_economy import (
    CoupledRecord,
    CovariateResult,
    RunRecord,
    WeightEconomyModel,
    WeightMeasurement,
    compute_ef,
    fit_weight_economy_model,
    join_runs_with_weight,
    nearest_weight,
)

__all__ = [
    "CoupledRecord",
    "CovariateResult",
    "RunRecord",
    "WeightEconomyModel",
    "WeightMeasurement",
    "compute_ef",
    "compute_hrv_recovery",
    "compute_rhr_trend",
    "decompose_weight_change",
    "fit_weight_economy_model",
    "join_runs_with_weight",
    "lean_power_to_weight",
    "nearest_weight",
]
