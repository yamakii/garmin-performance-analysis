"""Unit tests for GarminIngestWorker path configuration.

Tests the configurable data paths feature in GarminIngestWorker.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.mark.unit
class TestGarminWorkerDefaultPaths:
    """Tests for GarminIngestWorker with default paths."""

    def test_garmin_worker_uses_default_paths(self) -> None:
        """Test that GarminIngestWorker uses default paths when env vars not set."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove env vars if they exist
            if "GARMIN_DATA_DIR" in os.environ:
                del os.environ["GARMIN_DATA_DIR"]

            worker = GarminIngestWorker()

            # Should use project_root/data
            assert worker.raw_dir.parent.name == "data"
            assert worker.weight_raw_dir.parent.parent.name == "data"

            # Check subdirectory names
            assert worker.raw_dir.name == "raw"
            assert worker.weight_raw_dir.name == "weight"

            # All paths should be absolute
            assert worker.raw_dir.is_absolute()
            assert worker.weight_raw_dir.is_absolute()


@pytest.mark.unit
class TestGarminWorkerCustomPaths:
    """Tests for GarminIngestWorker with custom paths."""

    def test_garmin_worker_uses_custom_data_dir(self) -> None:
        """Test that GarminIngestWorker uses custom data dir from env var."""
        custom_data_dir = "/tmp/test_garmin_data"
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": custom_data_dir}):
            worker = GarminIngestWorker()

            # Should use custom data dir
            expected_raw = Path(custom_data_dir) / "raw"
            expected_weight = Path(custom_data_dir) / "raw" / "weight"

            assert worker.raw_dir == expected_raw
            assert worker.weight_raw_dir == expected_weight

    def test_garmin_worker_paths_are_absolute(self) -> None:
        """Test that custom paths are resolved to absolute paths."""
        custom_data_dir = "./test_data"
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": custom_data_dir}):
            worker = GarminIngestWorker()

            # All paths should be absolute even if env var is relative
            assert worker.raw_dir.is_absolute()
            assert worker.weight_raw_dir.is_absolute()


@pytest.mark.unit
class TestGarminWorkerBackwardCompatibility:
    """Tests for backward compatibility of path configuration."""

    def test_existing_behavior_preserved(self) -> None:
        """Test that existing behavior is preserved when env vars not set."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove env vars if they exist
            if "GARMIN_DATA_DIR" in os.environ:
                del os.environ["GARMIN_DATA_DIR"]

            worker = GarminIngestWorker()

            from garmin_mcp.utils.paths import get_project_root

            project_root = get_project_root()

            # Should match the default paths based on project root
            assert worker.raw_dir == project_root / "data" / "raw"
            assert worker.weight_raw_dir == project_root / "data" / "raw" / "weight"

    def test_directory_creation_still_works(self) -> None:
        """Test that directories are still created on initialization."""
        custom_data_dir = "/tmp/test_garmin_worker_dirs"
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": custom_data_dir}):
            # Clean up if exists
            import shutil

            if Path(custom_data_dir).exists():
                shutil.rmtree(custom_data_dir)

            worker = GarminIngestWorker()

            # Directories should be created
            assert worker.raw_dir.exists()
            assert worker.weight_raw_dir.exists()

            # Clean up
            shutil.rmtree(custom_data_dir)
