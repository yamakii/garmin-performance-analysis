"""Unit tests for the shared Garmin API retry helpers (issue #711).

Exercises :func:`call_with_retry` (429 exponential backoff, 401 re-auth,
immediate raise for non-retryable errors) plus the pure classification helpers
moved from ``scripts/backfill_wellness.py``. All sleeps are injected so no real
wait occurs, and the singleton reset / re-auth hooks are monkeypatched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from garmin_mcp.ingest import retry
from garmin_mcp.ingest.retry import (
    call_with_retry,
    is_auth_error,
    is_rate_limit_error,
)


class _FakeTooManyRequestsError(Exception):
    """Stand-in matching GarminConnectTooManyRequestsError by class name."""


_FakeTooManyRequestsError.__name__ = "GarminConnectTooManyRequestsError"


class _FakeAuthError(Exception):
    """Stand-in matching GarminConnectAuthenticationError by class name."""


_FakeAuthError.__name__ = "GarminConnectAuthenticationError"


# --------------------------------------------------------------------------- #
# call_with_retry
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_call_with_retry_backs_off_on_429() -> None:
    """Two 429s then success -> 3 calls, backoff sleeps of [60, 120]s."""
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise _FakeTooManyRequestsError("429 Too Many Requests")
        return "ok"

    sleeps: list[float] = []
    result = call_with_retry(fn, sleep=sleeps.append)

    assert result == "ok"
    assert calls["n"] == 3
    assert sleeps == [60.0, 120.0]


@pytest.mark.unit
def test_call_with_retry_raises_after_max_attempts() -> None:
    """Continuous 429 with max_attempts=3 -> 3 tries then original raise."""
    calls = {"n": 0}

    def fn() -> None:
        calls["n"] += 1
        raise _FakeTooManyRequestsError("429 Too Many Requests")

    with pytest.raises(_FakeTooManyRequestsError):
        call_with_retry(fn, max_attempts=3, sleep=lambda _s: None)

    assert calls["n"] == 3


@pytest.mark.unit
def test_call_with_retry_reauths_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 resets the client, re-authenticates once, then retries to success."""
    reset_mock = MagicMock()
    getclient_mock = MagicMock()
    monkeypatch.setattr(retry, "reset_client", reset_mock)
    monkeypatch.setattr(retry, "get_garmin_client", getclient_mock)

    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _FakeAuthError("401 Unauthorized")
        return "ok"

    result = call_with_retry(fn, sleep=lambda _s: None)

    assert result == "ok"
    assert calls["n"] == 2
    reset_mock.assert_called_once()
    getclient_mock.assert_called_once()


@pytest.mark.unit
def test_call_with_retry_raises_non_retryable_immediately() -> None:
    """A ValueError is re-raised immediately with no backoff sleep."""
    sleeps: list[float] = []

    def fn() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        call_with_retry(fn, sleep=sleeps.append)

    assert sleeps == []


# --------------------------------------------------------------------------- #
# is_auth_error
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_is_auth_error_detects_401() -> None:
    """A '401 Unauthorized' message is classified as an auth error."""
    assert is_auth_error(Exception("401 Unauthorized")) is True
    assert is_auth_error(_FakeAuthError("session expired")) is True
    assert is_auth_error(ValueError("boom")) is False


@pytest.mark.unit
def test_is_rate_limit_error_not_auth() -> None:
    """A rate-limit error is not misclassified as an auth error."""
    exc = _FakeTooManyRequestsError("429 Too Many Requests")
    assert is_rate_limit_error(exc) is True
    assert is_auth_error(exc) is False
