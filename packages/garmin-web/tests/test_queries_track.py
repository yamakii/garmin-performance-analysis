"""Unit tests for garmin_web.queries.track.get_track."""

import pytest

from garmin_web.queries.track import get_track

TRACK_ACTIVITY_ID = 9000002001

# seq_no values inserted out of order on purpose: ORDER BY seq_no must sort.
_SHUFFLED_SEQ_NOS = [5, 1, 9, 3, 7, 0, 8, 2, 6, 4]

_INSERT = (
    "INSERT INTO time_series_metrics"
    " (activity_id, seq_no, timestamp_s, heart_rate, speed, cadence,"
    "  latitude, longitude)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def _gps_row(seq_no: int, lat: float | None, lon: float | None) -> tuple:
    return (TRACK_ACTIVITY_ID, seq_no, seq_no, 140.0, 2.8, 170.0, lat, lon)


@pytest.mark.unit
def test_track_returns_ordered_coordinates(track_conn):
    track_conn.executemany(
        _INSERT,
        [
            _gps_row(seq_no, 35.6 + seq_no * 0.001, 139.7 + seq_no * 0.001)
            for seq_no in _SHUFFLED_SEQ_NOS
        ],
    )

    points = get_track(track_conn, TRACK_ACTIVITY_ID)

    assert len(points) == 10
    assert [point["seq_no"] for point in points] == list(range(10))
    assert points[0] == {"seq_no": 0, "lat": 35.6, "lon": 139.7}
    assert points[-1]["seq_no"] == 9
    assert points[-1]["lat"] == pytest.approx(35.609)
    assert points[-1]["lon"] == pytest.approx(139.709)


@pytest.mark.unit
def test_track_skips_null_coords(track_conn):
    null_seq_nos = {2, 5, 8}
    track_conn.executemany(
        _INSERT,
        [
            (
                _gps_row(seq_no, None, None)
                if seq_no in null_seq_nos
                else _gps_row(seq_no, 35.6 + seq_no * 0.001, 139.7 + seq_no * 0.001)
            )
            for seq_no in _SHUFFLED_SEQ_NOS
        ],
    )

    points = get_track(track_conn, TRACK_ACTIVITY_ID)

    assert len(points) == 7
    assert [point["seq_no"] for point in points] == [0, 1, 3, 4, 6, 7, 9]


@pytest.mark.unit
def test_track_no_gps_returns_empty(track_conn):
    track_conn.executemany(
        _INSERT,
        [_gps_row(seq_no, None, None) for seq_no in _SHUFFLED_SEQ_NOS],
    )

    points = get_track(track_conn, TRACK_ACTIVITY_ID)

    assert points == []
