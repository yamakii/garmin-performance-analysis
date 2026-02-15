"""Garmin Connect API client with singleton authentication.

Thread-safe singleton pattern for Garmin API authentication.
Credentials read from GARMIN_EMAIL and GARMIN_PASSWORD environment variables.
"""

import logging
import os
import threading

from garminconnect import Garmin

logger = logging.getLogger(__name__)

_client: Garmin | None = None
_lock = threading.Lock()


def get_garmin_client() -> Garmin:
    """Get or create singleton Garmin client (reuse authentication).

    Thread-safe singleton that reads credentials from environment variables:
    - GARMIN_EMAIL
    - GARMIN_PASSWORD

    Returns:
        Authenticated Garmin client

    Raises:
        ValueError: If credentials not found in environment
    """
    global _client

    if _client is not None:
        return _client

    with _lock:
        # Double-check after acquiring lock
        if _client is not None:
            return _client

        email = os.getenv("GARMIN_EMAIL")
        password = os.getenv("GARMIN_PASSWORD")

        if not email or not password:
            raise ValueError(
                "Garmin credentials not found. "
                "Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables."
            )

        logger.info(f"Authenticating with Garmin Connect as {email}")
        client = Garmin(email, password)
        client.login()
        logger.info("Garmin authentication successful")
        _client = client

    return _client


def reset_client() -> None:
    """Reset singleton client (for testing)."""
    global _client
    with _lock:
        _client = None
