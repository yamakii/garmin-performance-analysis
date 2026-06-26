"""Guard: weekly-review skill integrates recovery (RHR / HRV / sleep) signals.

The weekly-review is a prompt-driven workflow (orchestrated by the main session,
no Python generator), so the testable artifact is the SKILL.md prompt itself.
This test asserts the prompt instructs the orchestrator to:

- prefetch the recovery tools (``get_recovery_trend`` / ``get_recovery_status``),
- narrate the prior week's RHR trend and HRV baseline breach,
- combine load (ACWR) with recovery into a composite verdict, while degrading
  gracefully when recovery data is missing, and
- surface a personal-baseline early-warning note (#560) pairing each deviation
  (``get_wellness_baseline_deviation`` / HRV baseline breach) with a preventive
  action, persisted via ``review_data.recovery.early_warning_flag`` /
  ``early_warning_note``.

Catches regressions where the recovery integration (#503) or the early-warning
note integration (#560) is dropped from the prompt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# packages/garmin-mcp-server/tests/docs/<this file> -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SKILL = _REPO_ROOT / ".claude" / "skills" / "weekly-review" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert _SKILL.exists(), f"weekly-review SKILL.md not found at {_SKILL}"
    return _SKILL.read_text(encoding="utf-8")


@pytest.mark.integration
def test_weekly_review_includes_recovery_section(skill_text: str) -> None:
    """The prompt prefetches recovery tools and narrates RHR/HRV/sleep."""
    # Recovery prefetch tools must be instructed.
    assert "get_recovery_trend" in skill_text
    assert "get_recovery_status" in skill_text

    # RHR / HRV / sleep / readiness narration must be present.
    assert "RHR" in skill_text
    assert "HRV" in skill_text
    assert "睡眠" in skill_text
    assert "training readiness" in skill_text

    # The structured save schema must carry a recovery block.
    assert '"recovery"' in skill_text
    assert "rhr_trend" in skill_text
    assert "hrv_under_recovery" in skill_text


@pytest.mark.integration
def test_weekly_review_composite_load_recovery_verdict(skill_text: str) -> None:
    """Load (ACWR) x recovery (HRV/RHR) composite narration is required."""
    # Composite verdicts from the design.
    assert "積み過ぎ・回復不足" in skill_text
    assert "順調に吸収" in skill_text

    # Graceful degradation when recovery data is missing.
    assert "回復データ不足のため負荷ベースで講評" in skill_text


@pytest.mark.integration
def test_skill_includes_early_warning_instruction(skill_text: str) -> None:
    """Personal-baseline deviation (#555) must drive an early-warning note.

    Step 5-A-5 must instruct the orchestrator to pull
    ``get_wellness_baseline_deviation`` / HRV baseline breach and emit an
    early-warning note pairing the deviation's consequence with a
    preventive action.
    """
    # The #555 deviation tool must be referenced.
    assert "get_wellness_baseline_deviation" in skill_text

    # Early-warning note framing (consequence + preventive action).
    assert "early-warning" in skill_text
    assert "個人ベースライン逸脱" in skill_text
    assert "HRV ベースライン割れ" in skill_text
    # Preventive action examples from the design.
    assert "質練を" in skill_text
    assert "deload" in skill_text


@pytest.mark.integration
def test_skill_review_data_has_early_warning_fields(skill_text: str) -> None:
    """Step 7 review_data.recovery must carry the early-warning fields."""
    assert '"early_warning_flag"' in skill_text
    assert '"early_warning_note"' in skill_text
