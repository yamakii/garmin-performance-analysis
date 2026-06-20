"""Half-generate ``docs/spec/duckdb_schema_mapping.md`` from the live schema.

The per-table column tables (``| Column | Type |``) are rendered from the live
DuckDB schema (``PRAGMA table_info``) and inserted between sentinel markers:

    <!-- BEGIN GENERATED: schema:activities -->
    | Column | Type |
    | ... |
    <!-- END GENERATED: schema:activities -->

Everything outside the markers — purpose, source, calculation logic, change
history — is hand-written prose that the generator preserves verbatim. Building
the schema from a *fresh* ``GarminDBWriter`` (``_ensure_tables()`` + migrations)
means the column lists never depend on production data, yet always reflect the
code that defines the schema.

Usage::

    # Refresh the generated blocks in place
    uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.generate_schema_doc

    # Verify the committed doc is in sync (used by the drift test / CI)
    uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.generate_schema_doc --check

An integration test (``tests/scripts/test_generate_schema_doc.py``) asserts the
committed doc equals ``render_doc(fresh_db, committed_doc)``, so a schema change
without regenerating fails CI.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_writer import GarminDBWriter

# scripts -> garmin_mcp -> src -> garmin-mcp-server -> packages -> repo root
REPO_ROOT = Path(__file__).resolve().parents[5]
DOC_PATH = REPO_ROOT / "docs" / "spec" / "duckdb_schema_mapping.md"

# Migration bookkeeping table — documented as prose, not a domain table.
EXCLUDED_TABLES = frozenset({"schema_version"})

MARKER_BEGIN = "<!-- BEGIN GENERATED: schema:{table} -->"
MARKER_END = "<!-- END GENERATED: schema:{table} -->"


def list_domain_tables(db_path: str) -> list[str]:
    """Return the domain table names (excluding ``schema_version``), sorted."""
    with get_connection(db_path) as con:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
    return [name for (name,) in rows if name not in EXCLUDED_TABLES]


def read_columns(db_path: str, table: str) -> list[tuple[str, str, bool]]:
    """Return ``(name, type, is_pk)`` tuples for ``table`` in storage order."""
    with get_connection(db_path) as con:
        rows = con.execute(f"PRAGMA table_info('{table}')").fetchall()
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    return [(name, col_type, bool(pk)) for (_, name, col_type, _, _, pk) in rows]


def render_table_block(table: str, columns: list[tuple[str, str, bool]]) -> str:
    """Render the generated ``| Column | Type |`` block for one table.

    PK columns are marked ``name (PK)``. The output is wrapped in the
    BEGIN/END sentinel markers keyed by ``table``.
    """
    lines = [
        MARKER_BEGIN.format(table=table),
        "| Column | Type |",
        "|--------|------|",
    ]
    for name, col_type, is_pk in columns:
        col_label = f"{name} (PK)" if is_pk else name
        lines.append(f"| {col_label} | {col_type} |")
    lines.append(MARKER_END.format(table=table))
    return "\n".join(lines)


def apply_generated_blocks(doc_text: str, blocks: dict[str, str]) -> str:
    """Replace each marked region in ``doc_text`` with its rendered block.

    ``blocks`` maps table name -> rendered block (including markers). For each
    key, the text between ``BEGIN GENERATED: schema:<table>`` and the matching
    ``END`` marker (inclusive) is swapped for the rendered block. Prose outside
    the markers is preserved verbatim.

    Raises:
        ValueError: if a block's begin/end markers are not found in the doc.
    """
    result = doc_text
    for table, block in blocks.items():
        begin = MARKER_BEGIN.format(table=table)
        end = MARKER_END.format(table=table)
        start_idx = result.find(begin)
        if start_idx == -1:
            raise ValueError(f"missing BEGIN marker for table {table!r}: {begin}")
        end_idx = result.find(end, start_idx)
        if end_idx == -1:
            raise ValueError(f"missing END marker for table {table!r}: {end}")
        end_idx += len(end)
        result = result[:start_idx] + block + result[end_idx:]
    return result


def render_doc(db_path: str, current_doc: str) -> str:
    """Render the full doc: swap each table's marked block from the live schema.

    Reads the live schema from ``db_path`` and replaces the generated blocks in
    ``current_doc`` (prose preserved). The returned text is what the committed
    doc must equal.
    """
    blocks = {
        table: render_table_block(table, read_columns(db_path, table))
        for table in list_domain_tables(db_path)
    }
    return apply_generated_blocks(current_doc, blocks)


def _build_fresh_db(db_path: str) -> None:
    """Initialize a fresh DB so ``_ensure_tables()`` + migrations define schema."""
    GarminDBWriter(db_path=db_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed doc differs from the generated output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DOC_PATH,
        help=f"Doc path (default: {DOC_PATH})",
    )
    args = parser.parse_args(argv)

    if not args.output.exists():
        print(f"MISSING: {args.output} does not exist.")
        return 1
    current = args.output.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "schema_probe.duckdb")
        _build_fresh_db(db_path)
        content = render_doc(db_path, current)

    if args.check:
        if current != content:
            print(
                f"OUT OF SYNC: {args.output} differs from the live schema. "
                "Regenerate with: python -m garmin_mcp.scripts.generate_schema_doc"
            )
            return 1
        print(f"OK: {args.output} is in sync with the live schema.")
        return 0

    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {args.output}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
