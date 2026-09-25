"""The plan card built from what each step of the prescription asked for (#1406).

A prescription with a stored step structure is judged step by step
(``analysis.plan_axes``) on laps aligned through their workout step index. A
legacy row of the steady family keeps exactly the card it has always had, and
a legacy quality row whose laps cannot be matched to its three synthesized
steps is not judged on its band -- the verdict rests on the other axes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from garmin_mcp.validation.validators import check_run_note_grounding
from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)
from tests.database.readers.run_report.test_strides import (
    _COOLDOWN,
    _JOG,
    _seed_today,
    _strides,
)

# The 2026-09-09 build-up (24294972923): 1 km bookends around five 1 km stages.
BUILD_UP_ID = 24294972923
BUILD_UP_DATE = "2026-09-09"
STAGE_BANDS = [(136, 150), (136, 150), (151, 161), (162, 165), (166, 169)]
BUILD_UP_STRUCTURE: list[dict[str, Any]] = [
    {"step_type": "warmup", "distance_m": 1000},
    *(
        {"step_type": "run", "distance_m": 1000, "hr_low": lo, "hr_high": hi}
        for lo, hi in STAGE_BANDS
    ),
    {"step_type": "cooldown", "distance_m": 1000},
]
# ``(workout_step_index, intensity_type, role_phase, km, seconds, avg_hr)``.
BUILD_UP_LAPS: list[tuple[int | None, str, str | None, float, float, float]] = [
    (0, "WARMUP", "warmup", 1.0, 420.0, 128.0),
    (1, "INTERVAL", "run", 1.0, 400.0, 142.0),
    (2, "INTERVAL", "run", 1.0, 380.0, 150.0),
    (3, "INTERVAL", "run", 1.0, 355.0, 157.0),
    (4, "INTERVAL", "run", 1.0, 335.0, 164.0),
    (5, "INTERVAL", "run", 1.0, 320.0, 168.0),
    (6, "COOLDOWN", "cooldown", 1.0, 400.0, 155.0),
    (6, "COOLDOWN", "cooldown", 1.0, 410.0, 148.0),
    (6, "COOLDOWN", "cooldown", 0.5, 215.0, 144.0),
    (None, "ACTIVE", None, 0.03, 13.0, 143.0),
]


def _seed_build_up(db_path: Path) -> None:
    """The 9/9 activity with its ten laps, each stamped with its step index."""
    _seed_run(
        db_path,
        activity_id=BUILD_UP_ID,
        activity_date=BUILD_UP_DATE,
        pace=3248.0 / 8.53,
        avg_hr=152,
        distance_km=8.53,
        duration_s=3248,
        training_type="tempo",
    )
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("DELETE FROM splits WHERE activity_id = ?", [BUILD_UP_ID])
        elapsed = 0.0
        for index, (step, intensity, role, km, seconds, hr) in enumerate(
            BUILD_UP_LAPS, start=1
        ):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    start_time_s, end_time_s, intensity_type, role_phase,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss, workout_step_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 180.0, 1.0, 1.0, ?)
                """,
                [
                    BUILD_UP_ID,
                    index,
                    km,
                    seconds,
                    elapsed,
                    elapsed + seconds,
                    intensity,
                    role,
                    seconds / km,
                    hr,
                    hr + 3,
                    step,
                ],
            )
            elapsed += seconds
    finally:
        conn.close()


def _set_prescription_columns(db_path: Path, **columns: Any) -> None:
    """Write the JSON / text columns ``_seed_prescription`` does not take."""
    conn = duckdb.connect(str(db_path))
    try:
        for column, value in columns.items():
            stored = value if isinstance(value, str) else json.dumps(value)
            conn.execute(f"UPDATE weekly_prescriptions SET {column} = ?", [stored])
    finally:
        conn.close()


def _seed_build_up_plan(db_path: Path, *, structured: bool) -> None:
    """The 9/9 prescription: with its 7-step structure, or as its legacy row."""
    _seed_prescription(
        db_path,
        on_date=BUILD_UP_DATE,
        session_type="tempo",
        title="ビルドアップ 1km×5",
        target_km=8.5,
        hr_low=None if structured else 136,
        hr_high=None if structured else 169,
    )
    if structured:
        _set_prescription_columns(
            db_path, structure=BUILD_UP_STRUCTURE, purpose="progression"
        )


def _axes(report: dict[str, Any]) -> list[str]:
    return [check["axis"] for check in report["plan"]["checks"]]


def _check(report: dict[str, Any], axis: str) -> dict[str, Any]:
    return next(c for c in report["plan"]["checks"] if c["axis"] == axis)


@pytest.mark.integration
def test_run_report_structured_build_up(reader_db_path: Path) -> None:
    """Five stages, each in its band and rising: judged as one stages axis."""
    _seed_build_up(reader_db_path)
    _seed_build_up_plan(reader_db_path, structured=True)

    report = _report(reader_db_path, BUILD_UP_ID)

    assert report is not None
    assert _axes(report) == ["intensity", "volume", "stages"]
    stages = _check(report, "stages")
    assert stages["actual"] == "142 → 150 → 157 → 164 → 168 bpm"
    assert stages["status"] == "on_plan"
    assert stages["verdict"] == "✅"
    assert stages["label_ja"] == "段階的ビルドアップ"
    assert [s["label"] for s in stages["segments"]] == [f"第{n}段" for n in range(1, 6)]
    assert report["plan"]["verdict"] == "✅"
    # Every row has the same shape.
    for row in report["plan"]["checks"]:
        assert set(row) == {
            "axis",
            "label_ja",
            "target",
            "actual",
            "status",
            "on_plan",
            "verdict",
            "segments",
        }
    json.dumps(report)


@pytest.mark.integration
def test_run_report_legacy_axes_unchanged(reader_db_path: Path) -> None:
    """A legacy easy row keeps today's four rows and values."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=5.8,
        duration_s=35 * 60,
    )
    _seed_prescription(
        reader_db_path,
        on_date=TODAY,
        session_type="easy",
        title="イージー 35分",
        target_km=None,
        target_minutes=35,
        hr_low=None,
        hr_high=150,
    )

    report = _report(reader_db_path)

    assert report is not None
    assert _axes(report) == ["intensity", "volume", "hr_ceiling", "continuity"]
    rows = {
        c["axis"]: (c["target"], c["actual"], c["status"])
        for c in report["plan"]["checks"]
    }
    assert rows == {
        "intensity": ("イージー", "イージー", "on_plan"),
        "volume": ("35分", "35分（100%）", "on_plan"),
        "hr_ceiling": ("150 bpm 以下", "144 bpm", "on_plan"),
        "continuity": ("最後まで走り続ける", "保てた", "on_plan"),
    }
    assert report["plan"]["verdict"] == "✅"


@pytest.mark.integration
def test_run_report_legacy_quality_misaligned_is_insufficient(
    reader_db_path: Path,
) -> None:
    """3 synthesized steps against 7 lap indices: the band is not judged."""
    _seed_build_up(reader_db_path)
    _seed_build_up_plan(reader_db_path, structured=False)

    report = _report(reader_db_path, BUILD_UP_ID)

    assert report is not None
    # The tempo purpose also asks for continuity on the one body step; with
    # the laps unmatched that is not judged either.
    assert _axes(report) == ["intensity", "volume", "hr_band", "continuity"]
    band = _check(report, "hr_band")
    assert band["status"] == "insufficient"
    assert band["on_plan"] is False
    assert band["verdict"] == "-"
    assert band["target"] == "136-169 bpm"
    assert _check(report, "continuity")["status"] == "insufficient"
    # Intensity and volume decide the verdict; the unjudged axes do not.
    assert _check(report, "intensity")["on_plan"] is True
    assert _check(report, "volume")["on_plan"] is True
    assert report["plan"]["verdict"] == "✅"


@pytest.mark.integration
def test_run_report_strides_short_feeds_verdict(reader_db_path: Path) -> None:
    """Two of four strides: the strides row is short and the verdict 🟡."""
    _seed_today(reader_db_path, [*_JOG, *_strides(2), _COOLDOWN])

    report = _report(reader_db_path)

    assert report is not None
    strides = _check(report, "strides")
    assert strides["status"] == "short"
    assert strides["verdict"] == "🟡"
    assert all(c["on_plan"] for c in report["plan"]["checks"] if c["axis"] != "strides")
    assert report["plan"]["verdict"] == "🟡"


@pytest.mark.integration
def test_existing_run_notes_still_resolve(reader_db_path: Path) -> None:
    """A note written against the 9/9 legacy card, read against the new one.

    The note stored for 24294972923 (run_id 225) was grounded on the legacy
    card, whose rows included ``hr_ceiling``. Its intensity / volume keys and
    every scene id still resolve after the laps are relabelled from the
    structure; the key the new card no longer carries is named in the result
    rather than silently accepted.
    """
    _seed_build_up(reader_db_path)
    _seed_build_up_plan(reader_db_path, structured=True)
    report = _report(reader_db_path, BUILD_UP_ID)
    assert report is not None
    moment_ids = [m["id"] for m in report["moments"]]
    assert moment_ids

    note: dict[str, Any] = {
        "story": "段階的に心拍を上げていくビルドアップを予定どおりこなせました。",
        "good_points": [
            {"text": "処方どおりの距離を走り切れています。", "evidence": "plan.volume"},
            {"text": "五段とも帯に収めて上げられました。", "evidence": "plan.stages"},
        ],
        "growth_points": [],
        "next_challenge": "次も一段ずつ心拍を確かめながら上げていきましょう。",
        "next_challenge_evidence": "plan.stages",
        "timeline": [
            {"moment_id": moment_id, "text": "流れを確認しました。"}
            for moment_id in moment_ids[:5]
        ],
        "notes": [],
    }
    assert check_run_note_grounding(note, report) == (True, None)

    stale = {
        **note,
        "good_points": [
            *note["good_points"],
            {"text": "心拍上限を守れました。", "evidence": "plan.hr_ceiling"},
        ],
    }
    ok, reason = check_run_note_grounding(stale, report)
    assert ok is False
    assert reason is not None
    assert "plan.hr_ceiling" in reason
