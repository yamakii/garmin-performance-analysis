# Data Analysis Guide

This guide describes the **DuckDB × MCP × Python Architecture** for bulk performance data analysis. Use this workflow when analyzing 10+ activities, multi-month trends, race predictions, and statistical comparisons with **99.7% token efficiency**.

## When to Use This Workflow

**✅ USE THIS WORKFLOW when:**
- Analyzing **10+ activities** (multi-month trends, growth rate, correlation)
- **Race prediction** (VDOT calculation, Riegel formula, time estimation)
- **Statistical comparison** (t-test, effect size, period comparison)
- **Bulk queries** requiring 50+ rows of data

**❌ DON'T USE when:**
- Single activity analysis → Use `get_performance_trends(activity_id)`
- <10 activities → Individual MCP calls more efficient
- Report generation → Use section analysis agents
- Metadata lookup → Use `get_activity_by_date`, `get_date_by_activity_id`

**Example Trigger Prompts:**
- "Analyze my 5-month progression"
- "Predict my half-marathon time in 3 months"
- "Compare August vs October performance"
- "What's the correlation between pace and heart rate over 100 runs?"

## Architecture Awareness

**CRITICAL: Responsibility Separation**

```
┌─────────────────────────────────────────────────────────────────┐
│  YOU (LLM)                                                       │
│  - STEP 1: PLAN (extract requirements, check schema, design SQL)│
│  - STEP 5: INTERPRET (receive summary, explain in natural lang) │
└─────────────────────────────────────────────────────────────────┘
           ↓ (25 tokens)              ↑ (125 tokens)
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (garmin-db)                                          │
│  - STEP 2: EXPORT (return handle only, NOT raw data)            │
└─────────────────────────────────────────────────────────────────┘
           ↓ (handle path)            ↑ (summary JSON)
┌─────────────────────────────────────────────────────────────────┐
│  Python Executor (Bash tool)                                     │
│  - STEP 3: CODE (load parquet, analyze, return summary only)    │
│  - STEP 4: RESULT (validate output size <1KB JSON)              │
└─────────────────────────────────────────────────────────────────┘
```

**Token Protection Rules:**
- ✅ YOU see: MCP handle (~25 tokens), Python summary (~125 tokens)
- ❌ YOU NEVER see: Raw data (thousands of rows), full DataFrame
- ✅ Total: ~150 tokens (vs 55,000 tokens in old approach = **99.7% reduction**)

## Workflow (5 Steps)

### STEP 1: PLAN (Your Responsibility)

**Extract Requirements:**
1. Date range: "5 months" → `today - 150 days` to `today`
2. Metrics: pace, heart_rate, distance, form metrics, etc.
3. Analysis type: trend, prediction, comparison, correlation

**Pre-Check with profile() (RECOMMENDED - データ量確認, 未実装):**
```python
# データ量とカラム統計を事前確認（export前の安全確認）
profile_result = mcp__garmin-db__profile(
    table_or_query="activities",
    date_range=("2025-05-01", "2025-10-17")
)
# → row_count: 107, NULL率確認, 範囲妥当性確認
# → 大量データ（10,000+行）なら集計クエリに変更
```

**Check Schema (MANDATORY - prevents column name errors):**
```python
# ALWAYS run this to avoid column name errors
schema_check = mcp__garmin-db__export(
    query="""
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_name IN ('activities', 'splits', 'form_efficiency', 'hr_efficiency')
    ORDER BY table_name, ordinal_position
    """,
    format="parquet",
    max_rows=500
)
```

**Design Query (Single SQL with CTEs):**
```sql
-- Good: Aggregate in SQL, not Python
WITH splits_agg AS (
  SELECT
    activity_id,
    AVG(pace_seconds_per_km) as avg_pace,
    AVG(heart_rate) as avg_hr,
    AVG(cadence) as avg_cadence
  FROM splits
  GROUP BY activity_id
)
SELECT
  a.activity_id,
  a.activity_date,
  a.total_distance_km,
  a.avg_pace_seconds_per_km,
  s.avg_pace as splits_avg_pace,
  s.avg_hr,
  s.avg_cadence,
  fe.gct_average,
  fe.vo_average,
  he.training_type
FROM activities a
LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
LEFT JOIN form_efficiency fe ON a.activity_id = fe.activity_id
LEFT JOIN hr_efficiency he ON a.activity_id = he.activity_id
WHERE a.activity_date >= '2025-05-01'
  AND a.total_distance_km > 1.0
ORDER BY a.activity_date
```

**Output:** SQL query ready for export.

### STEP 2: EXPORT (MCP Server)

**Single Export Call:**
```python
handle = mcp__garmin-db__export(
    query="<your_sql_from_step1>",
    format="parquet",  # MANDATORY: NOT csv
    max_rows=1000
)
# Returns: {"handle": "/path/to/export.parquet", "rows": 107, "columns": 10}
# Token cost: ~25 tokens (NOT 55,000!)
```

**CRITICAL Rules:**
- ✅ Use `format="parquet"` (3x faster than CSV, preserves types)
- ✅ Single export call (NOT 100+ individual calls)
- ✅ Receive handle only (NOT raw data)
- ❌ NEVER read the exported file in this step

**Output:** File handle path.

### STEP 3: CODE (Python via Bash)

**Analysis Template:**
```python
import pandas as pd
import numpy as np
from scipy import stats
import json

# Load exported data
df = pd.read_parquet("<handle_path>")

# Example: Linear Regression for Growth Rate
df['activity_date'] = pd.to_datetime(df['activity_date'])
df = df.sort_values('activity_date')

# Calculate growth rate (sec/km per week)
days = (df['activity_date'] - df['activity_date'].min()).dt.days
slope, intercept, r_value, p_value, std_err = stats.linregress(days, df['avg_pace'])
growth_rate_per_week = slope * 7

# Summary only (NOT full DataFrame)
summary = {
    "activities_count": len(df),
    "date_range": {
        "start": df['activity_date'].min().isoformat(),
        "end": df['activity_date'].max().isoformat()
    },
    "pace_stats": {
        "mean": float(df['avg_pace'].mean()),
        "std": float(df['avg_pace'].std()),
        "min": float(df['avg_pace'].min()),
        "max": float(df['avg_pace'].max())
    },
    "regression": {
        "slope": float(slope),
        "growth_rate_per_week": float(growth_rate_per_week),
        "r_squared": float(r_value ** 2),
        "p_value": float(p_value),
        "significant": p_value < 0.05
    },
    "interpretation": {
        "trend": "improving" if growth_rate_per_week < 0 else "declining",
        "weeks_to_goal": None  # Calculate if goal pace provided
    }
}

# Output summary JSON (keep <1KB)
print(json.dumps(summary, indent=2))
```

**Execute via Bash:**
```bash
cd $(git rev-parse --show-toplevel)

cat > /tmp/analyze.py << 'EOF'
<python_code_from_above>
EOF

uv run python /tmp/analyze.py
```

**Output:** Summary JSON (~500 bytes, ~125 tokens).

### STEP 4: RESULT (Auto-validation)

**Output Size Limits:**
- JSON: <1KB (auto-trim if exceeded)
- Table: <10 rows (show top N + "... X more rows")
- Plot: Save to file, return path only

**Validation:**
```python
# Auto-applied by helper functions (already implemented)
from tools.utils.llm_safe_data import safe_json_output, safe_summary_table

# JSON output (auto-trims if >1KB)
safe_json_output(summary)

# Table output (auto-limits to 10 rows)
safe_summary_table(df.head(100))
```

**Output:** Validated summary JSON.

### STEP 5: INTERPRET (Your Responsibility)

**Receive Summary (~125 tokens):**
```json
{
  "activities_count": 107,
  "regression": {
    "growth_rate_per_week": -3.2,
    "r_squared": 0.85,
    "p_value": 0.001,
    "significant": true
  }
}
```

**Natural Language Interpretation:**
```
Based on 107 activities over 5 months:

**Growth Rate:** You're improving by 3.2 seconds/km per week on average.

**Statistical Significance:** This improvement is statistically significant
(R²=0.85, p<0.001), meaning it's a real trend, not random variation.

**Practical Impact:** At this rate, you'll reach your goal pace of 5:00/km
in approximately 8 weeks (assuming 3 runs per week).

**Recommendation:** Maintain current training volume. Consider adding tempo
runs to accelerate progress.
```

**Output:** User-friendly explanation with actionable insights.

## Tools Available

### 1. mcp__garmin-db__export (必須)

**Purpose:** Single-call data extraction (token-optimized)

**Signature:**
```python
mcp__garmin-db__export(
    query: str,        # DuckDB SQL query
    format: str,       # "parquet" (MANDATORY) or "csv"
    max_rows: int      # Default 100000
) -> dict
```

**Returns:**
```json
{
  "handle": "/path/to/export.parquet",
  "rows": 107,
  "columns": 10,
  "tables_used": ["activities", "splits"],
  "query_time_ms": 45
}
```

**Usage:**
```python
# Step 1: Schema check
schema = mcp__garmin-db__export(
    query="SELECT * FROM information_schema.columns WHERE table_name='activities'",
    format="parquet"
)

# Step 2: Data export
data = mcp__garmin-db__export(
    query="SELECT * FROM activities WHERE activity_date >= '2025-05-01'",
    format="parquet",
    max_rows=1000
)
```

### 2. mcp__garmin-db__profile (推奨 - 事前確認) — 未実装

**Purpose:** データの要約統計を取得（export前の事前確認に最適）

**Signature:**
```python
mcp__garmin-db__profile(
    table_or_query: str,              # テーブル名 or SQL query
    date_range: Optional[tuple] = None  # (start_date, end_date)
) -> dict
```

**Returns:**
```json
{
  "row_count": 107,
  "date_range": ["2025-05-01", "2025-10-17"],
  "columns": {
    "pace_seconds_per_km": {
      "min": 240, "max": 360, "mean": 270,
      "median": 265, "std": 15, "null_rate": 0.01
    },
    "heart_rate": {
      "min": 120, "max": 180, "mean": 150,
      "null_rate": 0.0
    }
  }
}
```

**Usage:**
```python
# データ量とカラム統計を事前確認
profile = mcp__garmin-db__profile(
    table_or_query="activities",
    date_range=("2025-05-01", "2025-10-17")
)
# → 107行、NULL率確認、範囲確認後にexport実行
```

**When to Use:**
- ✅ Export前のデータ量確認（大量データ防止）
- ✅ NULL率確認（欠損値対策）
- ✅ 日付範囲の妥当性確認
- ✅ 複雑なクエリの事前テスト

**Token Cost:** ~500 bytes（exportの1/50）

### 3. mcp__garmin-db__histogram (推奨 - 分布確認) — 未実装

**Purpose:** カラムの分布特性を取得（生データなし）

**Signature:**
```python
mcp__garmin-db__histogram(
    table_or_query: str,              # テーブル名 or SQL query
    column: str,                       # 対象カラム
    bins: int = 20,                    # ビン数
    date_range: Optional[tuple] = None # (start_date, end_date)
) -> dict
```

**Returns:**
```json
{
  "column": "pace_seconds_per_km",
  "bins": [
    {"min": 240, "max": 250, "count": 12},
    {"min": 250, "max": 260, "count": 45},
    {"min": 260, "max": 270, "count": 30},
    ...
  ],
  "total_count": 107
}
```

**Usage:**
```python
# ペース分布を確認（可視化前の分析）
pace_dist = mcp__garmin-db__histogram(
    table_or_query="SELECT pace_seconds_per_km FROM splits WHERE activity_date >= '2025-05-01'",
    column="pace_seconds_per_km",
    bins=20
)
# → 分布が正規分布か、外れ値がないかを確認
```

**When to Use:**
- ✅ 分布特性の確認（正規分布、偏り、外れ値）
- ✅ グラフ生成前の事前分析
- ✅ 異常値検出
- ✅ ビン境界の最適化

**Token Cost:** ~1KB（20ビン × 50バイト）

### 4. mcp__garmin-db__materialize (推奨 - 複雑クエリ最適化) — 未実装

**Purpose:** 一時ビュー作成（複雑なクエリを再利用、高速化）

**Signature:**
```python
mcp__garmin-db__materialize(
    name: str,              # ビュー名（ユニーク）
    query: str,             # 物質化するSQL
    ttl_seconds: int = 3600 # 有効期限（デフォルト1時間）
) -> dict
```

**Returns:**
```json
{
  "view": "temp_view_abc123",
  "rows": 107,
  "expires_at": "2025-10-17T12:00:00Z"
}
```

**Usage:**
```python
# 複雑なJOINを物質化（2回目以降が高速）
view = mcp__garmin-db__materialize(
    name="analysis_5months",
    query="""
    WITH splits_agg AS (...)
    SELECT a.*, s.avg_pace, fe.gct_average
    FROM activities a
    LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
    LEFT JOIN form_efficiency fe ON a.activity_id = fe.activity_id
    WHERE a.activity_date >= '2025-05-01'
    """
)

# ビューを参照して高速クエリ
data = mcp__garmin-db__export(
    query=f"SELECT * FROM {view['view']} WHERE avg_pace < 270",
    format="parquet"
)
```

**When to Use:**
- ✅ 複雑なJOINクエリを複数回実行する場合
- ✅ 同じデータセットを異なる条件でフィルタする場合
- ✅ パフォーマンス最適化（2-5x高速化）

**Token Cost:** ~100 bytes（ハンドルのみ）

### 5. Bash (必須)

**Purpose:** Execute Python analysis scripts

**Usage:**
```bash
# Create temporary Python script
cat > /tmp/analyze.py << 'EOF'
import pandas as pd
# ... analysis code ...
EOF

# Execute with uv
uv run python /tmp/analyze.py
```

**CRITICAL:**
- Use absolute paths: `$(git rev-parse --show-toplevel)`
- Use `uv run python` (NOT plain `python`)
- Clean up temp files after use

## Example Prompts

### ✅ GOOD Examples (Call This Agent)

**Time Series Analysis:**
```
User: "Analyze my running performance over the past 5 months"

Agent Steps:
1. PLAN: Date range (today - 150 days), metrics (pace, HR, distance)
2. EXPORT: Single query with CTEs (activities + splits + form)
3. CODE: Linear regression, growth rate calculation
4. RESULT: Summary JSON (150 tokens)
5. INTERPRET: "Improving by 3.2 sec/km/week, R²=0.85, significant"

Token Cost: ~150 tokens (vs 55,000 old way)
```

**Race Prediction:**
```
User: "What's my predicted half-marathon time in 3 months?"

Agent Steps:
1. PLAN: Recent 3 months, best 10km time, VDOT calculation
2. EXPORT: Best times by distance (5km, 10km, 15km)
3. CODE: VDOT formula, Riegel prediction, temperature adjustment
4. RESULT: Predicted time with confidence interval
5. INTERPRET: "1:35:00 ± 3 min (90% CI), based on VDOT 52.3"

Token Cost: ~200 tokens
```

**Comparative Analysis:**
```
User: "Compare my August vs October running performance"

Agent Steps:
1. PLAN: Two date ranges (2025-08-01 to 2025-08-31, 2025-10-01 to 2025-10-31)
2. EXPORT: Activities + splits for both periods
3. CODE: t-test, Cohen's d effect size
4. RESULT: Statistical comparison
5. INTERPRET: "October 15 sec/km faster (p<0.01, d=0.8 large effect)"

Token Cost: ~180 tokens
```

### ❌ BAD Examples (Don't Call This Agent)

**Single Activity:**
```
User: "Analyze my run from yesterday"
→ Use: get_performance_trends(activity_id) instead
→ Why: Single activity = individual MCP call more efficient
```

**Small Dataset:**
```
User: "Show me my last 5 runs"
→ Use: Loop with get_activity_by_date() + get_splits_pace_hr()
→ Why: 5 activities × 2 calls = 10 calls < export overhead
```

**Report Generation:**
```
User: "Generate a report for activity 12345"
→ Use: Section analysis agents (split/phase/efficiency/etc)
→ Why: Report generation has different workflow
```

## Token Cost Efficiency

### Old Approach (Before This Agent)

**5-Month Analysis Example:**
- 107 activities × 2 MCP calls (`get_activity_by_date` + `get_performance_trends`)
- = 214 MCP calls
- Each call returns ~250 tokens of data
- **Total: ~55,000 tokens**
- Execution time: 5-10 minutes

**Problems:**
- Network overhead (214 round-trips)
- Column name errors (no schema check)
- CSV parsing inefficiency
- LLM context pollution

### New Approach (This Agent)

**Same 5-Month Analysis:**
1. Schema check: 1 export call (~25 tokens)
2. Data export: 1 export call (~25 tokens handle)
3. Python analysis: 1 Bash call (~125 tokens summary)
4. **Total: ~175 tokens**
5. Execution time: <2 minutes

**Benefits:**
- **99.7% token reduction** (55,000 → 175)
- **Zero column errors** (schema check first)
- **3x faster** (Parquet + single call)
- **LLM context preserved** (summary only)

**Efficiency Proof:**
```
Token Reduction = (55,000 - 175) / 55,000 = 99.68%
Time Reduction = (10 min - 2 min) / 10 min = 80%
Error Reduction = 100% (schema validation prevents errors)
```

## Common Analysis Patterns

### 1. Growth Rate Calculation

```python
# Linear regression for pace improvement
from scipy import stats

days = (df['activity_date'] - df['activity_date'].min()).dt.days
slope, intercept, r_value, p_value, std_err = stats.linregress(
    days, df['avg_pace_seconds_per_km']
)

growth_rate_per_week = slope * 7  # sec/km per week
growth_rate_per_month = slope * 30  # sec/km per month

# Confidence interval
from scipy.stats import t as t_dist
n = len(df)
t_val = t_dist.ppf(0.975, n-2)  # 95% CI
margin = t_val * std_err * 7
confidence_interval = (growth_rate_per_week - margin, growth_rate_per_week + margin)
```

### 2. VDOT Calculation (Jack Daniels)

```python
# VDOT from race time
def calculate_vdot(distance_km, time_seconds):
    velocity = distance_km / (time_seconds / 3600)  # km/h
    vo2 = -4.60 + 0.182258 * velocity + 0.000104 * velocity**2
    pct_max = 0.8 + 0.1894393 * np.exp(-0.012778 * (time_seconds / 60))
    vdot = vo2 / pct_max
    return vdot

# Predict race time from VDOT
def predict_time(vdot, distance_km):
    # Riegel formula: T2 = T1 * (D2/D1)^1.06
    # Use known VDOT to estimate VO2, then time
    # (Simplified - full calculation more complex)
    pass
```

### 3. Statistical Comparison

```python
# Compare two periods
from scipy import stats

period1 = df[df['period'] == 'august']['avg_pace']
period2 = df[df['period'] == 'october']['avg_pace']

# t-test (assumes normal distribution)
t_stat, p_value = stats.ttest_ind(period1, period2)

# Effect size (Cohen's d)
mean_diff = period2.mean() - period1.mean()
pooled_std = np.sqrt((period1.std()**2 + period2.std()**2) / 2)
cohens_d = mean_diff / pooled_std

# Interpretation
if abs(cohens_d) < 0.2:
    effect = "negligible"
elif abs(cohens_d) < 0.5:
    effect = "small"
elif abs(cohens_d) < 0.8:
    effect = "medium"
else:
    effect = "large"
```

## Error Handling

### Schema Validation Errors

**Error:** Column doesn't exist
```
ERROR: Column "avg_hr" not found in table "activities"
```

**Solution:**
```python
# ALWAYS check schema first
schema = mcp__garmin-db__export(
    query="""
    SELECT column_name FROM information_schema.columns
    WHERE table_name='activities'
    """,
    format="parquet"
)
# Read schema, then build query
```

### Empty Result Errors

**Error:** No data in date range
```
ERROR: Query returned 0 rows
```

**Solution:**
```python
# Check data availability first
count = mcp__garmin-db__export(
    query="""
    SELECT COUNT(*) as cnt FROM activities
    WHERE activity_date >= '2025-05-01'
    """,
    format="parquet"
)
# If count > 0, proceed
```

### Output Size Exceeded

**Error:** JSON output >1KB
```
WARNING: Output truncated to 1KB
```

**Solution:**
```python
# Return summary stats, not full data
summary = {
    "count": len(df),
    "stats": df.describe().to_dict(),  # Aggregated only
    "top_10": df.head(10).to_dict()    # Limited rows
}
```

## Best Practices

### DO:
- ✅ Check schema FIRST (prevents all column errors)
- ✅ Use single export with CTEs (99% token reduction)
- ✅ Use Parquet format (3x faster than CSV)
- ✅ Return summary JSON <1KB (preserve LLM context)
- ✅ Include statistical significance (p-value + effect size)
- ✅ Provide actionable insights ("Continue 3x/week for 8 weeks")

### DON'T:
- ❌ Skip schema check (causes column name errors)
- ❌ Use multiple individual MCP calls (token-heavy)
- ❌ Use CSV format for 50+ rows (slow + type loss)
- ❌ Return full DataFrame to LLM (context pollution)
- ❌ Report p-value alone (need effect size too)
- ❌ Give vague advice ("Keep training" - not actionable)

## Success Criteria

After completing analysis, verify:
- [ ] Token cost <500 tokens (99%+ reduction vs old approach)
- [ ] Execution time <2 minutes (for 100+ activities)
- [ ] Zero column name errors (schema checked first)
- [ ] Summary output <1KB JSON (LLM context preserved)
- [ ] Statistical significance reported (p-value + effect size)
- [ ] Actionable insights provided (specific recommendations)

---

## Quick Reference

**Complete Workflow Example:**
```
User: "Analyze 2021 injury risk"

STEP 1 (PLAN):
  → Design query for training load, consecutive hard runs, form metrics

STEP 2 (EXPORT):
  → Call mcp__garmin-db__export(query, format="parquet")

STEP 3 (CODE):
  → Write /tmp/analyze.py with risk scoring algorithm
  → Execute with: uv run python /tmp/analyze.py

STEP 4 (RESULT):
  → Capture JSON output (monthly risk scores, patterns, recommendations)

STEP 5 (INTERPRET):
  → "Based on 121 activities, highest risk was February (58% hard training)...
     Recommendations: 10% rule, mandatory rest days, GCT monitoring"
```

**Remember:** Always work with summaries (<1KB JSON), never request raw data.
