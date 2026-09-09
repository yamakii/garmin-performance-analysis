"""Integration tests for the expanded prefetch_activity_context bundle (Issue #235).

These exercise prefetch_activity_context() against the verification DuckDB
(fixture activity 12345678901, training_type=aerobic_base) to confirm the new
bundle keys are populated by the real readers and that existing keys do not
regress (backward compatibility).
"""

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.scripts.prefetch_activity_context import prefetch_activity_context

FIXTURE_ACTIVITY_ID = 12345678901
FIXTURE_ACTIVITY_DATE = "2025-01-15"


def _patch_db_path(monkeypatch: pytest.MonkeyPatch, verification_db_path: Path) -> None:
    """Point prefetch_activity_context.get_db_path() at the verification DB.

    prefetch resolves the path once and passes it explicitly to every reader,
    so patching this single entry point routes all reads to the fixture DB.
    """
    monkeypatch.setattr(
        "garmin_mcp.scripts.prefetch_activity_context.get_db_path",
        lambda *a, **k: verification_db_path,
    )


def _insert_form_evaluation(db_path: Path) -> None:
    """Insert a minimal form_evaluations row for the fixture activity.

    The verification fixture has no form_evaluations row; this seeds one with a
    known gct_needs_improvement flag so the bundle's form_evaluation key is
    populated by FormReader.get_form_evaluations.
    """
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO form_evaluations (
            eval_id, activity_id,
            gct_ms_expected, vo_cm_expected, vr_pct_expected,
            gct_ms_actual, vo_cm_actual, vr_pct_actual,
            gct_delta_pct, vo_delta_cm, vr_delta_pct,
            gct_star_rating, gct_score, gct_needs_improvement,
            vo_star_rating, vo_score, vo_needs_improvement,
            vr_star_rating, vr_score, vr_needs_improvement,
            cadence_actual, cadence_minimum, cadence_achieved,
            overall_score, overall_star_rating,
            integrated_score, training_mode
        ) VALUES (
            1, ?,
            245.0, 8.0, 7.0,
            250.0, 8.5, 7.2,
            2.0, 0.5, 2.8,
            '★★★★☆', 4.0, false,
            '★★★★☆', 4.0, false,
            '★★★★☆', 4.0, false,
            178.0, 170, true,
            4.0, '★★★★☆',
            90.0, 'aerobic'
        )
        """,
        [FIXTURE_ACTIVITY_ID],
    )
    conn.close()


# Baseline set of existing keys prior to the S1 bundle expansion. These must
# always be present and unchanged (backward compatibility guarantee).
EXISTING_KEYS = {
    "activity_id",
    "activity_date",
    "training_type",
    "temperature_c",
    "humidity_pct",
    "wind_mps",
    "wind_direction",
    "terrain_category",
    "avg_elevation_gain_per_km",
    "total_elevation_gain",
    "total_elevation_loss",
    "zone_percentages",
    "primary_zone",
    "zone_distribution_rating",
    "hr_stability",
    "aerobic_efficiency",
    "training_quality",
    "zone2_focus",
    "zone4_threshold_work",
    "form_scores",
    "phase_structure",
}


@pytest.mark.integration
class TestPrefetchBundleExpansion:
    """Bundle expansion behavior against the verification DuckDB."""

    def test_prefetch_includes_form_evaluation(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _insert_form_evaluation(verification_db_path)
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        assert "form_evaluation" in result
        form_eval = result["form_evaluation"]
        assert form_eval is not None
        # FormReader returns nested per-metric blocks; needs_improvement is bool.
        assert isinstance(form_eval["gct"]["needs_improvement"], bool)
        assert form_eval["gct"]["needs_improvement"] is False

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

    def test_prefetch_vo2max_conditional_easy(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        # Fixture training_type is aerobic_base → vo2_max excluded (None),
        # lactate_threshold also excluded for non-tempo/threshold types.
        assert result["training_type"] == "aerobic_base"
        assert result["vo2_max"] is None
        assert result["lactate_threshold"] is None

    def test_prefetch_existing_keys_unchanged(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        # All pre-existing keys remain present (no regression).
        assert EXISTING_KEYS.issubset(result.keys())
        # New keys are strictly additive.
        new_keys = {
            "form_evaluation",
            "hr_zones_detail",
            "form_baseline_trend",
            "similar_workouts",
            "vo2_max",
            "lactate_threshold",
        }
        assert new_keys.issubset(result.keys())
        # Core existing values still resolve from the fixture.
        assert result["activity_id"] == FIXTURE_ACTIVITY_ID
        assert result["training_type"] == "aerobic_base"

    def test_prefetch_integration_no_plan(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan vs actual removed (Issue #785): no plan keys, still serializable.

        The bundle must not carry planned_workout / plan_achievement, and the
        generic derivations (phase_category / next_run_target) still resolve
        from training_type with no plan. The whole bundle stays JSON-safe.
        """
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        assert "planned_workout" not in result
        assert "plan_achievement" not in result
        # Generic derivations still resolve from training_type alone.
        assert result["phase_category"] == "low_moderate"
        assert result["next_run_target"]["recommended_type"] == "easy"
        # The whole bundle stays JSON-serializable with no custom encoder.
        json.dumps(result, ensure_ascii=False)

    def test_prefetch_emits_next_run_target_key(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """next_run_target is a deterministic dict with recommended_type.

        The fixture training_type is aerobic_base → HR-based "easy" target.
        Issue #863: when the athlete's Garmin native zones are available the
        band is the Zone2 band; otherwise it falls back to the legacy
        avg_heart_rate ± 5 (Issue #672). No LLM involved either way.
        """
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        assert "next_run_target" in result
        nrt = result["next_run_target"]
        assert isinstance(nrt, dict)
        assert nrt["recommended_type"] == "easy"
        if nrt.get("hr_basis") == "garmin_native_zone":
            # Band equals the athlete's own Garmin native Zone2 bounds.
            zone2 = next(
                z for z in result["hr_zones_detail"]["zones"] if z["zone_number"] == 2
            )
            assert nrt["target_hr_low"] == int(zone2["low_boundary"])
            assert nrt["target_hr_high"] == int(zone2["high_boundary"])
            assert nrt["target_zone"] == "Zone2"
            assert "typical_hr" in nrt
        else:
            # Legacy fallback: avg_heart_rate (148 bpm) ± 5.
            assert nrt["target_hr_low"] == 143
            assert nrt["target_hr_high"] == 153

    def test_prefetch_bundle_is_json_serializable(
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

    def test_prefetch_emits_category_keys(
        self, verification_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """phase_category / environment_category are deterministic (Issue #673).

        The fixture training_type is aerobic_base with no plan, so the prefetch
        maps it to phase_category='low_moderate' and
        environment_category='base_moderate' without any LLM involvement.
        """
        _patch_db_path(monkeypatch, verification_db_path)

        result = prefetch_activity_context(FIXTURE_ACTIVITY_ID)

        assert result["phase_category"] == "low_moderate"
        assert result["environment_category"] == "base_moderate"
