# 計画: Cadence Column Refactoring

## プロジェクト情報
- **プロジェクト名**: `cadence_column_refactoring`
- **作成日**: `2025-10-19`
- **ステータス**: 計画中
- **GitHub Issue**: [#31](https://github.com/yamakii/garmin-performance-analysis/issues/31)
- **優先度**: Medium
- **推定工数**: 2.5時間

---

## 要件定義

### 目的
Refactor the `time_series_metrics` table to clearly distinguish between single-foot cadence (raw API data) and total cadence (both feet combined), eliminating confusion and manual multiplication requirements when analyzing running data.

### 解決する問題

**Current Issue:**
- `time_series_metrics.cadence` column stores single-foot cadence from Garmin API (`directRunCadence`)
- Other data sources (Garmin Connect web UI, splits table) display total cadence (cadence × 2)
- Users must manually multiply by 2 every time they query the data
- Confusion about which cadence value is being referenced in queries and analysis
- Inconsistency with user expectations (runners typically think in total cadence, e.g., 180 spm)

**Impact:**
- Manual multiplication required in all queries: `SELECT cadence * 2 AS total_cadence FROM time_series_metrics`
- Risk of forgetting to multiply in data analysis (reporting incorrect values)
- Inconsistent column naming between `splits` table (uses total cadence) and `time_series_metrics` (uses single-foot)
- Performance trends analyzer uses `splits_all` for cadence (bypassing time_series_metrics) due to this confusion

**Example Confusion:**
```sql
-- Current (confusing):
SELECT AVG(cadence) FROM time_series_metrics WHERE activity_id = 12345;
-- Returns: 90 spm (single-foot) → User expects 180 spm (total)

-- After refactoring (clear):
SELECT AVG(cadence_total) FROM time_series_metrics WHERE activity_id = 12345;
-- Returns: 180 spm (total) → Matches user expectations
SELECT AVG(cadence_single_foot) FROM time_series_metrics WHERE activity_id = 12345;
-- Returns: 90 spm (single-foot) → Explicitly labeled
```

### ユースケース

1. **Data Analysis Without Manual Multiplication**
   - User queries time_series_metrics for cadence trends
   - System returns total cadence (both feet) directly
   - No manual `* 2` calculation needed

2. **Consistent Cross-Table Queries**
   - User joins time_series_metrics with splits table
   - Both tables use total cadence values
   - No unit conversion mismatch

3. **Raw API Data Preservation**
   - System stores original single-foot cadence from Garmin API
   - Researchers can access raw data if needed
   - Calculated total cadence available for typical use cases

4. **Backward Compatibility During Migration**
   - Existing queries using `cadence` column continue to work (deprecated)
   - New queries use explicit `cadence_total` or `cadence_single_foot`
   - Migration period allows gradual transition

---

## 設計

### アーキテクチャ

**Current State:**
```
Garmin API (directRunCadence: 90 spm) → time_series_metrics.cadence (90 spm)
                                         ↓
                                    User Query: SELECT cadence * 2 AS total_cadence
```

**Target State:**
```
Garmin API (directRunCadence: 90 spm) → time_series_metrics.cadence_single_foot (90 spm)
                                         ↓
                                    INSERT: cadence_total = cadence_single_foot * 2 (180 spm)
                                         ↓
                                    User Query: SELECT cadence_total (180 spm)
```

**Migration Strategy:**
1. **Phase 1:** Add new columns (`cadence_single_foot`, `cadence_total`) alongside existing `cadence`
2. **Phase 2:** Migrate existing data: Copy `cadence` → `cadence_single_foot`, calculate `cadence_total`
3. **Phase 3:** Update insertion logic to populate new columns
4. **Phase 4:** (Future) Deprecate and drop old `cadence` column

**Components Affected:**
- `tools/database/inserters/time_series_metrics.py` - Insertion logic
- `tools/database/db_writer.py` - Schema definition (indirect via inserter)
- `tools/scripts/regenerate_duckdb.py` - Database regeneration
- `servers/garmin_db_server.py` - MCP tool documentation (if any)
- `tests/database/inserters/test_time_series_metrics.py` - Unit tests

### データモデル

**Current Schema:**
```sql
CREATE TABLE time_series_metrics (
    activity_id BIGINT NOT NULL,
    seq_no INTEGER NOT NULL,
    timestamp_s INTEGER NOT NULL,
    ...
    cadence DOUBLE,  -- Single-foot cadence (90 spm)
    ...
    PRIMARY KEY (activity_id, seq_no)
)
```

**Target Schema (Phase 1):**
```sql
CREATE TABLE time_series_metrics (
    activity_id BIGINT NOT NULL,
    seq_no INTEGER NOT NULL,
    timestamp_s INTEGER NOT NULL,
    ...
    cadence DOUBLE,              -- DEPRECATED: Single-foot cadence (keep for backward compat)
    ...
    fractional_cadence DOUBLE,
    double_cadence DOUBLE,
    cadence_single_foot DOUBLE,  -- NEW: Explicit single-foot cadence (90 spm)
    cadence_total DOUBLE,        -- NEW: Total cadence both feet (180 spm)
    PRIMARY KEY (activity_id, seq_no)
)
```

**Column Definitions:**
- `cadence_single_foot DOUBLE` - Raw single-foot cadence from Garmin API (`directRunCadence`)
  - Unit: steps per minute (spm) for one foot
  - Source: Direct mapping from API
  - Typical range: 80-100 spm

- `cadence_total DOUBLE` - Calculated total cadence (both feet)
  - Unit: steps per minute (spm) for both feet
  - Calculation: `cadence_single_foot * 2`
  - Typical range: 160-200 spm
  - Matches user expectations and Garmin Connect UI

- `cadence DOUBLE` - DEPRECATED (backward compatibility only)
  - Will be removed in future version
  - Currently duplicates `cadence_single_foot`
  - Kept during migration period for existing queries

**Alternative Column Names Considered:**
- `cadence_spm_single` vs `cadence_single_foot` → Chose latter (more explicit)
- `cadence_spm_total` vs `cadence_total` → Chose latter (consistent with `cadence_single_foot`)
- `cadence_raw` vs `cadence_single_foot` → Chose latter ("raw" ambiguous)

**Data Migration Plan:**
```sql
-- Step 1: Add new columns (schema migration)
ALTER TABLE time_series_metrics ADD COLUMN cadence_single_foot DOUBLE;
ALTER TABLE time_series_metrics ADD COLUMN cadence_total DOUBLE;

-- Step 2: Migrate existing data
UPDATE time_series_metrics
SET
    cadence_single_foot = cadence,
    cadence_total = cadence * 2
WHERE cadence IS NOT NULL;

-- Step 3: Verify migration
SELECT
    COUNT(*) AS total_rows,
    COUNT(cadence) AS old_cadence_count,
    COUNT(cadence_single_foot) AS new_single_foot_count,
    COUNT(cadence_total) AS new_total_count
FROM time_series_metrics;
```

### API/インターフェース設計

**1. Inserter Changes (tools/database/inserters/time_series_metrics.py)**

**Current Mapping:**
```python
column_spec = [
    ...
    ("directRunCadence", "cadence"),  # Single-foot → cadence
    ...
]
```

**New Mapping:**
```python
column_spec = [
    ...
    ("directRunCadence", "cadence"),              # DEPRECATED: Backward compat
    ("directRunCadence", "cadence_single_foot"),  # NEW: Explicit single-foot
    ...
]

# After metric extraction, calculate total cadence
for seq_no, data_point in enumerate(activity_detail_metrics):
    # ... existing extraction logic ...

    # Extract single-foot cadence
    cadence_single_foot = extracted_values[cadence_single_foot_index]

    # Calculate total cadence
    cadence_total = cadence_single_foot * 2 if cadence_single_foot is not None else None

    # Append to value_tuples
    value_tuples.append((
        activity_id,
        seq_no,
        timestamp_s,
        ...,
        cadence_single_foot,  # Old cadence column (deprecated)
        ...,
        cadence_single_foot,  # New explicit single-foot
        cadence_total,        # New calculated total
    ))
```

**2. Schema Definition (time_series_metrics.py line 123-157)**

**Current:**
```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS time_series_metrics (
        ...
        cadence DOUBLE,
        ...
        double_cadence DOUBLE,
        PRIMARY KEY (activity_id, seq_no)
    )
""")
```

**New:**
```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS time_series_metrics (
        ...
        cadence DOUBLE,              -- DEPRECATED: Use cadence_single_foot
        ...
        double_cadence DOUBLE,
        cadence_single_foot DOUBLE,  -- Explicit single-foot cadence (90 spm)
        cadence_total DOUBLE,        -- Total cadence both feet (180 spm)
        PRIMARY KEY (activity_id, seq_no)
    )
""")
```

**3. Query Interface (No Changes Required)**

MCP tools don't currently expose time_series_metrics cadence directly:
- `analyze_performance_trends()` uses `splits_all` for cadence (not time_series_metrics)
- No MCP tool directly queries `time_series_metrics.cadence`
- Impact: **None** (MCP tools unaffected)

**4. Regeneration Script (regenerate_duckdb.py)**

**No Code Changes Required:**
- Script calls `GarminIngestWorker.process_activity()` which uses updated inserter
- Inserter handles new column population automatically
- Migration handled by: `--delete-db` (complete reset) or manual data update

**Manual Migration Command:**
```bash
# Option 1: Complete regeneration (recommended)
uv run python tools/scripts/regenerate_duckdb.py --delete-db

# Option 2: Selective table regeneration (if implemented)
uv run python tools/scripts/regenerate_duckdb.py --tables time_series_metrics --force
```

---

## 実装フェーズ

### Phase 1: Schema Migration and Insertion Logic

**Branch:** `feature/cadence-column-refactoring`
**Files Modified:**
- `tools/database/inserters/time_series_metrics.py`

**Tasks:**

1. **Add New Columns to Schema (TDD: Red)**
   ```python
   # Test first (test_time_series_metrics.py)
   def test_cadence_columns_exist():
       """Verify new cadence columns in schema."""
       schema = conn.execute("PRAGMA table_info(time_series_metrics)").fetchall()
       column_names = [row[1] for row in schema]

       assert "cadence" in column_names  # Deprecated
       assert "cadence_single_foot" in column_names  # New
       assert "cadence_total" in column_names  # New
   ```

2. **Update Schema Definition (TDD: Green)**
   - Use Serena MCP: `mcp__serena__find_symbol("CREATE TABLE.*time_series_metrics")`
   - Add columns after `double_cadence`:
     ```sql
     cadence_single_foot DOUBLE,
     cadence_total DOUBLE,
     ```

3. **Update Column Mapping (TDD: Red → Green)**
   ```python
   # Test first
   def test_cadence_mapping_includes_new_columns():
       """Verify column_spec includes new cadence columns."""
       column_spec = get_column_spec()  # Extract to testable function

       assert ("directRunCadence", "cadence_single_foot") in column_spec
       # Note: cadence_total calculated, not in column_spec
   ```

4. **Implement Calculation Logic (TDD: Red → Green)**
   - After metric extraction loop, calculate `cadence_total`
   - Insert both `cadence_single_foot` and `cadence_total` into value_tuples
   - Test with real activity data (activity_id: 20721683500)

5. **Refactor for Clarity (TDD: Refactor)**
   - Extract cadence calculation to helper function if complex
   - Add docstring explaining single-foot vs total distinction
   - Update code comments

**Expected Diff:**
```diff
# tools/database/inserters/time_series_metrics.py

         column_spec = [
             ...
-            ("directRunCadence", "cadence"),
+            ("directRunCadence", "cadence"),              # DEPRECATED
+            ("directRunCadence", "cadence_single_foot"),
             ...
         ]

         # Schema definition
         conn.execute("""
             CREATE TABLE IF NOT EXISTS time_series_metrics (
                 ...
                 double_cadence DOUBLE,
+                cadence_single_foot DOUBLE,  -- Explicit single-foot (90 spm)
+                cadence_total DOUBLE,        -- Total both feet (180 spm)
                 PRIMARY KEY (activity_id, seq_no)
             )
         """)

         # Value extraction and calculation
         for seq_no, data_point in enumerate(activity_detail_metrics):
             # ... existing extraction ...

+            # Calculate total cadence from single-foot
+            cadence_single_foot = extracted_values[cadence_single_foot_idx]
+            cadence_total = (
+                cadence_single_foot * 2 if cadence_single_foot is not None else None
+            )
+
             value_tuples.append((
                 activity_id,
                 seq_no,
                 timestamp_s,
                 ...,
+                cadence_single_foot,
+                cadence_total,
             ))
```

### Phase 2: Data Migration

**Tasks:**

1. **Test Migration Strategy (TDD: Red)**
   ```python
   def test_migration_preserves_data():
       """Verify existing cadence data migrated correctly."""
       # Insert with old schema
       insert_time_series_metrics(old_activity, db_path)

       # Run migration (manual SQL or regeneration)
       # ...

       # Verify new columns populated
       result = conn.execute("""
           SELECT cadence, cadence_single_foot, cadence_total
           FROM time_series_metrics
           WHERE activity_id = ? AND seq_no = 0
       """, [activity_id]).fetchone()

       assert result[0] == result[1]  # cadence == cadence_single_foot
       assert result[2] == result[0] * 2  # cadence_total == cadence * 2
   ```

2. **Document Migration Options**
   - **Option A:** Complete database regeneration (`--delete-db`)
     - Pros: Clean, no manual SQL
     - Cons: Time-consuming (100+ activities)
     - Recommended for: Development environment

   - **Option B:** Manual SQL migration
     - Pros: Fast, preserves existing data
     - Cons: Requires SQL expertise
     - Recommended for: Production (if needed)

3. **Execute Migration**
   ```bash
   # Recommended: Complete regeneration
   uv run python tools/scripts/regenerate_duckdb.py --delete-db
   ```

4. **Verify Migration Success**
   ```sql
   -- Check column existence
   PRAGMA table_info(time_series_metrics);

   -- Verify data consistency
   SELECT
       COUNT(*) AS total_rows,
       COUNT(cadence) AS old_cadence_count,
       COUNT(cadence_single_foot) AS single_foot_count,
       COUNT(cadence_total) AS total_count,
       AVG(cadence_total / cadence_single_foot) AS avg_ratio  -- Should be 2.0
   FROM time_series_metrics
   WHERE cadence_single_foot IS NOT NULL;
   ```

### Phase 3: Testing

**Unit Tests (tests/database/inserters/test_time_series_metrics.py):**

1. **test_cadence_columns_exist()**
   - Verify schema includes `cadence_single_foot` and `cadence_total`
   - Assert column types are DOUBLE
   - Verify old `cadence` column still exists (backward compat)

2. **test_cadence_single_foot_extraction()**
   - Mock `directRunCadence` with value 90
   - Insert time series metrics
   - Query: `SELECT cadence_single_foot WHERE seq_no = 0`
   - Assert: 90 (raw API value)

3. **test_cadence_total_calculation()**
   - Mock `directRunCadence` with value 90
   - Insert time series metrics
   - Query: `SELECT cadence_total WHERE seq_no = 0`
   - Assert: 180 (90 * 2)

4. **test_cadence_null_handling()**
   - Mock `directRunCadence` as None (missing data)
   - Insert time series metrics
   - Query: `SELECT cadence_single_foot, cadence_total WHERE seq_no = 0`
   - Assert: Both are None (no crash, graceful handling)

5. **test_backward_compatibility()**
   - Insert with new logic
   - Query old column: `SELECT cadence WHERE seq_no = 0`
   - Assert: Still returns single-foot value (90 spm)
   - Verify existing queries don't break

**Integration Tests (tests/integration/test_cadence_migration.py - new):**

1. **test_real_activity_insertion()**
   - Use real activity file: `/home/yamakii/garmin_data/data/raw/activity/20721683500/activity_details.json`
   - Insert with new inserter logic
   - Query first 10 rows with cadence data
   - Verify:
     - `cadence_single_foot` in range 80-100
     - `cadence_total` = `cadence_single_foot * 2`
     - `cadence_total` in range 160-200 (typical running cadence)

2. **test_regeneration_consistency()**
   - Delete test database
   - Regenerate single activity with new logic
   - Compare cadence_total values with manual calculation
   - Verify: No data loss, calculations correct

3. **test_cross_table_consistency()**
   - Query splits table cadence (total cadence)
   - Query time_series_metrics cadence_total
   - Compare averages per split
   - Verify: Similar values (within measurement error)

**Performance Tests (tests/performance/test_cadence_insertion.py - optional):**

1. **test_insertion_performance_overhead()**
   - Measure insertion time before refactoring
   - Measure insertion time after refactoring
   - Assert: Overhead <5% (calculation trivial: multiplication)

2. **test_query_performance()**
   - Query `SELECT AVG(cadence_total)` from 1000+ rows
   - Assert: Query time <100ms (no index needed for AVG)

### Phase 4: Documentation and Cleanup

**Files to Update:**

1. **CLAUDE.md** - Schema documentation
   ```diff
   **DuckDB Schema:**
   - time_series_metrics: 26 metrics × 1000-2000 rows/activity
     - Core metrics: timestamp_s, heart_rate, speed, pace
   -   - Cadence: Single-foot cadence from API (multiply by 2 for total)
   +   - Cadence: cadence_total (both feet, 160-200 spm), cadence_single_foot (raw API, 80-100 spm)
     - Form metrics: GCT, VO, VR
   ```

2. **tools/database/inserters/time_series_metrics.py** - Code comments
   ```python
   # Column mapping: API key → DuckDB column
   # Note: directRunCadence is single-foot cadence (e.g., 90 spm)
   #       We store both raw (cadence_single_foot) and calculated total (cadence_total)
   ("directRunCadence", "cadence_single_foot"),  # Raw single-foot cadence
   # cadence_total calculated as: cadence_single_foot * 2 (inserted separately)
   ```

3. **Migration Notes (completion_report.md)**
   - Document migration command
   - List affected queries (if any)
   - Deprecation timeline for `cadence` column

**Deprecation Plan (Future Phase):**
```python
# Phase 5 (Future): Remove deprecated cadence column
# Steps:
# 1. Grep codebase for "SELECT.*cadence" (not cadence_total/single_foot)
# 2. Update all queries to use explicit cadence_total or cadence_single_foot
# 3. Remove "cadence DOUBLE" from schema
# 4. Update column_spec to remove ("directRunCadence", "cadence") mapping
# Timeline: 3-6 months after Phase 4 completion
```

---

## 影響分析

### Affected Components

**1. Database Schema:**
- ✅ time_series_metrics table (2 new columns added)
- ❌ splits table (no changes - already uses total cadence)
- ❌ Other tables (no cadence columns)

**2. Insertion Code:**
- ✅ `tools/database/inserters/time_series_metrics.py` (mapping + calculation logic)
- ❌ `tools/database/inserters/splits.py` (uses different cadence source)
- ❌ `tools/database/db_writer.py` (indirect, calls inserter)

**3. Query Code:**
- ❌ `tools/rag/queries/trends.py` (uses `splits_all` for cadence, not time_series_metrics)
- ❌ `tools/database/readers/*.py` (no direct time_series_metrics cadence queries found)
- ❌ `servers/garmin_db_server.py` (no MCP tools expose time_series_metrics cadence)

**4. Scripts:**
- ✅ `tools/scripts/regenerate_duckdb.py` (regeneration triggers new insertion logic)
- ❌ `tools/scripts/bulk_fetch_raw_data.py` (no changes - API fetching only)

**5. Tests:**
- ✅ `tests/database/inserters/test_time_series_metrics.py` (update assertions)
- ✅ New: `tests/integration/test_cadence_migration.py` (migration verification)
- ❌ Other test files (no time_series_metrics cadence dependencies)

**6. MCP Tools:**
- ❌ **No impact** - MCP tools don't query time_series_metrics.cadence
- Note: `analyze_performance_trends` uses `splits` table cadence (already total)

### Risk Assessment

**Risk 1: Data Loss During Migration**
- **Probability:** Very Low
- **Impact:** High
- **Mitigation:**
  - Use `--delete-db` for clean regeneration (raw data preserved)
  - Test migration on sample activity first
  - Backup database before manual SQL migration
- **Rollback:** Regenerate from raw data (no API calls needed)

**Risk 2: Backward Compatibility Break**
- **Probability:** Low
- **Impact:** Medium
- **Mitigation:**
  - Keep old `cadence` column during migration period
  - Grep codebase for existing queries: `SELECT.*cadence` (found 1 test query)
  - Update test to use new columns explicitly
- **Detection:** Integration tests fail if backward compat broken

**Risk 3: Calculation Error (cadence_total)**
- **Probability:** Very Low
- **Impact:** Medium
- **Mitigation:**
  - Simple calculation: `cadence_single_foot * 2`
  - Unit tests verify calculation with known values
  - Integration test compares with splits table cadence
- **Detection:** Automated tests, manual spot checks

**Risk 4: Performance Degradation**
- **Probability:** Very Low
- **Impact:** Low
- **Mitigation:**
  - Multiplication is O(1), negligible overhead
  - No additional queries or joins required
  - Performance test verifies <5% overhead
- **Measurement:** Benchmark insertion time before/after

**Risk 5: Incomplete Migration**
- **Probability:** Low (if using manual SQL)
- **Impact:** Medium
- **Mitigation:**
  - Prefer `--delete-db` regeneration (automatic, complete)
  - If manual SQL: Verify row counts match
  - Check for NULL values in new columns
- **Detection:** SQL verification queries (see Phase 2)

### Breaking Changes

**None Expected:**
- Old `cadence` column preserved (deprecated but functional)
- No external APIs exposed (internal database schema)
- MCP tools unaffected (don't use time_series_metrics.cadence)
- Existing queries continue to work during migration period

**Deprecation Notice:**
```python
# tools/database/inserters/time_series_metrics.py
# WARNING: The `cadence` column is DEPRECATED and will be removed in a future version.
# Use `cadence_single_foot` (raw API value) or `cadence_total` (both feet) instead.
# Migration timeline: 6 months from 2025-10-19 (target removal: 2025-04-19)
```

---

## テスト計画

### Unit Tests

**File:** `tests/database/inserters/test_time_series_metrics.py`

- [ ] **test_cadence_columns_exist()**
  - Verify schema includes `cadence_single_foot` and `cadence_total`
  - Assert both are DOUBLE type
  - Confirm old `cadence` still exists

- [ ] **test_cadence_single_foot_extraction()**
  - Mock `directRunCadence = 90`
  - Insert and query `cadence_single_foot`
  - Assert: 90 (unchanged from API)

- [ ] **test_cadence_total_calculation()**
  - Mock `directRunCadence = 90`
  - Insert and query `cadence_total`
  - Assert: 180 (90 * 2)

- [ ] **test_cadence_null_handling()**
  - Mock `directRunCadence = None`
  - Insert and query both cadence columns
  - Assert: Both are None (no crash)

- [ ] **test_cadence_backward_compatibility()**
  - Insert with new logic
  - Query old `cadence` column
  - Assert: Returns single-foot value (90)

- [ ] **test_column_count()**
  - Count columns in time_series_metrics
  - Assert: 28 columns (26 old + 2 new)

### Integration Tests

**File:** `tests/integration/test_cadence_migration.py` (new)

- [ ] **test_real_activity_insertion()**
  - Load: `activity/20721683500/activity_details.json`
  - Insert with new inserter
  - Query first 10 cadence rows
  - Assert:
    - `cadence_single_foot` in [80, 100]
    - `cadence_total = cadence_single_foot * 2`
    - `cadence_total` in [160, 200]

- [ ] **test_regeneration_consistency()**
  - Delete temp database
  - Regenerate single activity
  - Compare new vs old cadence values
  - Assert: cadence_total = old_cadence * 2

- [ ] **test_cross_table_consistency()**
  - Query splits.cadence (total)
  - Query time_series_metrics.cadence_total
  - Compare averages per split window
  - Assert: Difference <5% (measurement variance)

- [ ] **test_migration_completeness()**
  - Insert 3 activities with varying cadence data
  - Verify all rows have cadence_total populated
  - Check: `COUNT(cadence_total) = COUNT(cadence_single_foot)`

### Performance Tests

**File:** `tests/performance/test_cadence_insertion_performance.py` (optional)

- [ ] **test_insertion_overhead()**
  - Measure: Insertion time for 1000 rows (old schema)
  - Measure: Insertion time for 1000 rows (new schema)
  - Assert: Overhead <5% (<50ms for 1000 rows)

- [ ] **test_query_performance()**
  - Insert 2000 rows with cadence data
  - Query: `SELECT AVG(cadence_total) FROM time_series_metrics`
  - Assert: Query time <100ms

### Manual Testing Checklist

- [ ] **Schema Verification:**
  - [ ] Run `PRAGMA table_info(time_series_metrics)`
  - [ ] Verify 28 columns exist
  - [ ] Confirm `cadence_single_foot` and `cadence_total` are DOUBLE

- [ ] **Data Verification:**
  - [ ] Query 10 random activities
  - [ ] Spot check: `cadence_total = cadence_single_foot * 2`
  - [ ] Check typical ranges (single-foot: 80-100, total: 160-200)

- [ ] **Regeneration Test:**
  - [ ] Backup production database
  - [ ] Run: `uv run python tools/scripts/regenerate_duckdb.py --delete-db`
  - [ ] Verify: No errors during regeneration
  - [ ] Compare: Row counts before/after (should match)

- [ ] **Code Quality:**
  - [ ] Run: `uv run black .`
  - [ ] Run: `uv run ruff check .`
  - [ ] Run: `uv run mypy .`
  - [ ] Run: `uv run pytest`
  - [ ] Run: `uv run pre-commit run --all-files`

---

## 受け入れ基準

### Functional Requirements

- [ ] New columns `cadence_single_foot` and `cadence_total` added to time_series_metrics schema
- [ ] `cadence_single_foot` stores raw API value (single-foot cadence, e.g., 90 spm)
- [ ] `cadence_total` calculates and stores both-feet cadence (`cadence_single_foot * 2`)
- [ ] Old `cadence` column preserved for backward compatibility (deprecated)
- [ ] All existing activities migrated to new schema (via regeneration or manual SQL)
- [ ] Sample queries return expected values:
  - `SELECT AVG(cadence_single_foot)` ≈ 85-95 spm
  - `SELECT AVG(cadence_total)` ≈ 170-190 spm

### Code Quality

- [ ] All unit tests pass (`uv run pytest -m unit`)
- [ ] All integration tests pass (`uv run pytest -m integration`)
- [ ] Code coverage ≥80% for modified code
- [ ] `uv run black .` - No formatting issues
- [ ] `uv run ruff check .` - No linting errors
- [ ] `uv run mypy .` - No type errors
- [ ] Pre-commit hooks pass

### Documentation

- [ ] CLAUDE.md updated: Cadence description clarified (single-foot vs total)
- [ ] Code comments added explaining calculation logic
- [ ] Deprecation notice for old `cadence` column documented
- [ ] completion_report.md generated with migration instructions
- [ ] Schema changes documented in planning.md (this document)

### Testing

- [ ] 6 unit tests implemented and passing
- [ ] 4 integration tests implemented and passing
- [ ] Manual testing checklist completed
- [ ] Performance overhead verified <5%
- [ ] Cross-table consistency verified (splits vs time_series_metrics)

### Git Workflow

- [ ] Planning committed to main branch
- [ ] Implementation in feature branch (worktree)
- [ ] Commits follow Conventional Commits format
- [ ] All commits include co-author tag
- [ ] PR created with completion_report.md
- [ ] Merged to main, worktree removed

### Data Integrity

- [ ] No data loss during migration
- [ ] All activities have cadence_total populated (where cadence exists)
- [ ] Calculation correctness verified: `cadence_total = cadence_single_foot * 2`
- [ ] NULL values handled gracefully (no crashes)
- [ ] Backward compatibility maintained (old queries still work)

---

## 成功メトリクス

### Quantitative Metrics

- **Test Coverage:** ≥80% for time_series_metrics.py
- **Migration Time:** <10 minutes for full database regeneration (100+ activities)
- **Performance Overhead:** <5% insertion time increase
- **Data Consistency:** 100% of rows with cadence have correct cadence_total (= cadence_single_foot * 2)
- **Implementation Time:** ≤3 hours (target: 2.5 hours)

### Qualitative Metrics

- Code review approval with no major issues
- Clear distinction between single-foot and total cadence in queries
- No confusion about which cadence value is being used
- Documentation sufficient for future developers to understand schema
- Serena MCP successfully used for symbol-based editing

---

## 参考資料

### Current Implementation

- **Inserter:** `tools/database/inserters/time_series_metrics.py` (lines 17-281)
- **Schema Definition:** `tools/database/inserters/time_series_metrics.py` (lines 123-157)
- **Column Mapping:** `tools/database/inserters/time_series_metrics.py` (lines 88-109)
- **Regeneration Script:** `tools/scripts/regenerate_duckdb.py`

### Related Code

- **Splits Inserter:** `tools/database/inserters/splits.py` (uses total cadence from different source)
- **Performance Trends:** `tools/rag/queries/trends.py` (uses splits_all for cadence, not time_series_metrics)
- **MCP Server:** `servers/garmin_db_server.py` (cadence exposed via analyze_performance_trends from splits)

### Test Examples

- **Existing Tests:** `tests/database/inserters/test_time_series_metrics.py`
- **Integration Pattern:** `tests/integration/test_*_insertion.py`
- **Real Data Location:** `/home/yamakii/garmin_data/data/raw/activity/20721683500/`

### Garmin API Documentation

- **directRunCadence:** Single-foot cadence in steps per minute
- **directDoubleCadence:** Exists but purpose unclear (investigate if needed)
- **directFractionalCadence:** Sub-step precision (not used in this refactoring)

### Similar Projects

- **Body Composition Table Support:** `docs/project/2025-10-18_body_composition_table_support/`
  - Similar pattern: Add missing columns to existing table
  - Migration via `--delete-db` regeneration
  - TDD approach with unit + integration tests

---

## Next Steps

### Immediate Actions (Planning Phase)

1. ✅ Create planning.md (this document)
2. ⬜ Create GitHub Issue with planning.md content
3. ⬜ User review and approval
4. ⬜ Create worktree for implementation

### Handoff to tdd-implementer

After planning approval:
1. Create worktree: `git worktree add -b feature/cadence-column-refactoring ../garmin-cadence-refactoring main`
2. Activate Serena MCP: `mcp__serena__activate_project("/absolute/path/to/worktree")`
3. Execute Phase 1: Schema migration and insertion logic (TDD)
4. Execute Phase 2: Data migration (regeneration)
5. Execute Phase 3: Testing (unit + integration)
6. Execute Phase 4: Documentation updates
7. Generate completion_report.md
8. Create PR and merge to main

### Long-term Enhancements (Out of Scope)

- **Phase 5: Deprecate old `cadence` column**
  - Timeline: 6 months after Phase 4 completion
  - Tasks: Grep all queries, update to use explicit columns, drop old column

- **Investigate directDoubleCadence**
  - Purpose unclear from API documentation
  - May be alternative calculation method
  - Low priority (current refactoring sufficient)

- **MCP Tool Enhancement**
  - Add `get_time_series_cadence(activity_id)` tool
  - Return both single-foot and total cadence time series
  - Use case: Detailed cadence variability analysis

---

## Appendix: Data Analysis

### Sample Activity Data (20721683500)

**Expected Values:**
- Single-foot cadence: ~90 spm (API value)
- Total cadence: ~180 spm (calculated)
- Typical range: 80-100 spm (single), 160-200 spm (total)

### Query Examples

**Before Refactoring (Confusing):**
```sql
-- User query: What's my average cadence?
SELECT AVG(cadence) FROM time_series_metrics WHERE activity_id = 20721683500;
-- Result: 90 spm (user expects 180 spm!) ❌ Confusing
```

**After Refactoring (Clear):**
```sql
-- User query: What's my average total cadence?
SELECT AVG(cadence_total) FROM time_series_metrics WHERE activity_id = 20721683500;
-- Result: 180 spm ✅ Matches expectation

-- Research query: What's the raw API single-foot value?
SELECT AVG(cadence_single_foot) FROM time_series_metrics WHERE activity_id = 20721683500;
-- Result: 90 spm ✅ Explicitly labeled as single-foot
```

### Migration Verification Query

```sql
-- After migration, verify all data consistent
SELECT
    activity_id,
    COUNT(*) AS total_rows,
    COUNT(cadence) AS old_cadence_count,
    COUNT(cadence_single_foot) AS single_foot_count,
    COUNT(cadence_total) AS total_count,
    AVG(cadence) AS avg_old_cadence,
    AVG(cadence_single_foot) AS avg_single_foot,
    AVG(cadence_total) AS avg_total,
    AVG(cadence_total / NULLIF(cadence_single_foot, 0)) AS avg_ratio  -- Should be 2.0
FROM time_series_metrics
WHERE cadence IS NOT NULL
GROUP BY activity_id
ORDER BY activity_id DESC
LIMIT 10;
```

**Expected Output:**
```
activity_id  | total_rows | old_cadence_count | single_foot_count | total_count | avg_old_cadence | avg_single_foot | avg_total | avg_ratio
-------------|------------|-------------------|-------------------|-------------|-----------------|-----------------|-----------|----------
20721683500  | 1853       | 1853              | 1853              | 1853        | 90.5            | 90.5            | 181.0     | 2.0
...
```

---

**Planning Document Version:** 1.0
**Last Updated:** 2025-10-19
**Status:** Ready for Review
