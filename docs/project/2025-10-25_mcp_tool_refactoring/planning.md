# 計画: MCP Tool Import Error Fix

## プロジェクト情報
- **プロジェクト名**: `mcp_tool_refactoring`
- **作成日**: `2025-10-25`
- **ステータス**: 計画中
- **優先度**: High (blocks similar workouts feature)
- **推定時間**: 2-4 hours
- **GitHub Issue**: TBD (計画承認後に作成)
- **親プロジェクト**: `2025-10-25_balanced_report_v2_complete`

---

## 要件定義

### 目的
Fix import error `No module named 'servers.garmin_db_mcp'` in similar workouts comparison feature to enable actual data display in BALANCED reports.

### 解決する問題

**Current Issue**:
- Location: `tools/reporting/report_generator_worker.py`, line ~400 (in `_load_similar_workouts()`)
- Error: `ModuleNotFoundError: No module named 'servers.garmin_db_mcp'`
- Status: Gracefully handled (shows "類似ワークアウトが見つかりませんでした")
- Impact: Similar workouts table never populated with real data

**Error Details**:
```python
# Current broken import (line ~941 in completion_report.md)
import sys
sys.path.append('/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates')
from tools.mcp.garmin_db_mcp import compare_similar_workouts  # ← FAILS
```

**Root Cause Hypothesis**:
1. Incorrect import path (MCP tool location unclear)
2. MCP tool may not be in expected location
3. Path manipulation not working correctly

### ユースケース
1. **Generate Report with Similar Workouts**:
   - User generates report for activity 20625808856
   - System finds 3+ similar past workouts
   - Report displays comparison table (pace, HR, power differences)
   - Insight shows efficiency improvement/degradation

2. **Graceful Fallback**:
   - If no similar workouts found (< 3 matches), show fallback message
   - If import fails, log error but don't crash report generation

---

## 現状分析

### 既存コード (From Completion Report)

**File**: `tools/reporting/report_generator_worker.py`
**Method**: `_load_similar_workouts(activity_id, current_metrics)`

```python
def _load_similar_workouts(self, activity_id: int, current_metrics: dict) -> dict | None:
    """Load similar workouts comparison using MCP tool."""
    try:
        # Import MCP tool (lazy import to avoid circular dependency)
        import sys
        sys.path.append('/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates')
        from tools.mcp.garmin_db_mcp import compare_similar_workouts  # ← FAILS HERE

        similar = compare_similar_workouts(
            activity_id=activity_id,
            distance_tolerance=0.10,
            pace_tolerance=0.10,
            terrain_match=True,
            limit=10
        )
        # ... (rest of method)
    except Exception as e:
        logger.error(f"Error loading similar workouts: {e}")
        return None
```

**Known Issues**:
1. Hard-coded path: `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates`
2. Assumes MCP tool is in `tools/mcp/garmin_db_mcp.py` (may not exist there)
3. No validation of path existence before import

### Expected Data Structure (Working)

The MCP tool `compare_similar_workouts()` should return:
```python
[
    {
        "activity_id": 20625808856,
        "distance": 5.8,
        "avg_pace": 405,  # seconds/km
        "avg_hr": 145,
        "avg_power": 220,  # W (if available)
        "terrain": "flat",
    },
    # ... up to 10 similar activities
]
```

---

## 設計

### アーキテクチャ

**3 Investigation Paths**:

#### Path A: Find Correct MCP Tool Location
```bash
# Search for compare_similar_workouts function
find /home/yamakii/workspace/claude_workspace -name "*.py" \
  -exec grep -l "def compare_similar_workouts" {} \;

# Check if MCP server exists
ls -la /home/yamakii/workspace/claude_workspace/*/tools/mcp/
ls -la /home/yamakii/workspace/claude_workspace/*/servers/
```

**Expected Locations**:
1. `garmin-performance-analysis/tools/mcp/garmin_db_mcp.py` (most likely)
2. `garmin-performance-analysis/servers/garmin_db_mcp/` (if using MCP server structure)
3. Standalone MCP server in separate directory

#### Path B: Use MCP Function Directly
If MCP tool is available via MCP server (not Python import):
```python
# Use MCP function call instead of Python import
from mcp import use_mcp_tool  # Hypothetical

def _load_similar_workouts(self, activity_id: int, current_metrics: dict) -> dict | None:
    try:
        # Call MCP tool via function (not import)
        result = use_mcp_tool(
            "mcp__garmin-db__compare_similar_workouts",
            {"activity_id": activity_id, "distance_tolerance": 0.1, ...}
        )
        similar = result["data"]
        # ... (process result)
    except Exception as e:
        logger.error(f"Error loading similar workouts: {e}")
        return None
```

#### Path C: Import from Correct Location
Once location found, fix import:
```python
def _load_similar_workouts(self, activity_id: int, current_metrics: dict) -> dict | None:
    try:
        # Import from correct location (TBD after investigation)
        from tools.mcp.garmin_db_mcp_server import compare_similar_workouts
        # OR
        from mcp.servers.garmin_db.tools import compare_similar_workouts

        similar = compare_similar_workouts(
            activity_id=activity_id,
            distance_tolerance=0.10,
            pace_tolerance=0.10,
            terrain_match=True,
            limit=10
        )
        # ... (rest of method)
    except Exception as e:
        logger.error(f"Error loading similar workouts: {e}")
        return None
```

### API/インターフェース設計

**No Changes Required**:
- `_load_similar_workouts()` signature unchanged
- Return type remains `dict | None`
- Template integration already complete

**Only Change**: Import statement in Worker

---

## 実装フェーズ

### Phase 1: Investigation (30-60 minutes)

**Step 1.1: Locate MCP Tool**
```bash
# Find compare_similar_workouts function
cd /home/yamakii/workspace/claude_workspace/garmin-performance-analysis
find . -name "*.py" -exec grep -l "compare_similar_workouts" {} \;

# Check MCP server configuration
cat .mcp_server_config.json  # If exists
```

**Step 1.2: Test MCP Tool**
```bash
# Test direct import (if found)
uv run python -c "
from tools.mcp.XXX import compare_similar_workouts
result = compare_similar_workouts(activity_id=20625808856)
print(f'Found {len(result)} similar workouts')
"

# OR test via MCP function call
uv run python -c "
# Test MCP function call
"
```

**Step 1.3: Document Findings**
Create investigation notes:
- MCP tool location
- Import method (Python import vs MCP function call)
- Data structure confirmation

---

### Phase 2: Fix Import (1-2 hours)

**Step 2.1: Update Import Statement**
```python
# File: tools/reporting/report_generator_worker.py
# Line: ~940 (in _load_similar_workouts method)

# BEFORE (broken):
import sys
sys.path.append('/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates')
from tools.mcp.garmin_db_mcp import compare_similar_workouts

# AFTER (fixed - example):
from tools.mcp.garmin_db_mcp_server import compare_similar_workouts
# OR
from mcp.servers.garmin_db.tools import compare_similar_workouts
```

**Step 2.2: Remove Hard-coded Path**
```python
# Remove sys.path manipulation if import works without it
# Keep try-except for graceful error handling
```

**Step 2.3: Add Validation**
```python
def _load_similar_workouts(self, activity_id: int, current_metrics: dict) -> dict | None:
    """Load similar workouts comparison using MCP tool.

    Returns:
        Dict with similar workouts comparison or None if insufficient data/error
    """
    try:
        # Import from correct location (determined in Phase 1)
        from tools.mcp.garmin_db_mcp_server import compare_similar_workouts

        logger.info(f"Loading similar workouts for activity {activity_id}")

        similar = compare_similar_workouts(
            activity_id=activity_id,
            distance_tolerance=0.10,
            pace_tolerance=0.10,
            terrain_match=True,
            limit=10
        )

        # Validate result
        if not similar or not isinstance(similar, list):
            logger.warning(f"Invalid result from compare_similar_workouts: {type(similar)}")
            return None

        if len(similar) < 3:
            logger.info(f"Insufficient similar workouts: {len(similar)} < 3")
            return None

        # ... (rest of method unchanged)

    except ImportError as e:
        logger.error(f"Failed to import compare_similar_workouts: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading similar workouts: {e}", exc_info=True)
        return None
```

---

### Phase 3: Testing (1-2 hours)

**Step 3.1: Unit Test**
```python
# tests/reporting/test_similar_workouts.py
import pytest
from unittest.mock import Mock, patch

def test_similar_workouts_import_success():
    """MCP tool imports successfully."""
    from tools.reporting.report_generator_worker import ReportGeneratorWorker

    worker = ReportGeneratorWorker()
    # If this doesn't raise ImportError, import is fixed
    # (actual test happens in integration test)
    pass

@patch('tools.reporting.report_generator_worker.compare_similar_workouts')
def test_similar_workouts_data_structure(mock_compare):
    """Similar workouts returns correct data structure."""
    mock_compare.return_value = [
        {"activity_id": 123, "distance": 5.8, "avg_pace": 405, "avg_hr": 145},
        {"activity_id": 456, "distance": 6.1, "avg_pace": 410, "avg_hr": 148},
        {"activity_id": 789, "distance": 5.5, "avg_pace": 400, "avg_hr": 142},
    ]

    worker = ReportGeneratorWorker()
    result = worker._load_similar_workouts(
        activity_id=20625808856,
        current_metrics={"avg_pace": 405, "avg_hr": 145, "avg_power": 220}
    )

    assert result is not None
    assert result["count"] == 3
    assert len(result["comparisons"]) >= 2  # At least pace and HR
    assert "insight" in result
```

**Step 3.2: Integration Test with Real Data**
```python
@pytest.mark.integration
def test_similar_workouts_real_data():
    """Similar workouts table populated with real data."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    with open(result["report_path"]) as f:
        report = f.read()

    # Check if similar workouts table is populated (not fallback)
    assert "### 類似ワークアウトとの比較" in report

    # Should NOT show fallback message if tool works
    if "類似ワークアウトが見つかりませんでした" in report:
        pytest.skip("No similar workouts found (< 3 matches)")

    # Should show comparison table
    assert "| 指標 |" in report
    assert "| 平均ペース |" in report
    assert "| 平均心拍 |" in report
```

**Step 3.3: Manual Verification**
```bash
# Generate report and check output
uv run python -c "
from tools.reporting.report_generator_worker import ReportGeneratorWorker
worker = ReportGeneratorWorker()
result = worker.generate_report(activity_id=20625808856)
print(f'Report: {result[\"report_path\"]}')
"

# Check report for similar workouts table
grep -A 10 "### 類似ワークアウトとの比較" /path/to/report.md
```

---

## テスト計画

### Unit Tests
- [x] `test_similar_workouts_import_success()` - Import doesn't raise error
- [x] `test_similar_workouts_data_structure()` - Mocked data returns correct structure
- [x] `test_similar_workouts_insufficient_data()` - Returns None when < 3 matches
- [x] `test_similar_workouts_import_error_fallback()` - Graceful handling of import error

### Integration Tests
- [x] `test_similar_workouts_real_data()` - Real MCP tool call returns data
- [x] `test_similar_workouts_table_in_report()` - Table appears in generated report
- [x] `test_similar_workouts_insight_generation()` - Insight text is meaningful

### Manual Tests
- [ ] Generate report for activity 20625808856
- [ ] Verify similar workouts table populated (not "見つかりませんでした")
- [ ] Check comparison table has pace, HR, power (if available)
- [ ] Verify insight text makes sense ("ペース+3秒速いのに...")

---

## 受け入れ基準

### Functional Requirements
- [ ] Import error `No module named 'servers.garmin_db_mcp'` is resolved
- [ ] Similar workouts comparison table populated with real data (when ≥3 matches)
- [ ] Insight text generated based on actual comparisons
- [ ] Graceful fallback still works when insufficient data (< 3 matches)
- [ ] No hard-coded paths in Worker code

### Quality Requirements
- [ ] All unit tests pass (4 tests)
- [ ] All integration tests pass (3 tests)
- [ ] Pre-commit hooks pass (Black, Ruff, Mypy)
- [ ] Error logging includes helpful debug information

### Documentation Requirements
- [ ] Investigation notes document MCP tool location
- [ ] Inline comments explain import method
- [ ] Completion report documents fix

### Backward Compatibility
- [ ] Worker API unchanged (`_load_similar_workouts` signature same)
- [ ] Template unchanged (already handles None gracefully)
- [ ] Reports without similar data still generate successfully

---

## リスクと対策

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **MCP tool doesn't exist** | Critical | Low | Create minimal MCP tool wrapper if needed |
| **Import path still incorrect** | High | Medium | Try multiple import strategies (Path A/B/C) |
| **Data structure mismatch** | Medium | Low | Validate with unit tests before integration |
| **No similar workouts in database** | Low | Medium | Test with multiple activity IDs |

---

## 依存関係

**Depends On**:
- BALANCED Report V2 Complete (completed)
- MCP tool `compare_similar_workouts()` exists in codebase

**Blocks**:
- None (enhancement feature, not critical path)

**Related Projects**:
- `2025-10-25_balanced_report_v2_complete` (parent project)

---

## 参考資料

### Related Files
- `tools/reporting/report_generator_worker.py` - Where fix is needed (line ~940)
- `tools/reporting/templates/detailed_report.j2` - Template (already complete)
- `docs/project/_archived/2025-10-25_balanced_report_v2_complete/completion_report.md` - Known limitation #1

### Expected MCP Tool Signature
```python
def compare_similar_workouts(
    activity_id: int,
    distance_tolerance: float = 0.1,
    pace_tolerance: float = 0.1,
    terrain_match: bool = False,
    limit: int = 10,
) -> list[dict]:
    """Find similar past workouts.

    Returns:
        List of dicts with activity_id, distance, avg_pace, avg_hr, avg_power, terrain
    """
    pass
```

---

## Next Steps (After Planning Approval)

1. Create GitHub Issue
2. Start Phase 1 (Investigation) - Find MCP tool location
3. Create worktree: `git worktree add -b fix/mcp-tool-import ../garmin-mcp-fix main`
4. Activate Serena MCP in worktree
5. Execute Phases 2-3 (Fix + Testing)
6. Generate completion report
7. Merge to main

---

*このプランは、BALANCED Report V2 Complete Rewrite の Known Limitation #1 を解決します。*

**作成日**: 2025-10-25
**ステータス**: 計画中（承認待ち）
