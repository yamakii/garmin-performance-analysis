# Testing Rules

## CRITICAL: Tests must NEVER depend on real production data.

## Test Types & Markers

- **unit** (`@pytest.mark.unit`): `@pytest.fixture` mocks, no I/O, <100ms
- **integration** (`@pytest.mark.integration`): `pytest-mock` (`mocker.Mock()`), mock DuckDB connections
- **performance** (`@pytest.mark.performance`): Real data OK, but skip if unavailable
- **garmin_api**: External API tests (skipped in CI)

## CRITICAL: Every test MUST have a pytest marker

- All test classes MUST have a class-level marker: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.performance`, or `@pytest.mark.garmin_api`
- Standalone test functions (not in a class) MUST have a function-level marker
- When adding a new test file, add the marker BEFORE writing any test logic
- Prefer class-level markers over per-method markers (less noise, same effect)
- Mixed marker classes (e.g., unit + integration methods) use per-method markers

**Verification after adding tests:**
```bash
# Must return 0 — no unmarked tests allowed
uv run pytest -m "not unit and not integration and not performance and not slow and not garmin_api" --collect-only -q 2>/dev/null | tail -1
```

## Mock Patterns

```python
@pytest.fixture
def mock_reader_factory(mocker):
    def _create(data):
        reader = mocker.Mock()
        reader.get_section_analysis.return_value = data
        return reader
    return _create

def test_analysis(mock_reader_factory):
    reader = mock_reader_factory({"rating": "****"})
    assert reader.get_section_analysis(12345, "phase")["rating"] == "****"
```

See `docs/testing_guidelines.md` for detailed patterns and examples.

## Test Performance Rules

- **Unit test budget**: Each unit test must complete in <200ms (setup + call). Use `--durations=10` to verify.
- **Fixture scoping**: Read-only fixtures should use `scope="class"` or `scope="module"`.
  - Use `tmp_path_factory.mktemp()` for class/module scope (not `tmp_path`)
- **DB schema initialization**: Use `initialized_db_path` fixture from `inserters/conftest.py` (~0.6ms file copy) instead of `GarminDBWriter()` per test (~50ms DDL).
- **No `GarminDBWriter` in inserter test bodies**: Always use the shared template fixture.
- **Parallel safety**: Tests must not depend on execution order. Use unique `activity_id` per test for DB isolation.

## Test Naming Convention (Issue Traceability)

- Issue Test Plan で指定された `test_xxx` 関数名はそのまま使用する
- 実装中に発見した追加テストは Issue body にも反映する（issue-sync）
- completion-reporter が関数名の exact match で検証する
