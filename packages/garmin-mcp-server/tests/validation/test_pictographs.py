"""Tests for the emoji guard on web-bound prose (Issue #1428).

The web app states verdicts in words or the ``✓`` / ``!`` glyphs (#1186 /
#1187 / #1188). These tests pin what counts as emoji -- and what the design
system still uses on purpose -- so the write gate and the display strip agree.
"""

from __future__ import annotations

import pytest

from garmin_mcp.validation.pictographs import (
    find_pictographs,
    reject_pictographs,
    strip_pictographs,
    strip_pictographs_deep,
)


@pytest.mark.unit
def test_find_pictographs_nested_paths() -> None:
    payload = {"overall": "✅良い", "recommendations": ["ok", "⚠️注意"]}

    assert find_pictographs(payload) == ["overall", "recommendations[1]"]


@pytest.mark.unit
def test_find_pictographs_exempts_rating() -> None:
    assert find_pictographs({"rating": "✅", "rationale": "ok"}) == []
    assert find_pictographs([{"rating": "🔴", "title": "閾値走"}]) == []


@pytest.mark.unit
def test_allowed_glyphs_pass() -> None:
    assert find_pictographs("✓ 良好 ! ★★★★☆ ⚠") == []
    # The same warning sign with the emoji variation selector renders as emoji.
    assert find_pictographs("⚠️") == ["<value>"]


@pytest.mark.unit
@pytest.mark.parametrize("mark", ["✅", "🟡", "🔴", "🟢", "❌", "⭐", "⚡", "🏃"])
def test_find_pictographs_catches_verdict_and_pictograph_marks(mark: str) -> None:
    assert find_pictographs({"text": f"{mark}ロング"}) == ["text"]


@pytest.mark.unit
def test_reject_pictographs_names_where_and_paths() -> None:
    with pytest.raises(ValueError, match=r"save_weekly_review: .*overall"):
        reject_pictographs({"overall": "🟡注意"}, where="save_weekly_review")


@pytest.mark.unit
def test_reject_pictographs_passes_plain_prose() -> None:
    reject_pictographs({"overall": "注意が必要な週です"}, where="save_weekly_review")


@pytest.mark.unit
def test_strip_pictographs() -> None:
    assert strip_pictographs("🟢絞る週 ✅ロング") == "絞る週 ロング"
    assert strip_pictographs("⚠️一方で") == "一方で"
    assert strip_pictographs("そのまま ★4.0") == "そのまま ★4.0"


@pytest.mark.unit
def test_strip_pictographs_deep_keeps_rating() -> None:
    review = {
        "overall": "✅ロング復活",
        "verdict": [{"rating": "✅", "comment": "🟡条件付き"}],
    }

    assert strip_pictographs_deep(review) == {
        "overall": "ロング復活",
        "verdict": [{"rating": "✅", "comment": "条件付き"}],
    }
