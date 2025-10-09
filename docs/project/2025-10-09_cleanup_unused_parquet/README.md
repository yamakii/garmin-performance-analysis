# Project: Cleanup Unused Parquet Files

**Status:** Planning Complete
**Created:** 2025-10-09
**Type:** Code Cleanup & Refactoring

## Overview

Remove unused parquet files from the Garmin performance analysis system to reduce storage usage and code complexity. The system currently generates two types of parquet files that are no longer used in production code.

## Quick Facts

- **Parquet files to remove:** 210 files (~2MB total)
  - Activity Parquet: 102 files (~1.3MB)
  - Weight Parquet: 108 files (~0.7MB)
- **Files to keep:** Precheck JSON files (actively used by WorkflowPlanner)
- **Primary storage:** DuckDB (unaffected)

## Key Changes

1. Remove parquet generation from `GarminIngestWorker.save_data()`
2. Delete physical parquet files (with backup)
3. Fix affected tests to use DuckDB instead
4. Update documentation (CLAUDE.md)

## Next Steps

To start implementation, invoke the **tdd-implementer** agent:

```bash
Task: tdd-implementer
prompt: "docs/project/2025-10-09_cleanup_unused_parquet/planning.md に基づいて、TDDサイクルで実装してください。Phase 0のDiscovery & Validationから開始してください。"
```

## Documents

- `planning.md` - Complete project plan with phases and test plan
- `README.md` - This file

## References

- Related code: `tools/ingest/garmin_worker.py` (lines 1058-1061)
- Test files: `tests/ingest/test_body_composition.py`, `tests/planner/test_workflow_planner.py`
- Documentation: `CLAUDE.md` (Data Files Naming Convention section)
