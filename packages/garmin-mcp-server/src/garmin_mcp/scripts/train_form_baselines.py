#!/usr/bin/env python3
"""CLI tool for training form baseline models from DuckDB data.

This script trains statistical models (GCT power law, VO/VR linear models)
from historical running data stored in DuckDB, and outputs the trained
model coefficients in JSON format.

Usage:
    uv run python -m garmin_mcp.scripts.train_form_baselines.py --condition flat_road
    uv run python -m garmin_mcp.scripts.train_form_baselines.py --db-path data/database/garmin_performance.duckdb

Output:
    JSON object with trained model coefficients:
    {
        "condition": "flat_road",
        "gct": {"alpha": 5.3, "d": -0.15, "rmse": 5.2, "n_samples": 1250},
        "vo": {"a": 10.2, "b": -2.1, "rmse": 0.8, "n_samples": 1250},
        "vr": {"a": 9.8, "b": -0.45, "rmse": 0.5, "n_samples": 1250}
    }
"""

import argparse
import json
import sys
from pathlib import Path

from garmin_mcp.database.connection import get_connection
from garmin_mcp.form_baseline import trainer, utils
from garmin_mcp.form_baseline.trainer import GCTPowerModel, LinearModel


def main() -> int:
    """Main entry point for CLI tool."""
    parser = argparse.ArgumentParser(
        description="Train form baseline models from DuckDB data"
    )
    parser.add_argument(
        "--condition",
        default="flat_road",
        help="Condition group name (default: flat_road)",
    )
    parser.add_argument(
        "--db-path",
        default="data/database/garmin_performance.duckdb",
        help="Path to DuckDB database (default: data/database/garmin_performance.duckdb)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Validate database path
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Loading data from: {db_path}", file=sys.stderr)

    # Connect to DuckDB and fetch data
    try:
        with get_connection(str(db_path)) as conn:
            query = """
                SELECT
                    pace_seconds_per_km,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    stride_length,
                    cadence
                FROM splits
                WHERE ground_contact_time IS NOT NULL
                  AND vertical_oscillation IS NOT NULL
                  AND vertical_ratio IS NOT NULL
                  AND pace_seconds_per_km > 0
                  AND pace_seconds_per_km < 600
            """

            df = conn.execute(query).df()

        if args.verbose:
            print(f"Loaded {len(df)} splits from database", file=sys.stderr)

    except Exception as e:
        print(f"Error loading data from database: {e}", file=sys.stderr)
        return 1

    # Check if we have enough data
    if len(df) < 10:
        print(
            f"Error: Insufficient data ({len(df)} samples). Need at least 10 samples.",
            file=sys.stderr,
        )
        return 1

    # Preprocess data
    if args.verbose:
        print("Preprocessing data (removing outliers)...", file=sys.stderr)

    # Remove outliers from each column
    df_clean = df.copy()
    df_clean = utils.drop_outliers(df_clean, "ground_contact_time", (150.0, 350.0))
    df_clean = utils.drop_outliers(df_clean, "vertical_oscillation", (5.0, 20.0))
    df_clean = utils.drop_outliers(df_clean, "vertical_ratio", (4.0, 15.0))

    if args.verbose:
        print(
            f"After outlier removal: {len(df_clean)} samples "
            f"({len(df) - len(df_clean)} removed)",
            file=sys.stderr,
        )

    # Add derived columns
    df_clean["speed_mps"] = df_clean["pace_seconds_per_km"].apply(utils.to_speed)
    df_clean["gct_ms"] = df_clean["ground_contact_time"]
    df_clean["vo_value"] = df_clean[
        "vertical_oscillation"
    ]  # Changed to match trainer.py expectation
    df_clean["vr_value"] = df_clean[
        "vertical_ratio"
    ]  # Changed to match trainer.py expectation

    # Train models
    if args.verbose:
        print("Training models...", file=sys.stderr)

    try:
        gct_model: GCTPowerModel = trainer.fit_gct_power(df_clean)
        vo_model: LinearModel = trainer.fit_linear(df_clean, "vo")
        vr_model: LinearModel = trainer.fit_linear(df_clean, "vr")
    except Exception as e:
        print(f"Error training models: {e}", file=sys.stderr)
        return 1

    # Prepare output
    output_data = {
        "condition": args.condition,
        "n_samples": len(df_clean),
        "speed_range": {
            "min": float(df_clean["speed_mps"].min()),
            "max": float(df_clean["speed_mps"].max()),
        },
        "gct": {
            "alpha": float(gct_model.alpha),
            "d": float(gct_model.d),
            "rmse": float(gct_model.rmse),
            "n_samples": int(gct_model.n_samples),
            "speed_range": {
                "min": float(gct_model.speed_range[0]),
                "max": float(gct_model.speed_range[1]),
            },
        },
        "vo": {
            "a": float(vo_model.a),
            "b": float(vo_model.b),
            "rmse": float(vo_model.rmse),
            "n_samples": int(vo_model.n_samples),
            "speed_range": {
                "min": float(vo_model.speed_range[0]),
                "max": float(vo_model.speed_range[1]),
            },
        },
        "vr": {
            "a": float(vr_model.a),
            "b": float(vr_model.b),
            "rmse": float(vr_model.rmse),
            "n_samples": int(vr_model.n_samples),
            "speed_range": {
                "min": float(vr_model.speed_range[0]),
                "max": float(vr_model.speed_range[1]),
            },
        },
    }

    # Output results
    json_output = json.dumps(output_data, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json_output)
        if args.verbose:
            print(f"Saved model coefficients to: {output_path}", file=sys.stderr)
    else:
        print(json_output)

    if args.verbose:
        print("Training complete!", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
