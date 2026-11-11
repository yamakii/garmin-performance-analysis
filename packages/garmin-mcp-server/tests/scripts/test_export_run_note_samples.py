"""Weekly sample of stored run_notes for the outcome rubric (Issue #1570)."""

import json

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.scripts.export_run_note_samples import (
    build_samples,
    fetch_stored_run_notes,
    main,
    select_samples,
)


def _row(aid, *, ttype="easy", analysis_id=None, created_at="2026-11-01 10:00:00"):
    return {
        "analysis_id": analysis_id if analysis_id is not None else aid,
        "activity_id": aid,
        "date": "2026-11-01",
        "created_at": created_at,
        "training_type": ttype,
        "run_note": {"story": f"note {aid} v{analysis_id}"},
    }


@pytest.mark.unit
def test_select_latest_version_per_activity():
    rows = [
        _row(1, analysis_id=10, created_at="2026-11-01 10:00:00"),
        _row(1, analysis_id=11, created_at="2026-11-02 10:00:00"),
        _row(2, analysis_id=12),
    ]

    picked = select_samples(rows, n=2, seed=0)

    assert sorted(r["activity_id"] for r in picked) == [1, 2]
    newer = next(r for r in picked if r["activity_id"] == 1)
    assert newer["analysis_id"] == 11


@pytest.mark.unit
def test_select_stratifies_training_type():
    rows = [_row(i, ttype="easy") for i in range(1, 6)] + [_row(6, ttype="long")]

    picked = select_samples(rows, n=2, seed=42)

    assert sorted(r["training_type"] for r in picked) == ["easy", "long"]


@pytest.mark.unit
def test_select_n_larger_than_pool():
    picked = select_samples([_row(1)], n=3, seed=0)

    assert [r["activity_id"] for r in picked] == [1]


@pytest.mark.unit
def test_select_same_seed_is_reproducible():
    rows = [_row(i, ttype="easy") for i in range(1, 9)]

    first = select_samples(rows, n=3, seed=202646)
    second = select_samples(rows, n=3, seed=202646)

    assert [r["activity_id"] for r in first] == [r["activity_id"] for r in second]


@pytest.mark.unit
def test_build_samples_drops_activity_without_report():
    picked = [_row(1), _row(2)]

    def inputs(aid):
        if aid == 2:
            return {"error": "no run report", "activity_id": aid}
        return {"activity_id": aid, "report": {"activity_id": aid}, "context": {}}

    out = build_samples(picked, inputs=inputs)

    assert [s["activity_id"] for s in out] == [1]
    assert set(out[0]) == {
        "activity_id",
        "date",
        "training_type",
        "run_note",
        "report",
        "context",
    }


@pytest.mark.integration
def test_fetch_stored_run_notes_reads_versions_and_type(initialized_db_path):
    db = str(initialized_db_path)
    with get_write_connection(db) as conn:
        conn.execute(
            "INSERT INTO hr_efficiency (activity_id, training_type) VALUES (15700001, 'long')"
        )
        for analysis_id, day, section in [
            (1, "2026-11-01", "run_note"),
            (2, "2026-11-01", "run_note"),
            (3, "2026-11-01", "summary"),
            (4, "2026-10-01", "run_note"),
        ]:
            conn.execute(
                "INSERT INTO section_analyses (analysis_id, activity_id, "
                "activity_date, section_type, analysis_data) VALUES (?, ?, ?, ?, ?)",
                [analysis_id, 15700001, day, section, json.dumps({"story": "x"})],
            )

    rows = fetch_stored_run_notes("2026-10-15", db_path=db)

    assert sorted(r["analysis_id"] for r in rows) == [1, 2]
    assert {r["training_type"] for r in rows} == {"long"}
    assert rows[0]["run_note"] == {"story": "x"}


@pytest.mark.unit
def test_main_writes_samples(tmp_path, monkeypatch):
    import garmin_mcp.scripts.export_run_note_samples as mod

    monkeypatch.setattr(mod, "fetch_stored_run_notes", lambda since: [_row(1)])
    monkeypatch.setattr(
        mod,
        "build_samples",
        lambda picked: [{**r, "report": {}, "context": None} for r in picked],
    )
    out = tmp_path / "samples.json"

    assert main(["--n", "3", "--since", "2026-11-01", "--out", str(out)]) == 0

    data = json.loads(out.read_text(encoding="utf-8"))
    assert [d["activity_id"] for d in data] == [1]
