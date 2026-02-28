# Progress Report Command

指定期間のプログレスレポートを生成してください。

## パラメータ

- `{{arg1}}`: 開始日 (YYYY-MM-DD)
- `{{arg2}}`: 終了日 (YYYY-MM-DD)

## ワークフロー

### Step 1: アクティビティ一覧の取得

MCP export ツールで対象期間のアクティビティデータを取得:

```
mcp__garmin-db__export(
    query="SELECT a.activity_id, a.activity_date, a.distance / 100000.0 as distance_km, a.avg_speed, a.avg_hr, a.training_type FROM activities a WHERE a.activity_date >= '{{arg1}}' AND a.activity_date <= '{{arg2}}' AND a.activity_type = 'running' ORDER BY a.activity_date",
    format="parquet"
)
```

### Step 2: 各アクティビティの詳細取得

取得した activity_id リストに対して、以下のデータを収集:
- `get_splits_comprehensive(activity_id, statistics_only=True)` -- ペース・HR
- `get_hr_efficiency_analysis(activity_id)` -- Zone 2%
- `get_form_efficiency_summary(activity_id)` -- フォームスコア

### Step 3: レポート生成

収集したデータを `ProgressReportWorker` の入力形式に変換し、`render()` でマークダウン生成。

```python
from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker

worker = ProgressReportWorker()
markdown = worker.render(activities, start_date="{{arg1}}", end_date="{{arg2}}")
```

### Step 4: 結果表示

生成されたマークダウンをユーザーに表示してください。

## 重要事項

- MCP ツール経由でデータ取得（直接 DuckDB アクセス禁止）
- 日本語で出力
- アクティビティ数が多い場合は export + Python スクリプトで効率化
