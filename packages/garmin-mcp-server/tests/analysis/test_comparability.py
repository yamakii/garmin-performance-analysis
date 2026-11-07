"""Which metrics two runs may be compared on, and how each metric came to be (#1523)."""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.comparability import (
    DYNAMICS_METRICS,
    HR_METRICS,
    assess,
    drop_excluded,
    provenance_for,
)


def _run(
    dynamics: str | None = "pod",
    hr: str | None = "chest_strap",
    load: float | None = None,
) -> dict[str, object]:
    return {"dynamics_source": dynamics, "hr_source": hr, "load_kg": load}


@pytest.mark.unit
def test_assess_same_sensors_all_comparable() -> None:
    result = assess(_run(), _run())

    assert result.excluded_metrics == frozenset()
    assert result.reasons == ()
    assert result.comparable_metrics == DYNAMICS_METRICS | HR_METRICS


@pytest.mark.unit
def test_assess_pod_vs_wrist_excludes_dynamics_only() -> None:
    result = assess(_run(dynamics="pod"), _run(dynamics="wrist"))

    assert result.excluded_metrics == DYNAMICS_METRICS
    assert result.reasons == ("dynamics_source_differs",)
    assert result.comparable_metrics >= HR_METRICS
    assert result.hr_comparable is True
    assert result.sensors_match is False


@pytest.mark.unit
def test_assess_load_differs_excludes_hr_and_dynamics() -> None:
    result = assess(_run(load=3.0), _run(load=None))

    assert result.excluded_metrics == DYNAMICS_METRICS | HR_METRICS
    assert result.reasons == ("load_differs",)
    assert result.hr_comparable is False
    # A load is not a sensor: same_sensor_only keeps the pair.
    assert result.sensors_match is True


@pytest.mark.unit
def test_assess_null_source_is_legacy_comparable() -> None:
    result = assess(_run(dynamics=None), _run(dynamics="pod"))

    assert result.excluded_metrics == frozenset()
    assert result.reasons == ()


@pytest.mark.unit
def test_provenance_gct_wrist_is_device_derived() -> None:
    assert provenance_for("gct_ms", "wrist") == "device_derived"
    assert provenance_for("gct_ms", "pod") == "measured"
    assert provenance_for("stride_length_cm", "wrist") == "device_derived"
    assert provenance_for("stride_length_cm", "pod") == "device_derived"


@pytest.mark.unit
def test_drop_excluded_removes_derived_keys() -> None:
    """pace_at_hr goes with avg_hr; ids and dates always stay."""
    deltas = {
        "avg_hr": {"delta": 3},
        "pace_at_hr": {"delta": -2},
        "pace_s_per_km": {"delta": -5},
        "previous_activity_id": 1,
    }

    kept = drop_excluded(deltas, assess(_run(hr="wrist"), _run(hr="chest_strap")))

    assert set(kept) == {"pace_s_per_km", "previous_activity_id", "comparability"}
    assert kept["comparability"]["reasons"] == ["hr_source_differs"]
