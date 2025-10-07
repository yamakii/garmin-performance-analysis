# Analyze Activity Command

Activity ID {{arg1}} ({{arg2}}) の完全な分析を実行してください。

## ワークフロー

1. **データ収集**: GarminIngestWorkerでデータ取得
2. **データ検証**: ValidationWorkerで品質チェック
3. **セクション分析**: 5つのエージェントを並列実行
   - efficiency-section-analyst
   - environment-section-analyst
   - phase-section-analyst
   - split-section-analyst
   - summary-section-analyst
4. **レポート生成**: report-generator-workerで最終レポート作成

## 実行手順

### Step 1: データ収集と検証

まず、Activity ID {{arg1}} のGarminデータを収集し、DuckDBに格納してください。

```python
from tools.ingest.garmin_worker import GarminIngestWorker
from tools.database.inserters.performance import insert_performance_data

worker = GarminIngestWorker()
result = worker.process_activity({{arg1}}, "{{arg2}}")
insert_performance_data(result["performance_file"], {{arg1}}, "{{arg2}}")
```

### Step 2: セクション分析（並列実行）

5つのエージェントを並列で呼び出してください：

```
Task: efficiency-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) のフォーム効率と心拍効率を分析してください。mcp__garmin-db__get_performance_section使用。"

Task: environment-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) の環境要因（気温、風速、地形）の影響を分析してください。"

Task: phase-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) のウォームアップ・メイン・フィニッシュの3フェーズを評価してください。"

Task: split-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) の全スプリットを詳細分析してください。mcp__garmin-db__get_splits_complete使用。"

Task: summary-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) のアクティビティタイプ判定と総合評価を生成してください。"
```

### Step 3: レポート生成

全てのセクション分析が完了したら、最終レポートを生成してください：

```
Task: report-generator
prompt: "Activity ID {{arg1}} ({{arg2}}) の最終レポートを生成してください。DuckDBからセクション分析を取得し、mcp__report-generator__create_report_structure使用。"
```

## 重要事項

- **並列実行必須**: セクション分析は必ず並列で実行（トークン効率）
- **DuckDB優先**: mcp__garmin-db__*ツールを使用してトークン削減
- **日本語出力**: 全ての分析は日本語で
- **データソース**: performance.jsonとDuckDBのみ使用
