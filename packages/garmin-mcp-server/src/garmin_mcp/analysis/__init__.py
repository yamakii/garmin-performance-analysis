"""Pure analysis helpers (no I/O).

Modules here hold side-effect-free computations used by readers and tools.
``body_composition`` decomposes a weight change into fat / lean components and
derives lean-mass power-to-weight.
"""

from garmin_mcp.analysis.body_composition import (
    decompose_weight_change,
    lean_power_to_weight,
)

__all__ = [
    "decompose_weight_change",
    "lean_power_to_weight",
]
