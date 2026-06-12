"""Tests for the garmin-web CLI entrypoint."""

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
