"""TABLE_PURPOSES stays in step with the live schema (#1604)."""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.table_purposes import TABLE_PURPOSES
from garmin_mcp.scripts.generate_schema_doc import list_domain_tables


@pytest.mark.integration
def test_table_purposes_match_live_schema(initialized_db_path: Path) -> None:
    """A new table cannot ship without a one-line purpose, nor a dropped one linger."""
    live = set(list_domain_tables(str(initialized_db_path)))
    assert set(TABLE_PURPOSES) == live
    assert all(line.strip() for line in TABLE_PURPOSES.values())
