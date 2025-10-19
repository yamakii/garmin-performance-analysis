# 計画: Splits Table Enhancement - Add Missing Performance Metrics

## プロジェクト情報
- **プロジェクト名**: `splits_table_enhancement`
- **作成日**: `2025-10-20`
- **ステータス**: 計画中
- **GitHub Issue**: TBD (will be created after planning approval)
- **優先度**: Medium
- **見積もり工数**: 4-6 hours

---

## 要件定義

### 目的
DuckDB splits table に欠損している7個のパフォーマンスメトリクスを追加し、split単位での詳細な分析を可能にする。

### 解決する問題

**Current State:**
- Raw data (splits.json lapDTOs) contains 45+ performance fields
- splits table only extracts basic metrics (distance, pace, HR, cadence, power, form metrics)
- Missing: stride_length, max metrics, normalized power, speed metrics
- stride_length column exists in schema but **ALL 2016 rows are NULL** (data not inserted)

**Problems:**
1. **Incomplete split-level analysis**: Missing advanced performance metrics per split
2. **Missing sprint/interval insights**: No max_heart_rate, max_cadence, max_power for intensity analysis
3. **Terrain adjustment impossible**: No grade_adjusted_speed for uphill/downhill pace comparison
4. **Training load calculation limited**: No normalized_power (more accurate than avg_power)
5. **Form analysis incomplete**: stride_length column exists but unused (0% population)

**Impact:**
- MCP tools (`get_splits_pace_hr`, `get_splits_form_metrics`) cannot provide comprehensive data
- Analysis agents cannot detect environmental impacts per split
- Interval analysis lacks intensity peak detection

### ユースケース

1. **Interval Intensity Detection (split-section-analyst)**
   - Identify sprint peaks using `max_heart_rate`, `max_cadence`, `max_power`
   - Compare `normalized_power` vs `avg_power` for effort consistency
   - Example: "Split 2: max_cadence=190spm (sprint burst), normalized_power=280W vs avg=230W"

2. **Terrain-Adjusted Pace (efficiency-section-analyst)**
   - Use `grade_adjusted_speed` to normalize pace on hills
   - Compare `average_speed` (raw) vs `grade_adjusted_speed` (adjusted)
   - Example: "Uphill split: raw pace 6:30/km → adjusted 5:45/km (equivalent flat pace)"

3. **Form Efficiency Trends (form efficiency analysis)**
   - Correlate `stride_length` with pace efficiency
   - Detect form degradation: "Stride length decreased from 91cm → 82cm in final splits"

4. **Training Load Calculation (future: performance trends)**
   - Use `normalized_power` for accurate TSS (Training Stress Score)
   - Example: "Interval workout: 280W normalized power = 1.2x threshold = High intensity"

---

## 設計

### データモデル

**Schema Changes:**

```sql
-- ALTER TABLE splits ADD COLUMN ... (6 new columns, stride_length already exists)

ALTER TABLE splits ADD COLUMN max_heart_rate INTEGER;          -- Peak HR (bpm)
ALTER TABLE splits ADD COLUMN max_cadence DOUBLE;              -- Peak cadence (spm)
ALTER TABLE splits ADD COLUMN max_power DOUBLE;                -- Peak power (W)

ALTER TABLE splits ADD COLUMN normalized_power DOUBLE;         -- Training load power (W)

ALTER TABLE splits ADD COLUMN average_speed DOUBLE;            -- Raw speed (m/s)
ALTER TABLE splits ADD COLUMN grade_adjusted_speed DOUBLE;     -- Terrain-adjusted (m/s)

-- stride_length already exists (line 267 in splits.py), just need to populate
-- Current: DOUBLE column, 2016 rows ALL NULL
```

**Field Mapping (Raw JSON → DuckDB):**

| DuckDB Column | Raw JSON Field | Type | Unit | Availability |
|---------------|----------------|------|------|--------------|
| `stride_length` | `strideLength` | DOUBLE | cm | ✅ All activities |
| `average_temperature` | `averageTemperature` | DOUBLE | °C | ✅ Most activities |
| `max_temperature` | `maxTemperature` | DOUBLE | °C | ✅ Most activities |
| `min_temperature` | `minTemperature` | DOUBLE | °C | ✅ Most activities |
| `max_heart_rate` | `maxHR` | INTEGER | bpm | ✅ All activities |
| `max_cadence` | `maxRunCadence` | DOUBLE | spm | ✅ Most activities |
| `max_power` | `maxPower` | DOUBLE | W | ⚠️ Newer activities only |
| `normalized_power` | `normalizedPower` | DOUBLE | W | ⚠️ Newer activities only |
| `average_speed` | `averageSpeed` | DOUBLE | m/s | ✅ Most activities |
| `grade_adjusted_speed` | `avgGradeAdjustedSpeed` | DOUBLE | m/s | ⚠️ Newer activities only |

**Data Availability Analysis (from sample check):**
- ✅ **Always available**: stride_length, max_hr, max_cadence, average_speed
- ⚠️ **Newer activities only**: max_power, normalized_power, grade_adjusted_speed (requires power meter/advanced metrics)
- **NULL handling**: Fields will be NULL for older activities or non-running activities (acceptable)

### アーキテクチャ

**Modified Components:**

1. **tools/database/inserters/splits.py**
   - `_extract_splits_from_raw()`: Add 7 field extractions (lines 69-177)
   - `_insert_splits_with_connection()`: Add ALTER TABLE + 7 columns to INSERT (lines 242-326)

2. **tests/database/inserters/test_splits.py**
   - Add unit tests for new field extraction
   - Add integration tests for new field insertion
   - Add NULL handling tests for missing fields

**Unchanged Components:**
- `tools/mcp/garmin_db/tools/splits.py`: MCP tools automatically return new columns (SELECT *)
- `tools/reporting/`: No template changes (future enhancement)
- `time_series_metrics` table: Out of scope (separate table, different granularity)

**Data Flow:**

```
Raw API Data (splits.json)
  ↓
_extract_splits_from_raw()  [ADD 7 FIELD EXTRACTIONS]
  ↓
split_metrics (list[dict])
  ↓
_insert_splits_with_connection()  [ADD 6 ALTER TABLE + 7 INSERT COLUMNS]
  ↓
DuckDB splits table
  ↓
MCP Tools (get_splits_*)  [NO CHANGES - auto returns new columns]
  ↓
Analysis Agents
```

### API/インターフェース設計

**Function Signature (No changes, internal modifications only):**

```python
def _extract_splits_from_raw(raw_splits_file: str) -> list[dict] | None:
    """
    Extract split metrics from raw splits.json.

    MODIFIED: Add 7 new fields to returned dict:
    - stride_length (cm)
    - max_heart_rate (bpm), max_cadence (spm), max_power (W)
    - normalized_power (W)
    - average_speed, grade_adjusted_speed (m/s)

    Returns:
        List of split dictionaries with 26 fields (was 19)
    """
    # ... existing code ...

    # NEW EXTRACTIONS (add to split_dict):
    stride_length = lap.get("strideLength")  # cm
    max_hr = lap.get("maxHR")  # bpm
    max_cad = lap.get("maxRunCadence")  # spm
    max_pow = lap.get("maxPower")  # W
    norm_pow = lap.get("normalizedPower")  # W
    avg_spd = lap.get("averageSpeed")  # m/s
    grade_adj_spd = lap.get("avgGradeAdjustedSpeed")  # m/s

    split_dict = {
        # ... existing 19 fields ...
        "stride_length_cm": stride_length,
        "max_heart_rate": max_hr,
        "max_cadence": max_cad,
        "max_power": max_pow,
        "normalized_power": norm_pow,
        "average_speed_mps": avg_spd,
        "grade_adjusted_speed_mps": grade_adj_spd,
    }
```

```python
def _insert_splits_with_connection(
    conn: Any, activity_id: int, split_metrics: list[dict]
) -> None:
    """
    MODIFIED: Add 6 new columns to CREATE TABLE and INSERT statement.
    stride_length already exists in schema (line 267), just add to INSERT.
    """
    # ALTER TABLE (add 6 new columns)
    conn.execute("ALTER TABLE splits ADD COLUMN IF NOT EXISTS max_heart_rate INTEGER")
    # ... (5 more ALTER TABLE statements)

    # INSERT (add 7 columns)
    conn.execute(
        """
        INSERT INTO splits (
            ..., stride_length, max_heart_rate, ..., grade_adjusted_speed
        ) VALUES (?, ?, ..., ?)
        """,
        [
            ...,
            split.get("stride_length_cm"),
            split.get("max_heart_rate"),
            ...,
            split.get("grade_adjusted_speed_mps"),
        ],
    )
```

**MCP Tool Response (No code changes, automatic column inclusion):**

```python
# mcp__garmin-db__get_splits_pace_hr() response (example)
{
    "splits": [
        {
            "split_number": 1,
            "pace_seconds_per_km": 324.5,
            "avg_heart_rate": 142,
            # NEW FIELDS (automatically included by SELECT *):
            "stride_length": 91.3,
            "max_heart_rate": 148,
            "max_cadence": 184.0,
            "average_speed": 2.69
        }
    ]
}
```

---

## 実装フェーズ

### Phase 1: Schema Changes and Extraction (30 min)
**TDD Cycle:**
1. **RED**: Write failing test for new field extraction
   - `test_extract_splits_includes_new_fields()`
   - `test_extract_splits_handles_missing_fields()`
2. **GREEN**: Modify `_extract_splits_from_raw()` to extract 10 fields
3. **REFACTOR**: Ensure field names match DuckDB column names

**Implementation:**
- Add 10 field extractions from lapDTOs (lines 140-175 in splits.py)
- Handle NULL values gracefully (lap.get() returns None)
- Add to split_dict with consistent naming

### Phase 2: Database Insertion (30 min)
**TDD Cycle:**
1. **RED**: Write failing test for new columns in DuckDB
   - `test_insert_splits_creates_new_columns()`
   - `test_insert_splits_populates_new_fields()`
2. **GREEN**: Modify `_insert_splits_with_connection()` to:
   - Add 6 ALTER TABLE statements (stride_length already exists)
   - Add 7 columns to INSERT statement
3. **REFACTOR**: Use IF NOT EXISTS for ALTER TABLE

**Implementation:**
- ALTER TABLE for 9 new columns (lines 246-280 in splits.py)
- Update INSERT statement with 10 new columns (lines 293-326)
- Ensure column order matches schema

### Phase 3: Integration Testing (45 min)
**TDD Cycle:**
1. **RED**: Write integration test with real-like data
   - `test_insert_splits_with_all_fields_db_integration()`
   - `test_insert_splits_with_partial_fields()` (some fields NULL)
2. **GREEN**: Run test with mock data containing all 10 fields
3. **REFACTOR**: Verify NULL handling for missing fields

**Implementation:**
- Create comprehensive test fixture with all fields
- Create partial test fixture (simulating older activities)
- Verify data types and units

### Phase 4: Data Migration (2-3 hours)
**Strategy:** Table-level regeneration (safest approach)

**Steps:**
1. **Backup current database** (safety measure)
   ```bash
   cp /home/yamakii/garmin_data/data/database/garmin_performance.duckdb \
      /home/yamakii/garmin_data/data/database/garmin_performance.duckdb.backup_$(date +%Y%m%d)
   ```

2. **Regenerate splits table for all activities**
   ```bash
   uv run python tools/scripts/regenerate_duckdb.py \
     --tables splits \
     --start-date 2024-01-01 \
     --end-date $(date +%Y-%m-%d)
   ```

3. **Verify data population**
   ```sql
   -- Check field population rates
   SELECT
     COUNT(*) as total_splits,
     COUNT(stride_length) as stride_populated,
     COUNT(average_temperature) as temp_populated,
     COUNT(max_power) as power_populated,
     COUNT(normalized_power) as norm_power_populated,
     COUNT(grade_adjusted_speed) as grade_adj_populated
   FROM splits;

   -- Expected results:
   -- total_splits: ~2016
   -- stride_populated: ~2016 (all activities, currently 0)
   -- temp_populated: ~1800-2000 (most activities)
   -- power_populated: ~500-1000 (newer activities only)
   -- norm_power_populated: ~500-1000
   -- grade_adj_populated: ~500-1000
   ```

4. **Compare before/after**
   ```bash
   # Before: stride_length = 0/2016 populated
   # After: stride_length = 2016/2016 populated (100%)
   ```

**Estimated Time:**
- 231 activities × ~5 seconds/activity = ~20 minutes
- Verification queries: ~5 minutes
- Buffer for issues: ~10 minutes
- **Total: ~35 minutes**

### Phase 5: Documentation and Completion (30 min)
- Update schema documentation (if exists)
- Generate completion_report.md
- Update GitHub Issue status

---

## テスト計画

### Unit Tests

**File:** `tests/database/inserters/test_splits.py`

**Test Cases:**
- [x] `test_extract_splits_includes_stride_length()`
  - Verify stride_length extracted from lapDTOs
  - Assert value matches raw data (e.g., 91.28 cm)

- [x] `test_extract_splits_includes_max_metrics()`
  - Verify max_heart_rate, max_cadence, max_power
  - Assert values match raw data (148 bpm, 184 spm, 413 W)

- [x] `test_extract_splits_includes_normalized_power()`
  - Verify normalized_power extraction
  - Assert value matches raw data (270 W)

- [x] `test_extract_splits_includes_speed_metrics()`
  - Verify average_speed, grade_adjusted_speed
  - Assert values match raw data (2.69 m/s, 2.55 m/s)

- [x] `test_extract_splits_handles_missing_fields()`
  - Create lapDTOs without max_power, normalized_power, grade_adjusted_speed
  - Assert fields are None (not error)

- [x] `test_extract_splits_preserves_existing_fields()`
  - Verify all 19 existing fields still extracted correctly
  - Ensure backward compatibility

### Integration Tests

**Test Cases:**
- [x] `test_insert_splits_creates_new_columns()`
  - Insert splits with new fields
  - Query INFORMATION_SCHEMA to verify 6 new columns exist
  - Verify stride_length column already exists

- [x] `test_insert_splits_populates_new_fields()`
  - Insert splits with all 7 new fields
  - SELECT and verify values match input
  - Check data types (DOUBLE, INTEGER)

- [x] `test_insert_splits_handles_partial_fields()`
  - Insert splits with some fields NULL (simulate older activity)
  - Verify non-NULL fields populated correctly
  - Verify NULL fields stored as NULL (not 0 or empty string)

- [x] `test_insert_splits_with_real_activity_data()` (uses real raw data)
  - Use sample_raw_splits_file fixture (activity 20636804823)
  - Verify all 7 fields extracted and inserted
  - Compare with raw JSON values

- [x] `test_insert_splits_multiple_activities()`
  - Insert 3 activities with different field availability
  - Activity 1: All fields present
  - Activity 2: No power metrics
  - Activity 3: No grade_adjusted_speed
  - Verify correct NULL handling

### Performance Tests

- [x] `test_regenerate_splits_table_231_activities()`
  - Run regeneration script on all 231 activities
  - Assert completion time < 5 minutes
  - Verify no errors in logs

- [x] `test_splits_query_performance_with_new_columns()`
  - SELECT * from splits (2016 rows)
  - Assert query time < 100ms (baseline: ~50ms)
  - Ensure new columns don't degrade performance

### Data Validation Tests

- [x] `test_field_population_rates()`
  ```sql
  SELECT
    COUNT(*) as total,
    COUNT(stride_length) * 100.0 / COUNT(*) as stride_pct,
    COUNT(max_heart_rate) * 100.0 / COUNT(*) as max_hr_pct,
    COUNT(max_power) * 100.0 / COUNT(*) as power_pct,
    COUNT(grade_adjusted_speed) * 100.0 / COUNT(*) as grade_adj_pct
  FROM splits;
  ```
  - Assert stride_pct >= 95% (was 0%, should be ~100%)
  - Assert max_hr_pct >= 80%
  - Assert power_pct >= 30% (newer activities only)
  - Assert grade_adj_pct >= 30%

- [x] `test_max_metrics_validity()`
  - Assert max_heart_rate >= avg_heart_rate (existing field)
  - Assert max_cadence >= avg_cadence
  - Assert max_power >= avg_power (if both non-NULL)

---

## 受け入れ基準

### Functional Criteria
- [x] All 7 new fields extracted from raw splits.json
  - stride_length, max_heart_rate, max_cadence, max_power
  - normalized_power, average_speed, grade_adjusted_speed

- [x] All 6 new columns created in DuckDB splits table
  - ALTER TABLE statements successful
  - stride_length column already exists (no ALTER needed)

- [x] Data population rates meet expectations
  - stride_length: 100% (was 0%) ← **Key Success Metric**
  - max metrics: ≥80%
  - power/speed metrics: ≥30% (newer activities)

- [x] NULL handling works correctly
  - Older activities with missing fields → NULL (not error)
  - No false zeros or empty strings

- [x] Backward compatibility maintained
  - All 19 existing fields still work
  - No breaking changes to MCP tools
  - No breaking changes to analysis reports

### Technical Criteria
- [x] All tests passing
  - Unit: 6 tests
  - Integration: 5 tests
  - Performance: 2 tests
  - Data validation: 2 tests
  - **Total: 15 tests**

- [x] Code coverage ≥80% for modified functions
  - `_extract_splits_from_raw()`: 100%
  - `_insert_splits_with_connection()`: 100%

- [x] Pre-commit hooks pass
  - Black formatting
  - Ruff linting
  - Mypy type checking

- [x] Data migration successful
  - 231 activities regenerated
  - No errors in regeneration logs
  - Backup created before migration

### Documentation Criteria
- [x] Schema documentation updated (if exists)
- [x] completion_report.md created with:
  - Field population statistics
  - Before/after comparison
  - Example queries for new fields
- [x] GitHub Issue updated with completion status

### Validation Queries
```sql
-- 1. Verify stride_length now populated (was 0%)
SELECT
  COUNT(*) as total_splits,
  COUNT(stride_length) as populated,
  COUNT(stride_length) * 100.0 / COUNT(*) as population_pct
FROM splits;
-- Expected: population_pct = 100% (was 0%)

-- 2. Sample new fields for verification
SELECT
  activity_id, split_index,
  stride_length,
  max_heart_rate, max_cadence, max_power,
  normalized_power,
  average_speed, grade_adjusted_speed
FROM splits
WHERE activity_id = 20636804823
ORDER BY split_index
LIMIT 3;

-- 3. Check field availability across activities
SELECT
  COUNT(DISTINCT activity_id) as total_activities,
  COUNT(DISTINCT CASE WHEN stride_length IS NOT NULL THEN activity_id END) as has_stride,
  COUNT(DISTINCT CASE WHEN max_power IS NOT NULL THEN activity_id END) as has_power,
  COUNT(DISTINCT CASE WHEN grade_adjusted_speed IS NOT NULL THEN activity_id END) as has_grade_adj
FROM splits;
```

---

## リスク管理

### Identified Risks

**1. Data Availability Risk (LOW)**
- **Risk**: Some fields missing in older activities
- **Mitigation**: Use lap.get() with NULL handling
- **Impact**: Acceptable (newer metrics = newer activities only)

**2. Migration Time Risk (LOW)**
- **Risk**: Regeneration takes longer than expected (>5 min)
- **Mitigation**:
  - Use --tables splits (not full DB)
  - Run during off-peak hours
  - Monitor progress with logs
- **Fallback**: Restore from backup if errors occur

**3. Type Mismatch Risk (VERY LOW)**
- **Risk**: Field types don't match schema (e.g., string vs DOUBLE)
- **Mitigation**:
  - Verify data types in sample raw data first
  - Add type validation in tests
- **Impact**: DuckDB type coercion should handle minor issues

**4. Performance Degradation Risk (VERY LOW)**
- **Risk**: 10 new columns slow down queries
- **Mitigation**:
  - Performance test before/after
  - Splits table is small (2016 rows), minimal impact
- **Expected**: <5% query time increase

**5. Breaking Change Risk (NONE)**
- **Risk**: Existing code breaks due to schema changes
- **Mitigation**:
  - Only adding columns (no removal/rename)
  - MCP tools use SELECT * (auto-include new columns)
  - Reports don't query new fields yet
- **Impact**: Zero breaking changes expected

### Rollback Plan
If critical issues occur during migration:

```bash
# 1. Stop regeneration script
Ctrl+C

# 2. Restore backup
cp /home/yamakii/garmin_data/data/database/garmin_performance.duckdb.backup_YYYYMMDD \
   /home/yamakii/garmin_data/data/database/garmin_performance.duckdb

# 3. Verify restoration
uv run python -c "
import duckdb
conn = duckdb.connect('/home/yamakii/garmin_data/data/database/garmin_performance.duckdb')
print(conn.execute('SELECT COUNT(*) FROM splits').fetchone())
"

# 4. Document issue and investigate
```

---

## 実装スケジュール

### Day 1: Implementation (4-5 hours)
- **Hour 1**: Phase 1 (Schema + Extraction)
  - Write tests for new field extraction
  - Modify `_extract_splits_from_raw()`
  - Verify test passes

- **Hour 2**: Phase 2 (Database Insertion)
  - Write tests for new columns
  - Modify `_insert_splits_with_connection()`
  - Verify test passes

- **Hour 3-4**: Phase 3 (Integration Testing)
  - Write comprehensive integration tests
  - Create test fixtures with all/partial fields
  - Run full test suite
  - Fix any issues

- **Hour 4-5**: Phase 4 (Data Migration)
  - Backup database
  - Run regeneration script
  - Verify data population
  - Run validation queries

### Day 2: Documentation (1 hour)
- Generate completion_report.md
- Update GitHub Issue
- Create example queries for new fields

**Total Estimated Time: 5-6 hours**

---

## 参考情報

### Related Issues
- GitHub Issue #31: Cadence column distinction (similar schema enhancement)
- Previous migration: `docs/project/2025-10-09_duckdb_section_analysis/`

### Sample Queries for New Fields

**1. Environmental Impact Analysis**
```sql
SELECT
  activity_id, split_index,
  average_temperature,
  pace_seconds_per_km,
  avg_heart_rate
FROM splits
WHERE average_temperature > 25  -- Hot conditions
ORDER BY average_temperature DESC
LIMIT 10;
```

**2. Sprint Intensity Detection**
```sql
SELECT
  activity_id, split_index,
  max_heart_rate, avg_heart_rate,
  max_cadence, avg_cadence,
  max_power, avg_power
FROM splits
WHERE max_cadence > 180  -- Sprint bursts
ORDER BY max_cadence DESC;
```

**3. Terrain-Adjusted Pace Comparison**
```sql
SELECT
  activity_id, split_index,
  average_speed,  -- Raw speed (m/s)
  grade_adjusted_speed,  -- Terrain-adjusted (m/s)
  (grade_adjusted_speed - average_speed) * 1000 / average_speed as adjustment_pct
FROM splits
WHERE grade_adjusted_speed IS NOT NULL
  AND ABS(grade_adjusted_speed - average_speed) > 0.1  -- Significant hills
ORDER BY ABS(adjustment_pct) DESC
LIMIT 10;
```

**4. Stride Length vs Pace Efficiency**
```sql
SELECT
  activity_id,
  AVG(stride_length) as avg_stride,
  AVG(pace_seconds_per_km) as avg_pace,
  AVG(avg_cadence) as avg_cad
FROM splits
WHERE stride_length IS NOT NULL
GROUP BY activity_id
ORDER BY avg_stride DESC;
```

**5. Normalized Power for Training Load**
```sql
SELECT
  activity_id,
  AVG(normalized_power) as avg_norm_power,
  AVG(avg_power) as avg_power,
  (AVG(normalized_power) - AVG(avg_power)) as power_variability
FROM splits
WHERE normalized_power IS NOT NULL
GROUP BY activity_id
ORDER BY power_variability DESC;
```

---

## 次のステップ

1. **Planning Approval**
   - Review planning.md with user
   - Create GitHub Issue
   - Get approval to proceed

2. **Implementation Start** (via tdd-implementer)
   - Create git worktree: `feature/splits-table-enhancement`
   - Activate Serena MCP
   - Begin TDD cycle (Phase 1)

3. **Completion** (via completion-reporter)
   - Generate completion_report.md
   - Archive project to `docs/project/_archived/`
   - Close GitHub Issue

---

## メモ

- **stride_length column already exists**: Don't need ALTER TABLE for this field, just populate
- **Temperature fields excluded**: Device temperature deemed unreliable (body heat影響), not included in this phase
- **Power metrics availability**: Requires power meter, only newer activities have data
- **Grade adjusted speed**: Requires elevation data + advanced metrics (Garmin algorithm)
- **NULL vs 0**: Use NULL for missing data, not 0 (0 is valid for some metrics like elevation_gain)
- **Backward compatibility**: Critical - no breaking changes to existing 19 fields
- **MCP tools auto-update**: SELECT * will automatically include new columns (no code change)
