"""Test training mode detection from hr_efficiency table."""

import duckdb
import pytest


@pytest.fixture
def tmp_db_with_hr_efficiency(tmp_path):
    """Create a temporary DuckDB database with hr_efficiency table."""
    db_path = tmp_path / "test_training_mode.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create hr_efficiency table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_efficiency (
            activity_id INTEGER PRIMARY KEY,
            activity_date VARCHAR,
            training_type VARCHAR,
            hr_zone_distribution_pct VARCHAR
        )
    """
    )

    # Insert test data
    conn.execute(
        """
        INSERT INTO hr_efficiency VALUES
            (12345, '2025-10-28', 'interval_sprint', '{}'),
            (12346, '2025-10-27', 'tempo_threshold', '{}'),
            (12347, '2025-10-26', 'low_moderate', '{}'),
            (12348, '2025-10-25', NULL, '{}')
    """
    )

    conn.close()
    return str(db_path)


@pytest.mark.unit
def test_get_training_mode_interval_sprint(tmp_db_with_hr_efficiency):
    """Should return 'interval_sprint' from hr_efficiency.training_type."""
    from tools.form_baseline.training_mode import get_training_mode

    mode = get_training_mode(activity_id=12345, db_path=tmp_db_with_hr_efficiency)

    assert mode == "interval_sprint"


@pytest.mark.unit
def test_get_training_mode_tempo_threshold(tmp_db_with_hr_efficiency):
    """Should return 'tempo_threshold' from hr_efficiency.training_type."""
    from tools.form_baseline.training_mode import get_training_mode

    mode = get_training_mode(activity_id=12346, db_path=tmp_db_with_hr_efficiency)

    assert mode == "tempo_threshold"


@pytest.mark.unit
def test_get_training_mode_low_moderate(tmp_db_with_hr_efficiency):
    """Should return 'low_moderate' from hr_efficiency.training_type."""
    from tools.form_baseline.training_mode import get_training_mode

    mode = get_training_mode(activity_id=12347, db_path=tmp_db_with_hr_efficiency)

    assert mode == "low_moderate"


@pytest.mark.unit
def test_get_training_mode_defaults_to_low_moderate(tmp_db_with_hr_efficiency):
    """Should default to 'low_moderate' when training_type is NULL."""
    from tools.form_baseline.training_mode import get_training_mode

    mode = get_training_mode(activity_id=12348, db_path=tmp_db_with_hr_efficiency)

    assert mode == "low_moderate"


@pytest.mark.unit
def test_get_training_mode_missing_activity(tmp_db_with_hr_efficiency):
    """Should default to 'low_moderate' when activity not found."""
    from tools.form_baseline.training_mode import get_training_mode

    mode = get_training_mode(activity_id=99999, db_path=tmp_db_with_hr_efficiency)

    assert mode == "low_moderate"
