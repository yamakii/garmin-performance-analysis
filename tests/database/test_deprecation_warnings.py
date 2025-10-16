"""
Test deprecation warnings and size limits for large data MCP functions.

Phase 0: Task 1-4 - get_splits_all() and get_section_analysis() deprecation.
"""

import json
import warnings
from unittest.mock import MagicMock, patch

import pytest

from tools.database.db_reader import GarminDBReader


class TestDeprecationWarnings:
    """Test deprecation warnings for large data functions."""

    @pytest.fixture
    def db_reader(self):
        """Create a GarminDBReader instance with mocked database."""
        with patch("tools.database.db_reader.duckdb") as mock_duckdb:
            reader = GarminDBReader()
            # Mock database connection
            mock_conn = MagicMock()
            mock_duckdb.connect.return_value = mock_conn
            yield reader, mock_conn

    def test_get_splits_all_shows_deprecation_warning(self, db_reader):
        """Test that get_splits_all() shows deprecation warning."""
        reader, mock_conn = db_reader

        # Mock database response - small result
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                1.0,
                "main",
                "5:00",
                300,
                150,
                "Zone 3",
                180,
                "Good",
                250,
                "High",
                1.2,
                240,
                8.5,
                7.0,
                10,
                5,
                "Flat",
                "Clear",
                "None",
                "Optimal",
                "Good",
            )
        ]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = reader.get_splits_all(
                activity_id=12345,
                max_output_size=10240,  # 10KB limit
            )

            # Should show deprecation warning
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "export()" in str(w[0].message)

    def test_get_section_analysis_shows_deprecation_warning(self, db_reader):
        """Test that get_section_analysis() shows deprecation warning."""
        reader, mock_conn = db_reader

        # Mock database response - small result
        mock_conn.execute.return_value.fetchone.return_value = (
            json.dumps({"section": "test", "data": "small"}),
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = reader.get_section_analysis(
                activity_id=12345,
                section_type="split",
                max_output_size=10240,  # 10KB limit
            )

            # Should show deprecation warning
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "extract_insights()" in str(w[0].message)

    def test_get_splits_all_size_limit_exceeded(self, db_reader):
        """Test that get_splits_all() raises error when size exceeds limit."""
        reader, mock_conn = db_reader

        # Mock database response - many splits to exceed limit
        large_result = [
            (
                i,
                float(i),
                "main",
                "5:00",
                300,
                150,
                "Zone 3",
                180,
                "Good",
                250,
                "High",
                1.2,
                240,
                8.5,
                7.0,
                10,
                5,
                "Flat",
                "Clear",
                "None",
                "Optimal",
                "Good",
            )
            for i in range(1, 100)  # 99 splits - should exceed 100 byte limit
        ]
        mock_conn.execute.return_value.fetchall.return_value = large_result

        with pytest.raises(ValueError) as exc_info:
            reader.get_splits_all(
                activity_id=12345,
                max_output_size=100,  # Very small limit to trigger error
            )

        assert "exceeds max_output_size" in str(exc_info.value)
        assert "export()" in str(exc_info.value)

    def test_get_section_analysis_size_limit_exceeded(self, db_reader):
        """Test that get_section_analysis() raises error when size exceeds limit."""
        reader, mock_conn = db_reader

        # Mock database response - large analysis data
        large_data = {"section": "test", "data": "x" * 10000}  # 10KB+ data
        mock_conn.execute.return_value.fetchone.return_value = (json.dumps(large_data),)

        with pytest.raises(ValueError) as exc_info:
            reader.get_section_analysis(
                activity_id=12345,
                section_type="split",
                max_output_size=100,  # Very small limit to trigger error
            )

        assert "exceeds max_output_size" in str(exc_info.value)
        assert "extract_insights()" in str(exc_info.value)

    def test_get_splits_all_backward_compatibility(self, db_reader):
        """Test that get_splits_all() still works without max_output_size (backward compatibility)."""
        reader, mock_conn = db_reader

        # Mock database response
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                1.0,
                "main",
                "5:00",
                300,
                150,
                "Zone 3",
                180,
                "Good",
                250,
                "High",
                1.2,
                240,
                8.5,
                7.0,
                10,
                5,
                "Flat",
                "Clear",
                "None",
                "Optimal",
                "Good",
            )
        ]

        # Should work without max_output_size parameter (default to 10KB)
        result = reader.get_splits_all(activity_id=12345)

        assert "splits" in result
        assert len(result["splits"]) > 0

    def test_get_section_analysis_backward_compatibility(self, db_reader):
        """Test that get_section_analysis() still works without max_output_size (backward compatibility)."""
        reader, mock_conn = db_reader

        # Mock database response
        mock_conn.execute.return_value.fetchone.return_value = (
            json.dumps({"section": "test", "data": "value"}),
        )

        # Should work without max_output_size parameter (default to 10KB)
        result = reader.get_section_analysis(activity_id=12345, section_type="split")

        assert result is not None
        assert isinstance(result, dict)

    def test_get_splits_all_no_limit(self, db_reader):
        """Test that get_splits_all() works without limit when max_output_size=None."""
        reader, mock_conn = db_reader

        # Mock database response - many splits
        large_result = [
            (
                i,
                float(i),
                "main",
                "5:00",
                300,
                150,
                "Zone 3",
                180,
                "Good",
                250,
                "High",
                1.2,
                240,
                8.5,
                7.0,
                10,
                5,
                "Flat",
                "Clear",
                "None",
                "Optimal",
                "Good",
            )
            for i in range(1, 100)
        ]
        mock_conn.execute.return_value.fetchall.return_value = large_result

        # Should work with max_output_size=None (no limit)
        result = reader.get_splits_all(activity_id=12345, max_output_size=None)

        assert "splits" in result
        assert len(result["splits"]) == 99

    def test_get_section_analysis_no_limit(self, db_reader):
        """Test that get_section_analysis() works without limit when max_output_size=None."""
        reader, mock_conn = db_reader

        # Mock database response - large data
        large_data = {"section": "test", "data": "x" * 10000}
        mock_conn.execute.return_value.fetchone.return_value = (json.dumps(large_data),)

        # Should work with max_output_size=None (no limit)
        result = reader.get_section_analysis(
            activity_id=12345, section_type="split", max_output_size=None
        )

        assert result is not None
        assert isinstance(result, dict)
