"""Objective fitness derivation from real-run data.

Pure-logic helpers (no DB/IO) that turn per-split run data into objective
fitness signals: best contiguous effort segments and their Daniels performance
VDOT (:mod:`garmin_mcp.objective_fitness.segments`), the rolling-max objective
fitness curve over those per-run VDOTs (:mod:`garmin_mcp.objective_fitness.curve`),
and a quarterly threshold-anchored Critical Speed fit
(:mod:`garmin_mcp.objective_fitness.critical_speed`).
"""

from garmin_mcp.objective_fitness.critical_speed import (
    CriticalSpeedFit,
    fit_critical_speed,
    quarterly_critical_speed,
)
from garmin_mcp.objective_fitness.curve import FitnessPoint, rolling_max_curve
from garmin_mcp.objective_fitness.segments import (
    BestEffort,
    best_contiguous_segment,
    performance_vdot,
    run_best_efforts,
)

__all__ = [
    "BestEffort",
    "CriticalSpeedFit",
    "best_contiguous_segment",
    "fit_critical_speed",
    "performance_vdot",
    "quarterly_critical_speed",
    "run_best_efforts",
    "FitnessPoint",
    "rolling_max_curve",
]
