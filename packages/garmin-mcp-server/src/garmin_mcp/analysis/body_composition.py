"""Body-composition analysis (pure functions, no I/O).

Decomposes a weight change between two measurements into fat-mass and lean-mass
components, and derives a lean-mass power-to-weight ratio. These helpers are the
analytic core behind ``GarminDBReader.get_body_composition_trend`` and the MCP
``get_body_composition_trend`` tool (#501).

All functions are null-safe: a missing body-fat percentage means the fat / lean
split is undefined, so the affected computation returns ``None`` rather than
raising.
"""

from __future__ import annotations

from collections.abc import Mapping

# A weight loss is "muscle-costly" when more than this fraction of the lost
# weight is lean mass (raises injury / leg-durability risk).
LEAN_LOSS_WARNING_RATIO = 0.40


def _fat_mass(weight_kg: float, body_fat_pct: float) -> float:
    """Fat mass (kg) = weight_kg * body_fat_pct / 100."""
    return weight_kg * body_fat_pct / 100.0


def decompose_weight_change(
    start: Mapping[str, float | None],
    end: Mapping[str, float | None],
) -> dict[str, float | bool | None]:
    """Decompose a weight change into fat / lean components.

    Args:
        start: Earlier measurement ``{"weight_kg": float, "body_fat_pct": float}``.
        end: Later measurement with the same keys.

    Each measurement needs a non-null ``weight_kg`` and ``body_fat_pct`` to be
    decomposed. When either body-fat value is missing the fat / lean split is
    undefined, so ``delta_fat`` / ``delta_lean`` / ``lean_loss_ratio`` are
    ``None`` and ``muscle_loss_warning`` is ``False`` (no exception).

    Returns:
        ``{"delta_weight", "delta_fat", "delta_lean", "lean_loss_ratio",
        "muscle_loss_warning"}``. ``delta_*`` are signed (negative = loss).
        ``lean_loss_ratio`` is the lean share of the lost weight (only
        meaningful, and only non-null, when weight decreased and both body-fat
        values are present); ``muscle_loss_warning`` is True when that ratio
        exceeds ``LEAN_LOSS_WARNING_RATIO`` (40%).
    """
    sw = start.get("weight_kg")
    ew = end.get("weight_kg")
    sf = start.get("body_fat_pct")
    ef = end.get("body_fat_pct")

    if sw is None or ew is None:
        return {
            "delta_weight": None,
            "delta_fat": None,
            "delta_lean": None,
            "lean_loss_ratio": None,
            "muscle_loss_warning": False,
        }

    delta_weight = round(ew - sw, 2)

    # Body fat missing on either end -> fat/lean split undefined (null-safe).
    if sf is None or ef is None:
        return {
            "delta_weight": delta_weight,
            "delta_fat": None,
            "delta_lean": None,
            "lean_loss_ratio": None,
            "muscle_loss_warning": False,
        }

    start_fat = _fat_mass(sw, sf)
    end_fat = _fat_mass(ew, ef)
    start_lean = sw - start_fat
    end_lean = ew - end_fat

    delta_fat = round(end_fat - start_fat, 2)
    delta_lean = round(end_lean - start_lean, 2)

    # Lean loss ratio is only meaningful for a net weight loss. When lean mass
    # actually rose (delta_lean >= 0) the cut cost no muscle -> ratio 0.0.
    lean_loss_ratio: float | None = None
    muscle_loss_warning = False
    if delta_weight < 0:
        weight_lost = -delta_weight
        lean_lost = -delta_lean if delta_lean < 0 else 0.0
        lean_loss_ratio = round(lean_lost / weight_lost, 3)
        muscle_loss_warning = lean_loss_ratio > LEAN_LOSS_WARNING_RATIO

    return {
        "delta_weight": delta_weight,
        "delta_fat": delta_fat,
        "delta_lean": delta_lean,
        "lean_loss_ratio": lean_loss_ratio,
        "muscle_loss_warning": muscle_loss_warning,
    }


def lean_power_to_weight(
    ftp_w: float | None,
    weight_kg: float | None,
    body_fat_pct: float | None,
) -> float | None:
    """Lean-mass power-to-weight (W/kg) = FTP / lean_mass.

    Args:
        ftp_w: Functional threshold power (watts).
        weight_kg: Body weight (kg).
        body_fat_pct: Body-fat percentage.

    Returns:
        FTP divided by lean mass (``weight_kg * (1 - body_fat_pct/100)``),
        rounded to 2 decimals. ``None`` when any input is missing or lean mass
        is non-positive (null-safe; never raises).
    """
    if ftp_w is None or weight_kg is None or body_fat_pct is None:
        return None
    lean_mass = weight_kg - _fat_mass(weight_kg, body_fat_pct)
    if lean_mass <= 0:
        return None
    return round(ftp_w / lean_mass, 2)
