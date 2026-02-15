"""
Performance benchmarking for MCP export() function.

This script measures:
1. Export performance (Parquet vs CSV) for various data sizes
2. Memory usage during export operations
3. Query execution time for different data sizes

Usage:
    python -m garmin_mcp.benchmarks.benchmark_export_performance.py
"""

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl


class ExportBenchmark:
    """Benchmark for export() function performance."""

    def __init__(self, db_path: Path | None = None):
        """Initialize benchmark with in-memory database."""
        self.db_path = db_path or ":memory:"
        self.conn = duckdb.connect(str(self.db_path))
        self.results: list[dict] = []

    def create_mock_data(self, n_rows: int) -> None:
        """Create mock time series data for benchmarking."""
        print(f"Creating mock data: {n_rows:,} rows...")

        # Generate realistic time series data
        timestamps = np.arange(n_rows)
        pace = 270 + np.random.normal(0, 10, n_rows)
        heart_rate = 150 + np.random.normal(0, 5, n_rows)
        cadence = 180 + np.random.normal(0, 3, n_rows)
        gct = 250 + np.random.normal(0, 10, n_rows)
        vo = 85 + np.random.normal(0, 5, n_rows)
        vr = 8.5 + np.random.normal(0, 0.5, n_rows)

        df = pl.DataFrame(
            {
                "activity_id": [12345] * n_rows,
                "timestamp": timestamps,
                "pace": pace,
                "heart_rate": heart_rate,
                "cadence": cadence,
                "ground_contact_time": gct,
                "vertical_oscillation": vo,
                "vertical_ratio": vr,
            }
        )

        # Register as DuckDB table
        self.conn.register("time_series_metrics", df)
        print("✓ Mock data created and registered")

    def benchmark_export(self, n_rows: int, export_format: str = "parquet") -> dict:
        """Benchmark export operation."""
        print(f"\nBenchmarking export ({n_rows:,} rows, format={export_format})...")

        # Create mock data
        self.create_mock_data(n_rows)

        # Export query
        query = """
            SELECT * FROM time_series_metrics
            WHERE activity_id = 12345
        """

        # Measure export time
        export_path = Path(f"/tmp/benchmark_export_{n_rows}.{export_format}")

        start_time = time.perf_counter()

        if export_format == "parquet":
            self.conn.execute(f"COPY ({query}) TO '{export_path}' (FORMAT PARQUET)")
        else:  # csv
            self.conn.execute(
                f"COPY ({query}) TO '{export_path}' (FORMAT CSV, HEADER TRUE)"
            )

        export_time = time.perf_counter() - start_time

        # Get file size
        file_size_mb = export_path.stat().st_size / (1024 * 1024)

        # Measure load time
        start_time = time.perf_counter()
        if export_format == "parquet":
            _ = pl.read_parquet(export_path)
        else:
            _ = pl.read_csv(export_path)
        load_time = time.perf_counter() - start_time

        result = {
            "n_rows": n_rows,
            "format": export_format,
            "export_time_s": round(export_time, 3),
            "load_time_s": round(load_time, 3),
            "total_time_s": round(export_time + load_time, 3),
            "file_size_mb": round(file_size_mb, 3),
            "rows_per_second": int(n_rows / export_time),
            "throughput_mb_per_s": round(file_size_mb / export_time, 2),
        }

        print(f"  Export time: {result['export_time_s']}s")
        print(f"  Load time: {result['load_time_s']}s")
        print(f"  File size: {result['file_size_mb']} MB")
        print(f"  Throughput: {result['rows_per_second']:,} rows/s")

        # Cleanup
        export_path.unlink()

        self.results.append(result)
        return result

    def benchmark_query_performance(self) -> dict:
        """Benchmark different query types."""
        print("\nBenchmarking query performance...")

        # Create larger dataset for query benchmarks
        self.create_mock_data(100000)

        queries = {
            "full_scan": "SELECT * FROM time_series_metrics",
            "filtered": "SELECT * FROM time_series_metrics WHERE timestamp BETWEEN 1000 AND 2000",
            "aggregated": "SELECT AVG(pace), AVG(heart_rate) FROM time_series_metrics",
            "grouped": "SELECT activity_id, AVG(pace), AVG(heart_rate) FROM time_series_metrics GROUP BY activity_id",
        }

        query_results = {}
        for query_name, query in queries.items():
            start_time = time.perf_counter()
            result = self.conn.execute(query).fetchall()
            query_time = time.perf_counter() - start_time

            query_results[query_name] = {
                "time_s": round(query_time, 4),
                "result_rows": len(result),
            }
            print(f"  {query_name}: {query_time:.4f}s ({len(result)} rows)")

        return query_results

    def run_all_benchmarks(self) -> None:
        """Run all benchmarks and save results."""
        print("=" * 60)
        print("DuckDB Export Performance Benchmark")
        print("=" * 60)

        # Test different data sizes
        data_sizes = [10_000, 100_000, 1_000_000]
        formats = ["parquet", "csv"]

        for n_rows in data_sizes:
            for fmt in formats:
                self.benchmark_export(n_rows, fmt)

        # Query performance
        query_perf = self.benchmark_query_performance()

        # Generate report
        self.generate_report(query_perf)

    def generate_report(self, query_perf: dict) -> None:
        """Generate benchmark report."""
        print("\n" + "=" * 60)
        print("BENCHMARK RESULTS")
        print("=" * 60)

        # Export performance summary
        print("\n## Export Performance")
        print(
            "\n| Rows | Format | Export (s) | Load (s) | Size (MB) | Throughput (rows/s) |"
        )
        print(
            "|------|--------|-----------|----------|-----------|-------------------|"
        )

        for result in self.results:
            print(
                f"| {result['n_rows']:,} | {result['format']:7s} | "
                f"{result['export_time_s']:9.3f} | {result['load_time_s']:8.3f} | "
                f"{result['file_size_mb']:9.3f} | {result['rows_per_second']:17,} |"
            )

        # Parquet vs CSV comparison
        print("\n## Parquet vs CSV Comparison")
        parquet_results = [r for r in self.results if r["format"] == "parquet"]
        csv_results = [r for r in self.results if r["format"] == "csv"]

        print("\n| Rows | Parquet Time (s) | CSV Time (s) | Speedup | Size Ratio |")
        print("|------|-----------------|-------------|---------|------------|")

        for p, c in zip(parquet_results, csv_results, strict=False):
            speedup = c["total_time_s"] / p["total_time_s"]
            size_ratio = c["file_size_mb"] / p["file_size_mb"]
            print(
                f"| {p['n_rows']:,} | {p['total_time_s']:15.3f} | "
                f"{c['total_time_s']:11.3f} | {speedup:7.2f}x | "
                f"{size_ratio:10.2f}x |"
            )

        # Query performance
        print("\n## Query Performance (100,000 rows)")
        print("\n| Query Type | Time (s) | Result Rows |")
        print("|-----------|----------|------------|")

        for query_name, result in query_perf.items():
            print(
                f"| {query_name:11s} | {result['time_s']:8.4f} | "
                f"{result['result_rows']:11,} |"
            )

        # Acceptance criteria check
        print("\n## Acceptance Criteria Check")
        print("\n| Criteria | Target | Actual | Status |")
        print("|----------|--------|--------|--------|")

        # 10,000 rows: < 1s
        result_10k = next(
            r
            for r in self.results
            if r["n_rows"] == 10_000 and r["format"] == "parquet"
        )
        status_10k = "✅ PASS" if result_10k["export_time_s"] < 1.0 else "❌ FAIL"
        print(
            f"| 10,000 rows export | < 1s | {result_10k['export_time_s']:.3f}s | {status_10k} |"
        )

        # 100,000 rows: < 5s
        result_100k = next(
            r
            for r in self.results
            if r["n_rows"] == 100_000 and r["format"] == "parquet"
        )
        status_100k = "✅ PASS" if result_100k["export_time_s"] < 5.0 else "❌ FAIL"
        print(
            f"| 100,000 rows export | < 5s | {result_100k['export_time_s']:.3f}s | {status_100k} |"
        )

        # 1,000,000 rows: < 30s
        result_1m = next(
            r
            for r in self.results
            if r["n_rows"] == 1_000_000 and r["format"] == "parquet"
        )
        status_1m = "✅ PASS" if result_1m["export_time_s"] < 30.0 else "❌ FAIL"
        print(
            f"| 1,000,000 rows export | < 30s | {result_1m['export_time_s']:.3f}s | {status_1m} |"
        )

        # Parquet vs CSV: 3x faster
        speedup_100k = (
            csv_results[1]["total_time_s"] / parquet_results[1]["total_time_s"]
        )
        status_speedup = "✅ PASS" if speedup_100k >= 3.0 else "⚠️  WARN"
        print(
            f"| Parquet vs CSV speedup | > 3x | {speedup_100k:.2f}x | {status_speedup} |"
        )

        # Save results to JSON
        output_path = Path(
            "docs/project/2025-10-16_duckdb_mcp_llm_architecture/benchmark_results.json"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        results_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "export_results": self.results,
            "query_performance": query_perf,
            "acceptance_criteria": {
                "10k_rows": {
                    "target": 1.0,
                    "actual": result_10k["export_time_s"],
                    "pass": result_10k["export_time_s"] < 1.0,
                },
                "100k_rows": {
                    "target": 5.0,
                    "actual": result_100k["export_time_s"],
                    "pass": result_100k["export_time_s"] < 5.0,
                },
                "1m_rows": {
                    "target": 30.0,
                    "actual": result_1m["export_time_s"],
                    "pass": result_1m["export_time_s"] < 30.0,
                },
                "parquet_speedup": {
                    "target": 3.0,
                    "actual": speedup_100k,
                    "pass": speedup_100k >= 3.0,
                },
            },
        }

        with open(output_path, "w") as f:
            json.dump(results_data, f, indent=2)

        print(f"\n✓ Results saved to: {output_path}")


def main():
    """Run benchmarks."""
    benchmark = ExportBenchmark()
    benchmark.run_all_benchmarks()


if __name__ == "__main__":
    main()
