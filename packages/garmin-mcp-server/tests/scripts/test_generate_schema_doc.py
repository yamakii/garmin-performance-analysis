"""Tests for the half-generated DuckDB schema doc (Issue #435)."""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts.generate_schema_doc import (
    DOC_PATH,
    apply_generated_blocks,
    main,
    render_doc,
    render_table_block,
)


@pytest.mark.unit
def test_apply_replaces_only_marked_region() -> None:
    """Prose outside markers is preserved; only the marked block is swapped."""
    doc = (
        "# Title\n\n"
        "Intro prose.\n\n"
        "<!-- BEGIN GENERATED: schema:foo -->\n"
        "OLD CONTENT\n"
        "<!-- END GENERATED: schema:foo -->\n\n"
        "Trailing prose.\n"
    )
    new_block = (
        "<!-- BEGIN GENERATED: schema:foo -->\n"
        "| Column | Type |\n"
        "|--------|------|\n"
        "| id (PK) | INTEGER |\n"
        "<!-- END GENERATED: schema:foo -->"
    )
    result = apply_generated_blocks(doc, {"foo": new_block})

    assert "Intro prose." in result
    assert "Trailing prose." in result
    assert "OLD CONTENT" not in result
    assert "| id (PK) | INTEGER |" in result


@pytest.mark.unit
def test_apply_raises_on_missing_marker() -> None:
    """A block key with no matching markers in the doc raises ValueError."""
    doc = "# Title\n\nNo markers here.\n"
    with pytest.raises(ValueError, match="missing BEGIN marker"):
        apply_generated_blocks(doc, {"foo": "anything"})


@pytest.mark.unit
def test_render_table_block_marks_pk() -> None:
    """PK columns show '(PK)'; output is wrapped in start/end markers."""
    block = render_table_block(
        "splits",
        [
            ("activity_id", "BIGINT", True),
            ("split_index", "INTEGER", True),
            ("distance", "DOUBLE", False),
        ],
    )

    assert block.startswith("<!-- BEGIN GENERATED: schema:splits -->")
    assert block.endswith("<!-- END GENERATED: schema:splits -->")
    assert "| activity_id (PK) | BIGINT |" in block
    assert "| split_index (PK) | INTEGER |" in block
    assert "| distance | DOUBLE |" in block
    # Non-PK column must not be marked.
    assert "distance (PK)" not in block


@pytest.mark.integration
def test_schema_doc_in_sync(tmp_path: Path) -> None:
    """Committed doc equals render_doc(fresh_db, committed_doc)."""
    db_path = str(tmp_path / "schema_probe.duckdb")
    GarminDBWriter(db_path=db_path)

    committed = DOC_PATH.read_text(encoding="utf-8")
    rendered = render_doc(db_path, committed)

    assert committed == rendered, (
        "docs/spec/duckdb_schema_mapping.md is out of sync with the live schema. "
        "Regenerate: python -m garmin_mcp.scripts.generate_schema_doc"
    )


@pytest.mark.integration
def test_check_mode_passes_when_in_sync() -> None:
    """`main(['--check'])` returns 0 when the committed doc matches the schema."""
    assert main(["--check"]) == 0
