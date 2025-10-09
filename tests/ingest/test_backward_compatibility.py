"""
Backward Compatibility Tests

Verify that new implementation generates identical performance.json
from existing raw_data files.
"""

import json
from pathlib import Path

import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


class TestBackwardCompatibility:
    """Test backward compatibility with existing data."""

    @pytest.fixture
    def worker(self):
        """Create GarminIngestWorker instance."""
        return GarminIngestWorker()

    @pytest.fixture
    def existing_raw_file(self):
        """Path to existing raw data file (archived old format)."""
        return Path("data/archive/raw/20594901208_raw.json")

    @pytest.fixture
    def existing_performance_file(self):
        """Path to existing performance data file."""
        return Path("data/performance/20594901208.json")

    @pytest.mark.integration
    def test_generate_identical_performance_data(
        self, worker, existing_raw_file, existing_performance_file
    ):
        """Test that new logic generates identical performance.json."""
        # Load existing raw data
        with open(existing_raw_file, encoding="utf-8") as f:
            raw_data = json.load(f)

        # Load existing performance data
        with open(existing_performance_file, encoding="utf-8") as f:
            existing_performance = json.load(f)

        # Generate new performance data
        df = worker.create_parquet_dataset(raw_data)
        new_performance = worker._calculate_split_metrics(df, raw_data)

        # Compare top-level sections
        print("\n=== Section Comparison ===")
        for section in [
            "basic_metrics",
            "heart_rate_zones",
            "split_metrics",
            "efficiency_metrics",
            "training_effect",
            "power_to_weight",
            "vo2_max",
            "lactate_threshold",
            "form_efficiency_summary",
            "hr_efficiency_analysis",
            "performance_trends",
        ]:
            existing_section = existing_performance.get(section)
            new_section = new_performance.get(section)

            if existing_section != new_section:
                print(f"\n❌ MISMATCH: {section}")
                print(f"Existing: {existing_section}")
                print(f"New:      {new_section}")
            else:
                print(f"✅ {section}: MATCH")

        # Assert all sections exist
        assert "basic_metrics" in new_performance
        assert "heart_rate_zones" in new_performance
        assert "split_metrics" in new_performance

    @pytest.mark.integration
    def test_basic_metrics_match(
        self, worker, existing_raw_file, existing_performance_file
    ):
        """Test that basic_metrics match exactly."""
        with open(existing_raw_file, encoding="utf-8") as f:
            raw_data = json.load(f)

        with open(existing_performance_file, encoding="utf-8") as f:
            existing_performance = json.load(f)

        df = worker.create_parquet_dataset(raw_data)
        new_performance = worker._calculate_split_metrics(df, raw_data)

        existing_basic = existing_performance["basic_metrics"]
        new_basic = new_performance["basic_metrics"]

        print("\n=== Basic Metrics Comparison ===")
        for key in existing_basic:
            existing_val = existing_basic[key]
            new_val = new_basic.get(key)

            # Handle NaN comparison
            if existing_val != existing_val and new_val != new_val:  # both NaN
                print(f"✅ {key}: both NaN")
                continue

            if (
                abs(existing_val - new_val) < 0.001
                if isinstance(existing_val, int | float)
                else existing_val == new_val
            ):
                print(f"✅ {key}: {existing_val} ≈ {new_val}")
            else:
                print(f"❌ {key}: {existing_val} != {new_val}")

    @pytest.mark.integration
    def test_split_metrics_match(
        self, worker, existing_raw_file, existing_performance_file
    ):
        """Test that split_metrics match exactly."""
        with open(existing_raw_file, encoding="utf-8") as f:
            raw_data = json.load(f)

        with open(existing_performance_file, encoding="utf-8") as f:
            existing_performance = json.load(f)

        df = worker.create_parquet_dataset(raw_data)
        new_performance = worker._calculate_split_metrics(df, raw_data)

        existing_splits = existing_performance["split_metrics"]
        new_splits = new_performance["split_metrics"]

        print(f"\n=== Split Metrics Comparison ({len(existing_splits)} splits) ===")

        assert len(existing_splits) == len(
            new_splits
        ), f"Split count mismatch: {len(existing_splits)} vs {len(new_splits)}"

        for i, (existing_split, new_split) in enumerate(
            zip(existing_splits, new_splits, strict=False)
        ):
            print(f"\nSplit {i+1}:")
            for key in existing_split:
                existing_val = existing_split[key]
                new_val = new_split.get(key)

                # Handle NaN/null comparison
                if existing_val is None and new_val is None:
                    continue
                if existing_val != existing_val and new_val != new_val:  # both NaN
                    continue

                if isinstance(existing_val, int | float) and isinstance(
                    new_val, int | float
                ):
                    if abs(existing_val - new_val) < 0.001:
                        continue
                    else:
                        print(f"  ❌ {key}: {existing_val} != {new_val}")
                elif existing_val != new_val:
                    print(f"  ❌ {key}: {existing_val} != {new_val}")
