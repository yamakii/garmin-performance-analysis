"""Tests for the activity_context / coaching_rules store (Issue #1520).

The tables live on a named in-memory DuckDB (``memory_db_path``), built from
the migration DDL plus a minimal ``activities`` table, so no file is written.
"""

from __future__ import annotations

import duckdb
import pytest

from garmin_mcp.database.inserters.athlete import (
    deactivate_coaching_rule,
    insert_activity_context,
    insert_coaching_rule,
)
from garmin_mcp.database.migrations.add_activity_context_and_coaching_rules import (
    add_activity_context_and_coaching_rules,
)
from garmin_mcp.database.readers.athlete import AthleteReader


@pytest.fixture
def store_db(memory_db_path: str) -> str:
    """In-memory DB with both new tables and two dated activities."""
    conn = duckdb.connect(memory_db_path)
    try:
        add_activity_context_and_coaching_rules(conn)
        conn.execute(
            "CREATE TABLE activities ("
            "activity_id BIGINT PRIMARY KEY, activity_date DATE NOT NULL)"
        )
        conn.execute(
            "INSERT INTO activities VALUES (1, '2026-10-28'), (2, '2026-10-30')"
        )
    finally:
        conn.close()
    return memory_db_path


@pytest.mark.unit
def test_insert_and_read_activity_context_roundtrip(store_db: str) -> None:
    context_id = insert_activity_context(
        {"activity_id": 1, "kind": "load", "load_kg": 3.0}, db_path=store_db
    )

    rows = AthleteReader(db_path=store_db).get_activity_context([1])

    assert len(rows) == 1
    row = rows[0]
    assert row["context_id"] == context_id
    assert row["load_kg"] == 3.0
    assert row["source"] == "athlete_stated"
    assert row["user_id"] == "default"
    assert row["activity_date"] == "2026-10-28"


@pytest.mark.unit
def test_activity_context_latest_row_wins_per_kind(store_db: str) -> None:
    insert_activity_context(
        {"activity_id": 1, "kind": "load", "load_kg": 2.0}, db_path=store_db
    )
    insert_activity_context(
        {"activity_id": 1, "kind": "load", "load_kg": 3.0}, db_path=store_db
    )
    insert_activity_context(
        {"activity_id": 1, "kind": "commute", "value": "to office"},
        db_path=store_db,
    )

    rows = AthleteReader(db_path=store_db).get_activity_context([1])

    loads = [r for r in rows if r["kind"] == "load"]
    assert len(loads) == 1
    assert loads[0]["load_kg"] == 3.0
    assert {r["kind"] for r in rows} == {"commute", "load"}


@pytest.mark.unit
def test_activity_context_date_range_filter(store_db: str) -> None:
    insert_activity_context({"activity_id": 1, "kind": "commute"}, db_path=store_db)
    insert_activity_context({"activity_id": 2, "kind": "commute"}, db_path=store_db)

    rows = AthleteReader(db_path=store_db).get_activity_context(start_date="2026-10-29")

    assert [(r["activity_id"], r["activity_date"]) for r in rows] == [(2, "2026-10-30")]


@pytest.mark.unit
def test_get_activity_context_missing_table_returns_empty(
    memory_db_path: str,
) -> None:
    reader = AthleteReader(db_path=memory_db_path)

    assert reader.get_activity_context([1]) == []
    assert reader.get_coaching_rules() == []


@pytest.mark.unit
def test_coaching_rules_scope_filter_includes_all(store_db: str) -> None:
    all_id = insert_coaching_rule(
        {"scope": "all", "rule_text": "Answer in Japanese."}, db_path=store_db
    )
    insert_coaching_rule(
        {"scope": "run_note", "rule_text": "Cite only comparable runs."},
        db_path=store_db,
    )

    rows = AthleteReader(db_path=store_db).get_coaching_rules(scopes=["checkin"])

    assert [r["rule_id"] for r in rows] == [all_id]
    assert rows[0]["scope"] == "all"


@pytest.mark.unit
def test_deactivated_rule_hidden_by_default(store_db: str) -> None:
    rule_id = insert_coaching_rule(
        {
            "scope": "conversation",
            "rule_text": "Do not propose a cool-morning test.",
            "rationale": "Repeated proposal was rejected.",
            "origin_date": "2026-09-15",
        },
        db_path=store_db,
    )

    assert deactivate_coaching_rule(rule_id, db_path=store_db) is True

    reader = AthleteReader(db_path=store_db)
    assert reader.get_coaching_rules() == []
    rows = reader.get_coaching_rules(include_inactive=True)
    assert len(rows) == 1
    assert rows[0]["active"] is False
    assert rows[0]["deactivated_at"] is not None
    assert rows[0]["origin_date"] == "2026-09-15"


@pytest.mark.unit
def test_deactivate_unknown_rule_returns_false(store_db: str) -> None:
    assert deactivate_coaching_rule(999, db_path=store_db) is False
