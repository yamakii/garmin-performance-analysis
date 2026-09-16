"""Tests for the gear derivations (Issue #1207).

``is_new_gear`` is the break-in window; ``format_gear_label`` names a shoe the
way the athlete does now that Garmin's gear form keeps the version in the
nickname rather than in the model string.
"""

import pytest

from garmin_mcp.analysis.derivations import format_gear_label, is_new_gear


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
