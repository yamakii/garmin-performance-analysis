"""Tests for the benchmark output-path resolution (Issue #412)."""

from __future__ import annotations

import pytest

from garmin_mcp.benchmarks.benchmark_export_performance import benchmark_output_path
from garmin_mcp.utils.paths import get_result_dir


@pytest.mark.unit
def test_benchmark_output_path_uses_result_dir() -> None:
    """Benchmark output resolves under the result dir, never under docs/."""
    path = benchmark_output_path()
    result_dir = get_result_dir()

    assert path == result_dir / "benchmarks" / "benchmark_results.json"
    assert path.is_relative_to(result_dir)
    assert "docs" not in path.parts


@pytest.mark.unit
def test_benchmark_output_path_follows_env(monkeypatch, tmp_path) -> None:
    """Output path honors $GARMIN_RESULT_DIR (env-based, not hardcoded)."""
    monkeypatch.setenv("GARMIN_RESULT_DIR", str(tmp_path))
    path = benchmark_output_path()
    assert path == tmp_path / "benchmarks" / "benchmark_results.json"
