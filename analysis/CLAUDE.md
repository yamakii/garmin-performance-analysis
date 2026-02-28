# CLAUDE.md — Analysis Workspace

Garmin ランニングパフォーマンス分析ツール。MCP tools を使って活動データを分析・レポート生成する。

## Activity Analysis

**Single Activity:**
```
1. Get activity ID: mcp__garmin-db__get_activity_by_date(date="2025-10-15")
2. Get performance: mcp__garmin-db__get_performance_trends(activity_id)
3. Get splits: mcp__garmin-db__get_splits_comprehensive(activity_id, statistics_only=True)
4. Get form: mcp__garmin-db__get_form_efficiency_summary(activity_id)
5. Get HR zones: mcp__garmin-db__get_hr_efficiency_analysis(activity_id)
```

**Multi-Activity Trends:**
```
mcp__garmin-db__analyze_performance_trends(
  metric="pace", start_date="2025-10-01", end_date="2025-10-31", activity_ids=[...]
)
```

**Similar Workout Comparison:**
```
mcp__garmin-db__compare_similar_workouts(activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.1)
```

## Data Analysis (10+ Activities)

Export-based 5-step workflow:
1. **PLAN** — Design SQL with CTEs
2. **EXPORT** — `mcp__garmin-db__export(query, format="parquet")`
3. **CODE** — Write Python to `/tmp/analyze.py`, load parquet, return summary JSON
4. **RESULT** — `uv run python /tmp/analyze.py`
5. **INTERPRET** — Explain with actionable insights

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/analyze-activity` | Analyze a single activity with 5 agents |
| `/batch-analyze` | Batch analyze multiple activities |
| `/plan-training` | Generate a training plan |

## Agent System

5 parallel analysis agents:
1. **split-section-analyst** — 1km split analysis (pace, HR, form)
2. **phase-section-analyst** — Phase evaluation (warmup/run/cooldown)
3. **summary-section-analyst** — Overall assessment
4. **efficiency-section-analyst** — Form (GCT/VO/VR) + HR efficiency
5. **environment-section-analyst** — Environmental impact (weather, terrain)

## Environment

This workspace uses `.env` to control data paths:
- `GARMIN_MCP_SERVER_DIR` — MCP server code location
- `GARMIN_DATA_DIR` — DuckDB and raw data path
- `GARMIN_RESULT_DIR` — Report output path

Copy `.env.example` to `.env` and customize as needed.
