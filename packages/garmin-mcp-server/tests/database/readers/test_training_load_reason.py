"""The ACWR status explains why its conservative gate applies (Issue #1524)."""

import pytest

from garmin_mcp.database.readers.training_load import _classify


@pytest.mark.unit
def test_classify_acwr_high_returns_reason_with_band():
    status, reason_ja = _classify(1.42)

    assert status == "caution"
    assert reason_ja is not None
    assert "1.42" in reason_ja
    assert "0.8〜1.3" in reason_ja
    # The condition that moves the gate back.
    assert "1.3 以下に戻れば解除" in reason_ja


@pytest.mark.unit
def test_classify_acwr_optimal_reason_none():
    assert _classify(1.05) == ("optimal", None)


@pytest.mark.unit
def test_classify_acwr_keeps_status_boundaries():
    """The tuple return keeps the original status thresholds."""
    assert _classify(None) == ("insufficient_data", None)
    assert _classify(0.8) == ("optimal", None)
    assert _classify(1.3) == ("optimal", None)
    assert _classify(1.5)[0] == "caution"
    assert _classify(1.51)[0] == "high_risk"
    assert _classify(0.79)[0] == "undertraining"
    assert _classify(1.6)[1] is not None
    assert _classify(0.5)[1] is not None


@pytest.mark.unit
def test_reason_adds_build_baseline_sentence():
    """Issue #1571: the window composition and build-baseline ratio join the reason."""
    baseline = {"status": "ok", "weekly_km": 40.0, "ratio": 1.1}
    composition = [
        {"week_start": "2026-10-12", "load_km": 20.0, "kind": "recovery"},
        {"week_start": "2026-10-19", "load_km": 22.0, "kind": "recovery"},
        {"week_start": "2026-10-26", "load_km": 25.0, "kind": "recovery"},
        {"week_start": "2026-11-02", "load_km": 44.0, "kind": "build"},
    ]

    status, reason_ja = _classify(1.6, baseline, composition)

    assert status == "high_risk"
    assert reason_ja is not None
    assert reason_ja.startswith(_classify(1.6)[1] or "")
    assert "1.1" in reason_ja
    assert "回復期" in reason_ja
    assert "3週" in reason_ja


@pytest.mark.unit
def test_reason_unchanged_without_baseline():
    baseline = {"status": "no_blocks", "weekly_km": None, "ratio": None}
    composition = [{"week_start": "2026-11-02", "load_km": 44.0, "kind": "recovery"}]

    assert _classify(1.6, baseline, composition) == _classify(1.6)
