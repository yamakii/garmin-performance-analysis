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
