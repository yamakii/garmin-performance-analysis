"""Export a small sample of stored run_notes for the weekly rubric check (#1570).

The coach-review eval (``.claude/hillclimb/coach-review/``) normally runs the
run-note-analyst on fixed cases. This read-only CLI feeds its second mode: a few
run_notes already stored in ``section_analyses`` are picked each week and scored
on the outcome rubric by the judge alone (``sample-stored.mjs``), so a slow
narrowing of the coach review shows up as a trend.

Usage:
    uv run python -m garmin_mcp.scripts.export_run_note_samples \\
        --n 3 --since 2026-11-01 --out /tmp/run_note_samples.json

The output is a JSON array ``[{activity_id, date, training_type, run_note,
report, context}]``. ``report`` and ``context`` are rebuilt now with the same
code ``get_run_note_inputs`` uses, so they reflect today's report, not the one
the note was written against. Nothing is written to DuckDB.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from garmin_mcp.database.connection import get_connection, get_db_path

_UNKNOWN_TYPE = "unknown"


def _version_key(row: dict) -> tuple[str, int]:
    """Order key of one stored version: creation time, then analysis_id."""
    return (str(row.get("created_at") or ""), int(row.get("analysis_id") or 0))


def _latest_per_activity(rows: list[dict]) -> list[dict]:
    """Keep only the newest stored run_note of each activity."""
    latest: dict[int, dict] = {}
    for row in rows:
        aid = int(row["activity_id"])
        if aid not in latest or _version_key(row) > _version_key(latest[aid]):
            latest[aid] = row
    return list(latest.values())


def select_samples(rows: list[dict], n: int, seed: int) -> list[dict]:
    """Pick up to ``n`` run_notes, one version per activity, spread over types.

    Only the latest version (``created_at``, then ``analysis_id``) of each
    activity is eligible. The pool is grouped by ``training_type`` (a missing
    type counts as its own group) and drawn round-robin over the groups in a
    seeded random order, so each type is sampled before any type is sampled
    twice.

    Args:
        rows: Stored run_note rows with at least ``activity_id`` and optionally
            ``training_type``, ``created_at`` and ``analysis_id``.
        n: How many samples to return at most.
        seed: Seed of the random draw, for a reproducible weekly sample.

    Returns:
        Up to ``n`` rows, ordered by date then activity_id.
    """
    if n <= 0:
        return []
    rng = random.Random(seed)
    groups: dict[str, list[dict]] = {}
    for row in sorted(_latest_per_activity(rows), key=lambda r: r["activity_id"]):
        groups.setdefault(row.get("training_type") or _UNKNOWN_TYPE, []).append(row)
    for members in groups.values():
        rng.shuffle(members)
    order = sorted(groups)
    rng.shuffle(order)

    picked: list[dict] = []
    while len(picked) < n and any(groups[t] for t in order):
        for t in order:
            if groups[t] and len(picked) < n:
                picked.append(groups[t].pop())
    return sorted(picked, key=lambda r: (str(r.get("date") or ""), r["activity_id"]))


def _iso_week_seed(today: date) -> int:
    """A seed that stays the same within one ISO week (YYYYWW)."""
    year, week, _ = today.isocalendar()
    return year * 100 + week


def fetch_stored_run_notes(since: str, db_path: str | None = None) -> list[dict]:
    """Every stored run_note on/after ``since``, all versions, read-only."""
    with get_connection(get_db_path(db_path)) as conn:
        result = conn.execute(
            """
            SELECT s.analysis_id, s.activity_id, s.activity_date, s.created_at,
                   s.analysis_data, h.training_type
            FROM section_analyses s
            LEFT JOIN hr_efficiency h ON h.activity_id = s.activity_id
            WHERE s.section_type = 'run_note'
              AND s.activity_date >= CAST(? AS DATE)
            """,
            [since],
        ).fetchall()
    rows = []
    for analysis_id, activity_id, activity_date, created_at, data, ttype in result:
        try:
            note = json.loads(data) if isinstance(data, str) else data
        except ValueError:
            note = None
        rows.append(
            {
                "analysis_id": int(analysis_id),
                "activity_id": int(activity_id),
                "date": str(activity_date),
                "created_at": str(created_at),
                "training_type": ttype,
                "run_note": note,
            }
        )
    return rows


def _run_note_inputs(activity_id: int) -> dict[str, Any]:
    """The report and context the run-note agent reads (``get_run_note_inputs``)."""
    from garmin_mcp.database.db_reader import GarminDBReader
    from garmin_mcp.tools.run_report import GetRunReportParams, _get_run_note_inputs

    result: dict[str, Any] = _get_run_note_inputs(
        GarminDBReader(), GetRunReportParams(activity_id=activity_id)
    )
    return result


def build_samples(
    picked: list[dict],
    inputs: Callable[[int], dict[str, Any]] = _run_note_inputs,
) -> list[dict]:
    """Attach the rebuilt report and context to each picked run_note.

    A note whose activity no longer has a run report is dropped.
    """
    out = []
    for row in picked:
        got = inputs(row["activity_id"])
        if not got or got.get("error") or got.get("report") is None:
            print(
                f"skip {row['activity_id']}: no run report "
                f"({(got or {}).get('error', 'empty')})",
                file=sys.stderr,
            )
            continue
        out.append(
            {
                "activity_id": row["activity_id"],
                "date": row["date"],
                "training_type": row.get("training_type"),
                "run_note": row["run_note"],
                "report": got["report"],
                "context": got.get("context"),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: write the sample JSON to ``--out``; 0 on success."""
    parser = argparse.ArgumentParser(
        description="Export a sample of stored run_notes (read-only)"
    )
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random seed (default: the current ISO week, YYYYWW)",
    )
    args = parser.parse_args(argv)
    try:
        date.fromisoformat(args.since)
    except ValueError:
        parser.error("--since must be YYYY-MM-DD")

    seed = args.seed if args.seed is not None else _iso_week_seed(date.today())
    picked = select_samples(fetch_stored_run_notes(args.since), args.n, seed)
    samples = build_samples(picked)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(samples, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(
        json.dumps({"out": str(args.out), "n": len(samples), "seed": seed}),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
