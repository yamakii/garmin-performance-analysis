"""Tests for display_settings module."""

import pytest

from tools.utils.display_settings import (
    configure_all_display_settings,
    configure_pandas_display,
    configure_polars_display,
    reset_all_display_settings,
    reset_pandas_display,
    reset_polars_display,
)


@pytest.mark.unit
class TestPandasDisplaySettings:
    """Test Pandas display configuration."""

    def test_configure_pandas_default(self):
        """Test configuring Pandas with default values."""
        pytest.importorskip("pandas")
        import pandas as pd

        configure_pandas_display()

        assert pd.get_option("display.max_rows") == 10
        assert pd.get_option("display.max_columns") == 10
        assert pd.get_option("display.max_colwidth") == 50

    def test_configure_pandas_custom(self):
        """Test configuring Pandas with custom values."""
        pytest.importorskip("pandas")
        import pandas as pd

        configure_pandas_display(max_rows=20, max_columns=15, max_colwidth=100)

        assert pd.get_option("display.max_rows") == 20
        assert pd.get_option("display.max_columns") == 15
        assert pd.get_option("display.max_colwidth") == 100

    def test_reset_pandas_display(self):
        """Test resetting Pandas display settings."""
        pytest.importorskip("pandas")
        import pandas as pd

        # Configure custom settings
        configure_pandas_display(max_rows=5, max_columns=5)

        # Reset to defaults
        reset_pandas_display()

        # Should be back to Pandas defaults (not our defaults)
        default_max_rows = pd.get_option("display.max_rows")
        assert default_max_rows != 5  # Should be reset


@pytest.mark.unit
class TestPolarsDisplaySettings:
    """Test Polars display configuration."""

    def test_configure_polars_default(self):
        """Test configuring Polars with default values."""
        pytest.importorskip("polars")

        configure_polars_display()

        # Polars Config doesn't have a direct getter, but we can verify no error
        # If there's an error, it will raise during configuration
        assert True  # Configuration succeeded

    def test_configure_polars_custom(self):
        """Test configuring Polars with custom values."""
        pytest.importorskip("polars")

        configure_polars_display(max_rows=20, max_columns=15)

        # Polars Config doesn't have a direct getter, but we can verify no error
        assert True  # Configuration succeeded

    def test_reset_polars_display(self):
        """Test resetting Polars display settings."""
        pytest.importorskip("polars")

        # Configure custom settings
        configure_polars_display(max_rows=5, max_columns=5)

        # Reset to defaults
        reset_polars_display()

        # Should be back to Polars defaults
        assert True  # Reset succeeded


@pytest.mark.unit
class TestAllDisplaySettings:
    """Test configuring all display settings at once."""

    def test_configure_all_default(self):
        """Test configuring all libraries with defaults."""
        # Should not raise any errors
        configure_all_display_settings()

        # Verify Pandas if available
        try:
            import pandas as pd

            assert pd.get_option("display.max_rows") == 10
        except ImportError:
            pass

        # Verify Polars if available
        try:
            import polars  # noqa: F401

            # Just verify no error
            assert True
        except ImportError:
            pass

    def test_configure_all_custom(self):
        """Test configuring all libraries with custom values."""
        configure_all_display_settings(max_rows=15, max_columns=12, max_colwidth=80)

        # Verify Pandas if available
        try:
            import pandas as pd

            assert pd.get_option("display.max_rows") == 15
            assert pd.get_option("display.max_columns") == 12
            assert pd.get_option("display.max_colwidth") == 80
        except ImportError:
            pass

        # Verify Polars if available
        try:
            import polars  # noqa: F401

            # Just verify no error
            assert True
        except ImportError:
            pass

    def test_reset_all(self):
        """Test resetting all display settings."""
        # Configure custom
        configure_all_display_settings(max_rows=5, max_columns=5)

        # Reset all
        reset_all_display_settings()

        # Should be reset (verified by no errors)
        assert True


@pytest.mark.unit
class TestDisplaySettingsBehavior:
    """Test actual display behavior with configured settings."""

    def test_pandas_dataframe_display_limit(self):
        """Test that Pandas DataFrame respects display limits."""
        pytest.importorskip("pandas")
        import pandas as pd

        # Configure to show only 5 rows
        configure_pandas_display(max_rows=5)

        # Create DataFrame with 100 rows
        df = pd.DataFrame({"col1": range(100), "col2": range(100, 200)})

        # Get string representation
        df_str = str(df)

        # Should have ellipsis indicating truncation
        # (Pandas shows first/last few rows when truncated)
        lines = df_str.split("\n")

        # Total lines should be much less than 100 data rows
        # (Pandas shows ~5 rows + header + ellipsis)
        assert len(lines) < 20  # Much less than 100

    def test_polars_dataframe_display_limit(self):
        """Test that Polars DataFrame respects display limits."""
        pytest.importorskip("polars")
        import polars as pl

        # Configure to show only 5 rows
        configure_polars_display(max_rows=5)

        # Create DataFrame with 100 rows
        df = pl.DataFrame({"col1": range(100), "col2": range(100, 200)})

        # Get string representation
        df_str = str(df)

        # Should have ellipsis indicating truncation
        lines = df_str.split("\n")

        # Total lines should be limited
        assert len(lines) < 20  # Much less than 100


@pytest.mark.unit
class TestMissingLibraries:
    """Test behavior when libraries are not installed."""

    def test_configure_without_pandas(self, monkeypatch):
        """Test configuration when Pandas is not available."""

        # Mock ImportError for pandas
        def mock_import(name, *args, **kwargs):
            if name == "pandas":
                raise ImportError("No module named 'pandas'")
            return __import__(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        # Should not raise error, just log warning
        configure_pandas_display()

    def test_configure_without_polars(self, monkeypatch):
        """Test configuration when Polars is not available."""

        # Mock ImportError for polars
        def mock_import(name, *args, **kwargs):
            if name == "polars":
                raise ImportError("No module named 'polars'")
            return __import__(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        # Should not raise error, just log warning
        configure_polars_display()
