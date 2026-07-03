"""Tests for the garmin-web CLI entrypoint."""

import logging
from unittest.mock import patch

import pytest

from garmin_web.cli import main


@pytest.mark.unit
def test_cli_default_args(monkeypatch):
    monkeypatch.setattr("sys.argv", ["garmin-web"])
    with (
        patch("garmin_web.cli.uvicorn.run") as mock_run,
        patch("garmin_web.cli.create_app") as mock_create_app,
    ):
        main()

    mock_run.assert_called_once_with(
        mock_create_app.return_value, host="127.0.0.1", port=8765
    )


@pytest.mark.unit
def test_cli_warns_on_public_host(monkeypatch, caplog):
    monkeypatch.setattr("sys.argv", ["garmin-web", "--host", "0.0.0.0"])
    with (
        patch("garmin_web.cli.uvicorn.run"),
        patch("garmin_web.cli.create_app"),
        caplog.at_level(logging.WARNING, logger="garmin_web.cli"),
    ):
        main()

    assert any(
        "WITHOUT authentication" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    )


@pytest.mark.unit
def test_cli_no_warning_on_localhost(monkeypatch, caplog):
    monkeypatch.setattr("sys.argv", ["garmin-web", "--host", "127.0.0.1"])
    with (
        patch("garmin_web.cli.uvicorn.run"),
        patch("garmin_web.cli.create_app"),
        caplog.at_level(logging.WARNING, logger="garmin_web.cli"),
    ):
        main()

    assert not any(
        "WITHOUT authentication" in record.message for record in caplog.records
    )
