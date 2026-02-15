"""
Aggregate reader - backward compatibility wrapper.

This module preserves backward compatibility by delegating to specialized readers:
- FormReader: form_efficiency, form_evaluations
- PhysiologyReader: hr_efficiency, heart_rate_zones, vo2_max, lactate_threshold
- PerformanceReader: performance_trends, weather, section_analyses
- UtilityReader: profile, histogram

New code should use the specialized readers directly via GarminDBReader.
"""

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.readers.form import FormReader
from garmin_mcp.database.readers.performance import PerformanceReader
from garmin_mcp.database.readers.physiology import PhysiologyReader
from garmin_mcp.database.readers.utility import UtilityReader

logger = logging.getLogger(__name__)


class AggregateReader(BaseDBReader):
    """Backward-compatible wrapper that delegates to specialized readers.

    This class is retained for backward compatibility. New code should
    access specialized readers directly via GarminDBReader attributes:
    - reader.form.get_form_efficiency_summary(...)
    - reader.physiology.get_hr_efficiency_analysis(...)
    - reader.performance.get_performance_trends(...)
    - reader.utility.profile_table_or_query(...)
    """

    def __init__(
        self,
        db_path: str | None = None,
        *,
        form: FormReader | None = None,
        physiology: PhysiologyReader | None = None,
        performance: PerformanceReader | None = None,
        utility: UtilityReader | None = None,
    ):
        """Initialize AggregateReader.

        Args:
            db_path: Optional path to DuckDB database file.
            form: Optional FormReader instance (avoids duplicate connections).
            physiology: Optional PhysiologyReader instance.
            performance: Optional PerformanceReader instance.
            utility: Optional UtilityReader instance.
        """
        super().__init__(db_path)
        self._form = form or FormReader(db_path)
        self._physiology = physiology or PhysiologyReader(db_path)
        self._performance = performance or PerformanceReader(db_path)
        self._utility = utility or UtilityReader(db_path)

    # Form delegation
    def get_form_efficiency_summary(self, activity_id: int) -> dict[str, Any] | None:
        return self._form.get_form_efficiency_summary(activity_id)

    def get_form_evaluations(self, activity_id: int) -> dict[str, Any] | None:
        return self._form.get_form_evaluations(activity_id)

    # Physiology delegation
    def get_hr_efficiency_analysis(self, activity_id: int) -> dict[str, Any] | None:
        return self._physiology.get_hr_efficiency_analysis(activity_id)

    def get_heart_rate_zones_detail(self, activity_id: int) -> dict[str, Any] | None:
        return self._physiology.get_heart_rate_zones_detail(activity_id)

    @staticmethod
    def _get_vo2_max_category(vo2_max_value: float | None) -> str:
        return PhysiologyReader._get_vo2_max_category(vo2_max_value)

    def get_vo2_max_data(self, activity_id: int) -> dict[str, Any] | None:
        return self._physiology.get_vo2_max_data(activity_id)

    def get_lactate_threshold_data(self, activity_id: int) -> dict[str, Any] | None:
        return self._physiology.get_lactate_threshold_data(activity_id)

    # Performance delegation
    def get_performance_trends(self, activity_id: int) -> dict[str, Any] | None:
        return self._performance.get_performance_trends(activity_id)

    def get_weather_data(self, activity_id: int) -> dict[str, Any] | None:
        return self._performance.get_weather_data(activity_id)

    def get_section_analysis(
        self, activity_id: int, section_type: str, max_output_size: int = 10240
    ) -> dict[str, Any] | None:
        return self._performance.get_section_analysis(
            activity_id, section_type, max_output_size
        )

    # Utility delegation
    def profile_table_or_query(
        self,
        table_or_query: str,
        date_range: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._utility.profile_table_or_query(table_or_query, date_range)

    def histogram_column(
        self,
        table_or_query: str,
        column: str,
        bins: int = 20,
        date_range: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._utility.histogram_column(table_or_query, column, bins, date_range)
