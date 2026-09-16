"""Tests for the gear derivations (Issue #1207).

``is_new_gear`` is the break-in window; ``format_gear_label`` names a shoe the
way the athlete does now that Garmin's gear form keeps the version in the
nickname rather than in the model string.
"""

import pytest

from garmin_mcp.analysis.derivations import (
    classify_gear_age,
    classify_gear_wear,
    format_gear_label,
    gear_age_months,
    gear_wear_pct,
    is_new_gear,
    replace_recommended,
)


@pytest.mark.unit
class TestIsNewGear:
    """Tests for is_new_gear()."""

    def test_is_new_gear_true_within_threshold(self) -> None:
        assert is_new_gear(1) is True
        assert is_new_gear(5) is True

    def test_is_new_gear_false_beyond_threshold(self) -> None:
        assert is_new_gear(6) is False
        assert is_new_gear(206) is False

    def test_is_new_gear_false_for_none(self) -> None:
        assert is_new_gear(None) is False

    def test_is_new_gear_false_for_non_positive(self) -> None:
        """A zero/negative count is a bug upstream, not a brand-new shoe."""
        assert is_new_gear(0) is False
        assert is_new_gear(-1) is False


@pytest.mark.unit
class TestFormatGearLabel:
    """Tests for format_gear_label()."""

    def test_model_and_nickname_are_combined(self) -> None:
        assert (
            format_gear_label("New Balance Fresh Foam X 1080", "v15")
            == "New Balance Fresh Foam X 1080 (v15)"
        )

    def test_model_alone_is_returned_unchanged(self) -> None:
        assert format_gear_label("asics novablast 4", None) == "asics novablast 4"

    def test_nickname_alone_is_returned(self) -> None:
        assert format_gear_label(None, "v15") == "v15"

    def test_redundant_nickname_is_dropped(self) -> None:
        """A nickname that just repeats the model adds nothing to the label."""
        assert format_gear_label("Nike Vaporfly", "nike vaporfly") == "Nike Vaporfly"

    def test_blank_strings_are_treated_as_missing(self) -> None:
        assert format_gear_label("  ", "  ") is None
        assert format_gear_label("Nike Vaporfly", "   ") == "Nike Vaporfly"

    def test_no_gear_returns_none(self) -> None:
        assert format_gear_label(None, None) is None


@pytest.mark.unit
class TestGearWear:
    """Tests for gear_wear_pct() and classify_gear_wear() (Issue #1209)."""

    def test_gear_wear_pct_computes_ratio(self) -> None:
        """The v14's real numbers: 552.5 km against a 643.7 km limit."""
        assert gear_wear_pct(552.5, 643.7) == 85.8

    def test_gear_wear_pct_none_without_max(self) -> None:
        """No recorded limit must not read as worn out."""
        assert gear_wear_pct(552.5, None) is None
        assert gear_wear_pct(None, 643.7) is None

    def test_gear_wear_pct_none_for_non_positive_max(self) -> None:
        """A zero limit means 'unset' in Garmin, not 'instantly worn out'."""
        assert gear_wear_pct(10.0, 0) is None
        assert gear_wear_pct(10.0, -1.0) is None

    def test_classify_gear_wear_bands(self) -> None:
        assert classify_gear_wear(59.9) == "ok"
        assert classify_gear_wear(60.0) == "monitor"
        assert classify_gear_wear(79.9) == "monitor"
        assert classify_gear_wear(80.0) == "due_soon"
        assert classify_gear_wear(99.9) == "due_soon"
        assert classify_gear_wear(100.0) == "over"
        assert classify_gear_wear(106.9) == "over"

    def test_classify_gear_wear_none_passthrough(self) -> None:
        """Unknown stays unknown rather than collapsing to 'ok'."""
        assert classify_gear_wear(None) is None


@pytest.mark.unit
class TestGearAge:
    """Tests for gear_age_months() and classify_gear_age() (Issue #1209)."""

    def test_gear_age_months_counts_whole_months(self) -> None:
        """The novablast: in service 2025-08-20, measured 2026-09-16."""
        assert gear_age_months("2025-08-20", "2026-09-16") == 12

    def test_gear_age_months_rolls_over_on_the_day(self) -> None:
        assert gear_age_months("2025-08-20", "2026-08-19") == 11
        assert gear_age_months("2025-08-20", "2026-08-20") == 12

    def test_gear_age_months_accepts_timestamps(self) -> None:
        """gear.json dates arrive as full timestamps."""
        assert gear_age_months("2025-08-20T00:00:00.0", "2026-09-16") == 12

    def test_gear_age_months_none_without_date(self) -> None:
        assert gear_age_months(None, "2026-09-16") is None

    def test_gear_age_months_none_for_unparseable(self) -> None:
        assert gear_age_months("not-a-date", "2026-09-16") is None

    def test_gear_age_months_never_negative(self) -> None:
        """A future in-service date is clamped, not reported as negative age."""
        assert gear_age_months("2026-12-01", "2026-09-16") == 0

    def test_classify_gear_age_bands(self) -> None:
        assert classify_gear_age(23) == "ok"
        assert classify_gear_age(24) == "aging"
        assert classify_gear_age(35) == "aging"
        assert classify_gear_age(36) == "aged"

    def test_classify_gear_age_none_passthrough(self) -> None:
        assert classify_gear_age(None) is None


@pytest.mark.unit
class TestReplaceRecommended:
    """Tests for replace_recommended() (Issue #1209)."""

    def test_replace_recommended_true_on_due_soon(self) -> None:
        assert replace_recommended("due_soon", "ok") is True

    def test_replace_recommended_true_on_over(self) -> None:
        assert replace_recommended("over", None) is True

    def test_replace_recommended_true_on_aged(self) -> None:
        """An old pair needs replacing however little it has run."""
        assert replace_recommended("ok", "aged") is True

    def test_replace_recommended_false_when_both_below(self) -> None:
        """monitor + aging is a watch, not yet an action."""
        assert replace_recommended("monitor", "aging") is False

    def test_replace_recommended_false_when_unknown(self) -> None:
        assert replace_recommended(None, None) is False
