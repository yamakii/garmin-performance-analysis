# 計画: Body Composition Table Support

## プロジェクト情報
- **プロジェクト名**: `body_composition_table_support`
- **作成日**: `2025-10-18`
- **ステータス**: 計画中
- **GitHub Issue**: [#29](https://github.com/yamakii/garmin-performance-analysis/issues/29)
- **優先度**: Medium
- **推定工数**: 1.5時間

---

## 要件定義

### 目的
Add missing `body_composition` table definition to enable storage and analysis of weight/body composition data from Garmin Index smart scale, completing the implementation that already has inserter code but lacks the table schema.

### 解決する問題

**Current Issue:**
- `body_composition` table is referenced in existing code but never created in database
- Runtime errors occur when attempting to insert weight data
- Valid raw data exists (153 measurements from 2020-12-26 to 2025-10-18) but cannot be stored
- Invalid files (20 × 2099-*.json) pollute the raw data directory

**Impact:**
- Weight tracking feature is completely non-functional
- Existing inserter code (`tools/database/inserters/body_composition.py`) cannot be used
- System cannot leverage 5 years of body composition data

**Root Cause:**
- `GarminDBWriter._ensure_tables()` method is missing body_composition table definition
- Table creation was never implemented despite inserter being fully ready

### ユースケース

1. **Daily Weight Tracking**
   - User syncs Garmin Index scale measurements
   - System stores weight, BMI, body fat % in DuckDB
   - Reports can display weight trends over time

2. **Performance Correlation Analysis**
   - Analyze relationship between weight and running pace
   - Identify optimal racing weight
   - Track body composition changes during training cycles

3. **Health Monitoring**
   - Track metabolic age, visceral fat rating
   - Monitor hydration percentage
   - Alert on abnormal BMI trends

4. **Data Cleanup**
   - Remove invalid 2099-*.json files (all point to 2025-10-03)
   - Maintain data integrity with only valid measurements

---

## 設計

### アーキテクチャ

**Existing Components (Already Implemented):**
```
GarminIngestWorker (API) → Raw JSON (weight/*.json) → GarminDBWriter.insert_body_composition() → [MISSING TABLE]
                                                                                                       ↓
                                                                                               DuckDB body_composition
```

**What Needs to be Added:**
- Table definition in `GarminDBWriter._ensure_tables()` method (db_writer.py:30-290)

**No Changes Required:**
- ✅ Inserter: `tools/database/inserters/body_composition.py`
- ✅ Insert method: `GarminDBWriter.insert_body_composition()` (db_writer.py:495-560)
- ✅ Raw data fetching (already working)

### データモデル

**DuckDB Schema:**
```sql
CREATE TABLE IF NOT EXISTS body_composition (
    measurement_id INTEGER PRIMARY KEY,
    date DATE NOT NULL,
    weight_kg DOUBLE,
    body_fat_percentage DOUBLE,
    muscle_mass_kg DOUBLE,
    bone_mass_kg DOUBLE,
    bmi DOUBLE,
    hydration_percentage DOUBLE,
    basal_metabolic_rate INTEGER,
    active_metabolic_rate INTEGER,
    metabolic_age INTEGER,
    visceral_fat_rating INTEGER,
    physique_rating INTEGER,
    measurement_source VARCHAR
)
```

**Schema Design Rationale:**
- `measurement_id`: Primary key from Garmin API (userProfilePK)
- `date`: Measurement date (calendarDate from JSON)
- Metrics: Direct mapping from Garmin Index scale measurements
- `measurement_source`: Device model (e.g., "Index S2")

**Data Validation:**
- All numeric fields nullable (not all scales support all metrics)
- Date must be NOT NULL (required for time-series analysis)
- measurement_id uniqueness enforced (prevent duplicates)

### API/インターフェース設計

**No API Changes Required** - Using existing implementation:

```python
# Existing method in GarminDBWriter (db_writer.py:495-560)
def insert_body_composition(self, weight_data: dict) -> None:
    """
    Insert body composition data from weight/*.json

    Args:
        weight_data: Parsed JSON from Garmin weight measurement

    Raises:
        ValueError: If required fields missing
        duckdb.Error: If table doesn't exist (currently happens!)
    """
    # Implementation already exists
    pass
```

**Only Change Needed:**
```python
# In GarminDBWriter._ensure_tables() method
def _ensure_tables(self) -> None:
    """Create all required tables if they don't exist."""
    # ... existing tables ...

    # ADD THIS (after lactate_threshold, before closing method):
    self.conn.execute("""
        CREATE TABLE IF NOT EXISTS body_composition (
            measurement_id INTEGER PRIMARY KEY,
            date DATE NOT NULL,
            weight_kg DOUBLE,
            body_fat_percentage DOUBLE,
            muscle_mass_kg DOUBLE,
            bone_mass_kg DOUBLE,
            bmi DOUBLE,
            hydration_percentage DOUBLE,
            basal_metabolic_rate INTEGER,
            active_metabolic_rate INTEGER,
            metabolic_age INTEGER,
            visceral_fat_rating INTEGER,
            physique_rating INTEGER,
            measurement_source VARCHAR
        )
    """)
```

### 実装位置

**File:** `tools/database/db_writer.py`
**Method:** `GarminDBWriter._ensure_tables()`
**Line Number:** After line 271 (lactate_threshold table), before line 290 (method end)

**Context:**
```python
# Line 262-271: lactate_threshold table
self.conn.execute("""CREATE TABLE IF NOT EXISTS lactate_threshold ...""")

# INSERT NEW TABLE HERE (line 272+)
self.conn.execute("""CREATE TABLE IF NOT EXISTS body_composition ...""")

# Line 290+: End of _ensure_tables() method
```

---

## 実装フェーズ

### Phase 0: Data Cleanup (Prerequisite)
**Status:** Execute before implementation worktree creation

**Task:** Remove invalid 2099-*.json files
```bash
# Verify files to be deleted (should be 20 files)
find /home/yamakii/garmin_data/data/raw/weight -name "2099-*.json" | wc -l

# Delete invalid files
find /home/yamakii/garmin_data/data/raw/weight -name "2099-*.json" -delete

# Verify remaining valid files (should be 153)
find /home/yamakii/garmin_data/data/raw/weight -name "*.json" ! -size 0 | wc -l
```

**Why First:** Prevents test pollution and ensures only valid data for integration tests.

### Phase 1: Table Schema Implementation
**Branch:** `feature/body-composition-table`
**Files Modified:** `tools/database/db_writer.py`

**Tasks:**
1. Create worktree: `git worktree add -b feature/body-composition-table ../garmin-body-composition main`
2. Activate Serena MCP: `mcp__serena__activate_project("/absolute/path/to/worktree")`
3. Use `mcp__serena__find_symbol("_ensure_tables", "tools/database/db_writer.py")` to locate insertion point
4. Use `mcp__serena__insert_before_symbol()` to add table definition after lactate_threshold
5. Verify syntax with `uv run python -m py_compile tools/database/db_writer.py`

**Expected Diff:**
```diff
# tools/database/db_writer.py

         # Lactate threshold table (existing)
         self.conn.execute("""...""")

+        # Body composition table
+        self.conn.execute("""
+            CREATE TABLE IF NOT EXISTS body_composition (
+                measurement_id INTEGER PRIMARY KEY,
+                ...
+            )
+        """)
+
     def insert_activity(self, activity_data: dict) -> None:
```

### Phase 2: Unit Testing
**Files:** `tests/unit/test_db_writer_schema.py` (new or extend existing)

**Test Cases:**
1. **test_body_composition_table_exists**
   - Create GarminDBWriter instance
   - Verify table exists: `SHOW TABLES` includes 'body_composition'
   - Assert 12 total tables (11 existing + 1 new)

2. **test_body_composition_schema**
   - Query table schema: `PRAGMA table_info(body_composition)`
   - Verify 14 columns with correct types
   - Verify PRIMARY KEY on measurement_id
   - Verify NOT NULL on date column

3. **test_body_composition_constraints**
   - Test unique constraint: Insert same measurement_id twice → Error
   - Test NOT NULL: Insert with NULL date → Error
   - Test nullable metrics: Insert with only weight_kg → Success

**Mock Strategy:**
```python
@pytest.fixture
def temp_db_writer(tmp_path):
    """Temporary database for schema tests."""
    db_path = tmp_path / "test.duckdb"
    writer = GarminDBWriter(str(db_path))
    yield writer
    writer.close()
```

### Phase 3: Integration Testing
**Files:** `tests/integration/test_body_composition_insertion.py` (new)

**Test Cases:**
1. **test_insert_valid_measurement**
   - Load real file: `/home/yamakii/garmin_data/data/raw/weight/2025-10-18.json`
   - Parse with `BodyCompositionInserter.parse()`
   - Insert with `writer.insert_body_composition()`
   - Query: `SELECT * FROM body_composition WHERE date = '2025-10-18'`
   - Assert: measurement_id, weight_kg, bmi populated

2. **test_insert_duplicate_measurement**
   - Insert same measurement twice
   - Verify: Second insert raises DuckDB error or updates existing (check behavior)

3. **test_bulk_insert_valid_files** (Optional)
   - Load all 153 valid files from `/home/yamakii/garmin_data/data/raw/weight/`
   - Bulk insert with progress tracking
   - Verify: 153 rows in database
   - Verify: Date range 2020-12-26 to 2025-10-18

**Test Data Source:**
```python
REAL_WEIGHT_DIR = Path("/home/yamakii/garmin_data/data/raw/weight")

def test_insert_valid_measurement():
    test_file = REAL_WEIGHT_DIR / "2025-10-18.json"
    assert test_file.exists(), "Test requires real data file"

    with open(test_file) as f:
        data = json.load(f)

    # ... test logic ...
```

### Phase 4: Documentation Update
**Files Modified:**
1. `CLAUDE.md` - Update schema documentation
2. `docs/project/2025-10-18_body_composition_table_support/completion_report.md` (generated by completion-reporter)

**CLAUDE.md Changes:**
```diff
 **DuckDB Schema (11 tables):**
+**DuckDB Schema (12 tables):**
 - Metadata: `activities`, `body_composition`
 - Performance: `splits`, `performance_trends`, `time_series_metrics`
 ...
```

---

## テスト計画

### Unit Tests
- [ ] `test_body_composition_table_exists()` - Verify table created in _ensure_tables()
- [ ] `test_body_composition_schema()` - Verify 14 columns, correct types, PRIMARY KEY
- [ ] `test_body_composition_constraints()` - Test unique/NOT NULL constraints
- [ ] `test_table_count()` - Update existing test: assert 12 tables (was 11)

**Target File:** `tests/unit/test_db_writer_schema.py`
**Coverage Goal:** 100% for _ensure_tables() body_composition section

### Integration Tests
- [ ] `test_insert_valid_measurement()` - Insert real 2025-10-18.json, verify data
- [ ] `test_insert_duplicate_measurement()` - Test PRIMARY KEY constraint behavior
- [ ] `test_parse_and_insert_pipeline()` - End-to-end: JSON → Parser → Inserter → Query
- [ ] `test_bulk_insert_153_files()` (Optional) - Performance test with all valid data

**Target File:** `tests/integration/test_body_composition_insertion.py` (new)
**Test Data:** Real files from `/home/yamakii/garmin_data/data/raw/weight/`
**Safety:** Tests use temp databases (`tmp_path`), production data not modified

### Performance Tests
- [ ] `test_bulk_insert_performance()` - Insert 153 measurements in <1 second
- [ ] `test_query_performance()` - Query 5 years of data in <100ms
- [ ] `test_index_efficiency()` - Verify PRIMARY KEY index usage in query plan

**Acceptance Criteria:**
- Bulk insert: >100 rows/second
- Single query: <100ms for date range selection
- Index usage: `EXPLAIN` shows index scan, not full table scan

### Manual Testing Checklist
- [ ] Run data cleanup script: Verify 20 files deleted, 153 remain
- [ ] Create fresh database: Verify table created automatically
- [ ] Insert sample measurement: Verify no errors
- [ ] Query by date: Verify correct data returned
- [ ] Run all tests: `uv run pytest -v`
- [ ] Pre-commit hooks: `uv run pre-commit run --all-files`

---

## 受け入れ基準

### Functional Requirements
- [ ] `body_composition` table created in `_ensure_tables()` method
- [ ] Table schema matches existing `insert_body_composition()` expectations
- [ ] Invalid 2099-*.json files removed (20 files deleted, 153 valid files remain)
- [ ] Sample insertion succeeds with real data (2025-10-18.json)
- [ ] Duplicate insertion handled gracefully (no crashes)

### Code Quality
- [ ] All unit tests pass (`uv run pytest -m unit`)
- [ ] All integration tests pass (`uv run pytest -m integration`)
- [ ] Code coverage ≥80% for modified code
- [ ] `uv run black .` - No formatting issues
- [ ] `uv run ruff check .` - No linting errors
- [ ] `uv run mypy .` - No type errors
- [ ] Pre-commit hooks pass

### Documentation
- [ ] CLAUDE.md updated: "11 tables" → "12 tables"
- [ ] Schema documented in "DuckDB Schema" section
- [ ] completion_report.md generated with test results
- [ ] Code comments added for table creation logic

### Git Workflow
- [ ] Planning committed to main branch
- [ ] Implementation in feature branch (worktree)
- [ ] Commits follow Conventional Commits format
- [ ] PR created with completion_report.md
- [ ] Merged to main, worktree removed

### Data Integrity
- [ ] No production database modifications during development (use temp DBs)
- [ ] Raw data cleanup verified: 153 valid files, 0 invalid files
- [ ] Existing tests still pass (no regression)
- [ ] Database schema backward compatible (existing code unaffected)

---

## リスク管理

### Technical Risks

**Risk 1: Schema Mismatch with Inserter**
- **Probability:** Low
- **Impact:** High (runtime errors)
- **Mitigation:** Use existing inserter code as schema source of truth
- **Detection:** Integration tests with real data

**Risk 2: Invalid Data Cleanup Breaks Tests**
- **Probability:** Very Low
- **Impact:** Medium (test failures)
- **Mitigation:** All tests use temp directories, not production data
- **Verification:** Confirmed in test files - all use `tempfile.TemporaryDirectory()`

**Risk 3: Production Database Corruption**
- **Probability:** Very Low
- **Impact:** Critical
- **Mitigation:**
  - Never use `--delete-db` flag
  - All development in temp databases
  - Integration tests use isolated database files
- **Rollback:** Database schema additions are additive (no data loss)

### Process Risks

**Risk 4: Worktree Conflicts**
- **Probability:** Low
- **Impact:** Low (workflow delay)
- **Mitigation:** Follow strict worktree workflow, remove after merge
- **Recovery:** `git worktree remove --force` if stuck

**Risk 5: Test Data Dependency**
- **Probability:** Medium
- **Impact:** Medium (flaky tests)
- **Mitigation:** Use real data for integration tests, but verify existence first
- **Fallback:** Skip optional bulk test if files missing

---

## 成功メトリクス

### Quantitative Metrics
- **Test Coverage:** ≥80% for db_writer.py
- **Test Execution Time:** <5 seconds for all body_composition tests
- **Data Cleanup:** 20 files deleted, 153 valid files remain
- **Implementation Time:** ≤2 hours (target: 1.5 hours)

### Qualitative Metrics
- Code review approval with no major issues
- Documentation clarity (reviewable by non-experts)
- No regression in existing tests
- Serena MCP successfully used for symbol-based editing

---

## 参考資料

### Existing Implementation
- **Inserter:** `tools/database/inserters/body_composition.py`
- **Insert Method:** `tools/database/db_writer.py:495-560` (`insert_body_composition()`)
- **Table Creation Pattern:** `tools/database/db_writer.py:30-290` (`_ensure_tables()`)

### Data Locations
- **Raw Data:** `/home/yamakii/garmin_data/data/raw/weight/`
- **Valid Files:** 153 measurements (2020-12-26 to 2025-10-18)
- **Invalid Files:** 20 × 2099-*.json (all calendarDate: 2025-10-03)

### Test Examples
- **Schema Tests:** `tests/unit/test_db_writer_schema.py` (existing patterns)
- **Insertion Tests:** `tests/integration/test_*_insertion.py` (existing patterns)

### Related Documentation
- **CLAUDE.md:** DuckDB schema section
- **DEVELOPMENT_PROCESS.md:** TDD workflow, worktree usage
- **docs/templates/planning.md:** This template structure

---

## Next Steps

### Immediate Actions (Planning Phase)
1. ✅ Create planning.md (this document)
2. ⬜ Create GitHub Issue with planning.md content
3. ⬜ User review and approval
4. ⬜ Execute Phase 0: Data cleanup (prerequisite)

### Handoff to tdd-implementer
After planning approval:
1. Create worktree: `feature/body-composition-table`
2. Activate Serena MCP in worktree
3. Execute Phases 1-4 with TDD workflow
4. Generate completion_report.md
5. Create PR and merge to main

### Long-term Enhancements (Out of Scope)
- MCP tool for body composition queries (similar to get_splits_*)
- Weight trend analysis in reports
- Correlation analysis: weight vs performance
- Body composition dashboard visualization

---

## Appendix: Data Analysis

### Valid File Sample (2025-10-18.json)
```json
{
  "userProfilePK": 123456789,
  "calendarDate": "2025-10-18",
  "weight": 70500.0,
  "bmi": 22.5,
  "bodyFat": 15.2,
  "muscleMass": 56800.0,
  "boneMass": 3200.0,
  "bodyWater": 58.3,
  "sourceType": "Index S2"
}
```

### Invalid File Sample (2099-01-01.json)
```json
{
  "userProfilePK": 987654321,
  "calendarDate": "2025-10-03",  // ← Wrong date (filename says 2099-01-01)
  "weight": 70300.0,
  ...
}
```

**All 20 invalid files have same issue:** Filename date (2099-XX-XX) doesn't match calendarDate (2025-10-03).

### File Statistics
```bash
# Total files
find /home/yamakii/garmin_data/data/raw/weight -name "*.json" | wc -l
# Output: 322

# Valid files (non-empty)
find /home/yamakii/garmin_data/data/raw/weight -name "*.json" ! -size 0 | wc -l
# Output: 173

# Invalid 2099 files
find /home/yamakii/garmin_data/data/raw/weight -name "2099-*.json" | wc -l
# Output: 20

# Valid after cleanup: 173 - 20 = 153
```

---

**Planning Document Version:** 1.0
**Last Updated:** 2025-10-18
**Status:** Ready for Review
