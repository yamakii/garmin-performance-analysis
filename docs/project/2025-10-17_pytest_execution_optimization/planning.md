# 計画: Pytest Execution Speed Optimization

## プロジェクト情報
- **プロジェクト名**: `pytest_execution_optimization`
- **作成日**: `2025-10-17`
- **ステータス**: 計画中
- **GitHub Issue**: (To be created)

## 要件定義

### 目的
Optimize pytest execution time from current 40 seconds to under 25 seconds, achieving a 37.5% performance improvement through targeted fixture optimization, test isolation improvements, and intelligent test categorization.

### 解決する問題

**Current Performance Bottlenecks:**
1. **test_phase1_integration.py**: ~5.7s (7 tests × 0.8s per test)
   - Issue: `test_db` fixture creates 500 rows per test with function scope
   - Impact: 500 rows × 7 tests = 3500 unnecessary rows created

2. **test_body_composition.py**: ~6s total execution
   - Issue: Random date generation using time.time() + hashing in fixture
   - Impact: Unnecessary complexity for test isolation

3. **test_time_series_metrics.py**: ~4.4s (performance test)
   - Issue: Intentionally slow test (2000 rows insertion benchmark)
   - Impact: Slows down regular development test runs

4. **test_materialize.py**: ~2s (TTL/cleanup tests)
   - Issue: Tests use actual time.sleep(1.5s) and time.sleep(0.1s) × 4
   - Impact: 1.9s wasted waiting for real time passage

**Total Identified Impact**: ~18.1s of 40s (45% of execution time)

### ユースケース

1. **Developer Workflow Improvement**
   - Developers run pytest during TDD cycles
   - Fast feedback loop required (< 30s target)
   - Slow tests should be optional for quick iterations

2. **CI/CD Pipeline Optimization**
   - GitHub Actions runs full test suite on every PR
   - Faster tests = faster deployment cycles
   - Maintain comprehensive coverage while improving speed

3. **Test Categorization**
   - Performance benchmarks should be separable from functional tests
   - Regular development tests vs. comprehensive validation tests
   - Enable selective test execution without losing coverage

---

## 設計

### アーキテクチャ

**Optimization Strategy - Multi-Phase Approach:**

```
Phase 1: High-Priority Quick Wins (Priority 1-2)
├── 1.1 test_phase1_integration.py fixture scope optimization (~4.8s reduction)
│   └── Change test_db fixture: function → module scope
└── 1.2 test_body_composition.py date fixture simplification (~5s reduction)
    └── Replace random date generation with fixed future date

Phase 2: Medium-Priority Optimizations (Priority 3)
└── 2.1 test_materialize.py time mocking (~2s reduction)
    └── Replace time.sleep() with unittest.mock.patch

Phase 3: Optional Enhancements (Priority 4)
└── 3.1 Slow test markers for selective execution
    └── Add @pytest.mark.slow + pytest configuration

Phase 4: Future Enhancements (Optional)
├── 4.1 Parallel test execution (pytest-xdist)
└── 4.2 Pytest configuration tuning
```

**Expected Performance Progression:**
- Baseline: 40s (593 tests)
- After Phase 1: 30s (25% reduction)
- After Phase 2: 28.5s (29% reduction)
- After Phase 3: 24.1s (40% reduction for regular runs)
- After Phase 4: 12-17s (50-70% reduction with parallelization)

### 実装詳細

#### Phase 1.1: test_phase1_integration.py Fixture Optimization

**File**: `tests/mcp/test_phase1_integration.py:23-58`

**Current Implementation (Function Scope):**
```python
@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test.duckdb"
    # Creates 500 rows EVERY TEST (7 times)
    ...
    yield db_path
    # Cleanup after each test
```

**Optimized Implementation (Module Scope):**
```python
@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    # Create temporary path at module level
    tmp_path = tmp_path_factory.mktemp("data")
    db_path = tmp_path / "test.duckdb"

    # Create DB once, reuse across all 7 tests
    conn = duckdb.connect(str(db_path))
    # ... populate 500 rows ONCE ...
    conn.close()

    yield db_path

    # Cleanup after module completes
    if db_path.exists():
        db_path.unlink()
```

**Impact Analysis:**
- Before: 7 tests × 0.8s = 5.7s
- After: 1 setup × 0.8s + 7 tests × 0.1s = 1.5s
- **Reduction: ~4.2s (73% improvement)**

**Verification Steps:**
1. Run tests individually to verify independence
2. Check for state pollution between tests
3. Confirm cleanup occurs after module completion

#### Phase 1.2: test_body_composition.py Date Fixture Simplification

**File**: `tests/ingest/test_body_composition.py:14-35`

**Current Implementation (Random Date):**
```python
@pytest.fixture
def test_date():
    # Complex random date generation using time.time() + hashing
    timestamp = int(time.time() * 1000000)
    hash_val = hash(timestamp) % 10000
    base_date = datetime(2099, 1, 1)
    days_offset = hash_val
    future_date = base_date + timedelta(days=days_offset)
    return future_date.strftime("%Y-%m-%d")
```

**Optimized Implementation (Fixed Date):**
```python
@pytest.fixture
def test_date():
    """
    Fixed future date for test isolation.
    Using 2099-06-15 ensures no conflict with production data.
    """
    return "2099-06-15"
```

**Impact Analysis:**
- Before: ~6s total test time (includes random date overhead)
- After: ~1s total test time
- **Reduction: ~5s (83% improvement)**

**Risk Assessment:**
- **Low Risk**: Fixed date is sufficient for isolation
- **Benefit**: Deterministic test behavior, easier debugging
- **Trade-off**: None (random dates unnecessary for this use case)

#### Phase 2.1: test_materialize.py Time Mocking

**Files**:
- `tests/mcp/test_materialize.py:104` (test_ttl_expiration)
- `tests/mcp/test_materialize.py:148` (test_cleanup_oldest_views)

**Current Implementation (Real Sleep):**
```python
def test_ttl_expiration(self, test_db):
    result = manager.create_view(query, ttl_seconds=1)
    time.sleep(1.5)  # Wait for TTL expiration
    manager.cleanup_expired_views()
    # Assertions...

def test_cleanup_oldest_views(self, test_db):
    for i in range(5):
        manager.create_view(query, max_views=3)
        time.sleep(0.1)  # Ensure different timestamps
    # Assertions...
```

**Optimized Implementation (Mocked Time):**
```python
from unittest.mock import patch

def test_ttl_expiration(self, test_db):
    with patch('time.time') as mock_time:
        # Initial time
        mock_time.return_value = 1000.0
        result = manager.create_view(query, ttl_seconds=1)

        # Simulate 1.5s passage
        mock_time.return_value = 1001.5
        manager.cleanup_expired_views()
        # Assertions...

def test_cleanup_oldest_views(self, test_db):
    with patch('time.time') as mock_time:
        base_time = 1000.0
        for i in range(5):
            mock_time.return_value = base_time + (i * 0.1)
            manager.create_view(query, max_views=3)
        # Assertions...
```

**Impact Analysis:**
- Before: 1.5s + (0.1s × 4) = 1.9s sleep time
- After: <0.01s (instantaneous time mocking)
- **Reduction: ~2s (100% sleep time elimination)**

**Implementation Notes:**
- Requires patching `time.time` in the module under test
- Verify TTL calculation logic uses time.time() (not datetime.now())
- Test both creation_time and expiration_time calculations

#### Phase 3.1: Slow Test Markers

**Files**:
- `tests/database/inserters/test_time_series_metrics.py:337`
- `pyproject.toml`

**Test Marker Implementation:**
```python
@pytest.mark.performance
@pytest.mark.slow
def test_batch_insert_performance(self, tmp_path):
    """
    Performance benchmark: Insert 2000 rows of time series data.
    This test is intentionally slow - use @pytest.mark.slow to skip in regular runs.
    """
    # ... existing test code ...
```

**Pytest Configuration:**
```toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests (fast, isolated)",
    "integration: Integration tests (moderate speed)",
    "performance: Performance benchmark tests",
    "slow: Slow tests (deselected by default)",
]
# Skip slow tests by default
addopts = "-m 'not slow' --strict-markers"
```

**Usage Examples:**
```bash
# Regular development (skips slow tests)
uv run pytest  # Runs in ~24s instead of ~28.5s

# Full validation (includes slow tests)
uv run pytest -m ""  # Runs all 593 tests in ~28.5s

# Only slow tests
uv run pytest -m slow  # Runs only performance benchmarks

# CI/CD pipeline
uv run pytest -m "not slow"  # Fast PR checks
uv run pytest -m ""  # Full nightly validation
```

**Impact Analysis:**
- Regular runs: Exclude 4.4s performance test
- CI full runs: No change (still run all tests)
- **Development cycle: Additional 4.4s reduction (15% improvement)**

### API/インターフェース設計

**No API changes required** - this is a testing infrastructure optimization project.

**Configuration Changes:**
```toml
# pyproject.toml additions
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselected by default)",
]
addopts = "-m 'not slow' --strict-markers"

# Optional: Add performance profiling
# addopts = "--durations=10 -m 'not slow'"
```

---

## 実装フェーズ

### Phase 1: High-Priority Quick Wins (Target: 10s reduction)
**Expected Duration**: 2-3 hours

#### Phase 1.1: Fixture Scope Optimization
- **Files**: `tests/mcp/test_phase1_integration.py`
- **Changes**:
  - Line 23: Change `@pytest.fixture` → `@pytest.fixture(scope="module")`
  - Line 24: Change `tmp_path` → `tmp_path_factory`
  - Line 25: Add `tmp_path = tmp_path_factory.mktemp("data")`
  - Add module-level cleanup logic
- **Tests**:
  - Run `uv run pytest tests/mcp/test_phase1_integration.py -v`
  - Verify all 7 tests pass
  - Check test independence (no state pollution)
  - Measure execution time improvement

#### Phase 1.2: Date Fixture Simplification
- **Files**: `tests/ingest/test_body_composition.py`
- **Changes**:
  - Lines 14-35: Replace entire fixture with fixed date "2099-06-15"
  - Add docstring explaining isolation strategy
- **Tests**:
  - Run `uv run pytest tests/ingest/test_body_composition.py -v`
  - Verify no date conflicts with production data
  - Measure execution time improvement

**Phase 1 Verification:**
```bash
# Baseline measurement
time uv run pytest --durations=20 > baseline.txt

# After Phase 1 implementation
time uv run pytest --durations=20 > phase1.txt

# Compare results
diff baseline.txt phase1.txt
```

### Phase 2: Medium-Priority Optimizations (Target: 2s reduction)
**Expected Duration**: 3-4 hours

#### Phase 2.1: Time Mocking Implementation
- **Files**: `tests/mcp/test_materialize.py`
- **Changes**:
  - Add `from unittest.mock import patch` import
  - Line 104: Wrap `test_ttl_expiration` with time mock
  - Line 148: Wrap `test_cleanup_oldest_views` with time mock
  - Replace all `time.sleep()` calls with `mock_time.return_value` updates
- **Tests**:
  - Run `uv run pytest tests/mcp/test_materialize.py -v`
  - Verify TTL expiration logic still works correctly
  - Verify cleanup ordering based on timestamps
  - Check for any datetime.now() vs time.time() issues

**Phase 2 Verification:**
```bash
# Measure after Phase 2
time uv run pytest --durations=20 > phase2.txt

# Expected: Total time ~28.5s (11.5s reduction from baseline)
```

### Phase 3: Optional Enhancements (Target: Selective execution)
**Expected Duration**: 1-2 hours

#### Phase 3.1: Slow Test Markers
- **Files**:
  - `tests/database/inserters/test_time_series_metrics.py`
  - `pyproject.toml`
- **Changes**:
  - Add `@pytest.mark.slow` to performance tests
  - Update `pyproject.toml` with marker configuration
  - Add addopts for default exclusion
- **Tests**:
  - Run `uv run pytest` (should skip slow tests)
  - Run `uv run pytest -m ""` (should include all tests)
  - Run `uv run pytest -m slow` (should run only slow tests)
  - Verify CI pipeline configuration

**Phase 3 Verification:**
```bash
# Regular development run
time uv run pytest  # Expected: ~24s

# Full validation run
time uv run pytest -m ""  # Expected: ~28.5s

# Only slow tests
time uv run pytest -m slow  # Expected: ~4.4s
```

### Phase 4: Future Enhancements (Optional)
**Expected Duration**: 2-3 hours

#### Phase 4.1: Parallel Test Execution
- **Dependencies**: Install pytest-xdist
- **Configuration**: Add to pyproject.toml
- **Usage**: `pytest -n auto`
- **Expected Impact**: 30-50% additional reduction (CPU-dependent)

#### Phase 4.2: Pytest Configuration Tuning
- Cache directory optimization
- Test collection improvements
- Minimal plugin loading

---

## テスト計画

### Unit Tests

**Phase 1.1: Fixture Scope Optimization**
- [ ] test_phase1_integration.py - All 7 tests pass with module scope
- [ ] test_phase1_integration.py - No state pollution between tests
- [ ] test_phase1_integration.py - Cleanup occurs after module completion
- [ ] test_phase1_integration.py - tmp_path_factory correctly creates temp directories

**Phase 1.2: Date Fixture Simplification**
- [ ] test_body_composition.py - All tests pass with fixed date "2099-06-15"
- [ ] test_body_composition.py - No date conflicts with production data
- [ ] test_body_composition.py - Test isolation maintained

**Phase 2.1: Time Mocking**
- [ ] test_materialize.py::test_ttl_expiration - TTL logic works with mocked time
- [ ] test_materialize.py::test_cleanup_oldest_views - Timestamp ordering preserved
- [ ] test_materialize.py - All time-dependent tests pass without sleep()

**Phase 3.1: Slow Test Markers**
- [ ] test_time_series_metrics.py - Performance test marked as @pytest.mark.slow
- [ ] pytest.ini configuration correctly excludes slow tests by default
- [ ] Slow tests can be explicitly included with `-m ""`

### Integration Tests

- [ ] Full test suite passes after Phase 1: `uv run pytest`
- [ ] Full test suite passes after Phase 2: `uv run pytest`
- [ ] Test count remains 593 tests (no tests accidentally excluded)
- [ ] All existing markers (unit, integration, performance) still work

**Test Independence Verification:**
```bash
# Run tests in different orders
uv run pytest --random-order
uv run pytest --random-order-seed=12345

# Run tests individually
for test_file in tests/**/*.py; do
    uv run pytest "$test_file" || echo "Failed: $test_file"
done
```

### Performance Tests

**Baseline Measurement (Before Optimization):**
```bash
time uv run pytest --durations=20 > baseline_performance.txt
# Expected: ~40s total, top slowest tests:
# - test_phase1_integration.py: ~5.7s
# - test_body_composition.py: ~6s
# - test_time_series_metrics.py: ~4.4s
# - test_materialize.py: ~2s
```

**Phase 1 Performance Target:**
- [ ] Total execution time ≤ 30s (25% reduction)
- [ ] test_phase1_integration.py ≤ 1.5s (73% improvement)
- [ ] test_body_composition.py ≤ 1s (83% improvement)

**Phase 2 Performance Target:**
- [ ] Total execution time ≤ 28.5s (29% reduction)
- [ ] test_materialize.py ≤ 0.1s (95% improvement)

**Phase 3 Performance Target:**
- [ ] Regular runs (without slow tests) ≤ 24s (40% reduction)
- [ ] Full runs (with slow tests) ≤ 28.5s (maintained)

**Performance Benchmarking Commands:**
```bash
# Detailed timing for top 20 slowest tests
uv run pytest --durations=20

# Per-phase timing comparison
uv run pytest --durations=0 | grep "test_phase1_integration"
uv run pytest --durations=0 | grep "test_body_composition"
uv run pytest --durations=0 | grep "test_materialize"
```

---

## 受け入れ基準

### Performance Criteria
- [ ] **Phase 1 Complete**: pytest execution time ≤ 30s (25% reduction from 40s baseline)
- [ ] **Phase 2 Complete**: pytest execution time ≤ 28.5s (29% reduction from baseline)
- [ ] **Phase 3 Complete**: Regular runs ≤ 24s (40% reduction for development workflow)
- [ ] All 593 tests continue to pass (no test loss)

### Quality Criteria
- [ ] **Test Coverage**: No reduction in code coverage (maintain current levels)
- [ ] **Test Independence**: All tests pass when run individually and in random order
- [ ] **No Flakiness**: Tests produce deterministic results (no random failures)
- [ ] **Code Quality**: Pre-commit hooks pass (Black, Ruff, Mypy)

### Documentation Criteria
- [ ] **CLAUDE.md Updated**: Add pytest optimization notes to "Common Development Commands" section
- [ ] **Slow Test Usage**: Document how to run slow tests separately
- [ ] **CI/CD Guide**: Update with selective test execution examples
- [ ] **Completion Report**: Include before/after performance metrics

### CI/CD Integration
- [ ] GitHub Actions workflow updated (if needed for slow test handling)
- [ ] Pytest markers properly registered in pyproject.toml
- [ ] CI runs full test suite (including slow tests) for comprehensive validation
- [ ] PR checks use fast test subset for quick feedback

### Verification Commands
```bash
# Full test suite validation
uv run pytest  # Should complete in ≤ 24s (Phase 3)

# Coverage check (should maintain current levels)
uv run pytest --cov=tools --cov-report=term-missing

# Code quality checks
uv run black . --check
uv run ruff check .
uv run mypy .

# Test independence verification
uv run pytest --random-order --random-order-seed=42

# Performance profiling
uv run pytest --durations=20 --durations-min=0.1
```

---

## リスク分析

### Phase 1.1: Fixture Scope Optimization
**Risk Level**: Low-Medium

**Potential Issues:**
- Test state pollution if tests modify shared database
- Cleanup failures leaving temp files

**Mitigation:**
- Verify each test reads but doesn't modify shared data
- Add explicit cleanup in module-level teardown
- Run tests in random order to detect dependencies

### Phase 1.2: Date Fixture Simplification
**Risk Level**: Very Low

**Potential Issues:**
- Fixed date conflicts with existing production data

**Mitigation:**
- Use far-future date (2099-06-15) to avoid conflicts
- Add docstring explaining isolation strategy

### Phase 2.1: Time Mocking
**Risk Level**: Medium

**Potential Issues:**
- Complex mocking may miss edge cases
- Code may use datetime.now() instead of time.time()
- Mock cleanup failures affecting other tests

**Mitigation:**
- Thorough testing of TTL expiration logic
- Review code to ensure consistent time source
- Use context managers for automatic mock cleanup

### Phase 3.1: Slow Test Markers
**Risk Level**: Low

**Potential Issues:**
- Developers accidentally skip important tests
- CI configuration misses slow tests

**Mitigation:**
- Clear documentation of marker usage
- CI runs both fast and full test suites
- Add markers to pytest --markers output

---

## 実装スケジュール

**Total Estimated Time**: 8-12 hours

| Phase | Tasks | Estimated Time | Expected Improvement |
|-------|-------|----------------|---------------------|
| Phase 1.1 | Fixture scope optimization | 2-3 hours | 4.8s reduction |
| Phase 1.2 | Date fixture simplification | 1 hour | 5s reduction |
| Phase 2.1 | Time mocking implementation | 3-4 hours | 2s reduction |
| Phase 3.1 | Slow test markers | 1-2 hours | 4.4s reduction (dev runs) |
| Documentation | CLAUDE.md updates | 1 hour | N/A |

**Total Expected Improvement:**
- **Development runs**: 40s → 24s (40% reduction)
- **CI full runs**: 40s → 28.5s (29% reduction)

---

## 参考資料

**Pytest Documentation:**
- [Fixture Scopes](https://docs.pytest.org/en/stable/how-to/fixtures.html#scope-sharing-fixtures-across-classes-modules-packages-or-session)
- [Markers](https://docs.pytest.org/en/stable/how-to/mark.html)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)

**Related Project Files:**
- Baseline performance: Run `pytest --durations=20` before starting
- Test configuration: `pyproject.toml` (pytest.ini_options section)
- CI workflow: `.github/workflows/*.yml` (if applicable)

**Performance Profiling Tools:**
- `pytest-benchmark` (optional for detailed benchmarking)
- `pytest-xdist` (Phase 4 parallel execution)
- `pytest-profiling` (advanced performance analysis)
