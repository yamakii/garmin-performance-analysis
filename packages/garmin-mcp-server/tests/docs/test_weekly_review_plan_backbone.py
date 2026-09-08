"""Guard: the weekly review is anchored on the stored block, not Garmin (#980).

`/weekly-review` and `/daily-checkin` are prompt-driven (no Python generator),
so the testable artifact is the SKILL.md prompt. These tests assert the prompts
keep the three properties issue #980 introduced:

- the review's backbone is ``training_block`` (block + long-run ladder step)
  and the phase gap is measured against it, not against the Garmin plan;
- Garmin's calendar only enters through ``garmin_conflicts``;
- the review saves structured prescriptions via ``save_weekly_prescriptions``
  using the ``review_id`` returned by ``save_weekly_review``, and the daily
  check-in reads those rows (``get_weekly_prescriptions``) as its backbone.

Catches regressions where the backbone silently reverts to the Garmin adaptive
plan or the structured save is dropped back to prose-only ``verdict`` rows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# packages/garmin-mcp-server/tests/docs/<this file> -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_WEEKLY_REVIEW = _REPO_ROOT / ".claude" / "skills" / "weekly-review" / "SKILL.md"
_DAILY_CHECKIN = _REPO_ROOT / ".claude" / "skills" / "daily-checkin" / "SKILL.md"


@pytest.fixture(scope="module")
def weekly_review_text() -> str:
    assert (
        _WEEKLY_REVIEW.exists()
    ), f"weekly-review SKILL.md not found at {_WEEKLY_REVIEW}"
    return _WEEKLY_REVIEW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def daily_checkin_text() -> str:
    assert (
        _DAILY_CHECKIN.exists()
    ), f"daily-checkin SKILL.md not found at {_DAILY_CHECKIN}"
    return _DAILY_CHECKIN.read_text(encoding="utf-8")


@pytest.mark.integration
def test_weekly_review_backbone_is_training_block(weekly_review_text: str) -> None:
    """Step 3 reads the block + ladder step and the gap is block-relative."""
    assert "training_block" in weekly_review_text
    assert "ladder_step" in weekly_review_text
    assert "weeks_to_block_end" in weekly_review_text
    assert "quality_sessions_per_week" in weekly_review_text
    # The gap is measured against the stored block, not the Garmin plan.
    assert "登録ブロックとのギャップ" in weekly_review_text
    assert '"block_alignment"' in weekly_review_text


@pytest.mark.integration
def test_weekly_review_garmin_is_conflicts_only(weekly_review_text: str) -> None:
    """Garmin's calendar enters only through the deterministic conflict list."""
    assert "garmin_conflicts" in weekly_review_text
    for reason in (
        "quality_on_long_day",
        "second_quality_session",
        "quality_in_cutback_week",
    ):
        assert reason in weekly_review_text


@pytest.mark.integration
def test_weekly_review_saves_structured_prescriptions(
    weekly_review_text: str,
) -> None:
    """Step 7 saves the review, then its prescriptions linked by review_id."""
    assert "save_weekly_prescriptions" in weekly_review_text
    assert "review_id" in weekly_review_text
    # The prev-week adherence is transcribed, never recomputed.
    assert "prescriptions_prev_week" in weekly_review_text


@pytest.mark.integration
def test_daily_checkin_reads_prescriptions_as_backbone(
    daily_checkin_text: str,
) -> None:
    """The check-in's backbone is today's structured prescription row."""
    assert "get_weekly_prescriptions" in daily_checkin_text
    assert "date=<対象日>" in daily_checkin_text
    # get_weekly_review stays, demoted to context.
    assert "get_weekly_review" in daily_checkin_text


@pytest.mark.integration
def test_weekly_review_saves_rating_in_prescriptions_not_verdict(
    weekly_review_text: str,
) -> None:
    """The per-day rating/comment is saved as prescription fields, not verdict."""
    assert '"rating"' in weekly_review_text
    assert "rationale" in weekly_review_text
    # The review JSON example must not carry per-day verdict rows any more.
    assert '"verdict"' not in weekly_review_text


@pytest.mark.integration
def test_weekly_review_has_mid_week_revision_step(weekly_review_text: str) -> None:
    """A mid-week revision re-issues the review version with the new batch."""
    assert "プランを改訂" in weekly_review_text
    assert "revision_note" in weekly_review_text
    assert "schedule_weekly_prescriptions" in weekly_review_text


@pytest.mark.integration
def test_daily_checkin_matches_review_id(daily_checkin_text: str) -> None:
    """The check-in only layers the review prose when the review_id matches."""
    assert "review_id" in daily_checkin_text
    assert "fbtAdaptiveWorkout" in daily_checkin_text


@pytest.mark.unit
def test_weekly_review_skill_states_target_minutes_convention(
    weekly_review_text: str,
) -> None:
    """``target_minutes`` is the whole run except for quality bodies (#1041).

    The builder registers long/easy/recovery as a single step of exactly
    ``target_minutes`` and the reconciler compares it with no allowance, so the
    skill has to say the number is the total. Quality sessions keep the
    body-only convention (the tool adds the 10+5 min bookends).
    """
    assert "`target_minutes` の定義" in weekly_review_text
    # Quality sessions: body only.
    assert "本体のみ" in weekly_review_text
    # long / easy / recovery: the whole run.
    assert "全体（総量）" in weekly_review_text
    assert "本体だけの分数を入れてはいけない" in weekly_review_text
    # The title must not advertise a different total than target_minutes.
    assert "別の総量を名乗らない" in weekly_review_text


@pytest.mark.unit
def test_weekly_review_skill_has_no_bookend_split_example(
    weekly_review_text: str,
) -> None:
    """No example row splits an easy run into W/U + body + C/D minutes (#1041).

    Batch 6 rows such as ``計35分（W/U10分＋本体20分＋C/D5分）`` with
    ``target_minutes=20`` are exactly what the convention forbids; the skill
    must not model that shape anywhere.
    """
    bookend_split = re.compile(r"W/U\s*\d+\s*分\s*[＋+]\s*本体")
    assert bookend_split.search(weekly_review_text) is None
