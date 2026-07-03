"""
Database readers package.

This package provides specialized reader classes for accessing DuckDB data:
- BaseDBReader: Base class with DuckDB connection management
- MetadataReader: Activity metadata queries
- SplitsReader: Splits data queries
- FormReader: Form efficiency and evaluation metrics
- PhysiologyReader: HR efficiency, VO2 max, lactate threshold
- PerformanceReader: Performance trends, weather, section analyses
- RaceReader: Race readiness (current VDOT + goal gap)
- TrainingLoadReader: Distance-based training load (ACWR)
- DurabilityReader: Long-run cardiac decoupling / pace fade trend
- FitnessCurveReader: Objective fitness curve + Garmin VO2max optimism gap
- StrengthSessionsReader: Strength-training (補強) summaries
- UtilityReader: Profiling and histogram operations
- TimeSeriesReader: Time series data and anomaly detection
- ExportReader: Query result export functionality
"""

from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.readers.durability import DurabilityReader
from garmin_mcp.database.readers.export import ExportReader
from garmin_mcp.database.readers.fitness_curve import FitnessCurveReader
from garmin_mcp.database.readers.form import FormReader
from garmin_mcp.database.readers.metadata import MetadataReader
from garmin_mcp.database.readers.performance import PerformanceReader
from garmin_mcp.database.readers.physiology import PhysiologyReader
from garmin_mcp.database.readers.race import RaceReader
from garmin_mcp.database.readers.splits import SplitsReader
from garmin_mcp.database.readers.strength_sessions import StrengthSessionsReader
from garmin_mcp.database.readers.time_series import TimeSeriesReader
from garmin_mcp.database.readers.training_load import TrainingLoadReader
from garmin_mcp.database.readers.trends_narration import TrendNarrationReader
from garmin_mcp.database.readers.utility import UtilityReader

__all__ = [
    "BaseDBReader",
    "MetadataReader",
    "SplitsReader",
    "FormReader",
    "PhysiologyReader",
    "PerformanceReader",
    "RaceReader",
    "TrainingLoadReader",
    "DurabilityReader",
    "FitnessCurveReader",
    "StrengthSessionsReader",
    "TrendNarrationReader",
    "UtilityReader",
    "TimeSeriesReader",
    "ExportReader",
]
