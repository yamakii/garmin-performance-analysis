"""Shared helpers for the splits tests (split from test_splits.py, #1069)."""


def _eight_lap_splits_data(activity_id: int, invalid_lap_cadence=None) -> dict:
    """Build raw splits.json data with 8 laps.

    Lap 5 (index 4) is a short walk/recovery lap. When ``invalid_lap_cadence``
    is provided it is applied to lap 5's ``averageRunCadence``.
    """
    laps = []
    for i in range(1, 9):
        lap = {
            "lapIndex": i,
            "distance": 1000.0 if i != 5 else 118.0,
            "duration": 390.0 if i != 5 else 105.0,
            "startTimeGMT": f"2026-07-24T00:{i:02d}:00.0",
            "intensityType": "INTERVAL",
            "averageHR": 140,
            "averageRunCadence": 180.0 if i != 5 else 92.95,
        }
        laps.append(lap)
    if invalid_lap_cadence is not None:
        laps[4]["averageRunCadence"] = invalid_lap_cadence
    return {"activityId": activity_id, "lapDTOs": laps}
