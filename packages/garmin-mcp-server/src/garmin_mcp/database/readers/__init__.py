"""
Database readers package.

This package provides specialized reader classes for accessing DuckDB data:
- BaseDBReader: Base class with DuckDB connection management
- MetadataReader: Activity metadata queries
- SplitsReader: Splits data queries
- FormReader: Form efficiency and evaluation metrics
- PhysiologyReader: HR efficiency, VO2 max, lactate threshold
- PerformanceReader: Performance trends, weather, section analyses
- UtilityReader: Profiling and histogram operations
- AggregateReader: Backward-compatible wrapper (delegates to above)
- TimeSeriesReader: Time series data and anomaly detection
- ExportReader: Query result export functionality
"""

from garmin_mcp.database.readers.aggregate import AggregateReader
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.readers.export import ExportReader
from garmin_mcp.database.readers.form import FormReader
from garmin_mcp.database.readers.metadata import MetadataReader
from garmin_mcp.database.readers.performance import PerformanceReader
from garmin_mcp.database.readers.physiology import PhysiologyReader
from garmin_mcp.database.readers.splits import SplitsReader
from garmin_mcp.database.readers.time_series import TimeSeriesReader
from garmin_mcp.database.readers.utility import UtilityReader

__all__ = [
    "BaseDBReader",
    "MetadataReader",
    "SplitsReader",
    "FormReader",
    "PhysiologyReader",
    "PerformanceReader",
    "UtilityReader",
    "AggregateReader",
    "TimeSeriesReader",
    "ExportReader",
]
