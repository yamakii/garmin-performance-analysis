"""Shared helpers for the trainer tests (split from test_trainer.py, #1069)."""

from datetime import date, datetime, timedelta

import duckdb


def _seed_baseline_db(db_path: str) -> None:
    """Seed a real DuckDB with splits/activities for train_form_baselines.

    Creates 20 activities x 5 splits = 100 rows within a 60-day window.
    Each split carries GCT/VO/VR/cadence that vary with speed (so the
    linear/power fits are well-conditioned) and stay inside the trainer's
    outlier bounds. Splits are full 1 km laps (distance = 1.0) so they pass
    the GPS-fragment filter. Power + base_weight_kg are included so the
    trailing power-efficiency training also has data.
    """
    conn = duckdb.connect(db_path)

    conn.execute("""
        CREATE TABLE activities (
            activity_id INTEGER PRIMARY KEY,
            activity_date DATE,
            base_weight_kg FLOAT
        )
        """)
    conn.execute("""
        CREATE TABLE splits (
            split_id INTEGER PRIMARY KEY,
            activity_id INTEGER,
            pace_seconds_per_km FLOAT,
            ground_contact_time FLOAT,
            vertical_oscillation FLOAT,
            vertical_ratio FLOAT,
            stride_length FLOAT,
            cadence FLOAT,
            average_speed FLOAT,
            grade_adjusted_speed FLOAT,
            power FLOAT,
            role_phase VARCHAR,
            distance FLOAT
        )
        """)
    conn.execute("CREATE SEQUENCE seq_history_id START 1")
    conn.execute("CREATE SEQUENCE form_baseline_history_seq START 1")
    conn.execute("""
        CREATE TABLE form_baseline_history (
            history_id INTEGER PRIMARY KEY DEFAULT nextval('seq_history_id'),
            user_id VARCHAR DEFAULT 'default',
            condition_group VARCHAR DEFAULT 'flat_road',
            metric VARCHAR,
            model_type VARCHAR,
            coef_alpha FLOAT,
            coef_d FLOAT,
            coef_a FLOAT,
            coef_b FLOAT,
            period_start DATE,
            period_end DATE,
            trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            n_samples INTEGER,
            rmse FLOAT,
            speed_range_min FLOAT,
            speed_range_max FLOAT,
            power_a FLOAT,
            power_b FLOAT,
            power_rmse FLOAT,
            UNIQUE (user_id, condition_group, metric, period_start, period_end)
        )
        """)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=55)

    activity_rows = []
    split_rows = []
    for i in range(20):
        activity_date = start_date + timedelta(days=i * 2)
        activity_id = 2000 + i
        base_weight_kg = 70.0
        activity_rows.append((activity_id, activity_date.date(), base_weight_kg))

        for j in range(5):
            split_id = activity_id * 10 + j
            # Pace 330 -> 270 sec/km => speed ~3.03 -> 3.70 m/s
            pace = 330.0 - (i * 5 + j * 12) % 60
            speed = 1000.0 / pace
            # Form metrics vary with speed, within outlier bounds:
            # GCT 150-350, VO 5-20, VR 4-15, cadence 140-210
            gct = 300.0 - 20.0 * speed
            vo = 12.0 - 1.0 * speed
            vr = 11.0 - 1.0 * speed
            cadence = 160.0 + 5.0 * speed  # positive slope with speed
            stride_length = 1.0 + 0.1 * speed
            power = 180.0 + 30.0 * speed
            split_rows.append(
                (
                    split_id,
                    activity_id,
                    pace,
                    gct,
                    vo,
                    vr,
                    stride_length,
                    cadence,
                    speed,
                    speed,  # grade_adjusted_speed mirrors average_speed
                    power,
                    "run",
                    1.0,  # full 1 km lap
                )
            )

    conn.executemany("INSERT INTO activities VALUES (?, ?, ?)", activity_rows)
    conn.executemany(
        "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", split_rows
    )
    conn.close()


def _create_baseline_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the activities/splits/form_baseline_history schema for ensure tests."""
    conn.execute("""
        CREATE TABLE activities (
            activity_id INTEGER PRIMARY KEY,
            activity_date DATE,
            base_weight_kg FLOAT
        )
        """)
    conn.execute("""
        CREATE TABLE splits (
            split_id INTEGER PRIMARY KEY,
            activity_id INTEGER,
            pace_seconds_per_km FLOAT,
            ground_contact_time FLOAT,
            vertical_oscillation FLOAT,
            vertical_ratio FLOAT,
            stride_length FLOAT,
            cadence FLOAT,
            average_speed FLOAT,
            grade_adjusted_speed FLOAT,
            power FLOAT,
            role_phase VARCHAR,
            distance FLOAT
        )
        """)
    conn.execute("CREATE SEQUENCE seq_history_id START 1")
    conn.execute("CREATE SEQUENCE form_baseline_history_seq START 1")
    conn.execute("""
        CREATE TABLE form_baseline_history (
            history_id INTEGER PRIMARY KEY DEFAULT nextval('seq_history_id'),
            user_id VARCHAR DEFAULT 'default',
            condition_group VARCHAR DEFAULT 'flat_road',
            metric VARCHAR,
            model_type VARCHAR,
            coef_alpha FLOAT,
            coef_d FLOAT,
            coef_a FLOAT,
            coef_b FLOAT,
            period_start DATE,
            period_end DATE,
            trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            n_samples INTEGER,
            rmse FLOAT,
            speed_range_min FLOAT,
            speed_range_max FLOAT,
            power_a FLOAT,
            power_b FLOAT,
            power_rmse FLOAT,
            UNIQUE (user_id, condition_group, metric, period_start, period_end)
        )
        """)


def _make_splits(activity_id: int) -> list[tuple]:
    """Return 5 well-conditioned full 1 km splits (within outlier bounds)."""
    rows = []
    for j in range(5):
        split_id = activity_id * 10 + j
        # Pace 330 -> 270 sec/km => speed ~3.03 -> 3.70 m/s
        pace = 330.0 - (activity_id * 5 + j * 12) % 60
        speed = 1000.0 / pace
        gct = 300.0 - 20.0 * speed  # 150-350
        vo = 12.0 - 1.0 * speed  # 5-20
        vr = 11.0 - 1.0 * speed  # 4-15
        cadence = 160.0 + 5.0 * speed  # 140-210
        stride_length = 1.0 + 0.1 * speed
        power = 180.0 + 30.0 * speed
        rows.append(
            (
                split_id,
                activity_id,
                pace,
                gct,
                vo,
                vr,
                stride_length,
                cadence,
                speed,
                speed,  # grade_adjusted_speed mirrors average_speed
                power,
                "run",
                1.0,  # full 1 km lap
            )
        )
    return rows


def _seed_two_month_window(db_path: str, activity_date: str, splits_per_month: int):
    """Seed activities/splits across the activity month and prior month.

    ``splits_per_month`` controls how many 5-split activities go into EACH of the
    two months. With 12 activities/month -> 60 splits/month (>=50) so both the
    current and prior baseline periods (each a 2-month window) have enough data.
    Use a small value (e.g. 1 -> 5 splits) to exercise the insufficient path.
    """
    conn = duckdb.connect(db_path)
    _create_baseline_schema(conn)

    d = datetime.strptime(activity_date, "%Y-%m-%d").date()
    # Mid-points of the activity month and the prior month.
    current_mid = date(d.year, d.month, 15)
    prior_first = date(d.year, d.month, 1) - timedelta(days=1)
    prior_mid = date(prior_first.year, prior_first.month, 15)

    activity_rows = []
    split_rows = []
    next_id = 3000
    for month_anchor in (current_mid, prior_mid):
        for k in range(splits_per_month):
            activity_id = next_id
            next_id += 1
            act_date = month_anchor + timedelta(days=k % 10)
            activity_rows.append((activity_id, act_date, 70.0))
            split_rows.extend(_make_splits(activity_id))

    if activity_rows:
        conn.executemany("INSERT INTO activities VALUES (?, ?, ?)", activity_rows)
    if split_rows:
        conn.executemany(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            split_rows,
        )
    conn.close()


def _count_baseline_rows(db_path: str) -> int:
    """Return the total number of rows in form_baseline_history."""
    conn = duckdb.connect(db_path, read_only=True)
    try:
        row = conn.execute("SELECT COUNT(*) FROM form_baseline_history").fetchone()
        return int(row[0]) if row is not None else 0
    finally:
        conn.close()


FRAGMENT_END_DATE = "2026-03-31"  # 2-month window: 2026-02-01 .. 2026-03-31


FULL_SPLIT_COUNT = 60  # 12 activities x 5 full 1 km laps


def _seed_fragment_contaminated_db(db_path: str) -> None:
    """Seed 60 full 1 km splits plus 12 GPS-fragment laps in one window.

    The full laps follow the physiological relation ``cadence = 160 + 5 *
    speed`` at 3.03-3.70 m/s. The fragments are 8 m manual-lap-press artifacts
    whose pace (4:04/km) is a measurement artifact while their cadence is
    walk-like; unfiltered they drag the fitted cadence slope negative (#873).
    """
    conn = duckdb.connect(db_path)
    _create_baseline_schema(conn)

    activity_rows = []
    split_rows = []
    for k in range(12):
        activity_id = 5000 + k
        act_date = date(2026, 3, 1) + timedelta(days=k)
        activity_rows.append((activity_id, act_date, 70.0))
        split_rows.extend(_make_splits(activity_id))

        # One 8 m GPS fragment per activity, at an impossible 4:04/km.
        fragment_pace = 244.0
        fragment_speed = 1000.0 / fragment_pace
        split_rows.append(
            (
                activity_id * 10 + 5,
                activity_id,
                fragment_pace,
                300.0 - 20.0 * fragment_speed,
                12.0 - 1.0 * fragment_speed,
                11.0 - 1.0 * fragment_speed,
                1.0 + 0.1 * fragment_speed,
                170.0,  # walk-like cadence at an artifact "sprint" pace
                fragment_speed,
                fragment_speed,
                180.0 + 30.0 * fragment_speed,
                "run",
                0.008,  # 8 m
            )
        )

    conn.executemany("INSERT INTO activities VALUES (?, ?, ?)", activity_rows)
    conn.executemany(
        "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", split_rows
    )
    conn.close()
