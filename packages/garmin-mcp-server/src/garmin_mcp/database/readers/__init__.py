"""
Database readers package.

This package provides specialized reader classes for accessing DuckDB data:
- BaseDBReader: Base class with DuckDB connection management
- MetadataReader: Activity metadata queries
- SplitsReader: Splits data queries
- AggregateReader: Aggregated performance metrics
- TimeSeriesReader: Time series data and anomaly detection
- ExportReader: Query result export functionality
"""

from garmin_mcp.database.readers.aggregate import AggregateReader
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.readers.export import ExportReader
from garmin_mcp.database.readers.metadata import MetadataReader
from garmin_mcp.database.readers.splits import SplitsReader
from garmin_mcp.database.readers.time_series import TimeSeriesReader

__all__ = [
    "BaseDBReader",
    "MetadataReader",
    "SplitsReader",
    "AggregateReader",
    "TimeSeriesReader",
    "ExportReader",
]
