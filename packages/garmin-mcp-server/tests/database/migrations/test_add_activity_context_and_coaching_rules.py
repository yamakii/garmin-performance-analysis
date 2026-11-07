"""Tests for the activity_context + coaching_rules migration (Issue #1520)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_activity_context_and_coaching_rules import (
    add_activity_context_and_coaching_rules,
)
from garmin_mcp.database.migrations.registry import MIGRATIONS


@pytest.mark.unit
def test_registry_has_version_36() -> None:
    """The tables are registered as migration 36, the schema head."""
    assert (36, "add_activity_context_and_coaching_rules") in [
        (version, name) for version, name, _ in MIGRATIONS
    ]
    assert max(version for version, _, _ in MIGRATIONS) == 36


@pytest.mark.integration
def test_migration_36_idempotent(tmp_path: Path) -> None:
    conn = duckdb.connect(str(tmp_path / "m36.duckdb"))
    try:
        add_activity_context_and_coaching_rules(conn)
        add_activity_context_and_coaching_rules(conn)

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        conn.execute("INSERT INTO activity_context (activity_id, kind) VALUES (1, 'x')")
        conn.execute(
            "INSERT INTO coaching_rules (scope, rule_text) VALUES ('all', 'r')"
        )
        ctx = conn.execute("SELECT context_id, user_id, source FROM activity_context")
        ctx_row = ctx.fetchone()
        rule = conn.execute("SELECT rule_id, active FROM coaching_rules").fetchone()
    finally:
        conn.close()

    assert {"activity_context", "coaching_rules"} <= tables
    assert ctx_row == (1, "default", "athlete_stated")
    assert rule == (1, True)
