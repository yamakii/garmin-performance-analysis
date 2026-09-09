"""FormAnomalyDetector: z-score threshold, magnitude gate, sustained / direction gates (#820)."""

from typing import cast

import pytest

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector


@pytest.mark.unit
def test_zscore_threshold_default_3(detector: FormAnomalyDetector) -> None:
    """Test _detect_anomalies_by_zscore default z_threshold is 3.0.

    Verify that:
    - The default threshold is 3.0 (raised from 2.0)
    - A point with 2.0 < z <= 3.0 is NOT flagged when the default is used
    """
    import inspect

    sig = inspect.signature(detector._detect_anomalies_by_zscore)
    assert sig.parameters["z_threshold"].default == 3.0

    # A metric without a magnitude gate, with z = 2.5 (between old and new
    # thresholds) should NOT be flagged under the default threshold.
    # mean=200, std=2 -> value 205 gives z = 2.5
    time_series: list[float | None] = cast(
        list[float | None], [200.0] * 50 + [205.0] + [200.0] * 49
    )
    rolling_means = [200.0] * 100
    rolling_stds = [2.0] * 100

    anomalies = detector._detect_anomalies_by_zscore(
        "directHeartRate", time_series, rolling_means, rolling_stds
    )

    assert len(anomalies) == 0


@pytest.mark.unit
def test_anomaly_zscore_threshold_golden(detector: FormAnomalyDetector) -> None:
    """Golden: a fixed GCT spike freezes the z-score the detector fires at.

    rolling mean 240 ms, std 2.5 ms, with one point at 253 ms: deviation 13 ms
    (>= the 10 ms GCT magnitude gate) and z = 13 / 2.5 = 5.2 (> default 3.0). The
    spike must be flagged exactly once with a frozen z-score of 5.2. This guards
    the z-score formula and the gate interplay against silent drift; recompute
    deliberately if the detection math is intentionally changed.
    """
    time_series: list[float | None] = cast(
        list[float | None], [240.0] * 50 + [253.0] + [240.0] * 49
    )
    rolling_means = [240.0] * 100
    rolling_stds = [2.5] * 100

    anomalies = detector._detect_anomalies_by_zscore(
        "directGroundContactTime", time_series, rolling_means, rolling_stds
    )

    assert len(anomalies) == 1
    assert anomalies[0]["value"] == 253.0
    assert anomalies[0]["z_score"] == pytest.approx(5.2, abs=1e-6)


@pytest.mark.unit
def test_vo_small_change_not_flagged(detector: FormAnomalyDetector) -> None:
    """Test VO small (0.4cm) deviation is not flagged despite high z-score.

    Verify that:
    - VO deviation of 0.4 cm with z > 3 is filtered by the magnitude gate
      (gate = 0.5 cm)
    """
    # mean=8.0, std=0.1 -> value 8.4 gives deviation 0.4, z = 4.0 (> 3)
    time_series: list[float | None] = cast(
        list[float | None], [8.0] * 50 + [8.4] + [8.0] * 49
    )
    rolling_means = [8.0] * 100
    rolling_stds = [0.1] * 100

    anomalies = detector._detect_anomalies_by_zscore(
        "directVerticalOscillation", time_series, rolling_means, rolling_stds
    )

    assert len(anomalies) == 0


@pytest.mark.unit
def test_vo_material_change_flagged(detector: FormAnomalyDetector) -> None:
    """Test VO material (0.7cm) deviation with z > 3 is flagged.

    Verify that:
    - VO deviation of 0.7 cm with z > 3 passes both z and magnitude gates
    """
    # mean=8.0, std=0.1 -> value 8.7 gives deviation 0.7, z = 7.0 (> 3)
    time_series: list[float | None] = cast(
        list[float | None], [8.0] * 50 + [8.7] + [8.0] * 49
    )
    rolling_means = [8.0] * 100
    rolling_stds = [0.1] * 100

    anomalies = detector._detect_anomalies_by_zscore(
        "directVerticalOscillation", time_series, rolling_means, rolling_stds
    )

    assert len(anomalies) == 1
    assert anomalies[0]["value"] == 8.7


@pytest.mark.unit
def test_gct_magnitude_gate(detector: FormAnomalyDetector) -> None:
    """Test GCT magnitude gate: 8ms ignored, 12ms detected.

    Verify that:
    - GCT deviation of 8 ms (z > 3) is below the 10 ms gate -> not flagged
    - GCT deviation of 12 ms (z > 3) is at/above the gate -> flagged
    """
    rolling_means = [240.0] * 100
    rolling_stds = [2.0] * 100

    # 8ms deviation: value 248, z = 4.0 (> 3) but below 10ms gate
    series_8ms: list[float | None] = cast(
        list[float | None], [240.0] * 50 + [248.0] + [240.0] * 49
    )
    anomalies_8 = detector._detect_anomalies_by_zscore(
        "directGroundContactTime", series_8ms, rolling_means, rolling_stds
    )
    assert len(anomalies_8) == 0

    # 12ms deviation: value 252, z = 6.0 (> 3) and >= 10ms gate
    series_12ms: list[float | None] = cast(
        list[float | None], [240.0] * 50 + [252.0] + [240.0] * 49
    )
    anomalies_12 = detector._detect_anomalies_by_zscore(
        "directGroundContactTime", series_12ms, rolling_means, rolling_stds
    )
    assert len(anomalies_12) == 1
    assert anomalies_12[0]["value"] == 252.0


@pytest.mark.unit
def test_fatigue_requires_sustained_trend(detector: FormAnomalyDetector) -> None:
    """Test fatigue label requires a sustained degradation trend.

    Verify that:
    - A single z anomaly with HR drift > 10% but no sustained trend and no
      pace signal is classified as "isolated" (not fatigue, not pace_change)
      after #666
    - The same anomaly with sustained_degradation=True is classified as fatigue
    """
    anomaly = {"timestamp": 500, "metric": "directVerticalOscillation", "value": 9.0}

    # Minimal elevation and pace change so neither takes priority (pace constant
    # -> pace_change 0, below the 0.25 threshold).
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 600)
    pace_series: list[float | None] = cast(list[float | None], [4.0] * 600)

    # Significant HR drift (>10%): baseline 150, current ~172
    hr_series: list[float | None] = cast(
        list[float | None],
        [150.0] * 300 + [158.0] * 100 + [168.0] * 100 + [172.0] * 100,
    )

    # Without sustained degradation -> NOT fatigue; with no pace signal it now
    # falls through to "isolated" (was the artificial low-confidence pace_change).
    cause_no_trend, details_no_trend = detector._analyze_anomaly_causes(
        anomaly, elevation_series, pace_series, hr_series, sustained_degradation=False
    )
    assert cause_no_trend == "isolated"
    assert abs(details_no_trend["hr_drift_percent"]) > 10.0
    assert "pace_correlation" not in details_no_trend

    # With sustained degradation -> fatigue
    cause_trend, _ = detector._analyze_anomaly_causes(
        anomaly, elevation_series, pace_series, hr_series, sustained_degradation=True
    )
    assert cause_trend == "fatigue"


@pytest.mark.unit
def test_improvement_direction_not_flagged(detector: FormAnomalyDetector) -> None:
    """GCT shortening (improvement) is not a form anomaly (#820).

    GCT mean 260 ms / std 10 ms with one point at 220 ms: deviation 40 ms
    (>= the 10 ms gate) and z = 4.0 (> 3.0), but it is in the *better* direction
    (shorter GCT), so the direction gate skips it.
    """
    time_series: list[float | None] = cast(
        list[float | None], [260.0] * 50 + [220.0] + [260.0] * 49
    )
    rolling_means = [260.0] * 100
    rolling_stds = [10.0] * 100

    anomalies = detector._detect_anomalies_by_zscore(
        "directGroundContactTime", time_series, rolling_means, rolling_stds
    )

    assert len(anomalies) == 0


@pytest.mark.unit
def test_vo_improvement_not_flagged(detector: FormAnomalyDetector) -> None:
    """VO dropping (improvement) with z > 3 is not flagged (#820).

    VO mean 7.1 cm / std 0.4 cm with one point at 5.6 cm: deviation 1.5 cm
    (z = 3.75, > 3) but in the better direction, so it is skipped.
    """
    time_series: list[float | None] = cast(
        list[float | None], [7.1] * 50 + [5.6] + [7.1] * 49
    )
    rolling_means = [7.1] * 100
    rolling_stds = [0.4] * 100

    anomalies = detector._detect_anomalies_by_zscore(
        "directVerticalOscillation", time_series, rolling_means, rolling_stds
    )

    assert len(anomalies) == 0


@pytest.mark.unit
def test_single_second_spike_not_flagged(detector: FormAnomalyDetector) -> None:
    """A single-second worse GCT spike is dropped by the sustained gate (#820).

    One 430 ms point in an otherwise 260 ms series is a worse-direction outlier
    with z > 3, but it spans only 1 second (< MIN_SUSTAINED_SECONDS=5), so
    _detect_all_anomalies filters it out.
    """
    form_metrics: dict[str, list[float | None]] = {
        "directGroundContactTime": cast(
            list[float | None], [260.0] * 50 + [430.0] + [260.0] * 49
        ),
    }
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 100)
    pace_series: list[float | None] = cast(list[float | None], [5.0] * 100)
    hr_series: list[float | None] = cast(list[float | None], [150.0] * 100)

    anomalies = detector._detect_all_anomalies(
        form_metrics, elevation_series, pace_series, hr_series, z_threshold=3.0
    )

    assert anomalies == []


@pytest.mark.unit
def test_short_cluster_below_min_sustained_not_flagged(
    detector: FormAnomalyDetector,
) -> None:
    """A 3-second worse cluster (span 3 < 5) is dropped by the sustained gate (#820)."""
    form_metrics: dict[str, list[float | None]] = {
        "directGroundContactTime": cast(
            list[float | None], [260.0] * 50 + [430.0, 425.0, 428.0] + [260.0] * 47
        ),
    }
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 100)
    pace_series: list[float | None] = cast(list[float | None], [5.0] * 100)
    hr_series: list[float | None] = cast(list[float | None], [150.0] * 100)

    anomalies = detector._detect_all_anomalies(
        form_metrics, elevation_series, pace_series, hr_series, z_threshold=3.0
    )

    assert anomalies == []


@pytest.mark.unit
def test_sustained_worse_deviation_flagged(detector: FormAnomalyDetector) -> None:
    """A sustained (>= 5s) worse GCT deviation is retained with a cause (#820).

    Five contiguous 300 ms points (baseline 260 ms) each clear the z > 3 and
    10 ms gates in the worse direction and form a run spanning 5 seconds
    (>= MIN_SUSTAINED_SECONDS=5), so all five survive the sustained filter and
    receive a ``probable_cause``.
    """
    form_metrics: dict[str, list[float | None]] = {
        "directGroundContactTime": cast(
            list[float | None], [260.0] * 50 + [300.0] * 5 + [260.0] * 45
        ),
    }
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 100)
    pace_series: list[float | None] = cast(list[float | None], [5.0] * 100)
    hr_series: list[float | None] = cast(list[float | None], [150.0] * 100)

    anomalies = detector._detect_all_anomalies(
        form_metrics, elevation_series, pace_series, hr_series, z_threshold=3.0
    )

    assert len(anomalies) == 5
    assert [a["timestamp"] for a in anomalies] == [50, 51, 52, 53, 54]
    assert all("probable_cause" in a for a in anomalies)


@pytest.mark.unit
def test_sustained_bridges_short_gap(detector: FormAnomalyDetector) -> None:
    """Worse points at 100,102,104,106,108 bridge 1s gaps into one run (#820).

    With SUSTAINED_ADJACENCY_TOLERANCE_SEC=2 the five points (each 2s apart)
    belong to a single run spanning 9 seconds (>= 5), so all are retained.
    """
    anomalies = [
        {
            "timestamp": ts,
            "metric": "directGroundContactTime",
            "value": 300.0,
            "baseline": 260.0,
            "z_score": 4.0,
        }
        for ts in (100, 102, 104, 106, 108)
    ]

    result = detector._filter_sustained(anomalies)

    assert [a["timestamp"] for a in result] == [100, 102, 104, 106, 108]


@pytest.mark.unit
def test_direction_gate_absent_for_unlisted_metric(
    detector: FormAnomalyDetector,
) -> None:
    """Metrics not in WORSE_IS_HIGHER keep symmetric abs detection (#820).

    A below-mean cadence dip (which would be skipped for a WORSE_IS_HIGHER
    metric) is still flagged because cadence has no configured worse direction.
    """
    time_series: list[float | None] = cast(
        list[float | None], [180.0] * 50 + [150.0] + [180.0] * 49
    )
    rolling_means = [180.0] * 100
    rolling_stds = [5.0] * 100

    anomalies = detector._detect_anomalies_by_zscore(
        "directRunCadence", time_series, rolling_means, rolling_stds
    )

    assert len(anomalies) == 1
    assert anomalies[0]["value"] == 150.0


@pytest.mark.unit
def test_filter_sustained_empty_input(detector: FormAnomalyDetector) -> None:
    """_filter_sustained returns [] for empty input (#820)."""
    assert detector._filter_sustained([]) == []
