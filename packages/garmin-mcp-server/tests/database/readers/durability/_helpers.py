"""Shared helpers for the durability tests (split from test_durability_reader.py, #1069)."""

from __future__ import annotations

from pathlib import Path

import duckdb


def _insert_activity(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    distance_km: float,
    temp_celsius: float | None = None,
    activity_name: str | None = None,
) -> None:
    """Insert one running activity row with a given distance."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, activity_name, total_distance_km,
                total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate,
                temp_celsius
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                activity_date,
                activity_name,
                distance_km,
                int(distance_km * 300),
                300.0,
                150,
                temp_celsius,
            ],
        )
    finally:
        conn.close()


def _insert_time_series_with_cadence(
    db_path: Path,
    *,
    activity_id: int,
    front_cadence: float,
    back_cadence: float,
    front_gct: float,
    back_gct: float,
    points_per_half: int = 5,
) -> None:
    """Insert a constant-per-half series carrying cadence and GCT.

    HR/speed are constant (150 bpm @ 3.0 m/s) so decoupling and pace fade are
    zero and only the cadence / GCT deltas are under test.
    """
    conn = duckdb.connect(str(db_path))
    try:
        for seq_no in range(2 * points_per_half):
            front = seq_no < points_per_half
            conn.execute(
                """
                INSERT INTO time_series_metrics (
                    activity_id, seq_no, timestamp_s, heart_rate, speed,
                    cadence, ground_contact_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    activity_id,
                    seq_no,
                    seq_no,
                    150.0,
                    3.0,
                    front_cadence if front else back_cadence,
                    front_gct if front else back_gct,
                ],
            )
    finally:
        conn.close()


def _insert_time_series(
    db_path: Path,
    *,
    activity_id: int,
    rows: list[tuple[int, float | None, float | None]],
) -> None:
    """Insert ``(timestamp_s, heart_rate, speed)`` rows for an activity.

    ``seq_no`` is assigned sequentially (PK is activity_id + seq_no).
    """
    conn = duckdb.connect(str(db_path))
    try:
        for seq_no, (timestamp_s, heart_rate, speed) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO time_series_metrics (
                    activity_id, seq_no, timestamp_s, heart_rate, speed
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [activity_id, seq_no, timestamp_s, heart_rate, speed],
            )
    finally:
        conn.close()


def _insert_time_series_with_form(
    db_path: Path,
    *,
    activity_id: int,
    rows: list[
        tuple[
            int,
            float | None,
            float | None,
            float | None,
            float | None,
            float | None,
        ]
    ],
) -> None:
    """Insert ``(timestamp_s, heart_rate, speed, gct, vo, vr)`` rows.

    Like ``_insert_time_series`` but also populates the form columns
    (``ground_contact_time`` / ``vertical_oscillation`` / ``vertical_ratio``).
    """
    conn = duckdb.connect(str(db_path))
    try:
        for seq_no, (timestamp_s, hr, speed, gct, vo, vr) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO time_series_metrics (
                    activity_id, seq_no, timestamp_s, heart_rate, speed,
                    ground_contact_time, vertical_oscillation, vertical_ratio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [activity_id, seq_no, timestamp_s, hr, speed, gct, vo, vr],
            )
    finally:
        conn.close()


def _form_series(
    *,
    front_hr: float,
    front_speed: float,
    back_hr: float,
    back_speed: float,
    front_gct: float | None,
    back_gct: float | None,
    front_vo: float | None = None,
    back_vo: float | None = None,
    front_vr: float | None = None,
    back_vr: float | None = None,
    points_per_half: int = 5,
) -> list[
    tuple[int, float | None, float | None, float | None, float | None, float | None]
]:
    """Build a constant-per-half series including form metrics."""
    rows: list[
        tuple[int, float | None, float | None, float | None, float | None, float | None]
    ] = []
    total = 2 * points_per_half
    for ts in range(total):
        if ts < points_per_half:
            rows.append((ts, front_hr, front_speed, front_gct, front_vo, front_vr))
        else:
            rows.append((ts, back_hr, back_speed, back_gct, back_vo, back_vr))
    return rows


def _series(
    *,
    front_hr: float,
    front_speed: float,
    back_hr: float,
    back_speed: float,
    points_per_half: int = 5,
) -> list[tuple[int, float | None, float | None]]:
    """Build a time series with constant first/second-half HR and speed.

    Timestamps 0..(2*points_per_half-1). The first ``points_per_half`` samples
    fall strictly below the midpoint; the rest fall at/above it.
    """
    rows: list[tuple[int, float | None, float | None]] = []
    total = 2 * points_per_half
    for ts in range(total):
        if ts < points_per_half:
            rows.append((ts, front_hr, front_speed))
        else:
            rows.append((ts, back_hr, back_speed))
    return rows


def _durability_activity(
    activity_date: str,
    decoupling_pct: float,
    gct_fade_pct: float | None = None,
) -> dict[str, object]:
    """Build a minimal ``get_activity_durability``-shaped dict for _build_trend."""
    return {
        "activity_date": activity_date,
        "decoupling_pct": decoupling_pct,
        "gct_fade_pct": gct_fade_pct,
    }


def _ranking_activity(
    *,
    activity_id: int,
    activity_date: str,
    decoupling_pct: float,
    pace_fade_pct: float,
) -> dict[str, object]:
    """Build a minimal activity dict for ``_build_durability_ranking``."""
    return {
        "activity_id": activity_id,
        "activity_date": activity_date,
        "decoupling_pct": decoupling_pct,
        "pace_fade_pct": pace_fade_pct,
    }


def _fragility_activity(
    *,
    activity_id: int,
    activity_date: str,
    decoupling_pct: float,
    gct_fade_pct: float | None = None,
) -> dict[str, object]:
    """A ``_build_trend``-shaped activity that also carries ``activity_id``."""
    return {
        "activity_id": activity_id,
        "activity_date": activity_date,
        "decoupling_pct": decoupling_pct,
        "gct_fade_pct": gct_fade_pct,
    }


_WINDOW_845 = [
    _fragility_activity(activity_id=1, activity_date="2026-06-05", decoupling_pct=-6.8),
    _fragility_activity(
        activity_id=2, activity_date="2026-06-14", decoupling_pct=-1.51
    ),
    _fragility_activity(
        activity_id=3, activity_date="2026-06-21", decoupling_pct=-0.39
    ),
    _fragility_activity(activity_id=4, activity_date="2026-06-28", decoupling_pct=0.68),
    _fragility_activity(activity_id=5, activity_date="2026-07-05", decoupling_pct=0.39),
]
