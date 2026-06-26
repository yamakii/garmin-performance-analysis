"""Objective fitness derivation from real-run data.

Pure-logic helpers (no DB/IO) that turn per-split run data into objective
fitness signals: best contiguous effort segments and their Daniels performance
VDOT (:mod:`garmin_mcp.objective_fitness.segments`), and the rolling-max
objective fitness curve over those per-run VDOTs
(:mod:`garmin_mcp.objective_fitness.curve`).
"""

from garmin_mcp.objective_fitness.curve import FitnessPoint, rolling_max_curve
from garmin_mcp.objective_fitness.segments import (
    BestEffort,
    best_contiguous_segment,
    performance_vdot,
    run_best_efforts,
)

__all__ = [
    "BestEffort",
    "best_contiguous_segment",
    "performance_vdot",
    "run_best_efforts",
    "FitnessPoint",
    "rolling_max_curve",
]
