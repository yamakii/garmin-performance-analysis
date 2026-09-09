"""Shared helpers for the hr_efficiency tests (split from test_hr_efficiency.py, #1069)."""

import json


def _write_raw_files(tmp_path, zone_secs, label):
    """Helper: build hr_zones.json + activity.json from per-zone seconds.

    ``zone_secs`` maps zone number (1-5) to secsInZone. Passing values that sum
    to 100 makes each zone's percentage equal to its seconds value.
    """
    hr_zones_data = [
        {
            "zoneNumber": z,
            "zoneLowBoundary": 100 + z * 15,
            "secsInZone": float(zone_secs.get(z, 0.0)),
        }
        for z in range(1, 6)
    ]
    hr_zones_file = tmp_path / "hr_zones.json"
    with open(hr_zones_file, "w", encoding="utf-8") as f:
        json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

    summary = {"averageHR": 140.0, "maxHR": 170.0, "minHR": 110.0}
    if label is not None:
        summary["trainingEffectLabel"] = label
    activity_file = tmp_path / "activity.json"
    with open(activity_file, "w", encoding="utf-8") as f:
        json.dump({"summaryDTO": summary}, f, ensure_ascii=False, indent=2)

    return str(hr_zones_file), str(activity_file)
