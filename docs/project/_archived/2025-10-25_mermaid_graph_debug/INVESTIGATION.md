# Phase 1 Investigation Findings

## Root Cause Analysis

### Problem
Mermaid graphs not appearing in BALANCED reports. Template shows "グラフデータがありません" instead of graph.

### Investigation Results

#### 1. DuckDB Data Check ✅
**Status**: Data EXISTS

```
Database: ~/garmin_data/data/database/garmin_performance.duckdb
Test Activity: 20625808856
```

**Findings**:
- 7 splits found in database
- All required data present (pace, HR, power)
- Column name is `split_index` (NOT `split_number`)

**Sample Data**:
```
Split 1: pace=397.6s/km, hr=128, power=267.0
Split 2: pace=403.3s/km, hr=145, power=259.0
...
Split 7: pace=404.3s/km, hr=151, power=271.0
```

#### 2. Schema Discovery
**Important**: DuckDB column is `split_index`, not `split_number` as assumed in planning.md

```sql
SELECT split_index, pace_seconds_per_km, heart_rate, power
FROM splits
WHERE activity_id = ?
ORDER BY split_index
```

#### 3. Code Analysis

**File**: `tools/reporting/report_generator_worker.py`

**Finding 1**: `_generate_mermaid_data()` method EXISTS (lines 269-312) ✅
- Method is correctly implemented
- Expects splits with `index`, `pace_seconds_per_km`, `heart_rate`, `power` fields
- Returns proper data structure for template

**Finding 2**: `_load_splits()` method DOES NOT EXIST ❌
- Searched entire file
- No method to load splits from DuckDB

**Finding 3**: `load_performance_data()` method (lines 36-267)
- Loads basic metrics, form efficiency, performance trends
- **MISSING**: No splits loading
- **MISSING**: No call to `_generate_mermaid_data()`

**Expected Code (NOT PRESENT)**:
```python
# At end of load_performance_data() method
data["splits"] = self._load_splits(activity_id)
data["mermaid_data"] = self._generate_mermaid_data(data["splits"])
```

---

## Root Causes Identified

### Primary Causes
1. **Missing `_load_splits()` method** - No code to query splits from DuckDB
2. **Missing integration** - `load_performance_data()` doesn't call splits loading or mermaid generation
3. **Column name mismatch** - Planning assumed `split_number`, actual is `split_index`

### Why This Happened
Looking at planning.md history:
- Phase 2 completion report (line 337-351) noted: "mermaid_data が None を返すため、「グラフデータがありません」と表示される"
- Phase 2 implemented `_generate_mermaid_data()` method ✅
- Phase 2 integrated template ✅
- **BUT**: Phase 2 did NOT implement splits loading from DuckDB ❌

---

## Required Fixes

### Fix 1: Create `_load_splits()` Method

**Location**: `tools/reporting/report_generator_worker.py`
**Insert After**: `_generate_mermaid_data()` method (after line 312)

```python
def _load_splits(self, activity_id: int) -> list[dict[str, Any]]:
    """
    Load splits from DuckDB.

    Args:
        activity_id: Activity ID

    Returns:
        List of split dictionaries with index, pace, HR, etc.
    """
    import duckdb

    try:
        conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

        result = conn.execute(
            """
            SELECT
                split_index AS index,
                pace_seconds_per_km,
                heart_rate,
                cadence,
                power,
                stride_length,
                ground_contact_time,
                vertical_oscillation,
                vertical_ratio,
                elevation_gain,
                elevation_loss,
                intensity_type
            FROM splits
            WHERE activity_id = ?
            ORDER BY split_index
            """,
            [activity_id],
        ).fetchall()

        conn.close()

        if not result:
            logger.warning(f"No splits found for activity {activity_id}")
            return []

        # Convert to dict format expected by template
        splits = []
        for row in result:
            splits.append({
                "index": row[0],
                "pace_seconds_per_km": row[1],
                "heart_rate": row[2],
                "cadence": row[3],
                "power": row[4],
                "stride_length": row[5],
                "ground_contact_time": row[6],
                "vertical_oscillation": row[7],
                "vertical_ratio": row[8],
                "elevation_gain": row[9],
                "elevation_loss": row[10],
                "intensity_type": row[11],
            })

        logger.info(f"Loaded {len(splits)} splits for activity {activity_id}")
        return splits

    except Exception as e:
        logger.error(f"Error loading splits: {e}", exc_info=True)
        return []
```

### Fix 2: Integrate into `load_performance_data()`

**Location**: End of `load_performance_data()` method (before `return data`)
**Insert Before**: Line 267 (`return data`)

```python
            # Load splits and generate Mermaid graph data
            data["splits"] = self._load_splits(activity_id)
            data["mermaid_data"] = self._generate_mermaid_data(data.get("splits"))

            return data
```

---

## Test Plan

### Unit Tests

```python
# tests/reporting/test_splits_loading.py

def test_load_splits_success():
    """Test successful splits loading from DuckDB."""
    worker = ReportGeneratorWorker()
    splits = worker._load_splits(activity_id=20625808856)

    assert len(splits) == 7
    assert splits[0]["index"] == 1
    assert "pace_seconds_per_km" in splits[0]
    assert "heart_rate" in splits[0]
    assert splits[0]["pace_seconds_per_km"] > 0

def test_load_splits_no_data():
    """Test graceful handling when no splits exist."""
    worker = ReportGeneratorWorker()
    splits = worker._load_splits(activity_id=99999999)

    assert splits == []

def test_mermaid_data_generation():
    """Test mermaid data generation from splits."""
    worker = ReportGeneratorWorker()

    # Load real splits
    splits = worker._load_splits(activity_id=20625808856)
    mermaid_data = worker._generate_mermaid_data(splits)

    assert mermaid_data is not None
    assert len(mermaid_data["x_axis_labels"]) == 7
    assert len(mermaid_data["pace_data"]) == 7
    assert len(mermaid_data["heart_rate_data"]) == 7
    assert mermaid_data["pace_min"] > 0
    assert mermaid_data["pace_max"] > mermaid_data["pace_min"]

def test_load_performance_data_includes_mermaid():
    """Test that load_performance_data includes mermaid_data."""
    worker = ReportGeneratorWorker()
    data = worker.load_performance_data(activity_id=20625808856)

    assert data is not None
    assert "splits" in data
    assert "mermaid_data" in data
    assert data["mermaid_data"] is not None
    assert "x_axis_labels" in data["mermaid_data"]
```

### Integration Test

```python
# tests/reporting/test_mermaid_graph_integration.py

@pytest.mark.integration
def test_mermaid_graph_in_report():
    """Test that Mermaid graph appears in generated report."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    with open(result["report_path"]) as f:
        report = f.read()

    # Should have Mermaid graph
    assert "```mermaid" in report
    assert "xychart-beta" in report
    assert "x-axis" in report

    # Should NOT show fallback message
    assert "グラフデータがありません" not in report
```

---

## Acceptance Criteria

- [ ] `_load_splits()` method created
- [ ] `load_performance_data()` calls splits loading and mermaid generation
- [ ] All unit tests pass (4 tests)
- [ ] Integration test passes
- [ ] Generate report for activity 20625808856
- [ ] Verify Mermaid graph appears (NOT "グラフデータがありません")
- [ ] Pre-commit hooks pass (Black, Ruff, Mypy)

---

## Next Steps (Phase 2+)

Hand off to `tdd-implementer` agent with this investigation report.

**Tasks for TDD Agent**:
1. Implement `_load_splits()` method
2. Integrate into `load_performance_data()`
3. Add unit tests (4 tests)
4. Add integration test (1 test)
5. Run all tests and verify passing
6. Verify with real activity (manual test)
7. Commit with conventional commit message

---

**Investigation Date**: 2025-10-25
**Investigated By**: Claude (Phase 1)
**Status**: Ready for Phase 2 Implementation
