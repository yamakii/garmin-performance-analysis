"""Anti-staleness guard: doc magic numbers must match live code.

Asserts that the hard-coded counts in ``README.md`` and ``CLAUDE.md`` match the
live code surface:

- the MCP tool count (``len(ALL_DEFS) + len(_SERVER_TOOLS)``), and
- the DuckDB domain-table count built from a fresh schema.

Prevents the "14 tables" / "46 tools" drift fixed in #426.
"""

import re
from pathlib import Path

import pytest

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.tool_schemas import _SERVER_TOOLS
from garmin_mcp.tools import ALL_DEFS

# packages/garmin-mcp-server/tests/docs/<this file> -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOC_PATHS = [_REPO_ROOT / "README.md", _REPO_ROOT / "CLAUDE.md"]


def _expected_tool_count() -> int:
    """Return the live MCP tool count (domain tools + server tools)."""
    return len(ALL_DEFS) + len(_SERVER_TOOLS)


def _expected_table_count(db_path: str) -> int:
    """Return the domain-table count for a fresh DB at ``db_path``.

    Building the DB via ``GarminDBWriter`` runs ``_ensure_tables()`` plus
    migrations so the schema is defined without depending on a populated
    production database. ``schema_version`` is excluded as it is bookkeeping.
    """
    GarminDBWriter(db_path=db_path)
    with get_connection(db_path) as con:
        names = [
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main'"
            ).fetchall()
        ]
    return len([n for n in names if n != "schema_version"])


def _numbers_before(noun_pattern: str, text: str) -> list[int]:
    """Return integers that appear directly before ``noun_pattern`` in ``text``.

    ``noun_pattern`` is a regex fragment for the noun (e.g. ``r"(?:MCP )?tools"``).
    The number must be immediately adjacent (only whitespace between), so
    unrelated numbers like "100+ activities" are ignored.
    """
    pattern = re.compile(rf"(\d+)\s+{noun_pattern}")
    return [int(m.group(1)) for m in pattern.finditer(text)]


@pytest.mark.unit
def test_numbers_before_captures_count() -> None:
    assert _numbers_before(r"(?:MCP )?tools", "46 MCP tools and 19 tables") == [46]


@pytest.mark.unit
def test_numbers_before_ignores_unrelated() -> None:
    assert _numbers_before(r"(?:domain )?tables", "100+ activities") == []


@pytest.mark.unit
def test_readme_tool_count_matches_registry() -> None:
    """Any ``N tools`` literal in README/CLAUDE must match the registry.

    The concrete count is single-sourced to the generated
    ``docs/mcp-tools-reference.md`` (Issue #745), so README/CLAUDE no longer
    need to carry a number. This guard stays as a safety net: if a literal is
    (re)introduced, it must agree with ``len(ALL_DEFS) + len(_SERVER_TOOLS)``.
    """
    expected = _expected_tool_count()
    for doc in _DOC_PATHS:
        text = doc.read_text(encoding="utf-8")
        for count in _numbers_before(r"(?:MCP )?tools", text):
            assert (
                count == expected
            ), f"{doc.name}: doc says {count} tools but registry has {expected}"


@pytest.mark.integration
def test_doc_table_count_matches_schema(tmp_path: Path) -> None:
    expected = _expected_table_count(str(tmp_path / "fresh.duckdb"))
    found_any = False
    for doc in _DOC_PATHS:
        text = doc.read_text(encoding="utf-8")
        counts = _numbers_before(r"(?:domain )?tables", text)
        for count in counts:
            assert (
                count == expected
            ), f"{doc.name}: doc says {count} tables but schema has {expected}"
        found_any = found_any or bool(counts)
    assert found_any, "no 'N tables' string found in README.md or CLAUDE.md"
