"""Tests for backup_if_pending (auto-backup before pending migrations)."""

import shutil
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.backup import backup_if_pending
from garmin_mcp.database.migrations.registry import MIGRATIONS

_MAX_VERSION = max(v for v, _, _ in MIGRATIONS)


def _seed_db(db_path: Path, version: int) -> None:
    """Create a DuckDB file with schema_version seeded up to ``version``.

    If ``version`` is 0, the schema_version table is left absent so the DB
    looks like a fresh, pre-migration database.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "CREATE TABLE activities "
        "(activity_id BIGINT PRIMARY KEY, activity_date DATE)"
    )
    if version > 0:
        conn.execute(
            "CREATE TABLE schema_version ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "applied_at TIMESTAMP DEFAULT current_timestamp)"
        )
        for v in range(1, version + 1):
            conn.execute(
                "INSERT INTO schema_version (version, name) VALUES (?, ?)",
                [v, f"migration_{v}"],
            )
    conn.close()


def _production_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point GARMIN_DATA_DIR at tmp_path and return the production DB path."""
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    return tmp_path / "database" / "garmin_performance.duckdb"


@pytest.mark.unit
def test_backup_skips_memory() -> None:
    """`:memory:` returns None and creates no file."""
    assert backup_if_pending(":memory:") is None


@pytest.mark.unit
def test_backup_skips_temp_path(tmp_path: Path) -> None:
    """A DB outside the data dir (plain tmp path) is skipped."""
    db_path = tmp_path / "scratch.duckdb"
    _seed_db(db_path, version=1)

    assert backup_if_pending(db_path) is None
    assert list(tmp_path.glob("*_backup_*.duckdb")) == []


@pytest.mark.unit
def test_backup_skips_fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh DB (no schema_version / version 0) is skipped."""
    db_path = _production_db(tmp_path, monkeypatch)
    _seed_db(db_path, version=0)

    assert backup_if_pending(db_path) is None
    assert list(db_path.parent.glob("*_backup_*.duckdb")) == []


@pytest.mark.unit
def test_backup_skips_when_up_to_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB already at max registry version is skipped (no pending)."""
    db_path = _production_db(tmp_path, monkeypatch)
    _seed_db(db_path, version=_MAX_VERSION)

    assert backup_if_pending(db_path) is None
    assert list(db_path.parent.glob("*_backup_*.duckdb")) == []


@pytest.mark.integration
def test_backup_creates_when_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A production DB with pending migrations gets a backup copy."""
    db_path = _production_db(tmp_path, monkeypatch)
    _seed_db(db_path, version=1)
    assert _MAX_VERSION > 1  # sanity: pending migrations exist

    result = backup_if_pending(db_path)

    assert result is not None
    assert isinstance(result, Path)
    assert result.exists()
    backups = list(db_path.parent.glob("*_backup_*.duckdb"))
    assert len(backups) == 1
    assert backups[0] == result


@pytest.mark.integration
def test_backup_prunes_to_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With 3 existing backups, firing keeps only the newest two."""
    db_path = _production_db(tmp_path, monkeypatch)
    _seed_db(db_path, version=1)

    db_dir = db_path.parent
    stem = db_path.stem
    old_backups = [
        db_dir / f"{stem}_backup_20200101_00000{i}.duckdb" for i in range(1, 4)
    ]
    for b in old_backups:
        b.write_bytes(b"old")

    result = backup_if_pending(db_path)
    assert result is not None

    remaining = sorted(db_dir.glob(f"{stem}_backup_*.duckdb"))
    assert len(remaining) == 2
    # The newest backup (just created) must survive.
    assert result in remaining
    # The two oldest of the original three must be pruned.
    assert old_backups[0] not in remaining
    assert old_backups[1] not in remaining


@pytest.mark.unit
def test_backup_raises_on_copy_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shutil.copy2 failure propagates as RuntimeError."""
    db_path = _production_db(tmp_path, monkeypatch)
    _seed_db(db_path, version=1)

    def _raiser(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copy2", _raiser)

    with pytest.raises(RuntimeError, match="Migration backup failed"):
        backup_if_pending(db_path)
