#!/usr/bin/env python3
"""Manual test script for ActivityDetailsLoader."""

from pathlib import Path

from garmin_mcp.rag.loaders.activity_details_loader import ActivityDetailsLoader


def main():
    """Run manual tests on ActivityDetailsLoader."""

    # Initialize loader with main repo data directory
    base_path = Path(__file__).parent.parent / "garmin"
    loader = ActivityDetailsLoader(base_path=base_path)

    # Test with real activity
    activity_id = 20594901208

    print(f"🔍 Testing ActivityDetailsLoader with activity {activity_id}\n")
    print("=" * 70)

    # 1. Load activity details
    print("\n1️⃣  Loading activity_details.json...")
    try:
        data = loader.load_activity_details(activity_id)
        print(f"   ✅ Successfully loaded activity {activity_id}")
        print(f"   📊 Data keys: {list(data.keys())}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return

    # 2. Parse metric descriptors
    print("\n2️⃣  Parsing metric descriptors...")
    metric_descriptors = data.get("metricDescriptors", [])
    metrics_info = loader.parse_metric_descriptors(metric_descriptors)

    print(f"   ✅ Parsed {len(metrics_info)} metrics:")
    for i, (name, info) in enumerate(metrics_info.items()):
        if i < 5:  # Show first 5 metrics
            unit = info["unit"]
            factor = info["factor"]
            print(f"      • {name}: unit={unit}, factor={factor}")
    print(f"      ... and {len(metrics_info) - 5} more metrics")

    # 3. Check metrics array
    print("\n3️⃣  Checking metrics array...")
    metrics = data.get("activityDetailMetrics", [])
    print(f"   ✅ Found {len(metrics)} metric arrays")

    # Check first measurement has data
    if metrics and len(metrics) > 0:
        first_measurement = metrics[0]
        metric_values = first_measurement.get("metrics", [])
        non_null_count = sum(1 for v in metric_values if v is not None)
        print(
            f"   📈 First measurement: {len(metric_values)} metrics ({non_null_count} non-null)"
        )

    # 4. Extract time series for a specific metric
    print("\n4️⃣  Extracting time series data...")

    # Find heart rate metric index
    hr_metric_name = "directHeartRate"
    if hr_metric_name in metrics_info:
        hr_index = metrics_info[hr_metric_name]["index"]

        # Extract first 100 seconds
        time_series = loader.extract_time_series(
            metrics=metrics, metric_index=hr_index, start_index=0, end_index=100
        )

        # Filter out None values
        valid_values = [v for v in time_series if v is not None]

        if valid_values:
            avg_hr = sum(valid_values) / len(valid_values)
            print(f"   ✅ Extracted {len(time_series)} values for '{hr_metric_name}'")
            print(f"   💓 Average HR (first 100s): {avg_hr:.1f} bpm")
            print(f"   📊 Range: {min(valid_values):.0f} - {max(valid_values):.0f} bpm")
        else:
            print(f"   ⚠️  No valid values found for '{hr_metric_name}'")
    else:
        print(f"   ⚠️  Metric '{hr_metric_name}' not found")

    # 5. Test unit conversion
    print("\n5️⃣  Testing unit conversion...")

    # Find a metric with factor != 1.0
    for name, info in metrics_info.items():
        factor = info["factor"]
        if factor != 1.0:
            test_value = 1000.0
            converted = loader.apply_unit_conversion(info, test_value)
            print(f"   ✅ {name}:")
            print(f"      Raw value: {test_value}")
            print(f"      Factor: {factor}")
            print(f"      Converted: {converted}")
            break

    print("\n" + "=" * 70)
    print("✅ All manual tests completed successfully!\n")


if __name__ == "__main__":
    main()
