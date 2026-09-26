"""Tests for the intake-confirmation inserter (issue #1434)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.inserters.athlete import insert_intake_confirmation


@pytest.mark.unit
def test_insert_intake_confirmation_upserts(initialized_db_path: Path) -> None:
    db_path = str(initialized_db_path)

    insert_intake_confirmation(
        "2026-09-24", "incomplete", note="夕食未記録", db_path=db_path
    )
    saved = insert_intake_confirmation("2026-09-24", "complete", db_path=db_path)

    assert saved["status"] == "complete"
    conn = duckdb.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, CAST(date AS VARCHAR), status, note "
            "FROM intake_confirmations"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("default", "2026-09-24", "complete", None)]


@pytest.mark.unit
def test_intake_confirmation_rejects_pictographs(initialized_db_path: Path) -> None:
    with pytest.raises(ValueError, match="emoji"):
        insert_intake_confirmation(
            "2026-09-24",
            "complete",
            note="全部記録した \U0001f44d",
            db_path=str(initialized_db_path),
        )


@pytest.mark.unit
def test_intake_confirmation_rejects_unknown_status(
    initialized_db_path: Path,
) -> None:
    with pytest.raises(ValueError, match="status"):
        insert_intake_confirmation(
            "2026-09-24", "partial", db_path=str(initialized_db_path)
        )
