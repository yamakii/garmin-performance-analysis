"""
Splits helper classes for split metric calculations.

This package contains specialized calculators extracted from splits.py:
- TerrainClassifier: Terrain classification from elevation data
- PhaseMapper: Intensity type to phase mapping and estimation
- HRCalculator: Heart rate zone calculation
- CadencePowerCalculator: Cadence rating and power efficiency
- EnvironmentalCalculator: Environmental conditions and impact
- SplitsExtractor: Raw splits.json data extraction
"""

from garmin_mcp.database.inserters.splits_helpers.cadence_power import (
    CadencePowerCalculator,
)
from garmin_mcp.database.inserters.splits_helpers.environmental import (
    EnvironmentalCalculator,
)
from garmin_mcp.database.inserters.splits_helpers.extractor import SplitsExtractor
from garmin_mcp.database.inserters.splits_helpers.hr_calculations import HRCalculator
from garmin_mcp.database.inserters.splits_helpers.phase_mapping import PhaseMapper
from garmin_mcp.database.inserters.splits_helpers.terrain import TerrainClassifier

__all__ = [
    "TerrainClassifier",
    "PhaseMapper",
    "HRCalculator",
    "CadencePowerCalculator",
    "EnvironmentalCalculator",
    "SplitsExtractor",
]
