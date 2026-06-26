"""Objective fitness derivation from real-run data.

Pure-logic helpers (no DB/IO) that turn per-split run data into objective
fitness signals such as best contiguous effort segments and their Daniels
performance VDOT.
"""

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
]
