"""tests/support/schema.init_schema builds the template once and copies it (#1062)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.support import schema as schema_support


def _table_names(db_path: Path) -> set[str]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        conn.close()


@pytest.mark.unit
def test_init_schema_builds_template_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two init_schema calls construct GarminDBWriter at most once per process."""
    from garmin_mcp.database import db_writer

    real_writer = db_writer.GarminDBWriter
    calls: list[str] = []

    class CountingWriter(real_writer):  # type: ignore[misc,valid-type]
        def __init__(self, db_path: str | None = None) -> None:
            calls.append(str(db_path))
            super().__init__(db_path=db_path)

    monkeypatch.setattr(db_writer, "GarminDBWriter", CountingWriter)
    # Force a rebuild inside this test so the count is observable regardless
    # of which test on this worker touched the template first.
    monkeypatch.setattr(schema_support, "_TEMPLATE", None)

    first = schema_support.init_schema(tmp_path / "a.duckdb")
    second = schema_support.init_schema(tmp_path / "b.duckdb")

    assert len(calls) == 1
    assert "activities" in _table_names(first)
    assert "activities" in _table_names(second)


@pytest.mark.unit
def test_init_schema_copies_are_independent(tmp_path: Path) -> None:
    """A row inserted into one copy never shows up in another."""
    a = schema_support.init_schema(tmp_path / "a.duckdb")
    b = schema_support.init_schema(tmp_path / "nested" / "b.duckdb")

    conn = duckdb.connect(str(a))
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date) VALUES (1, '2025-01-01')"
    )
    conn.close()

    conn = duckdb.connect(str(b), read_only=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone() == (0,)
    finally:
        conn.close()


@pytest.mark.unit
def test_initialized_db_path_fixture_has_schema(initialized_db_path: Path) -> None:
    assert initialized_db_path.exists()
    assert {"activities", "splits", "schema_version"} <= _table_names(
        initialized_db_path
    )
