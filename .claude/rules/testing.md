# Testing Rules

## CRITICAL: Tests must NEVER depend on real production data.

## Test Types & Markers

- **unit** (`@pytest.mark.unit`): `@pytest.fixture` mocks, no I/O, <100ms
- **integration** (`@pytest.mark.integration`): `pytest-mock` (`mocker.Mock()`), mock DuckDB connections
- **performance** (`@pytest.mark.performance`): Real data OK, but skip if unavailable
- **garmin_api**: External API tests (skipped in CI)

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
