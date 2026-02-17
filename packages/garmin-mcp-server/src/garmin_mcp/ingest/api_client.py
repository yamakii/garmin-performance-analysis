"""Garmin Connect API client with singleton authentication.

Thread-safe singleton pattern for Garmin API authentication.
Credentials read from GARMIN_EMAIL and GARMIN_PASSWORD environment variables.
"""

import logging
import os
import threading
from pathlib import Path

from garminconnect import Garmin

logger = logging.getLogger(__name__)

_client: Garmin | None = None
_lock = threading.Lock()


def get_garmin_client() -> Garmin:
    """Get or create singleton Garmin client (reuse authentication).

    Thread-safe singleton that reads credentials from environment variables:
    - GARMIN_EMAIL
    - GARMIN_PASSWORD
    - GARMINTOKENS (optional, default: ~/.garth) - OAuth token cache directory

    Tries token-based login first (no password sent to Garmin).
    Falls back to credential login if tokens are missing or expired,
    then saves tokens for future use.

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

        tokenstore = os.getenv("GARMINTOKENS", "~/.garth")
        tokenstore_path = str(Path(tokenstore).expanduser().resolve())

        client = Garmin(email, password)

        try:
            client.login(tokenstore_path)
            logger.info(f"Garmin authentication via token cache ({tokenstore_path})")
        except (FileNotFoundError, Exception) as e:
            logger.info(
                f"Token login failed ({type(e).__name__}), "
                f"authenticating with credentials as {email}"
            )
            client.login()
            logger.info("Garmin credential authentication successful")

        # Always save tokens (captures refreshed OAuth2 tokens too)
        client.garth.dump(tokenstore_path)
        logger.info(f"Garmin tokens saved to {tokenstore_path}")

        _client = client

    return _client


def reset_client() -> None:
    """Reset singleton client (for testing)."""
    global _client
    with _lock:
        _client = None
