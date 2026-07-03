"""Shared Garmin API retry helpers (429 backoff + 401 re-auth).

Central home for the rate-limit / authentication retry logic that used to live
only in ``scripts/backfill_wellness.py``. The pure classification + backoff
helpers (``is_rate_limit_error``, ``backoff_seconds``, ``jittered``) are moved
here verbatim, and a single :func:`call_with_retry` wrapper applies them to any
Garmin API callable so every ingest path (running / weight / wellness / raw data
collection) is protected uniformly.

Retry policy:

- **429 / rate-limit** → exponential backoff (:func:`backoff_seconds`) with up to
  ``max_attempts`` total attempts, then the original exception is re-raised.
- **401 / auth** → reset the singleton client and re-authenticate exactly once,
  then retry the call one more time. A second auth failure propagates.
- **Anything else** → re-raised immediately (no backoff, no sleep).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from garmin_mcp.ingest.api_client import get_garmin_client, reset_client

logger = logging.getLogger(__name__)


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True when ``exc`` indicates a Garmin rate-limit / 429 response.

    Detects :class:`GarminConnectTooManyRequestsError` by class name (avoids a
    hard import dependency) and the strings ``"429"`` / ``"Too Many Requests"``
    in the exception message.

    Args:
        exc: The exception to classify.

    Returns:
        True if the exception is a rate-limit error, False otherwise.
    """
    if type(exc).__name__ == "GarminConnectTooManyRequestsError":
        return True
    message = str(exc).lower()
    return "429" in message or "too many requests" in message


def is_auth_error(exc: Exception) -> bool:
    """Return True when ``exc`` indicates an expired / rejected auth session.

    Detects :class:`GarminConnectAuthenticationError` by class name (avoids a
    hard import dependency) and the strings ``"401"`` / ``"unauthorized"`` in the
    exception message.

    Args:
        exc: The exception to classify.

    Returns:
        True if the exception is an authentication error, False otherwise.
    """
    if type(exc).__name__ == "GarminConnectAuthenticationError":
        return True
    message = str(exc).lower()
    return "401" in message or "unauthorized" in message


def backoff_seconds(attempt: int, base: float = 60.0, cap: float = 600.0) -> float:
    """Exponential backoff: ``base * 2**attempt`` capped at ``cap``.

    Args:
        attempt: Zero-based retry attempt (0 -> base, 1 -> 2*base, ...).
        base: Base delay in seconds for ``attempt == 0``.
        cap: Maximum delay in seconds.

    Returns:
        The (capped) backoff delay in seconds.
    """
    return float(min(base * (2.0**attempt), cap))


def jittered(throttle: float, jitter: float, rand: float) -> float:
    """Apply +/-``jitter`` fractional jitter to ``throttle``.

    Maps ``rand`` in ``[0, 1)`` linearly onto ``[throttle*(1-jitter),
    throttle*(1+jitter)]`` so callers can inject a deterministic ``rand`` in
    tests.

    Args:
        throttle: Base throttle in seconds.
        jitter: Jitter fraction (e.g. ``0.2`` for +/-20%).
        rand: Random value in ``[0, 1)``.

    Returns:
        The jittered throttle in seconds.
    """
    low = throttle * (1.0 - jitter)
    high = throttle * (1.0 + jitter)
    return low + (high - low) * rand


def call_with_retry[T](
    fn: Callable[..., T],
    *args: Any,
    max_attempts: int = 4,
    cap: float = 600.0,
    sleep: Callable[[float], None] | None = None,
    **kwargs: Any,
) -> T:
    """Call ``fn(*args, **kwargs)`` with 429 backoff + 401 re-auth retries.

    On a rate-limit (429) error the call is retried with exponential backoff
    (:func:`backoff_seconds`) up to ``max_attempts`` total attempts; once the
    budget is exhausted the original exception is re-raised. On an auth (401)
    error the singleton Garmin client is reset and re-authenticated exactly
    once, then the call is retried a single time. Any other exception is
    re-raised immediately without sleeping.

    Args:
        fn: The Garmin API callable to invoke.
        *args: Positional arguments forwarded to ``fn``.
        max_attempts: Maximum total attempts for rate-limit retries.
        cap: Backoff cap in seconds passed to :func:`backoff_seconds`.
        sleep: Injectable sleep function (defaults to :func:`time.sleep`).
        **kwargs: Keyword arguments forwarded to ``fn``.

    Returns:
        The return value of ``fn`` on success.

    Raises:
        Exception: The last rate-limit error once retries are exhausted, a
            second auth error, or any non-retryable exception immediately.
    """
    do_sleep = sleep if sleep is not None else time.sleep
    reauthed = False
    rate_limit_attempt = 0

    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - classify then re-raise
            if is_rate_limit_error(exc):
                # rate_limit_attempt is the count of prior 429 retries; once we
                # reach max_attempts total tries, give up and re-raise.
                if rate_limit_attempt >= max_attempts - 1:
                    logger.warning(
                        "call_with_retry: rate-limited, retries exhausted "
                        "(%d attempts)",
                        max_attempts,
                    )
                    raise
                delay = backoff_seconds(rate_limit_attempt, cap=cap)
                logger.warning(
                    "call_with_retry: rate-limited, backing off %.0fs "
                    "(attempt %d/%d)",
                    delay,
                    rate_limit_attempt + 1,
                    max_attempts,
                )
                rate_limit_attempt += 1
                do_sleep(delay)
                continue
            if is_auth_error(exc) and not reauthed:
                logger.warning(
                    "call_with_retry: auth error, resetting client and "
                    "re-authenticating"
                )
                reauthed = True
                reset_client()
                get_garmin_client()
                continue
            raise
