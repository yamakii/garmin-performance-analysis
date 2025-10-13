"""Database inserters for normalized DuckDB tables."""

from tools.database.inserters.activities import insert_activities
from tools.database.inserters.body_composition import insert_body_composition_data
from tools.database.inserters.form_efficiency import insert_form_efficiency
from tools.database.inserters.heart_rate_zones import insert_heart_rate_zones
from tools.database.inserters.hr_efficiency import insert_hr_efficiency
from tools.database.inserters.lactate_threshold import insert_lactate_threshold
from tools.database.inserters.performance_trends import insert_performance_trends
from tools.database.inserters.section_analyses import insert_section_analysis
from tools.database.inserters.splits import insert_splits
from tools.database.inserters.time_series_metrics import insert_time_series_metrics
from tools.database.inserters.vo2_max import insert_vo2_max

__all__ = [
    "insert_activities",
    "insert_body_composition_data",
    "insert_form_efficiency",
    "insert_heart_rate_zones",
    "insert_hr_efficiency",
    "insert_lactate_threshold",
    "insert_performance_trends",
    "insert_section_analysis",
    "insert_splits",
    "insert_time_series_metrics",
    "insert_vo2_max",
]
