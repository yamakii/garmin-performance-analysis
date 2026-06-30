#!/usr/bin/env python3
"""Shared body for form baseline training scripts.

Both ``train_form_baselines_weekly`` and ``train_form_baselines_monthly`` reuse
this module. They differ only in how the (period_start, period_end) window is
derived from CLI arguments; everything else (data loading, outlier removal,
model fitting, and persistence to ``form_baseline_history``) is identical.

The actual training is a thin delegation to
``garmin_mcp.form_baseline.trainer.train_form_baselines`` -- the single source
of truth that trains GCT/VO/VR/cadence (and best-effort power) from one cleaned
window in a single transaction. Keeping the batch path here in sync with the
trainer avoids the metric drift that caused cadence/power to be missing from
month-boundary periods (#640).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from garmin_mcp.form_baseline import trainer


def train_and_store_baseline(
    period_start: datetime,
    period_end: datetime,
    *,
    condition: str,
    db_path: Path,
    min_samples: int = 50,
    verbose: bool = False,
) -> int:
    """Train all form baselines for a window and persist them.

    Delegates to ``trainer.train_form_baselines``, which trains GCT/VO/VR/cadence
    from the same cleaned window in one transaction and additionally attempts the
    best-effort power model. ``period_start`` is accepted for CLI signature
    compatibility but is not used directly: the trainer recomputes the window
    start from ``period_end`` and ``window_months=2`` (which matches the weekly/
    monthly window derivation).

    Power may be legitimately absent for older periods because it requires
    ``role_phase = 'run'`` splits with a non-null ``base_weight_kg``; this is not
    treated as a failure.

    Args:
        period_start: Inclusive start of the rolling window (signature
            compatibility only; recomputed from period_end by the trainer).
        period_end: Inclusive end of the rolling window.
        condition: Condition group name (e.g., "flat_road").
        db_path: Path to the DuckDB database.
        min_samples: Minimum number of samples required (before and after
            outlier removal).
        verbose: Enable verbose logging to stderr.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    if verbose:
        print(
            f"Training period: {period_start.date()} to {period_end.date()} (2 months)",
            file=sys.stderr,
        )

    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    result = trainer.train_form_baselines(
        condition_group=condition,
        end_date=period_end.strftime("%Y-%m-%d"),
        window_months=2,
        db_path=str(db_path),
        min_samples=min_samples,
    )

    if result is None:
        print(
            f"Error: Training failed or insufficient data "
            f"(need at least {min_samples} samples) for window ending "
            f"{period_end.date()}.",
            file=sys.stderr,
        )
        return 1

    if verbose:
        print("✓ Training complete!", file=sys.stderr)
        print(
            f"  Period: {result['period_start']} to {result['period_end']}",
            file=sys.stderr,
        )
        for metric in ("gct", "vo", "vr", "cadence", "power"):
            model = result.get(metric)
            if model:
                print(f"  {metric.upper()}: n={model['n_samples']}", file=sys.stderr)

    return 0
