# Progress Report Command

過去 {{arg1}} 週間のプログレスレポートを生成してください。

## ワークフロー

1. **期間計算**: 今日から {{arg1}} 週間前までの日付範囲を決定
2. **データ収集**: DuckDB から期間内のアクティビティデータを取得
3. **レポート生成**: ProgressReportWorker でマークダウンレポートを生成

## 実行手順

### Step 1: 期間計算

```python
from datetime import date, timedelta
end_date = date.today()
start_date = end_date - timedelta(weeks=int("{{arg1}}" or "4"))
```

### Step 2: データ収集

DuckDB export で期間内のアクティビティとメトリクスを取得:

```python
mcp__garmin-db__export(query="""
    SELECT
        a.activity_id,
        a.activity_date,
        a.total_distance_km,
        a.total_time_seconds,
        a.avg_pace_seconds_per_km,
        a.avg_heart_rate,
        COALESCE(h.zone2_percentage, 0) as zone2_percentage,
        COALESCE(f.integrated_score, 0) as integrated_score
    FROM activities a
    LEFT JOIN hr_efficiency h ON a.activity_id = h.activity_id
    LEFT JOIN form_evaluations f ON a.activity_id = f.activity_id
    WHERE a.activity_date BETWEEN '{start_date}' AND '{end_date}'
    ORDER BY a.activity_date
""", format="csv")
```

### Step 3: レポート生成

```python
from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker

worker = ProgressReportWorker()
report = worker.render(
    activities=activities,  # parsed from CSV
    start_date=str(start_date),
    end_date=str(end_date),
    period="weekly",
)
print(report)
```

結果のマークダウンをユーザーに表示してください。
