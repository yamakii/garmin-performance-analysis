"""Unit tests guarding against re-introduction of removed legacy code.

Issue #348 removed unused legacy calculator methods and a permanent no-op
DuckDB cache stub from GarminIngestWorker. These tests assert those symbols
do not reappear (regression guard).
"""

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.mark.unit
def test_garmin_worker_no_dead_legacy_methods():
    """Removed legacy methods must not exist on GarminIngestWorker.

    `_calculate_hr_efficiency_analysis` is intentionally excluded: it is still
    exercised by tests/unit/test_hr_zone_percentage.py and is therefore kept.
    """
    removed_methods = (
        "_calculate_form_efficiency_summary",
        "_calculate_performance_trends",
        "_check_duckdb_cache",
    )

    for name in removed_methods:
        assert not hasattr(
            GarminIngestWorker, name
        ), f"{name} should have been removed (Issue #348)"
