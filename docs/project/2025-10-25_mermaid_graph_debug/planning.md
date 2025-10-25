# 計画: Mermaid Graph Data Source Investigation

## プロジェクト情報
- **プロジェクト名**: `mermaid_graph_debug`
- **作成日**: `2025-10-25`
- **ステータス**: 計画中
- **優先度**: High (important BALANCED feature)
- **推定時間**: 2-4 hours
- **GitHub Issue**: TBD (計画承認後に作成)
- **親プロジェクト**: `2025-10-25_balanced_report_v2_complete`

---

## 要件定義

### 目的
Investigate and fix why `_generate_mermaid_data()` returns None for some activities, preventing Mermaid graphs from appearing in BALANCED reports.

### 解決する問題

**Current Issue**:
- **Location**: `tools/reporting/report_generator_worker.py`, line ~260 (`_generate_mermaid_data()`)
- **Symptom**: Returns None for some activities, showing "グラフデータがありません" in reports
- **Status**: Phase 2 implementation complete (method exists, template integration done)
- **Impact**: Critical BALANCED feature (visual pace/HR trend) not working

**Error Scenario**:
```python
# In load_performance_data()
context["mermaid_data"] = self._generate_mermaid_data(context["splits"])
# ↓ Returns None

# In template (line ~299 in planning.md)
{% if mermaid_data %}
  {# Render graph #}
{% else %}
  グラフデータがありません。  # ← Shows this message
{% endif %}
```

**Known from Completion Report** (line ~337-351):
> **注意**: 現在の実装では mermaid_data が None を返すため、「グラフデータがありません」と表示される。これは splits データが空の場合の graceful handling。

**Hypotheses**:
1. `context["splits"]` is empty or None when loading
2. Splits exist in DuckDB but not loaded correctly in `load_performance_data()`
3. Data format mismatch (expected fields missing)
4. Activity-specific issue (works for some, not others)

### ユースケース
1. **User Opens Report**:
   - Report should display Mermaid graph showing pace/HR trends across splits
   - Graph provides quick visual overview of performance consistency
   - User can identify pacing issues (e.g., starting too fast)

2. **Compare Training Types**:
   - Base run: Simple pace/HR graph (2 lines)
   - Interval run: Pace/HR/Power graph (3 lines) with Work/Recovery highlighting
   - Visual helps understand workout structure

---

## 現状分析

### 既存実装 (Phase 2 - Complete)

**File**: `tools/reporting/report_generator_worker.py`
**Method**: `_generate_mermaid_data(splits)` (lines 824-855 in planning.md)

```python
def _generate_mermaid_data(self, splits: list) -> dict:
    """Generate mermaid graph data from splits.

    Returns:
        Dict with x_axis_labels (List[str]), pace_data (List[int]),
        heart_rate_data (List[int]), power_data (List[int] or None),
        and dynamic Y-axis ranges.
    """
    if not splits or len(splits) == 0:
        return None  # ← Graceful handling

    x_labels = [str(s["index"]) for s in splits]
    pace_data = [int(s["pace_seconds_per_km"]) for s in splits if s.get("pace_seconds_per_km")]
    hr_data = [int(s["heart_rate"]) for s in splits if s.get("heart_rate")]
    power_data = [int(s["power"]) for s in splits if s.get("power")]

    # Calculate dynamic Y-axis ranges
    pace_min = min(pace_data) - 20 if pace_data else 380
    pace_max = max(pace_data) + 20 if pace_data else 440
    hr_min = min(hr_data) - 10 if hr_data else 120
    hr_max = max(hr_data) + 10 if hr_data else 160

    return {
        "x_axis_labels": x_labels,  # List, not JSON
        "pace_data": pace_data,
        "heart_rate_data": hr_data,
        "power_data": power_data if len(power_data) > 0 else None,
        "pace_min": pace_min,
        "pace_max": pace_max,
        "hr_min": hr_min,
        "hr_max": hr_max,
    }
```

**Critical Questions**:
1. Is `splits` parameter empty when method is called?
2. Do splits have required fields (`pace_seconds_per_km`, `heart_rate`)?
3. Is splits loading working in `load_performance_data()`?

### Splits Loading Investigation

**File**: `tools/reporting/report_generator_worker.py`
**Method**: `load_performance_data(activity_id)` (line ~245 in planning.md)

**Expected Code**:
```python
# In load_performance_data() method
context["splits"] = self._load_splits(activity_id)  # ← Need to verify this exists
context["mermaid_data"] = self._generate_mermaid_data(context["splits"])
```

**Need to Check**:
1. Does `_load_splits()` method exist?
2. Does it query DuckDB correctly?
3. Does it return correct data structure?

### DuckDB Schema (Splits Table)

**Expected Columns** (from completion report):
```sql
CREATE TABLE splits (
    activity_id INTEGER,
    split_number INTEGER,  -- OR index INTEGER?
    distance REAL,
    pace_seconds_per_km REAL,
    heart_rate REAL,
    cadence REAL,
    power REAL,
    stride_length REAL,
    ground_contact_time REAL,
    vertical_oscillation REAL,
    vertical_ratio REAL,
    elevation_gain REAL,
    elevation_loss REAL,
    intensity_type TEXT,  -- For interval runs
    PRIMARY KEY (activity_id, split_number)
);
```

**Key Fields for Mermaid**:
- `split_number` (or `index`) → x_axis_labels
- `pace_seconds_per_km` → pace_data
- `heart_rate` → heart_rate_data
- `power` → power_data (optional)

---

## 設計

### Investigation Phases

#### Phase 1: Data Validation (30 minutes)

**Step 1.1: Check Splits in DuckDB**
```python
# Test: Do splits exist for test activity?
import duckdb

conn = duckdb.connect("data/database/garmin_performance.duckdb", read_only=True)

# Check splits for test activity
result = conn.execute("""
    SELECT split_number, pace_seconds_per_km, heart_rate, power
    FROM splits
    WHERE activity_id = 20625808856
    ORDER BY split_number
""").fetchall()

print(f"Found {len(result)} splits")
if result:
    print(f"First split: {result[0]}")
    print(f"Last split: {result[-1]}")
else:
    print("NO SPLITS FOUND IN DATABASE")

conn.close()
```

**Expected Output**:
```
Found 7 splits
First split: (1, 398.0, 128.0, 215.0)
Last split: (7, 404.0, 151.0, 227.0)
```

**If NO SPLITS**: Root cause found → Need to investigate splits insertion in `GarminDBWriter`

**Step 1.2: Check _load_splits() Method**
```bash
# Find _load_splits method in Worker
cd /home/yamakii/workspace/claude_workspace/garmin-performance-analysis
grep -n "def _load_splits" tools/reporting/report_generator_worker.py

# If not found, search for how splits are loaded
grep -n "splits" tools/reporting/report_generator_worker.py | grep -E "(load|fetch|query)"
```

**Expected**: Method exists and queries DuckDB

**If NOT FOUND**: Need to create `_load_splits()` method

#### Phase 2: Debug Splits Loading (1-2 hours)

**Scenario A: _load_splits() Exists but Returns Empty**

```python
# Add logging to debug
def _load_splits(self, activity_id: int) -> list:
    """Load splits from DuckDB."""
    logger.info(f"Loading splits for activity {activity_id}")

    result = self.db_reader.get_splits(activity_id)  # Hypothetical
    logger.info(f"Loaded {len(result)} splits")

    if not result:
        logger.warning(f"No splits found for activity {activity_id}")
        return []

    # Convert to required format
    splits = []
    for split in result:
        splits.append({
            "index": split.split_number,  # ← Check column name
            "pace_seconds_per_km": split.pace_seconds_per_km,
            "heart_rate": split.heart_rate,
            "power": split.power,
            # ... (other fields)
        })

    logger.info(f"Formatted {len(splits)} splits")
    return splits
```

**Debug Points**:
1. Check if `db_reader.get_splits()` returns data
2. Check column names (split_number vs index)
3. Check data types (ensure pace/HR are floats, not None)

**Scenario B: _load_splits() Doesn't Exist**

**Solution**: Create method based on MCP tool pattern

```python
def _load_splits(self, activity_id: int) -> list:
    """Load splits from DuckDB.

    Returns:
        List of dicts with index, pace_seconds_per_km, heart_rate, power, etc.
    """
    try:
        conn = duckdb.connect(self.db_path, read_only=True)

        result = conn.execute("""
            SELECT
                split_number AS index,
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
            ORDER BY split_number
        """, [activity_id]).fetchall()

        if not result:
            logger.warning(f"No splits found for activity {activity_id}")
            return []

        # Convert to dict format
        splits = []
        for row in result:
            splits.append({
                "index": row[0],
                "pace_seconds_per_km": row[1],
                "pace_formatted": self._format_pace(row[1]) if row[1] else "N/A",
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

    finally:
        if conn:
            conn.close()
```

**Scenario C: Splits Loaded but Missing Fields**

```python
# Debug: Check what fields are in splits
def _generate_mermaid_data(self, splits: list) -> dict:
    """Generate mermaid graph data from splits."""
    if not splits or len(splits) == 0:
        logger.warning("No splits provided to _generate_mermaid_data")
        return None

    # DEBUG: Log first split to check structure
    logger.debug(f"First split structure: {splits[0].keys()}")

    # Check for required fields
    required_fields = ["pace_seconds_per_km", "heart_rate"]
    missing_fields = [f for f in required_fields if f not in splits[0]]
    if missing_fields:
        logger.error(f"Missing required fields in splits: {missing_fields}")
        return None

    # ... (rest of method)
```

#### Phase 3: Fix and Test (1 hour)

**Step 3.1: Apply Fix**
Based on Phase 2 findings:
- If `_load_splits()` missing → Create method
- If query wrong → Fix SQL query
- If column names wrong → Update field mapping
- If data types wrong → Add type conversion

**Step 3.2: Verify with Test Activity**
```python
# Test script
from tools.reporting.report_generator_worker import ReportGeneratorWorker

worker = ReportGeneratorWorker()

# Load performance data
context = worker.load_performance_data(20625808856)

print(f"Splits loaded: {len(context.get('splits', []))} items")
print(f"Mermaid data: {context.get('mermaid_data')}")

if context["mermaid_data"]:
    print("✅ Mermaid graph data generated successfully")
    print(f"  X-axis: {context['mermaid_data']['x_axis_labels']}")
    print(f"  Pace data: {context['mermaid_data']['pace_data']}")
    print(f"  HR data: {context['mermaid_data']['heart_rate_data']}")
else:
    print("❌ Mermaid graph data is None")
```

**Step 3.3: Generate Report and Verify**
```bash
# Generate report
uv run python -c "
from tools.reporting.report_generator_worker import ReportGeneratorWorker
worker = ReportGeneratorWorker()
result = worker.generate_report(activity_id=20625808856)
print(f'Report: {result[\"report_path\"]}')
"

# Check for Mermaid graph
grep -A 10 "### ペース・心拍" /path/to/report.md | grep -E "(mermaid|グラフデータ)"
```

**Expected**: Should see Mermaid graph, NOT "グラフデータがありません"

---

## 実装フェーズ

### Phase 1: Investigation (30-60 minutes)

**Tasks**:
1. Run DuckDB query to check splits data
2. Find `_load_splits()` method in Worker
3. Add debug logging to trace data flow
4. Identify root cause (missing method, wrong query, field mismatch)

**Deliverable**: Investigation notes with root cause

---

### Phase 2: Fix Implementation (1-2 hours)

**Tasks**:
1. Implement fix based on root cause
2. Add unit tests for `_load_splits()` (if created/modified)
3. Update `_generate_mermaid_data()` if needed

**Deliverable**: Working splits loading + Mermaid data generation

---

### Phase 3: Testing and Validation (1 hour)

**Tasks**:
1. Unit tests for splits loading
2. Integration test for Mermaid graph in report
3. Test with multiple activities (base run, interval run)
4. Visual verification in GitHub markdown preview

**Deliverable**: All tests passing + visual confirmation

---

## テスト計画

### Unit Tests

```python
# tests/reporting/test_splits_loading.py
def test_load_splits_success():
    """Splits loaded successfully from DuckDB."""
    worker = ReportGeneratorWorker()
    splits = worker._load_splits(activity_id=20625808856)

    assert len(splits) > 0
    assert splits[0]["index"] == 1
    assert "pace_seconds_per_km" in splits[0]
    assert "heart_rate" in splits[0]

def test_load_splits_activity_not_found():
    """Graceful handling when activity has no splits."""
    worker = ReportGeneratorWorker()
    splits = worker._load_splits(activity_id=99999999)

    assert splits == []

def test_mermaid_data_generation():
    """Mermaid data generated from valid splits."""
    worker = ReportGeneratorWorker()
    splits = [
        {"index": 1, "pace_seconds_per_km": 398, "heart_rate": 128, "power": 215},
        {"index": 2, "pace_seconds_per_km": 403, "heart_rate": 145, "power": 225},
    ]

    mermaid_data = worker._generate_mermaid_data(splits)

    assert mermaid_data is not None
    assert mermaid_data["x_axis_labels"] == ["1", "2"]
    assert mermaid_data["pace_data"] == [398, 403]
    assert mermaid_data["heart_rate_data"] == [128, 145]
    assert mermaid_data["power_data"] == [215, 225]
```

### Integration Tests

```python
# tests/reporting/test_mermaid_graph_integration.py
@pytest.mark.integration
def test_mermaid_graph_in_report():
    """Mermaid graph appears in generated report."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    with open(result["report_path"]) as f:
        report = f.read()

    # Should have Mermaid graph (NOT fallback message)
    assert "```mermaid" in report
    assert "xychart-beta" in report
    assert "x-axis" in report
    assert "line" in report

    # Should NOT show fallback
    assert "グラフデータがありません" not in report

@pytest.mark.integration
@pytest.mark.parametrize("activity_id", [
    20625808856,  # Base run sample
    20744768051,  # Threshold run
])
def test_mermaid_graph_multiple_activities(activity_id):
    """Mermaid graph works for multiple activities."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=activity_id)

    with open(result["report_path"]) as f:
        report = f.read()

    assert "```mermaid" in report
    assert "グラフデータがありません" not in report
```

### Manual Tests
- [ ] Generate report for activity 20625808856
- [ ] Verify Mermaid graph appears (not "グラフデータがありません")
- [ ] Open report in GitHub markdown preview
- [ ] Check graph renders correctly (pace and HR lines visible)
- [ ] Test with interval run (power line should appear if show_physiological)

---

## 受け入れ基準

### Functional Requirements
- [ ] Mermaid graphs appear in reports for activities with splits data
- [ ] Graphs show pace and heart rate lines
- [ ] Graphs show power line for tempo/interval runs (if power data available)
- [ ] Dynamic Y-axis ranges calculated correctly
- [ ] Clear error message if splits genuinely missing from database

### Quality Requirements
- [ ] All unit tests pass (3 tests)
- [ ] All integration tests pass (2+ tests)
- [ ] Pre-commit hooks pass (Black, Ruff, Mypy)
- [ ] Logging includes helpful debug information

### Documentation Requirements
- [ ] Investigation notes document root cause
- [ ] Inline comments explain splits loading logic
- [ ] Completion report includes before/after comparison

### Backward Compatibility
- [ ] Graceful fallback still works (if no splits, show "グラフデータがありません")
- [ ] No changes to template (only Worker modification)
- [ ] No changes to DuckDB schema

---

## リスクと対策

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Splits not in database** | Critical | Low | Check splits insertion in `GarminDBWriter`, regenerate if needed |
| **Wrong column names** | High | Medium | Verify schema with `PRAGMA table_info(splits)` |
| **Data type mismatch** | Medium | Low | Add type conversion in `_load_splits()` |
| **Missing _load_splits() method** | High | Medium | Create method based on MCP tool pattern |
| **Performance issue (large splits)** | Low | Low | Use limit or pagination if needed |

---

## 依存関係

**Depends On**:
- BALANCED Report V2 Complete - Phase 2 (Mermaid framework) ✅ Complete
- DuckDB splits table populated
- `_generate_mermaid_data()` method exists ✅ Complete

**Blocks**:
- None (important feature but not blocking other work)

**Related Projects**:
- `2025-10-25_balanced_report_v2_complete` (parent project - Phase 2)

---

## 参考資料

### Related Files
- `tools/reporting/report_generator_worker.py` - Where fix is needed (line ~245, ~260)
- `tools/reporting/templates/detailed_report.j2` - Template (already complete, line ~299)
- `tools/database/garmin_db_writer.py` - Splits insertion (if needed to investigate)
- `docs/project/_archived/2025-10-25_balanced_report_v2_complete/completion_report.md` - Known limitation #3

### DuckDB Schema Check
```sql
-- Check splits table structure
PRAGMA table_info(splits);

-- Check splits for test activity
SELECT * FROM splits WHERE activity_id = 20625808856 LIMIT 5;

-- Check if splits exist for multiple activities
SELECT activity_id, COUNT(*) as split_count
FROM splits
GROUP BY activity_id
ORDER BY activity_id DESC
LIMIT 10;
```

### MCP Tool Reference (For Splits Loading Pattern)
```python
# Example from mcp__garmin-db__get_splits_pace_hr
@mcp.tool()
def get_splits_pace_hr(activity_id: int, statistics_only: bool = False) -> dict:
    """Get pace and heart rate data from splits."""
    conn = duckdb.connect(DB_PATH, read_only=True)

    result = conn.execute("""
        SELECT split_number, pace_seconds_per_km, heart_rate
        FROM splits
        WHERE activity_id = ?
        ORDER BY split_number
    """, [activity_id]).fetchall()

    # ... (process result)
    return data
```

---

## Next Steps (After Planning Approval)

1. Create GitHub Issue
2. Start Phase 1 (Investigation) - Check DuckDB splits data
3. Create worktree: `git worktree add -b fix/mermaid-graph-data ../garmin-mermaid-fix main`
4. Activate Serena MCP in worktree
5. Execute Phases 2-3 (Fix + Testing)
6. Generate completion report
7. Merge to main

---

*このプランは、BALANCED Report V2 Complete Rewrite の Known Limitation #3 を解決します。*

**作成日**: 2025-10-25
**ステータス**: 計画中（承認待ち）
**推定重要度**: High (Mermaid graphs are core BALANCED feature)
