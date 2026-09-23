"""Integration tests for the prefetch_activity_context bundle.

These exercise prefetch_activity_context() against the verification DuckDB
(fixture activity 12345678901, training_type=aerobic_base) to confirm the
bundle is filled by the real readers, carries exactly the keys that still have
a reader (#1287) and stays JSON-safe.
"""

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.scripts.prefetch_activity_context import prefetch_activity_context

FIXTURE_ACTIVITY_ID = 12345678901
FIXTURE_ACTIVITY_DATE = "2025-01-15"

# Every key of the bundle. Each one is read by build_run_note_context in
# garmin_mcp.scripts.prefetch_activity_context (or is the envelope / the raw
# prescription rows behind prescription_for_run); the run itself is carried by
# get_run_report, not by this bundle (#1287).
BUNDLE_KEYS = {
    "activity_id",
    "activity_date",
    "training_type",
    "gear",
    "similar_workouts",
    "long_run_gate",
    "prescription",
    "prescription_for_run",
    "week_position",
    "previous_same_type",
    "vs_previous",
    "morning_wellness",
}


def _patch_db_path(monkeypatch: pytest.MonkeyPatch, verification_db_path: Path) -> None:
    """Point prefetch_activity_context.get_db_path() at the verification DB.

    prefetch resolves the path once and passes it explicitly to every reader,
    so patching this single entry point routes all reads to the fixture DB.
    """
    monkeypatch.setattr(
        "garmin_mcp.scripts.prefetch_activity_context.get_db_path",
        lambda *a, **k: verification_db_path,
    )


@pytest.mark.integration
class TestPrefetchBundle:
    """Bundle behavior against the verification DuckDB."""

    def test_bundle_has_exactly_the_keys_with_a_reader(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        assert set(result) == BUNDLE_KEYS
        assert result["activity_id"] == FIXTURE_ACTIVITY_ID
        assert result["activity_date"] == FIXTURE_ACTIVITY_DATE
        assert result["training_type"] == "aerobic_base"
        # A 5-10 km fixture run: the long-run gate has no basis.
        assert result["long_run_gate"] is None
        # No plan ledger in the fixture: the layer is present and empty.
        assert result["prescription"] == []
        assert result["prescription_for_run"] is None

    def test_prefetch_similar_workouts_key_always_present(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        # Key must always exist even when there are no similar workouts.
        assert "similar_workouts" in result
        assert result["similar_workouts"] is None or isinstance(
            result["similar_workouts"], dict
        )

    def test_bundle_is_json_serialisable(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole bundle must be JSON-serializable with no custom encoder.

        The MCP layer json-serializes the bundle, so any raw datetime.date
        (e.g. similar_workouts activity_date) breaks the entire tool (Issue
        #235). json.dumps without default= would raise on such a value.
        """
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        # No default= encoder: a raw date anywhere in the bundle would raise.
        json.dumps(result, ensure_ascii=False)

    def test_bundle_survives_a_missing_hr_efficiency_row(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No hr_efficiency row: training_type is null, the bundle still whole."""
        conn = duckdb.connect(str(verification_db_path))
        conn.execute(
            "DELETE FROM hr_efficiency WHERE activity_id = ?", [FIXTURE_ACTIVITY_ID]
        )
        conn.close()

        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        assert "error" not in result
        assert set(result) == BUNDLE_KEYS
        assert result["training_type"] is None

    def test_bundle_includes_gear_block(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The shoe worn reaches the analysis CONTEXT (Issue #1207).

        The fixture carries no gear, so this seeds one and checks the derived
        history travels with it -- and that adding the key keeps the bundle
        JSON-serializable.
        """
        conn = duckdb.connect(str(verification_db_path))
        conn.execute(
            """
            UPDATE activities
            SET gear_type = 'Shoes',
                gear_model = 'Test Shoe',
                gear_nickname = 'v15',
                gear_uuid = 'uuid-test'
            WHERE activity_id = ?
            """,
            [FIXTURE_ACTIVITY_ID],
        )
        conn.close()

        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        gear = result["gear"]
        assert gear is not None
        assert gear["gear_model"] == "Test Shoe"
        assert gear["gear_nickname"] == "v15"
        assert gear["gear_label"] == "Test Shoe (v15)"
        assert gear["runs_on_gear"] == 1
        assert gear["is_new_gear"] is True
        assert gear["first_use_date"] == FIXTURE_ACTIVITY_DATE

        json.dumps(result, ensure_ascii=False)

    def test_bundle_gear_none_without_gear(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No gear registered in Garmin yields an explicit null, not a crash.

        Runs before 2021 have an empty gear.json in the real data.
        """
        conn = duckdb.connect(str(verification_db_path))
        conn.execute(
            """
            UPDATE activities
            SET gear_type = NULL,
                gear_model = NULL,
                gear_nickname = NULL,
                gear_uuid = NULL
            WHERE activity_id = ?
            """,
            [FIXTURE_ACTIVITY_ID],
        )
        conn.close()

        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        assert result["gear"] is None
        assert result["activity_id"] == FIXTURE_ACTIVITY_ID

    def test_bundle_gear_uses_fixture_gear_by_default(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The fixture's own gear.json reaches the bundle through ingest.

        Guards the whole path: gear.json -> inserter -> activities -> CONTEXT.
        The fixture predates nicknames, so gear_label is the bare model.
        """
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        gear = result["gear"]
        assert gear is not None
        assert gear["gear_model"] == "Nike Vaporfly 3"
        assert gear["gear_type"] == "Running Shoes"
        assert gear["gear_nickname"] is None
        assert gear["gear_label"] == "Nike Vaporfly 3"
