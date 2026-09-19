"""The split rows the run-scene tests are pinned against, plus read helpers.

Every builder here is **real split data** from a run that exposed a mistake in
one of the cuts: a 5 km run whose km 1 spikes to 155 bpm while averaging 131
(9/17), a short run whose sustained ceiling contact spans two kilometres with a
correction inside it (9/18), a 25 km long run that must not spend all five
slots on the ceiling (9/13), a 4 km recovery run whose single slow kilometre is
not a fade (7/31), a threshold session whose reps are recorded as two splits
each and whose rest covers 0.18 km (4/20), and a tempo run that is naturally
read in kilometres (9/9).

Positions (``km_from`` / ``t_from_s``) are **real distances and times** into the
run, never lap numbers -- conflating the two is what #1268 fixed -- so a
fixture's lap *n* of 1 km sits at km *n-1* .. *n*.
"""

from __future__ import annotations

from typing import Any


def _split(
    split_index: int,
    pace: float,
    avg_hr: float,
    max_hr: float,
    *,
    cadence: float = 178.0,
    elevation_gain_m: float = 2.0,
    distance_km: float = 1.0,
) -> dict[str, Any]:
    """One split row in the shape the reader hands to the detector."""
    return {
        "split_index": split_index,
        "distance_km": distance_km,
        "pace_s_per_km": pace,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "cadence": cadence,
        "elevation_gain_m": elevation_gain_m,
    }


def _rows(rows: list[tuple[float, float, float, float, float]]) -> list[dict[str, Any]]:
    """``(pace, avg_hr, max_hr, cadence, gain)`` tuples -> split rows from km 1."""
    return [
        _split(i, pace, avg_hr, max_hr, cadence=cadence, elevation_gain_m=gain)
        for i, (pace, avg_hr, max_hr, cadence, gain) in enumerate(rows, start=1)
    ]


def _momentary_peak_run() -> list[dict[str, Any]]:
    """The 9/17 run: km 1 peaks at 155 bpm while averaging 131 (ceiling 150)."""
    return _rows(
        [
            (423, 131, 155, 176, 2),
            (411, 144, 149, 181, 2),
            (416, 149, 155, 180, 2),
            (424, 150, 154, 181, 2),
            (421, 148, 156, 178, 2),
        ]
    )


def _ceiling_touch_run() -> list[dict[str, Any]]:
    """The 9/18 run: sustained contact at km 4-5, eased off at km 4."""
    return _rows(
        [
            (413, 129, 140, 177, 2),
            (407, 145, 149, 183, 2),
            (419, 147, 151, 184, 2),
            (432, 148, 156, 183, 2),
            (413, 148, 155, 178, 2),
        ]
    )


def _recovery_run() -> list[dict[str, Any]]:
    """The 7/31 recovery run: one slow km 3, then the fastest kilometre."""
    return _rows(
        [
            (485, 116, 126, 172, 2),
            (479, 128, 134, 174, 2),
            (497, 132, 137, 172, 2),
            (476, 135, 145, 170, 2),
        ]
    )


def _long_run_with_walk_breaks() -> list[dict[str, Any]]:
    """The 9/13 long run: 25 km, walk breaks at km 14 / 20 / 22, median 510."""
    paces = [
        446, 466, 514, 521, 540, 539, 528, 513, 517, 510, 486, 491, 485,
        530, 532, 505, 482, 508, 509, 563, 516, 538, 486, 473, 461,
    ]  # fmt: skip
    avg_hrs = [
        136, 148, 150, 150, 153, 149, 148, 149, 148, 142, 145, 146, 148,
        142, 140, 143, 148, 143, 144, 142, 143, 141, 147, 148, 148,
    ]  # fmt: skip
    max_hrs = [
        152, 152, 156, 154, 158, 154, 152, 155, 160, 152, 149, 156, 152,
        159, 151, 153, 156, 154, 149, 149, 147, 150, 152, 151, 152,
    ]  # fmt: skip
    cadences = [
        179, 181, 181, 178, 181, 180, 180, 183, 172, 179, 178, 176, 176,
        165, 172, 176, 177, 176, 177, 159, 177, 166, 179, 181, 181,
    ]  # fmt: skip
    return _rows(
        [
            (pace, avg_hr, max_hr, cadence, 3.0)
            for pace, avg_hr, max_hr, cadence in zip(
                paces, avg_hrs, max_hrs, cadences, strict=True
            )
        ]
    )


def _every_kind_run() -> list[dict[str, Any]]:
    """12 splits deliberately firing six scenes (median pace 425 s/km).

    km 1-2 fast start, km 4-5 climb, km 5-6 ceiling touch, km 8 walk break,
    km 9 surge, km 10-12 fade.
    """
    return _rows(
        [
            (400, 130, 140, 176, 2),
            (402, 138, 145, 176, 3),
            (425, 143, 147, 178, 2),
            (425, 143, 147, 176, 18),
            (428, 150, 156, 175, 20),
            (445, 149, 154, 174, 5),
            (420, 143, 147, 176, 2),
            (550, 138, 145, 160, 2),
            (412, 144, 148, 176, 3),
            (445, 146, 148, 175, 3),
            (450, 147, 149, 175, 3),
            (455, 147, 149, 174, 3),
        ]
    )


def _four_ceiling_contacts_run() -> list[dict[str, Any]]:
    """20 flat kilometres with four separate sustained contacts (ceiling 150).

    km 2 (1 split), km 5-7 (3), km 11-12 (2), km 15-18 (4); every gap is wide
    enough that ``MERGE_GAP_SPLITS`` cannot bridge it.
    """
    contacts = {2, 5, 6, 7, 11, 12, 15, 16, 17, 18}
    return _rows(
        [
            (500.0, 151.0 if km in contacts else 140.0, 156.0, 178.0, 2.0)
            for km in range(1, 21)
        ]
    )


def _fading_run(final_pace: float) -> list[dict[str, Any]]:
    """Nine kilometres at 7:00/km, then a closing stretch that lets go."""
    paces = [420.0] * 9 + [450.0, 455.0, final_pace]
    return _rows(
        [(pace, 140.0 + km, 150.0, 178.0, 2.0) for km, pace in enumerate(paces)]
    )


def _timed(
    rows: list[tuple[float, float, str, float, float]],
) -> list[dict[str, Any]]:
    """``(distance_km, duration_s, role, avg_hr, max_hr)`` tuples -> split rows.

    Pace is derived from the two quantities the watch actually records, so a
    fragment keeps the artifact pace that makes it a fragment.
    """
    rows_out: list[dict[str, Any]] = []
    for index, (distance, duration, role, avg_hr, max_hr) in enumerate(rows, start=1):
        row = _split(
            index,
            duration / distance,
            avg_hr,
            max_hr,
            distance_km=distance,
        )
        row["duration_s"] = duration
        row["role_phase"] = role
        rows_out.append(row)
    return rows_out


def _threshold_session() -> list[dict[str, Any]]:
    """The 4/20 threshold session: WU / rep / rest / rep / CD in nine splits.

    Each rep is recorded as two splits (the athlete presses the lap key a beat
    late), and the 120 s rest covers only 0.18 km -- invisible on a distance
    axis, which is why this session is narrated on a time axis by its steps.
    """
    return _timed(
        [
            (1.0, 393, "warmup", 128, 141),
            (0.51, 207, "warmup", 141, 150),
            (1.0, 324, "run", 170, 176),
            (0.11, 36, "run", 174, 176),
            (0.18, 120, "recovery", 154, 172),
            (1.0, 320, "run", 172, 182),
            (0.13, 40, "run", 178, 182),
            (0.91, 600, "cooldown", 140, 160),
            (0.16, 75, "cooldown", 130, 142),
        ]
    )


def _tempo_session() -> list[dict[str, Any]]:
    """The 9/9 tempo run: a 0.93 km warmup, a 5 km main set and a cooldown.

    The main set is long enough to be read kilometre by kilometre, which is the
    language this session is naturally described in.
    """
    return _timed(
        [
            (0.93, 400, "warmup", 132, 145),
            *[(1.0, 300, "run", 152, 160) for _ in range(5)],
            (0.13, 60, "cooldown", 145, 152),
            (1.0, 420, "cooldown", 135, 148),
            (0.05, 20, "cooldown", 120, 130),
            (0.03, 12, "cooldown", 118, 125),
        ]
    )


def _rep_session(reps: int) -> list[dict[str, Any]]:
    """A warmup, ``reps`` × (1 km rep + 400 m rest) and a cooldown."""
    rows: list[tuple[float, float, str, float, float]] = [
        (1.2, 480, "warmup", 130, 145)
    ]
    for number in range(reps):
        rows.append((1.0, 300 + number, "run", 168 + number, 178 + number))
        rows.append((0.4, 180, "recovery", 150, 170))
    rows.append((1.0, 420, "cooldown", 138, 150))
    return _timed(rows)


def _bookended_long_run() -> list[dict[str, Any]]:
    """1 km warmup, 20 km main set closing hard, 1 km cooldown."""
    main = [500.0] * 17 + [470.0, 465.0, 460.0]
    rows: list[tuple[float, float, str, float, float]] = [
        (1.0, 560, "warmup", 128, 140)
    ]
    rows.extend((1.0, pace, "run", 140, 150) for pace in main)
    rows.append((1.0, 580, "cooldown", 132, 142))
    return _timed(rows)


def _kinds_by_km(moments: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """``{kind: (km_from, km_to)}`` for readable assertions on unique kinds."""
    return {m["kind"]: (m["km_from"], m["km_to"]) for m in moments}


def _spans(moments: list[dict[str, Any]], kind: str) -> list[tuple[float, float]]:
    """Every ``(km_from, km_to)`` of one kind, in run order."""
    return [(m["km_from"], m["km_to"]) for m in moments if m["kind"] == kind]


def _occupied_splits(moment: dict[str, Any]) -> list[int]:
    """The laps a scene owns (``split_list`` for walk breaks, else its span)."""
    split_list = moment["facts"].get("split_list")
    if split_list:
        return [int(index) for index in split_list]
    return list(range(moment["split_from"], moment["split_to"] + 1))


def _labels(moments: list[dict[str, Any]]) -> list[str]:
    """Every scene's Japanese label, in run order."""
    return [str(moment["label_ja"]) for moment in moments]
