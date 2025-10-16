# LLM Behavior Rules for DuckDB × MCP × LLM Architecture

This document defines the behavioral guidelines for LLMs (Claude) when working with high-resolution Garmin activity data through the DuckDB × MCP × LLM architecture.

## Core Principles

### 1. Responsibility Separation

**LLM Role:**
- ✅ Plan data requirements (PLAN phase)
- ✅ Interpret processed results (INTERPRET phase)
- ✅ Provide natural language explanations
- ❌ NEVER directly read raw data
- ❌ NEVER expand full datasets in context

**MCP Server Role:**
- ✅ Extract data and return handles (not data)
- ✅ Provide summary statistics
- ✅ Generate aggregated distributions
- ❌ NEVER return raw high-resolution data

**Python Executor Role:**
- ✅ Load data from handles
- ✅ Process and aggregate data
- ✅ Generate visualizations
- ✅ Return summary statistics only
- ❌ NEVER return full DataFrames to LLM

### 2. Context Protection

**Output Size Limits:**
- JSON output: ≤ 1KB (1024 bytes)
- Table output: ≤ 10 rows
- Export handles: metadata only (path, row count, columns)

**Violation Behavior:**
- Automatic trimming with warning
- Error messages guide to correct approach
- Suggested alternative: aggregation, filtering, or file export

## Standard Data Analysis Flow

### Recommended Flow: PLAN → EXPORT → CODE → RESULT → INTERPRET

```
STEP 1: PLAN (LLM)
  ↓
  Analyze user request
  Identify required data
  Formulate MCP query

STEP 2: EXPORT (MCP)
  ↓
  Call mcp__garmin-db__export(query)
  Receive handle (NOT data)

STEP 3: CODE (Python)
  ↓
  Load data: safe_load_export(handle, max_rows=10000)
  Process: aggregation, resampling, rolling average
  Visualize: save plots to files
  Summarize: generate < 1KB JSON

STEP 4: RESULT (Validation)
  ↓
  Auto-validate output size
  Auto-trim if necessary
  Log warnings

STEP 5: INTERPRET (LLM)
  ↓
  Receive summary JSON (< 1KB)
  Receive plot file paths
  Generate natural language interpretation
  Suggest next analysis if needed
```

## Prohibited Actions

### ❌ DO NOT: Read Raw Data Directly

**Bad Example:**
```python
# WRONG: Loading entire time series into context
df = mcp__garmin-db__get_time_range_detail(activity_id=12345, start=0, end=3600)
print(df)  # 3600 rows × 26 columns = context explosion
```

**Correct Approach:**
```python
# RIGHT: Use statistics_only mode
stats = mcp__garmin-db__get_time_range_detail(
    activity_id=12345,
    start=0,
    end=3600,
    statistics_only=True  # Returns ~500 bytes
)
print(stats)  # Only summary statistics
```

### ❌ DO NOT: Print Full DataFrames

**Bad Example:**
```python
# WRONG: Printing entire DataFrame
df = safe_load_export(handle)
print(df)  # Could be 10,000 rows
```

**Correct Approach:**
```python
# RIGHT: Use safe_summary_table()
from tools.utils.llm_safe_data import safe_summary_table

df = safe_load_export(handle)
summary = safe_summary_table(df, max_rows=10)  # 10 rows only
print(summary)
```

### ❌ DO NOT: Return Large JSON Objects

**Bad Example:**
```python
# WRONG: Returning all data points
result = {
    "data_points": df.to_dict('records')  # Could be 10,000 records
}
```

**Correct Approach:**
```python
# RIGHT: Return aggregated statistics
from tools.utils.llm_safe_data import safe_json_output

result = {
    "statistics": {
        "count": len(df),
        "mean_pace": df['pace'].mean(),
        "std_pace": df['pace'].std(),
        "pace_range": [df['pace'].min(), df['pace'].max()]
    },
    "plot_path": "/tmp/pace_variation.png"
}
output = safe_json_output(result, max_size=1024)
```

## Recommended Patterns

### Pattern 1: Time Series Analysis

```python
# Export time range to handle
export_result = mcp__garmin-db__export(
    query="""
        SELECT timestamp, pace, heart_rate
        FROM time_series_metrics
        WHERE activity_id = 12345 AND timestamp BETWEEN 300 AND 600
    """,
    format="parquet"
)

# Load and process in Python
df = safe_load_export(export_result['handle'])
df_resampled = df.resample('10S').mean()  # 10-second bins
rolling_avg = df_resampled['pace'].rolling(3).mean()

# Save plot
import matplotlib.pyplot as plt
plt.plot(df_resampled['timestamp'], df_resampled['pace'], label='Pace')
plt.plot(df_resampled['timestamp'], rolling_avg, label='Rolling Avg')
plt.savefig('/tmp/pace_analysis.png')

# Return summary only
summary = {
    "avg_pace": float(df['pace'].mean()),
    "pace_variation": float(df['pace'].std()),
    "plot_path": "/tmp/pace_analysis.png"
}
print(safe_json_output(summary))
```

### Pattern 2: Distribution Analysis

```python
# Use histogram() for distribution (NO raw data)
hist = mcp__garmin-db__histogram(
    table_or_query="splits",
    column="pace",
    bins=20,
    date_range=("2025-01-01", "2025-01-31")
)

# Receive binned distribution (~1KB)
# Interpret and explain distribution characteristics
```

### Pattern 3: Multi-Activity Comparison

```python
# Step 1: Profile each activity (lightweight)
activities = [12345, 12346, 12347]
profiles = [
    mcp__garmin-db__profile(f"SELECT * FROM splits WHERE activity_id = {aid}")
    for aid in activities
]

# Step 2: Export specific metrics only
export_result = mcp__garmin-db__export(
    query="""
        SELECT activity_id, split_number, pace, heart_rate
        FROM splits
        WHERE activity_id IN (12345, 12346, 12347)
    """,
    format="parquet"
)

# Step 3: Load and aggregate
df = safe_load_export(export_result['handle'])
comparison = df.groupby('activity_id').agg({
    'pace': ['mean', 'std'],
    'heart_rate': ['mean', 'std']
}).to_dict()

print(safe_json_output({"comparison": comparison, "activity_count": len(activities)}))
```

## Error Handling

### Size Limit Exceeded

**Error Message:**
```
⚠️ Output size limit exceeded: JSON exceeds 1024 bytes
```

**Recommended Action:**
1. Reduce output data (remove unnecessary keys)
2. Aggregate further (use mean/median instead of all values)
3. Save detailed data to file, return file path only

### Row Limit Exceeded

**Error Message:**
```
⚠️ Output size limit exceeded: Table exceeds 10 rows
```

**Recommended Action:**
1. Use `safe_summary_table(df, max_rows=10)` for display
2. Save full table to CSV: `df.write_csv('/tmp/full_data.csv')`
3. Return file path and summary statistics

### Data Too Large to Load

**Error Message:**
```
Export exceeds max_rows: 100000 > 10000. Use aggregation or filtering.
```

**Recommended Action:**
1. Add WHERE clause to filter data
2. Use aggregation in SQL (GROUP BY, AVG, etc.)
3. Use `statistics_only=True` for summary mode
4. Break into smaller time ranges

## Use Case Examples

### Example 1: Interval Analysis (5:00-10:00 pace variation)

**User Request:**
> "5:00-10:00のペース変動を秒単位で分析して"

**LLM Response:**
```python
# Export 5-minute window
export_result = mcp__garmin-db__export(
    query="""
        SELECT timestamp, pace, heart_rate
        FROM time_series_metrics
        WHERE activity_id = 12345
        AND timestamp BETWEEN 300 AND 600
    """,
    format="parquet"
)

# Process in Python
df = safe_load_export(export_result['handle'])
df_stats = df.describe()
rolling_std = df['pace'].rolling(10).std()

# Summary output (< 1KB)
summary = {
    "duration_seconds": 300,
    "avg_pace": float(df['pace'].mean()),
    "pace_std": float(df['pace'].std()),
    "max_variation_point": int(rolling_std.idxmax()),
    "plot_path": "/tmp/pace_5to10min.png"
}
print(safe_json_output(summary))
```

**LLM Interpretation:**
> "5:00-10:00の区間では平均ペース4:30/km、標準偏差5秒でした。7:30付近でペースが大きく変動しており、rolling標準偏差が最大になっています。給水や地形変化の影響と推測されます。"

### Example 2: Form Anomaly Drill-Down

**User Request:**
> "GCTが急上昇した箇所の前後30秒を詳しく見たい"

**LLM Response:**
```python
# Find anomaly timestamp
anomaly_summary = mcp__garmin-db__detect_form_anomalies_summary(
    activity_id=12345,
    metrics=["ground_contact_time"]
)

# Get top anomaly
top_anomaly = anomaly_summary['top_anomalies'][0]
anomaly_time = top_anomaly['timestamp']

# Export 30-second window
export_result = mcp__garmin-db__export(
    query=f"""
        SELECT timestamp, ground_contact_time, pace, heart_rate, elevation
        FROM time_series_metrics
        WHERE activity_id = 12345
        AND timestamp BETWEEN {anomaly_time - 15} AND {anomaly_time + 15}
    """,
    format="parquet"
)

# Correlation analysis
df = safe_load_export(export_result['handle'])
correlation = df[['ground_contact_time', 'pace', 'elevation']].corr()

summary = {
    "anomaly_timestamp": anomaly_time,
    "gct_before": float(df[df['timestamp'] < anomaly_time]['ground_contact_time'].mean()),
    "gct_at_anomaly": float(df[df['timestamp'] == anomaly_time]['ground_contact_time'].iloc[0]),
    "gct_after": float(df[df['timestamp'] > anomaly_time]['ground_contact_time'].mean()),
    "correlation_with_elevation": float(correlation.loc['ground_contact_time', 'elevation']),
    "plot_path": "/tmp/gct_anomaly_context.png"
}
print(safe_json_output(summary))
```

## Display Configuration

The following display settings are automatically applied:

**Pandas:**
```python
pd.set_option('display.max_rows', 10)
pd.set_option('display.max_columns', 10)
pd.set_option('display.max_colwidth', 50)
```

**Polars:**
```python
pl.Config.set_tbl_rows(10)
pl.Config.set_tbl_cols(10)
pl.Config.set_fmt_str_lengths(50)
```

These settings prevent accidental large DataFrame output.

## Summary Checklist

Before returning analysis results, verify:

- [ ] No raw data returned (use handles or summaries)
- [ ] JSON output < 1KB (use `safe_json_output()`)
- [ ] Table output ≤ 10 rows (use `safe_summary_table()`)
- [ ] Plots saved to files (return paths only)
- [ ] Statistics aggregated (mean/std/min/max, not all values)
- [ ] Error handling in place (size limit exceeded → aggregate further)

## References

- MCP Server Functions: See `CLAUDE.md` § Garmin DB MCP Server
- Python Helper Functions: `tools/utils/llm_safe_data.py`
- Output Interceptor: `tools/utils/output_interceptor.py`
- Display Settings: `tools/utils/display_settings.py`
