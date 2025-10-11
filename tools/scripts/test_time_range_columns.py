"""
Test script to verify time range columns are properly saved to DuckDB.

Tests:
1. Re-ingest activity 20636804823 (interval training from 2025-10-07)
2. Query DuckDB to verify new columns
3. Print intensity_type distribution
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import duckdb

from tools.ingest.garmin_worker import GarminIngestWorker


def test_time_range_columns():
    """Test that time range columns are properly saved."""
    activity_id = 20636804823
    activity_date = "2025-10-07"

    print(f"Testing time range columns for activity {activity_id} ({activity_date})")
    print("=" * 80)

    # Step 1: Re-ingest activity
    print("\n1. Re-ingesting activity...")
    worker = GarminIngestWorker()
    result = worker.process_activity(activity_id, activity_date)

    if not result:
        print("❌ Failed to process activity")
        return False

    print("✅ Activity processed successfully")

    # Step 2: Query DuckDB for new columns
    print("\n2. Querying DuckDB for time range columns...")
    db_path = project_root / "data" / "database" / "garmin_performance.duckdb"

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False

    conn = duckdb.connect(str(db_path))

    # Query splits with new columns
    query = """
    SELECT
        split_index,
        duration_seconds,
        start_time_gmt,
        start_time_s,
        end_time_s,
        intensity_type,
        pace_str,
        heart_rate
    FROM splits
    WHERE activity_id = ?
    ORDER BY split_index
    """

    splits = conn.execute(query, [activity_id]).fetchall()

    if not splits:
        print("❌ No splits found in database")
        conn.close()
        return False

    print(f"✅ Found {len(splits)} splits")

    # Step 3: Verify data
    print("\n3. Verifying split data:")
    print(
        f"{'#':<3} {'Duration':<10} {'Start(s)':<10} {'End(s)':<10} {'Intensity':<12} {'Pace':<8} {'HR':<5}"
    )
    print("-" * 80)

    intensity_count: dict[str, int] = {}
    for split in splits:
        (
            idx,
            duration,
            start_gmt,
            start_s,
            end_s,
            intensity,
            pace,
            hr,
        ) = split

        # Count intensity types
        intensity_count[intensity] = intensity_count.get(intensity, 0) + 1

        # Check for missing values
        if duration is None or start_s is None or end_s is None:
            print(f"⚠️  Split {idx}: Missing time range data")
        else:
            duration_str = f"{duration:.1f}s" if duration else "N/A"
            print(
                f"{idx:<3} {duration_str:<10} {start_s:<10} {end_s:<10} {intensity or 'None':<12} {pace or 'N/A':<8} {hr or 'N/A':<5}"
            )

    # Step 4: Intensity type distribution
    print("\n4. Intensity Type Distribution:")
    print("-" * 40)
    for intensity, count in sorted(intensity_count.items()):
        print(f"  {intensity or 'None':<12}: {count:>3} splits")

    conn.close()

    # Step 5: Verification summary
    print("\n" + "=" * 80)
    print("Verification Summary:")
    has_duration = all(s[1] is not None for s in splits)
    has_time_range = all(s[3] is not None and s[4] is not None for s in splits)
    has_intensity = any(s[5] is not None for s in splits)

    print(f"  Duration values:    {'✅' if has_duration else '❌'}")
    print(f"  Time range values:  {'✅' if has_time_range else '❌'}")
    print(f"  Intensity types:    {'✅' if has_intensity else '❌'}")

    success = has_duration and has_time_range and has_intensity
    print(f"\nOverall: {'✅ PASS' if success else '❌ FAIL'}")

    return success


if __name__ == "__main__":
    success = test_time_range_columns()
    sys.exit(0 if success else 1)
