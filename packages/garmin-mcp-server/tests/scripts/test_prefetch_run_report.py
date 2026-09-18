"""Integration tests for the prefetch_run_report stdout wrapper (Issue #1253).

The ``analyze-activity`` fetch stage runs this module and hands its stdout to
the run-note agent verbatim, so what matters here is the contract at the shell
boundary: one line of JSON on stdout, and a non-zero exit when the activity is
unknown (an empty report must never be analysed as if it were a run).
"""

import json
from pathlib import Path

import pytest

from garmin_mcp.scripts import prefetch_run_report as module

FIXTURE_ACTIVITY_ID = 12345678901


def _patch_db_path(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    """Point the script's get_db_path() at the verification DB."""
    monkeypatch.setattr(
        "garmin_mcp.scripts.prefetch_run_report.get_db_path",
        lambda *a, **k: db_path,
    )


@pytest.mark.integration
def test_prefetch_run_report_prints_json(
    verification_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fixture activity prints a parsable report with the agent's keys."""
    _patch_db_path(monkeypatch, verification_db_path)
    monkeypatch.setattr("sys.argv", ["prefetch_run_report", str(FIXTURE_ACTIVITY_ID)])

    module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["activity_id"] == FIXTURE_ACTIVITY_ID
    assert "error" not in payload
    # The two blocks the run-note agent cannot write without.
    assert "headline" in payload
    assert "moments" in payload
    assert "signals" in payload


@pytest.mark.integration
def test_prefetch_run_report_unknown_activity_exits_nonzero(
    verification_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown id fails loudly: exit code 1 plus an ``error`` on stdout."""
    _patch_db_path(monkeypatch, verification_db_path)
    monkeypatch.setattr("sys.argv", ["prefetch_run_report", "1"])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["activity_id"] == 1
    assert "not found" in payload["error"]
