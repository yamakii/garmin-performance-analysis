"""Tests for TerrainClassifier.classify_terrain().

Pure function tests — no DB required. Validates terrain classification
thresholds: <5=平坦, <15=起伏, <30=丘陵, >=30=山岳.
"""

import pytest

from garmin_mcp.database.inserters.splits_helpers.terrain import TerrainClassifier


@pytest.mark.unit
class TestClassifyTerrain:
    """Tests for TerrainClassifier.classify_terrain()."""

    # --- 平坦 (flat): total < 5 ---

    def test_flat_zero_elevation(self):
        assert TerrainClassifier.classify_terrain(0.0, 0.0) == "平坦"

    def test_flat_small_elevation(self):
        assert TerrainClassifier.classify_terrain(2.0, 2.0) == "平坦"

    def test_flat_boundary_just_below(self):
        """total=4.9 → 平坦."""
        assert TerrainClassifier.classify_terrain(2.5, 2.4) == "平坦"

    # --- 起伏 (undulating): 5 <= total < 15 ---

    def test_undulating_boundary_exact(self):
        """total=5.0 → 起伏."""
        assert TerrainClassifier.classify_terrain(3.0, 2.0) == "起伏"

    def test_undulating_mid_range(self):
        """total=10.0 → 起伏."""
        assert TerrainClassifier.classify_terrain(5.0, 5.0) == "起伏"

    def test_undulating_boundary_just_below_15(self):
        """total=14.9 → 起伏."""
        assert TerrainClassifier.classify_terrain(7.5, 7.4) == "起伏"

    # --- 丘陵 (hilly): 15 <= total < 30 ---

    def test_hilly_boundary_exact(self):
        """total=15.0 → 丘陵."""
        assert TerrainClassifier.classify_terrain(8.0, 7.0) == "丘陵"

    def test_hilly_mid_range(self):
        """total=22.0 → 丘陵."""
        assert TerrainClassifier.classify_terrain(12.0, 10.0) == "丘陵"

    def test_hilly_boundary_just_below_30(self):
        """total=29.9 → 丘陵."""
        assert TerrainClassifier.classify_terrain(15.0, 14.9) == "丘陵"

    # --- 山岳 (mountainous): total >= 30 ---

    def test_mountainous_boundary_exact(self):
        """total=30.0 → 山岳."""
        assert TerrainClassifier.classify_terrain(15.0, 15.0) == "山岳"

    def test_mountainous_high(self):
        """total=100.0 → 山岳."""
        assert TerrainClassifier.classify_terrain(60.0, 40.0) == "山岳"

    # --- Edge cases: abs() behavior ---

    def test_negative_values_use_abs(self):
        """Negative elevation values should be treated via abs()."""
        assert TerrainClassifier.classify_terrain(-15.0, -15.0) == "山岳"
