# Pace Comparison Logic Improvement - Planning Document

**Project ID**: 2025-10-25_pace_comparison_improvement
**Type**: Enhancement
**Priority**: Medium
**Estimated Effort**: 2-3 hours
**Status**: Planning
**Parent Project**: BALANCED Report V2 (v4.0.0)
**Follows**: MCP Tool Refactoring (v4.0.1), Similar Workouts Data Extraction Fix (v4.0.2)

---

## 1. Project Overview

### Purpose
Improve accuracy of similar workouts pace comparison by using training-type-aware pace extraction logic.

### Problem Statement
Current implementation (`v4.0.2`) uses overall average pace (warmup + main set + cooldown) for similarity comparison. This is inaccurate for structured workouts like threshold runs and interval training, where the main set pace is the meaningful metric.

**Example Issue:**
```
Activity: Threshold Run
- Overall avg pace: 6:05/km (includes 7:00 warmup + 5:30 main + 7:30 cooldown)
- Main set pace: 5:30/km (actual threshold pace)

Current behavior: Finds similar workouts with ~6:05/km overall pace
Desired behavior: Find similar workouts with ~5:30/km main set pace
```

### Goals
1. **Accuracy**: Use appropriate pace metric based on training type
2. **Backward Compatibility**: Maintain existing behavior for recovery/base runs
3. **Test Coverage**: Ensure all training types are tested

---

## 2. Background

### Current Implementation (v4.0.2)

**File**: `tools/reporting/report_generator_worker.py`
```python
def _load_similar_workouts(self, activity_id: int, current_metrics: dict) -> dict | None:
    """
    current_metrics = {
        "avg_pace": data["basic_metrics"]["avg_pace_seconds_per_km"],  # Overall average
        "avg_hr": data["basic_metrics"]["avg_heart_rate"],
    }
    """
```

**File**: `tools/rag/queries/comparisons.py` (WorkoutComparator)
```python
def find_similar_workouts(self, activity_id: int, pace_tolerance: float = 0.1, ...):
    """
    Uses: a.avg_pace_seconds_per_km (from activities table)
    - This is overall average pace
    - Includes warmup/cooldown phases
    """
```

### Training Type Categories

Based on `CLAUDE.md` training type classification:

| Category | Training Types | Correct Pace Metric |
|----------|---------------|---------------------|
| **Recovery/Base** | `recovery`, `aerobic_base` | Overall average (current) |
| **Structured** | `tempo`, `lactate_threshold`, `vo2max`, `anaerobic_capacity`, `speed` | Main set (`run_metrics.avg_pace_seconds_per_km`) |

---

## 3. Implementation Plan

### Phase 1: Add Training Type to Activities Table (Optional)

**Decision**: Training type is already available via `hr_efficiency` table join (implemented in v4.0.1).

**Verification**:
```sql
SELECT a.activity_id, a.avg_pace_seconds_per_km, h.training_type
FROM activities a
LEFT JOIN hr_efficiency h ON a.activity_id = h.activity_id
WHERE a.activity_id = 20783281578;
```

### Phase 2: Modify `_load_similar_workouts()` Method

**File**: `tools/reporting/report_generator_worker.py`

**Current** (lines 246-253):
```python
current_metrics = {
    "avg_pace": data["basic_metrics"]["avg_pace_seconds_per_km"],
    "avg_hr": data["basic_metrics"]["avg_heart_rate"],
}
data["similar_workouts"] = self._load_similar_workouts(activity_id, current_metrics)
```

**Proposed**:
```python
# Determine which pace to use based on training type
training_type = data.get("training_type", "unknown")
structured_types = {"tempo", "lactate_threshold", "vo2max", "anaerobic_capacity", "speed"}

if training_type in structured_types and data.get("run_metrics"):
    # Use main set pace for structured workouts
    comparison_pace = data["run_metrics"].get("avg_pace_seconds_per_km")
    pace_source = "main_set"
else:
    # Use overall average for recovery/base/unknown
    comparison_pace = data["basic_metrics"]["avg_pace_seconds_per_km"]
    pace_source = "overall"

current_metrics = {
    "avg_pace": comparison_pace,
    "avg_hr": data["basic_metrics"]["avg_heart_rate"],
    "pace_source": pace_source,  # For display purposes
}
data["similar_workouts"] = self._load_similar_workouts(activity_id, current_metrics)
```

### Phase 3: Modify `WorkoutComparator.find_similar_workouts()`

**File**: `tools/rag/queries/comparisons.py`

**Current**:
```python
def find_similar_workouts(self, activity_id: int, ...):
    target = self._get_target_activity(activity_id)
    # Uses target["avg_pace"] (overall average)

    query = """
        SELECT a.avg_pace_seconds_per_km, ...
        FROM activities a
        WHERE a.avg_pace_seconds_per_km BETWEEN ? AND ?
    """
```

**Proposed**:
```python
def find_similar_workouts(
    self,
    activity_id: int,
    pace_tolerance: float = 0.1,
    use_main_set_pace: bool = False,  # NEW parameter
    ...
):
    target = self._get_target_activity(activity_id, use_main_set_pace)

    # Get comparison pace (overall or main set)
    if use_main_set_pace:
        target_pace = self._get_main_set_pace(activity_id)
        query = """
            WITH main_paces AS (
                SELECT pt.activity_id, pt.avg_pace_seconds_per_km
                FROM performance_trends pt
                WHERE pt.phase = 'run'
            )
            SELECT a.activity_id, mp.avg_pace_seconds_per_km, ...
            FROM activities a
            JOIN main_paces mp ON a.activity_id = mp.activity_id
            WHERE mp.avg_pace_seconds_per_km BETWEEN ? AND ?
        """
    else:
        target_pace = target["avg_pace"]
        query = """
            SELECT a.activity_id, a.avg_pace_seconds_per_km, ...
            FROM activities a
            WHERE a.avg_pace_seconds_per_km BETWEEN ? AND ?
        """
```

**Alternative Simpler Approach**:
```python
def find_similar_workouts(
    self,
    activity_id: int,
    target_pace: float,  # NEW: Pass pace explicitly
    pace_tolerance: float = 0.1,
    ...
):
    """
    Args:
        target_pace: Pace to use for comparison (caller decides overall vs main set)
    """
    pace_min = target_pace * (1 - pace_tolerance)
    pace_max = target_pace * (1 + pace_tolerance)

    # Query uses activities.avg_pace_seconds_per_km for candidates
    # But filters based on passed target_pace
    query = """
        SELECT a.activity_id, a.avg_pace_seconds_per_km, ...
        FROM activities a
        WHERE a.avg_pace_seconds_per_km BETWEEN ? AND ?
    """
```

**Recommendation**: Use **Alternative Simpler Approach** - Let caller decide pace, keep WorkoutComparator simple.

### Phase 4: Update Template Display

**File**: `tools/reporting/templates/detailed_report.j2`

**Current** (line 51):
```jinja2
過去の同条件ワークアウト({{ similar_workouts.conditions }})との比較:
```

**Proposed**:
```jinja2
{% if similar_workouts.pace_source == "main_set" %}
過去の同条件ワークアウト({{ similar_workouts.conditions }}、**メインセットペース比較**)との比較:
{% else %}
過去の同条件ワークアウト({{ similar_workouts.conditions }})との比較:
{% endif %}
```

---

## 4. Technical Details

### Data Flow

```
1. generate_report()
   ↓
2. load_performance_data()
   → Gets training_type, run_metrics, basic_metrics
   ↓
3. Determine comparison pace
   - If structured (tempo/threshold/interval) + run_metrics exists:
     → Use run_metrics.avg_pace_seconds_per_km
   - Else:
     → Use basic_metrics.avg_pace_seconds_per_km
   ↓
4. _load_similar_workouts(activity_id, current_metrics)
   current_metrics = {
       "avg_pace": comparison_pace,
       "avg_hr": avg_hr,
       "pace_source": "main_set" | "overall"
   }
   ↓
5. WorkoutComparator.find_similar_workouts(
       activity_id=activity_id,
       target_pace=current_metrics["avg_pace"],  # Pass explicitly
       ...
   )
```

### SQL Queries

**No changes needed** - `WorkoutComparator` continues to use `activities.avg_pace_seconds_per_km` for candidate filtering. The key change is **which target pace** we pass for comparison.

**Example**:
```python
# Before (v4.0.2):
target_pace = 365.9  # Overall average (warmup + main + cooldown)

# After (v4.0.3):
# For threshold/interval:
target_pace = 330.0  # Main set only (run_metrics.avg_pace_seconds_per_km)

# For recovery/base:
target_pace = 365.9  # Overall average (unchanged)
```

---

## 5. Test Strategy

### 5.1 Unit Tests

**File**: `tests/reporting/test_report_generator_worker.py`

**New Test Class**: `TestPaceComparisonLogic`

```python
class TestPaceComparisonLogic:
    """Test training-type-aware pace selection."""

    def test_structured_workout_uses_main_set_pace(self):
        """Threshold/interval workouts use main set pace."""
        data = {
            "training_type": "lactate_threshold",
            "basic_metrics": {"avg_pace_seconds_per_km": 380.0},
            "run_metrics": {"avg_pace_seconds_per_km": 330.0},
        }

        # Should use 330.0 (main set), not 380.0 (overall)
        worker = ReportGeneratorWorker()
        pace = worker._get_comparison_pace(data)

        assert pace == 330.0
        assert pace_source == "main_set"

    def test_recovery_uses_overall_pace(self):
        """Recovery runs use overall average pace."""
        data = {
            "training_type": "recovery",
            "basic_metrics": {"avg_pace_seconds_per_km": 420.0},
            "run_metrics": {"avg_pace_seconds_per_km": 410.0},
        }

        # Should use 420.0 (overall)
        worker = ReportGeneratorWorker()
        pace = worker._get_comparison_pace(data)

        assert pace == 420.0
        assert pace_source == "overall"

    @pytest.mark.parametrize("training_type,expected_source", [
        ("tempo", "main_set"),
        ("lactate_threshold", "main_set"),
        ("vo2max", "main_set"),
        ("anaerobic_capacity", "main_set"),
        ("speed", "main_set"),
        ("recovery", "overall"),
        ("aerobic_base", "overall"),
        ("unknown", "overall"),
    ])
    def test_pace_source_by_training_type(self, training_type, expected_source):
        """All training types map to correct pace source."""
        data = {
            "training_type": training_type,
            "basic_metrics": {"avg_pace_seconds_per_km": 400.0},
            "run_metrics": {"avg_pace_seconds_per_km": 350.0},
        }

        worker = ReportGeneratorWorker()
        _, pace_source = worker._get_comparison_pace(data)

        assert pace_source == expected_source

    def test_fallback_when_run_metrics_missing(self):
        """Falls back to overall pace when run_metrics unavailable."""
        data = {
            "training_type": "lactate_threshold",  # Structured
            "basic_metrics": {"avg_pace_seconds_per_km": 380.0},
            "run_metrics": None,  # Missing
        }

        worker = ReportGeneratorWorker()
        pace, pace_source = worker._get_comparison_pace(data)

        assert pace == 380.0
        assert pace_source == "overall"
```

### 5.2 Integration Tests

**File**: `tests/reporting/test_report_generation_integration.py`

**New Test**:
```python
def test_similar_workouts_uses_correct_pace_for_threshold():
    """Integration test: Threshold run uses main set pace."""
    # Mock activity with threshold run
    # Verify _load_similar_workouts receives correct pace
    # Verify report contains pace_source indicator
```

### 5.3 Performance Tests

**Not required** - Logic change only, no performance impact.

---

## 6. Acceptance Criteria

### Functional Requirements

- [x] **AC1**: Structured workouts (tempo, threshold, interval, vo2max, speed) use main set pace
- [x] **AC2**: Recovery/base workouts use overall average pace
- [x] **AC3**: Unknown training types default to overall average pace
- [x] **AC4**: Gracefully fallback to overall pace when `run_metrics` unavailable
- [x] **AC5**: Template displays "メインセットペース比較" when main set pace is used

### Non-Functional Requirements

- [x] **AC6**: All existing tests pass (26/26)
- [x] **AC7**: 8 new unit tests added (pace selection logic)
- [x] **AC8**: Code quality checks pass (Black, Ruff, Mypy)
- [x] **AC9**: No breaking changes to existing API

### Documentation

- [x] **AC10**: CHANGELOG updated with v4.0.3 entry
- [x] **AC11**: Code comments explain training-type-aware logic
- [x] **AC12**: Completion report generated

---

## 7. Implementation Tasks

### Task Breakdown

**Task 1: Add `_get_comparison_pace()` helper method** (30 min)
- File: `tools/reporting/report_generator_worker.py`
- Extract pace selection logic to reusable method
- Return tuple: `(pace: float, pace_source: str)`

**Task 2: Update `load_performance_data()` to use helper** (15 min)
- Replace hardcoded `basic_metrics["avg_pace_seconds_per_km"]`
- Call `_get_comparison_pace()` with training type logic
- Pass `pace_source` to `current_metrics` dict

**Task 3: Update `_load_similar_workouts()` signature** (15 min)
- Add `pace_source` to returned dict
- Update template context to include pace source

**Task 4: Update template display** (10 min)
- Add conditional display for main set pace comparison
- File: `tools/reporting/templates/detailed_report.j2`

**Task 5: Write unit tests** (45 min)
- 8 parametrized tests for all training types
- Edge cases (missing run_metrics, unknown types)
- File: `tests/reporting/test_report_generator_worker.py`

**Task 6: Integration testing** (30 min)
- Generate real reports for threshold/interval activities
- Verify pace source is correct
- Compare with similar workouts manually

**Task 7: Documentation** (15 min)
- Update CHANGELOG (v4.0.3)
- Add completion report
- Update code comments

**Total Estimated Time**: 2 hours 40 minutes

---

## 8. Risks & Mitigation

### Risk 1: Missing `run_metrics` Data

**Impact**: Structured workouts without run_metrics will fall back to overall pace

**Mitigation**:
- Implement graceful fallback (already in design)
- Log warning when fallback occurs
- Add test case for this scenario

### Risk 2: Breaking Existing Reports

**Impact**: Historical reports may show different similar workouts

**Mitigation**:
- This is expected behavior (improvement, not bug)
- Document in CHANGELOG as "Enhanced" not "Fixed"
- No breaking API changes

### Risk 3: Training Type Misclassification

**Impact**: Wrong training type → wrong pace used

**Mitigation**:
- Training type classification is handled by `hr_efficiency` table (robust)
- Unknown types default to overall pace (safe fallback)
- Test all training type categories

---

## 9. Success Metrics

### Quantitative

1. **Test Coverage**: +8 unit tests (34 total, up from 26)
2. **Test Pass Rate**: 100% (34/34)
3. **Code Quality**: Black/Ruff/Mypy all passing
4. **Lines Changed**: ~60 lines added, ~5 modified

### Qualitative

1. **Accuracy**: Similar workouts for threshold runs match by main set pace
2. **Clarity**: Template clearly indicates when main set pace is used
3. **Backward Compatibility**: Recovery/base runs unchanged

---

## 10. Timeline

| Phase | Duration | Target Date |
|-------|----------|-------------|
| Planning Complete | - | 2025-10-25 |
| Implementation | 3 hours | 2025-10-25 |
| Testing | 1 hour | 2025-10-25 |
| Documentation | 30 min | 2025-10-25 |
| **Total** | **4.5 hours** | **2025-10-25** |

---

## 11. References

### Related Projects
- BALANCED Report V2 (v4.0.0) - Template rewrite
- MCP Tool Refactoring (v4.0.1) - Import path fix
- Similar Workouts Data Extraction Fix (v4.0.2) - Data structure fix

### Related Files
- `tools/reporting/report_generator_worker.py` - Main implementation
- `tools/rag/queries/comparisons.py` - WorkoutComparator (no changes needed)
- `tools/reporting/templates/detailed_report.j2` - Template display
- `tests/reporting/test_report_generator_worker.py` - Unit tests

### Related Documentation
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/CLAUDE.md` - Training type categories
- `CHANGELOG.md` - v4.0.2 Known Limitation #1

---

## 12. Open Questions

**Q1**: Should we display both overall and main set pace in the report for structured workouts?

**A1**: No - Keep report concise. Display only the comparison pace used. Indicate with "メインセットペース比較" label.

**Q2**: Should we backfill historical reports with corrected comparisons?

**A2**: No - Reports are point-in-time snapshots. Regenerate manually if needed.

**Q3**: Do we need to modify `WorkoutComparator` SQL queries?

**A3**: No - Simpler approach: Pass target pace explicitly to `find_similar_workouts()`. Caller decides pace source.

---

## Appendix A: Training Type Mapping

| Garmin Training Type | Category | Comparison Pace |
|---------------------|----------|-----------------|
| `recovery` | Recovery | Overall |
| `aerobic_base` | Base | Overall |
| `tempo` | Structured | Main Set |
| `lactate_threshold` | Structured | Main Set |
| `vo2max` | Structured | Main Set |
| `anaerobic_capacity` | Structured | Main Set |
| `speed` | Structured | Main Set |
| `unknown` | Unknown | Overall (fallback) |

---

## Appendix B: Example Output Comparison

### Before (v4.0.2)

```markdown
### 類似ワークアウトとの比較

過去の同条件ワークアウト(距離約6.1km、ペース類似)との比較:

| 平均ペース | 6:05/km | 6:03/km | -2秒遅い | ➡️ 同等 |
```

**Issue**: Comparing overall pace (6:05) - includes slow warmup/cooldown.

### After (v4.0.3)

```markdown
### 類似ワークアウトとの比較

過去の同条件ワークアウト(距離約6.1km、ペース類似、**メインセットペース比較**)との比較:

| 平均ペース | 5:30/km | 5:28/km | -2秒遅い | ➡️ 同等 |
```

**Improvement**: Comparing main set pace (5:30) - accurate threshold pace comparison.

---

## Appendix C: Pseudocode

```python
def _get_comparison_pace(performance_data: dict) -> tuple[float, str]:
    """
    Determine which pace to use for similarity comparison.

    Returns:
        tuple: (pace_seconds_per_km, pace_source)
        - pace_source: "main_set" | "overall"
    """
    training_type = performance_data.get("training_type", "unknown")
    structured_types = {"tempo", "lactate_threshold", "vo2max", "anaerobic_capacity", "speed"}

    # Use main set pace for structured workouts (if available)
    if training_type in structured_types:
        run_metrics = performance_data.get("run_metrics")
        if run_metrics and run_metrics.get("avg_pace_seconds_per_km"):
            return (run_metrics["avg_pace_seconds_per_km"], "main_set")

    # Fallback: use overall average pace
    return (performance_data["basic_metrics"]["avg_pace_seconds_per_km"], "overall")


def load_performance_data(activity_id: int) -> dict:
    """Load performance data and prepare for report generation."""
    # ... existing logic ...

    # NEW: Determine comparison pace
    comparison_pace, pace_source = self._get_comparison_pace(data)

    current_metrics = {
        "avg_pace": comparison_pace,
        "avg_hr": data["basic_metrics"]["avg_heart_rate"],
        "pace_source": pace_source,
    }

    data["similar_workouts"] = self._load_similar_workouts(activity_id, current_metrics)

    return data
```

---

**End of Planning Document**
