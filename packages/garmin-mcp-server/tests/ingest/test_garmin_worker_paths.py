"""Unit tests for GarminIngestWorker path configuration.

Tests the configurable data paths feature in GarminIngestWorker.
"""

from pathlib import Path

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.mark.unit
class TestGarminWorkerDefaultPaths:
    """Tests for GarminIngestWorker with default paths."""

    def test_garmin_worker_uses_default_paths(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that GarminIngestWorker uses default paths when env vars not set."""
        monkeypatch.delenv("GARMIN_DATA_DIR", raising=False)
        fake_root = tmp_path / "project"
        (fake_root / ".git").mkdir(parents=True)
        monkeypatch.setattr(
            "garmin_mcp.utils.paths.get_project_root", lambda: fake_root
        )

        worker = GarminIngestWorker()

        assert worker.raw_dir == fake_root / "data" / "raw"
        assert worker.weight_raw_dir == fake_root / "data" / "raw" / "weight"
        assert worker.raw_dir.is_absolute()
        assert worker.weight_raw_dir.is_absolute()


@pytest.mark.unit
class TestGarminWorkerCustomPaths:
    """Tests for GarminIngestWorker with custom paths."""

    def test_garmin_worker_uses_custom_data_dir(self, tmp_path: Path) -> None:
        """Test that GarminIngestWorker uses custom data dir from env var."""
        # autouse fixture already sets GARMIN_DATA_DIR to tmp_path/data
        worker = GarminIngestWorker()

        expected_base = tmp_path / "data"
        expected_raw = expected_base / "raw"
        expected_weight = expected_base / "raw" / "weight"

        assert worker.raw_dir == expected_raw
        assert worker.weight_raw_dir == expected_weight

    def test_garmin_worker_paths_are_absolute(self, tmp_path: Path) -> None:
        """Test that custom paths are resolved to absolute paths."""
        # autouse fixture already sets an absolute tmp_path
        worker = GarminIngestWorker()

        # All paths should be absolute
        assert worker.raw_dir.is_absolute()
        assert worker.weight_raw_dir.is_absolute()


@pytest.mark.unit
class TestGarminWorkerBackwardCompatibility:
    """Tests for backward compatibility of path configuration."""

    def test_existing_behavior_preserved(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that existing behavior is preserved when env vars not set."""
        monkeypatch.delenv("GARMIN_DATA_DIR", raising=False)
        fake_root = tmp_path / "project"
        (fake_root / ".git").mkdir(parents=True)
        monkeypatch.setattr(
            "garmin_mcp.utils.paths.get_project_root", lambda: fake_root
        )

        worker = GarminIngestWorker()

        assert worker.raw_dir == fake_root / "data" / "raw"
        assert worker.weight_raw_dir == fake_root / "data" / "raw" / "weight"

    def test_directory_creation_is_lazy(self, tmp_path: Path) -> None:
        """Test that directories are created lazily, not on init."""
        # autouse fixture already sets GARMIN_DATA_DIR to tmp_path/data
        worker = GarminIngestWorker()

        # Directories should NOT be created on init
        assert not worker.raw_dir.exists()
        assert not worker.weight_raw_dir.exists()

        # After _ensure_dirs(), directories should exist
        worker._ensure_dirs()
        assert worker.raw_dir.exists()
        assert worker.weight_raw_dir.exists()
