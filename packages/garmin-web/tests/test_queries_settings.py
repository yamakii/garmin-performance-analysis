"""Tests for garmin_web.queries.settings (Issue #605)."""

import pytest

from garmin_web.queries.settings import get_week_start_day


@pytest.mark.integration
def test_week_start_day_default_when_no_profile(settings_conn_no_profile):
    """No profile row -> falls back to 0 (Monday)."""
    assert get_week_start_day(settings_conn_no_profile) == 0


@pytest.mark.integration
def test_week_start_day_from_profile(settings_conn_sunday_start):
    """A stored week_start_day of 6 (Sunday) is returned as-is."""
    assert get_week_start_day(settings_conn_sunday_start) == 6
