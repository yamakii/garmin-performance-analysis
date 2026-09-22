"""Stride / stride-recovery lap roles from the workout step index (#1296)."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.splits import insert_splits
from garmin_mcp.database.inserters.splits_helpers.stride_roles import (
    assign_stride_roles,
)


def _lap(step_index: int | None, duration: float, role: str | None = "run") -> dict:
    return {
        "workout_step_index": step_index,
        "duration_seconds": duration,
        "role_phase": role,
    }


def _jog_with_strides() -> list[dict]:
    """Jog (idx0 x3) + 4x (idx1 20 s stride, idx2 90 s recovery) + idx3 300 s."""
    laps = [_lap(0, 410.0), _lap(0, 412.0), _lap(0, 408.0)]
    for _ in range(4):
        laps.append(_lap(1, 20.0))
        laps.append(_lap(2, 90.0))
    laps.append(_lap(3, 300.0))
    return laps


class TestAssignStrideRoles:
    @pytest.mark.unit
    def test_stride_role_from_repeating_step_index(self):
        """A repeating step index marks 4 strides and 4 recoveries."""
        laps = _jog_with_strides()
        result = assign_stride_roles(laps)

        roles = [lap["role_phase"] for lap in result]
        assert roles.count("stride") == 4
        assert roles.count("recovery") == 4
        assert roles == ["run"] * 3 + ["stride", "recovery"] * 4 + ["run"]
        # idx0 / idx3 are untouched.
        assert [
            lap["role_phase"] for lap in result if lap["workout_step_index"] in (0, 3)
        ] == ["run"] * 4
        # The input is not mutated.
        assert all(lap["role_phase"] == "run" for lap in laps)

    @pytest.mark.unit
    def test_manual_short_lap_not_stride(self):
        """A 30 s ACTIVE lap whose index appears once stays 'run'."""
        laps = [_lap(0, 400.0), _lap(1, 30.0), _lap(2, 400.0)]
        result = assign_stride_roles(laps)
        assert [lap["role_phase"] for lap in result] == ["run", "run", "run"]

    @pytest.mark.unit
    def test_autolap_split_inside_step_not_stride(self):
        """Auto-lap splits of one step (1000 m + 1000 m + 62 m) are not strides."""
        laps = [_lap(0, 410.0), _lap(0, 405.0), _lap(0, 25.0)]
        result = assign_stride_roles(laps)
        assert [lap["role_phase"] for lap in result] == ["run", "run", "run"]

    @pytest.mark.unit
    def test_no_step_index_untouched(self):
        """Laps without workout_step_index keep their role_phase."""
        laps = [
            _lap(None, 20.0),
            _lap(None, 90.0, "recovery"),
            _lap(None, 20.0),
            _lap(None, 400.0, "warmup"),
        ]
        result = assign_stride_roles(laps)
        assert [lap["role_phase"] for lap in result] == [
            "run",
            "recovery",
            "run",
            "warmup",
        ]


class TestSplitsIngestStepIndex:
    @pytest.mark.integration
    def test_splits_ingest_stores_workout_step_index(
        self, tmp_path, initialized_db_path
    ):
        """A raw lapDTO with wktStepIndex: 1 lands in splits.workout_step_index."""
        activity_id = 91296001
        laps = [
            {
                "lapIndex": 1,
                "distance": 1000.0,
                "duration": 410.0,
                "intensityType": "ACTIVE",
                "averageHR": 140,
                "wktStepIndex": 1,
            },
            {
                "lapIndex": 2,
                "distance": 1000.0,
                "duration": 405.0,
                "intensityType": "ACTIVE",
                "averageHR": 142,
            },
        ]
        raw_splits_file = tmp_path / "splits.json"
        raw_splits_file.write_text(
            json.dumps({"activityId": activity_id, "lapDTOs": laps}),
            encoding="utf-8",
        )

        conn = duckdb.connect(str(initialized_db_path))
        try:
            assert insert_splits(activity_id, conn, str(raw_splits_file)) is True
            rows = conn.execute(
                "SELECT split_index, workout_step_index, role_phase FROM splits "
                "WHERE activity_id = ? ORDER BY split_index",
                [activity_id],
            ).fetchall()
        finally:
            conn.close()

        assert rows == [(1, 1, "run"), (2, None, "run")]

    @pytest.mark.integration
    def test_splits_ingest_marks_stride_roles(self, tmp_path, initialized_db_path):
        """Repeat-group strides are stored as role_phase 'stride' / 'recovery'."""
        activity_id = 91296002
        laps = []
        for position, lap in enumerate(_jog_with_strides(), start=1):
            duration = lap["duration_seconds"]
            distance = 1000.0 if duration > 200 else duration * 4.0
            laps.append(
                {
                    "lapIndex": position,
                    "distance": distance,
                    "duration": duration,
                    "intensityType": "ACTIVE",
                    "averageHR": 140,
                    "wktStepIndex": lap["workout_step_index"],
                }
            )
        raw_splits_file = tmp_path / "splits.json"
        raw_splits_file.write_text(
            json.dumps({"activityId": activity_id, "lapDTOs": laps}),
            encoding="utf-8",
        )

        conn = duckdb.connect(str(initialized_db_path))
        try:
            assert insert_splits(activity_id, conn, str(raw_splits_file)) is True
            roles = [
                row[0]
                for row in conn.execute(
                    "SELECT role_phase FROM splits WHERE activity_id = ? "
                    "ORDER BY split_index",
                    [activity_id],
                ).fetchall()
            ]
        finally:
            conn.close()

        assert roles == ["run"] * 3 + ["stride", "recovery"] * 4 + ["run"]
