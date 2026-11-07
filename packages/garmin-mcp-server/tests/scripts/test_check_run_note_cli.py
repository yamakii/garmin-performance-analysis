"""Read-only run_note checker used by the coach-review eval (Issue #1521).

``check_run_note`` applies the two merge gates (section schema + grounding) to a
note and a report given as data, so the eval can grade a headless analyst's
``run_note.json`` without inserting anything into DuckDB.
"""

import json

import pytest

from garmin_mcp.scripts.check_run_note import check, main
from tests.scripts.test_merge_section_analyses_run_note import _REPORT, _run_note


@pytest.mark.unit
def test_check_run_note_valid_passes():
    result = check(_REPORT, _run_note())

    assert result == {"schema_ok": True, "grounding_ok": True, "errors": []}


@pytest.mark.unit
def test_check_run_note_valid_passes_with_section_payload():
    payload = {"activity_id": 1, "section_type": "run_note"}
    payload["analysis_data"] = _run_note()

    result = check(_REPORT, payload)

    assert result["schema_ok"] is True
    assert result["grounding_ok"] is True


@pytest.mark.unit
def test_check_run_note_growth_point_on_within_signal_fails():
    note = _run_note(
        growth_points=[
            {
                "text": "接地時間をもう少し短くしていきたいところです。",
                "evidence": "signals.gct",
            }
        ]
    )

    result = check(_REPORT, note)

    assert result["schema_ok"] is True
    assert result["grounding_ok"] is False
    assert len(result["errors"]) == 1
    assert "signals.gct" in result["errors"][0]


@pytest.mark.unit
def test_check_run_note_cli_prints_json(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    note_path = tmp_path / "run_note.json"
    report_path.write_text(json.dumps(_REPORT, ensure_ascii=False), encoding="utf-8")
    note_path.write_text(json.dumps(_run_note(), ensure_ascii=False), encoding="utf-8")

    code = main(["--report", str(report_path), "--note", str(note_path)])

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"schema_ok", "grounding_ok", "errors"}
    assert out["schema_ok"] is True
    assert out["grounding_ok"] is True


@pytest.mark.unit
def test_check_run_note_cli_missing_file_still_exits_zero(tmp_path, capsys):
    code = main(
        ["--report", str(tmp_path / "nope.json"), "--note", str(tmp_path / "x.json")]
    )

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema_ok"] is False
    assert out["grounding_ok"] is False
    assert out["errors"]
