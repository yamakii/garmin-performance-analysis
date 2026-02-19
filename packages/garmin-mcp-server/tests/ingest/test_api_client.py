"""Tests for Garmin Connect API client singleton."""

import os
from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from garmin_mcp.ingest.api_client import get_garmin_client, reset_client


@pytest.mark.unit
class TestGetGarminClient:
    """Tests for get_garmin_client() and reset_client()."""

    @pytest.fixture(autouse=True)
    def _cleanup_singleton(self) -> Generator[None, None, None]:  # noqa: PT004
        """Reset singleton state after each test."""
        yield
        reset_client()

    def test_missing_credentials_raises_value_error(
        self, mocker: MockerFixture
    ) -> None:
        """No GARMIN_EMAIL env var raises ValueError."""
        mocker.patch.dict(os.environ, {}, clear=True)
        with pytest.raises(ValueError, match="Garmin credentials not found"):
            get_garmin_client()

    def test_token_login_success(self, mocker: MockerFixture) -> None:
        """Token login succeeds and returns client."""
        mocker.patch.dict(
            os.environ,
            {
                "GARMIN_EMAIL": "test@test.com",
                "GARMIN_PASSWORD": "pass",
                "GARMINTOKENS": "/tmp/test_tokens",
            },
        )
        mock_garmin_cls = mocker.patch("garmin_mcp.ingest.api_client.Garmin")
        mock_instance = mock_garmin_cls.return_value

        result = get_garmin_client()

        assert result is mock_instance
        mock_garmin_cls.assert_called_once_with("test@test.com", "pass")
        mock_instance.login.assert_called_once()
        # Token login is called with a path argument
        args, _ = mock_instance.login.call_args
        assert len(args) == 1  # tokenstore_path passed
        mock_instance.garth.dump.assert_called_once()

    def test_token_login_failure_falls_back_to_credential(
        self, mocker: MockerFixture
    ) -> None:
        """Token login raises exception, falls back to credential login."""
        mocker.patch.dict(
            os.environ,
            {
                "GARMIN_EMAIL": "test@test.com",
                "GARMIN_PASSWORD": "pass",
                "GARMINTOKENS": "/tmp/test_tokens",
            },
        )
        mock_garmin_cls = mocker.patch("garmin_mcp.ingest.api_client.Garmin")
        mock_instance = mock_garmin_cls.return_value

        # First call (with token path) raises, second call (no args) succeeds
        mock_instance.login.side_effect = [FileNotFoundError("no tokens"), None]

        result = get_garmin_client()

        assert result is mock_instance
        assert mock_instance.login.call_count == 2
        # First call: token login with path
        first_call_args, _ = mock_instance.login.call_args_list[0]
        assert len(first_call_args) == 1
        # Second call: credential login without path
        second_call_args, _ = mock_instance.login.call_args_list[1]
        assert len(second_call_args) == 0
        mock_instance.garth.dump.assert_called_once()

    def test_singleton_returns_same_instance(self, mocker: MockerFixture) -> None:
        """Calling get_garmin_client() twice returns the same object."""
        mocker.patch.dict(
            os.environ,
            {
                "GARMIN_EMAIL": "test@test.com",
                "GARMIN_PASSWORD": "pass",
                "GARMINTOKENS": "/tmp/test_tokens",
            },
        )
        mock_garmin_cls = mocker.patch("garmin_mcp.ingest.api_client.Garmin")

        first = get_garmin_client()
        second = get_garmin_client()

        assert first is second
        mock_garmin_cls.assert_called_once()  # Only constructed once

    def test_reset_client_clears_singleton(self, mocker: MockerFixture) -> None:
        """After reset_client(), get_garmin_client() creates a new instance."""
        mocker.patch.dict(
            os.environ,
            {
                "GARMIN_EMAIL": "test@test.com",
                "GARMIN_PASSWORD": "pass",
                "GARMINTOKENS": "/tmp/test_tokens",
            },
        )
        mock_garmin_cls = mocker.patch("garmin_mcp.ingest.api_client.Garmin")

        first = get_garmin_client()
        reset_client()

        # Create a different mock instance for the second call
        second_mock = mocker.Mock()
        mock_garmin_cls.return_value = second_mock

        second = get_garmin_client()

        assert first is not second
        assert second is second_mock
        assert mock_garmin_cls.call_count == 2  # Constructed twice
