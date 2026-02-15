"""Handler modules for MCP tool dispatch."""

from garmin_mcp.handlers.analysis_handler import AnalysisHandler
from garmin_mcp.handlers.base import ToolHandler
from garmin_mcp.handlers.export_handler import ExportHandler
from garmin_mcp.handlers.metadata_handler import MetadataHandler
from garmin_mcp.handlers.performance_handler import PerformanceHandler
from garmin_mcp.handlers.physiology_handler import PhysiologyHandler
from garmin_mcp.handlers.splits_handler import SplitsHandler
from garmin_mcp.handlers.time_series_handler import TimeSeriesHandler

__all__ = [
    "ToolHandler",
    "AnalysisHandler",
    "ExportHandler",
    "MetadataHandler",
    "PerformanceHandler",
    "PhysiologyHandler",
    "SplitsHandler",
    "TimeSeriesHandler",
]
