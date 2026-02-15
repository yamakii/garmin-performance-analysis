"""
Display Settings enforcement for Pandas and Polars DataFrames.

This module configures display settings to prevent large DataFrame outputs
from bloating LLM context.
"""

import logging

logger = logging.getLogger(__name__)


# Display configuration constants
DEFAULT_MAX_ROWS = 10
DEFAULT_MAX_COLUMNS = 10
DEFAULT_MAX_COL_WIDTH = 50


def configure_pandas_display(
    max_rows: int | None = None,
    max_columns: int | None = None,
    max_colwidth: int | None = None,
) -> None:
    """
    Configure Pandas display settings for LLM-safe output.

    Args:
        max_rows: Maximum rows to display (default: 10)
        max_columns: Maximum columns to display (default: 10)
        max_colwidth: Maximum column width (default: 50)
    """
    try:
        import pandas as pd

        max_rows = max_rows or DEFAULT_MAX_ROWS
        max_columns = max_columns or DEFAULT_MAX_COLUMNS
        max_colwidth = max_colwidth or DEFAULT_MAX_COL_WIDTH

        pd.set_option("display.max_rows", max_rows)
        pd.set_option("display.max_columns", max_columns)
        pd.set_option("display.max_colwidth", max_colwidth)

        # Prevent scientific notation for better readability
        pd.set_option("display.float_format", lambda x: f"{x:.2f}")

        logger.info(
            f"Pandas display configured: max_rows={max_rows}, "
            f"max_columns={max_columns}, max_colwidth={max_colwidth}"
        )

    except ImportError:
        logger.warning("Pandas not available - skipping display configuration")


def configure_polars_display(
    max_rows: int | None = None,
    max_columns: int | None = None,
) -> None:
    """
    Configure Polars display settings for LLM-safe output.

    Args:
        max_rows: Maximum rows to display (default: 10)
        max_columns: Maximum columns to display (default: 10)
    """
    try:
        import polars as pl

        max_rows = max_rows or DEFAULT_MAX_ROWS
        max_columns = max_columns or DEFAULT_MAX_COLUMNS

        # Polars Config API
        pl.Config.set_tbl_rows(max_rows)
        pl.Config.set_tbl_cols(max_columns)

        # Set formatting options
        pl.Config.set_fmt_str_lengths(50)  # Max string length in display
        pl.Config.set_tbl_hide_column_data_types(False)  # Show dtypes for clarity

        logger.info(
            f"Polars display configured: tbl_rows={max_rows}, "
            f"tbl_cols={max_columns}"
        )

    except ImportError:
        logger.warning("Polars not available - skipping display configuration")


def configure_all_display_settings(
    max_rows: int | None = None,
    max_columns: int | None = None,
    max_colwidth: int | None = None,
) -> None:
    """
    Configure display settings for all available DataFrame libraries.

    This is the recommended function to call at startup to ensure
    LLM-safe DataFrame display across all libraries.

    Args:
        max_rows: Maximum rows to display (default: 10)
        max_columns: Maximum columns to display (default: 10)
        max_colwidth: Maximum column width for Pandas (default: 50)
    """
    logger.info("Configuring LLM-safe display settings for all DataFrame libraries")

    configure_pandas_display(max_rows, max_columns, max_colwidth)
    configure_polars_display(max_rows, max_columns)

    logger.info("Display settings configuration complete")


def reset_pandas_display() -> None:
    """Reset Pandas display settings to defaults."""
    try:
        import pandas as pd

        pd.reset_option("display.max_rows")
        pd.reset_option("display.max_columns")
        pd.reset_option("display.max_colwidth")
        pd.reset_option("display.float_format")
        logger.info("Pandas display settings reset to defaults")
    except ImportError:
        pass


def reset_polars_display() -> None:
    """Reset Polars display settings to defaults."""
    try:
        import polars as pl

        # Polars defaults
        pl.Config.set_tbl_rows(8)  # Polars default
        pl.Config.set_tbl_cols(8)  # Polars default
        pl.Config.set_fmt_str_lengths(32)  # Polars default
        logger.info("Polars display settings reset to defaults")
    except ImportError:
        pass


def reset_all_display_settings() -> None:
    """Reset all display settings to library defaults."""
    logger.info("Resetting all display settings to defaults")
    reset_pandas_display()
    reset_polars_display()
    logger.info("Display settings reset complete")


# Auto-configure on import
configure_all_display_settings()
