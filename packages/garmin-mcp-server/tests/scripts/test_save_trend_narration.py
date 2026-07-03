"""Tests for save_trend_narration (issue #792): trend.json -> trend_analyses."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.readers.trends_narration import TrendNarrationReader
from garmin_mcp.scripts import save_trend_narration


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp_path = tmp_path_factory.mktemp("save_trend_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


def _write_trend(temp_dir: Path, payload: dict) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)
    (temp_dir / "trend.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.integration
def test_save_trend_narration_inserts_and_reads_back(
    initialized_db_path: Path, tmp_path: Path
) -> None:
    """A well-formed trend.json is appended and read back with prose intact."""
    td = tmp_path / "trend_week"
    _write_trend(
        td,
        {
            "granularity": "week",
            "period_start": "2026-06-15",
            "period_end": "2026-06-21",
            "analysis_data": {
                "narrative": "有酸素ベースが順調に積み上がっています。",
                "key_learnings": ["ロング走で脚が保った"],
                "recommendations": ["来週は距離を10%増やす"],
            },
        },
    )

    result = save_trend_narration.save_trend_narration(
        str(td), db_path=str(initialized_db_path)
    )
    assert result == {
        "saved": True,
        "granularity": "week",
        "period_start": "2026-06-15",
    }

    row = TrendNarrationReader(str(initialized_db_path)).get_trend_analysis(
        "week", "2026-06-15"
    )
    assert row is not None
    assert (
        row["analysis_data"]["narrative"] == "有酸素ベースが順調に積み上がっています。"
    )


@pytest.mark.unit
def test_save_trend_narration_missing_key_raises(tmp_path: Path) -> None:
    """A trend.json missing a required key fails closed (never persists)."""
    td = tmp_path / "bad"
    _write_trend(
        td,
        {"granularity": "week", "period_start": "2026-06-15"},  # no period_end/data
    )
    with pytest.raises(ValueError):
        save_trend_narration.save_trend_narration(str(td), db_path=None)


@pytest.mark.unit
def test_save_trend_narration_missing_file_raises(tmp_path: Path) -> None:
    """An absent trend.json raises FileNotFoundError."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        save_trend_narration.save_trend_narration(str(empty), db_path=None)
