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
