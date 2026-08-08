"""Tests for form_baseline.split_filter — the shared running-split predicate."""

import pytest

from garmin_mcp.form_baseline import trainer
from garmin_mcp.form_baseline.split_filter import (
    MAX_RUNNING_PACE_S_PER_KM,
    MIN_SPLIT_KM,
    running_split_params,
    running_split_sql,
)


@pytest.mark.unit
class TestRunningSplitSql:
    """The predicate must be emittable with and without a table alias."""

    def test_running_split_sql_without_alias(self) -> None:
        """Bare column names, both bounds present, one placeholder each."""
        sql = running_split_sql()

        assert "pace_seconds_per_km > 0" in sql
        assert "pace_seconds_per_km < ?" in sql
        assert "distance >= ?" in sql
        assert "." not in sql
        assert sql.count("?") == len(running_split_params())

    def test_running_split_sql_with_alias(self) -> None:
        """Every referenced column is prefixed with the given alias."""
        sql = running_split_sql("s")

        assert "s.pace_seconds_per_km > 0" in sql
        assert "s.pace_seconds_per_km < ?" in sql
        assert "s.distance >= ?" in sql
        # No bare (unprefixed) column survives.
        assert " pace_seconds_per_km" not in sql.replace("s.pace_seconds_per_km", "")
        assert " distance" not in sql.replace("s.distance", "")

    def test_running_split_params_order_matches_placeholders(self) -> None:
        """Params bind pace ceiling first, then the distance floor."""
        assert running_split_params() == [MAX_RUNNING_PACE_S_PER_KM, MIN_SPLIT_KM]


@pytest.mark.unit
class TestTrainerDelegation:
    """The trainer must not keep a private copy of the threshold (#878)."""

    def test_trainer_delegates_to_shared_min_split_km(self) -> None:
        """The old module-level constant is gone; the shared helpers are used."""
        assert not hasattr(trainer, "MIN_TRAINING_SPLIT_KM")
        assert trainer.running_split_sql is running_split_sql
        assert trainer.running_split_params is running_split_params
