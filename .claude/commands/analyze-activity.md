# Analyze Activity Command

日付 {{arg1}} のアクティビティの完全な分析を実行してください。

## ワークフロー

1. **データ収集**: WorkflowPlannerで日付からアクティビティを取得・処理
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

`tools/planner/workflow_planner.py` を使用して、日付からアクティビティを取得し、データを収集してDuckDBに格納してください。

```bash
uv run python -m tools.planner.workflow_planner {{arg1}}
```

このコマンドは以下を実行します：
- 日付 {{arg1}} からアクティビティIDを解決
- GarminIngestWorkerでデータ収集
- DuckDBへの自動挿入

実行後、出力されたJSONから `activity_id` と `date` を取得してください。

### Step 2: セクション分析（並列実行）

WorkflowPlannerの結果から取得した `activity_id` と `date` を使用して、5つのエージェントを並列で呼び出してください：

```
Task: efficiency-section-analyst
prompt: "Activity ID {activity_id} ({date}) のフォーム効率と心拍効率を分析してください。"

Task: environment-section-analyst
prompt: "Activity ID {activity_id} ({date}) の環境要因（気温、風速、地形）の影響を分析してください。"

Task: phase-section-analyst
prompt: "Activity ID {activity_id} ({date}) のフェーズ評価を実行してください。"

Task: split-section-analyst
prompt: "Activity ID {activity_id} ({date}) の全スプリットを詳細分析してください。"

Task: summary-section-analyst
prompt: "Activity ID {activity_id} ({date}) のアクティビティタイプ判定と総合評価を生成してください。"
```

### Step 3: レポート生成

全てのセクション分析が完了したら、最終レポートを生成してください：

```bash
uv run python -m tools.reporting.report_generator_worker {activity_id} {date}
```

## 重要事項

- **並列実行必須**: セクション分析は必ず並列で実行（トークン効率）
- **DuckDB優先**: mcp__garmin-db__*ツールを使用してトークン削減
- **日本語出力**: 全ての分析は日本語で
- **データソース**: DuckDBのみ使用（raw JSONから直接抽出）
