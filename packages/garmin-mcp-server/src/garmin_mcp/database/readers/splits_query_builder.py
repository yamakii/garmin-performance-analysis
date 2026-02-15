"""
Query builder for splits statistics and full-mode queries.

Eliminates SQL duplication across get_splits_pace_hr, get_splits_form_metrics,
get_splits_elevation, and get_splits_comprehensive by generating SQL and
parsing results from field definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SplitField:
    """Definition of a split field for query generation.

    Attributes:
        db_column: Column name in the splits table.
        stat_key: Key name in the statistics output dict.
        full_key: Key name in the full-mode output dict.
        default: Default value when the DB value is None (full mode only).
    """

    db_column: str
    stat_key: str
    full_key: str
    default: Any = None


# Field group definitions for each query type
STAT_FUNCS = ("AVG", "MEDIAN", "STDDEV", "MIN", "MAX")
STAT_KEYS = ("mean", "median", "std", "min", "max")

PACE_HR_FIELDS = (
    SplitField("pace_seconds_per_km", "pace", "avg_pace_seconds_per_km"),
    SplitField("heart_rate", "heart_rate", "avg_heart_rate"),
)

FORM_FIELDS = (
    SplitField("ground_contact_time", "ground_contact_time", "ground_contact_time_ms"),
    SplitField(
        "vertical_oscillation", "vertical_oscillation", "vertical_oscillation_cm"
    ),
    SplitField("vertical_ratio", "vertical_ratio", "vertical_ratio_percent"),
)

ELEVATION_FIELDS = (
    SplitField("elevation_gain", "elevation_gain", "elevation_gain_m"),
    SplitField("elevation_loss", "elevation_loss", "elevation_loss_m"),
)

COMPREHENSIVE_STAT_FIELDS = (
    SplitField("pace_seconds_per_km", "pace", "avg_pace_seconds_per_km"),
    SplitField("heart_rate", "heart_rate", "avg_heart_rate"),
    SplitField("ground_contact_time", "ground_contact_time", "ground_contact_time_ms"),
    SplitField(
        "vertical_oscillation", "vertical_oscillation", "vertical_oscillation_cm"
    ),
    SplitField("vertical_ratio", "vertical_ratio", "vertical_ratio_percent"),
    SplitField("power", "power", "power_watts", 0.0),
    SplitField("stride_length", "stride_length", "stride_length_cm", 0.0),
    SplitField("cadence", "cadence", "cadence_spm"),
    SplitField("elevation_gain", "elevation_gain", "elevation_gain_m"),
    SplitField("elevation_loss", "elevation_loss", "elevation_loss_m"),
    SplitField("max_heart_rate", "max_heart_rate", "max_heart_rate_bpm"),
    SplitField("max_cadence", "max_cadence", "max_cadence_spm"),
)

# Full-mode columns for pace_hr (split_index + distance + fields)
PACE_HR_FULL_COLUMNS = ("split_index", "distance", "pace_seconds_per_km", "heart_rate")
PACE_HR_FULL_KEYS = (
    "split_number",
    "distance_km",
    "avg_pace_seconds_per_km",
    "avg_heart_rate",
)

FORM_FULL_COLUMNS = (
    "split_index",
    "ground_contact_time",
    "vertical_oscillation",
    "vertical_ratio",
)
FORM_FULL_KEYS = (
    "split_number",
    "ground_contact_time_ms",
    "vertical_oscillation_cm",
    "vertical_ratio_percent",
)

ELEVATION_FULL_COLUMNS = (
    "split_index",
    "elevation_gain",
    "elevation_loss",
    "terrain_type",
)
ELEVATION_FULL_KEYS = (
    "split_number",
    "elevation_gain_m",
    "elevation_loss_m",
    "terrain_type",
)
ELEVATION_EXTRA_KEYS = {"max_elevation_m": None, "min_elevation_m": None}

COMPREHENSIVE_FULL_COLUMNS = (
    "split_index",
    "distance",
    "pace_seconds_per_km",
    "heart_rate",
    "ground_contact_time",
    "vertical_oscillation",
    "vertical_ratio",
    "power",
    "stride_length",
    "cadence",
    "elevation_gain",
    "elevation_loss",
    "max_heart_rate",
    "max_cadence",
    "intensity_type",
    "role_phase",
)
COMPREHENSIVE_FULL_KEYS = (
    "split_number",
    "distance_km",
    "avg_pace_seconds_per_km",
    "avg_heart_rate",
    "ground_contact_time_ms",
    "vertical_oscillation_cm",
    "vertical_ratio_percent",
    "power_watts",
    "stride_length_cm",
    "cadence_spm",
    "elevation_gain_m",
    "elevation_loss_m",
    "max_heart_rate_bpm",
    "max_cadence_spm",
    "intensity_type",
    "role_phase",
)
# Columns that need default values when None in comprehensive full mode
COMPREHENSIVE_FULL_DEFAULTS: dict[str, Any] = {
    "power_watts": 0.0,
    "stride_length_cm": 0.0,
    "intensity_type": "",
    "role_phase": "",
}


def build_statistics_sql(fields: tuple[SplitField, ...]) -> str:
    """Generate SQL SELECT clause for statistics aggregation.

    Args:
        fields: Tuple of SplitField definitions.

    Returns:
        SQL query string with AVG/MEDIAN/STDDEV/MIN/MAX for each field.
    """
    select_parts = []
    for field in fields:
        for func in STAT_FUNCS:
            alias = f"{field.stat_key}_{func.lower()}"
            select_parts.append(f"{func}({field.db_column}) as {alias}")

    columns = ",\n                            ".join(select_parts)
    return f"""
                        SELECT
                            {columns}
                        FROM splits
                        WHERE activity_id = ?
                        """


def parse_statistics_result(
    result: tuple[Any, ...] | None, fields: tuple[SplitField, ...], activity_id: int
) -> dict[str, Any]:
    """Parse a statistics query result into the standard output dict.

    Args:
        result: Raw database row tuple.
        fields: Tuple of SplitField definitions (same order as SQL).
        activity_id: Activity ID for output.

    Returns:
        Dict with activity_id, statistics_only=True, and metrics.
    """
    if not result or result[0] is None:
        return {
            "activity_id": activity_id,
            "statistics_only": True,
            "metrics": {},
        }

    metrics: dict[str, dict[str, float]] = {}
    for i, field in enumerate(fields):
        offset = i * len(STAT_KEYS)
        metrics[field.stat_key] = {
            key: float(result[offset + j]) if result[offset + j] is not None else 0.0
            for j, key in enumerate(STAT_KEYS)
        }

    return {
        "activity_id": activity_id,
        "statistics_only": True,
        "metrics": metrics,
    }


def build_full_sql(columns: tuple[str, ...]) -> str:
    """Generate SQL SELECT clause for full-mode queries.

    Args:
        columns: Tuple of column names to select.

    Returns:
        SQL query string selecting the specified columns.
    """
    cols = ",\n                        ".join(columns)
    return f"""
                    SELECT
                        {cols}
                    FROM splits
                    WHERE activity_id = ?
                    ORDER BY split_index
                    """


def parse_full_result(
    rows: list[tuple],
    keys: tuple[str, ...],
    extra_keys: dict[str, Any] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, list[dict]]:
    """Parse full-mode query results into the standard output dict.

    Args:
        rows: List of raw database row tuples.
        keys: Tuple of output key names (same order as columns).
        extra_keys: Optional dict of additional keys with static values.
        defaults: Optional dict of key→default for None replacement.

    Returns:
        Dict with 'splits' key containing list of split dicts.
    """
    if not rows:
        return {"splits": []}

    splits = []
    for row in rows:
        split_dict: dict[str, Any] = {}
        for j, key in enumerate(keys):
            value = row[j]
            if value is None and defaults and key in defaults:
                value = defaults[key]
            split_dict[key] = value
        if extra_keys:
            split_dict.update(extra_keys)
        splits.append(split_dict)

    return {"splits": splits}


def empty_stats_result(activity_id: int) -> dict[str, Any]:
    """Return an empty statistics result for error cases."""
    return {
        "activity_id": activity_id,
        "statistics_only": True,
        "metrics": {},
    }
