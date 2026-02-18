# Analyze Activity Command

日付 {{arg1}} のアクティビティの完全な分析を実行してください。

## ワークフロー

1. **データ収集 + コンテキスト事前取得**: WorkflowPlanner → mkdir → prefetch を1コマンドで実行
2. **セクション分析**: 5つのエージェントを並列実行（事前取得コンテキスト付き）
3. **結果登録**: merge script でDuckDBに一括登録
4. **レポート生成**: report-generator-worker で最終レポート作成

## 実行手順

### Step 1: データ収集 + コンテキスト事前取得

以下を**1つのBashコマンドチェーン**で実行してください：

```bash
RESULT=$(uv run python -m garmin_mcp.planner.workflow_planner {{arg1}}) && \
ACTIVITY_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['activity_id'])") && \
ACTIVITY_DATE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['date'])") && \
mkdir -p /tmp/analysis_$ACTIVITY_ID && \
uv run python -m garmin_mcp.scripts.prefetch_activity_context $ACTIVITY_ID
```

このコマンドは以下を実行します：
- 日付 {{arg1}} からアクティビティIDを解決
- GarminIngestWorkerでデータ収集・DuckDB格納
- 分析用tempフォルダ作成
- 共有コンテキストの事前取得（training_type, weather, terrain）

実行後、出力された最終行のJSONを `CONTEXT` として保持し、`activity_id` と `date` を取得してください。
tempフォルダパスは `ANALYSIS_TEMP_DIR=/tmp/analysis_{activity_id}` として以降使用。

### Step 2: セクション分析（並列実行）

5つのエージェントを並列で呼び出してください。**各エージェントのpromptに事前取得コンテキスト（CONTEXT）を含めること**：

```
Task: efficiency-section-analyst
prompt: "Activity ID {activity_id} ({date}) のフォーム効率と心拍効率を分析してください。
事前取得コンテキスト: {CONTEXT}
結果は {ANALYSIS_TEMP_DIR}/efficiency.json に保存してください。"

Task: environment-section-analyst
prompt: "Activity ID {activity_id} ({date}) の環境要因（気温、風速、地形）の影響を分析してください。
事前取得コンテキスト: {CONTEXT}
結果は {ANALYSIS_TEMP_DIR}/environment.json に保存してください。"

Task: phase-section-analyst
prompt: "Activity ID {activity_id} ({date}) のフェーズ評価を実行してください。
事前取得コンテキスト: {CONTEXT}
結果は {ANALYSIS_TEMP_DIR}/phase.json に保存してください。"

Task: split-section-analyst
prompt: "Activity ID {activity_id} ({date}) の全スプリットを詳細分析してください。
結果は {ANALYSIS_TEMP_DIR}/split.json に保存してください。"

Task: summary-section-analyst
prompt: "Activity ID {activity_id} ({date}) のアクティビティタイプ判定と総合評価を生成してください。
事前取得コンテキスト: {CONTEXT}
結果は {ANALYSIS_TEMP_DIR}/summary.json に保存してください。"
```

**注意**: split-section-analyst にはCONTEXT不要（既にcomprehensive 1回で最適化済み）

### Step 2.5: 分析結果のDuckDB登録（Merge）

全エージェント完了後、1コマンドで一括登録：

```bash
uv run python -m garmin_mcp.scripts.merge_section_analyses /tmp/analysis_{activity_id}
```

- 全 `.json` を読み込み→DuckDBに一括挿入→成功時にtempフォルダ自動削除
- 失敗時: JSONファイルは残る（`--keep` で明示的に残すことも可能）

### Step 3: レポート生成

全てのセクション分析が完了したら、最終レポートを生成してください：

```bash
uv run python -m garmin_mcp.reporting.report_generator_worker {activity_id} {date}
```

## 重要事項

- **並列実行必須**: セクション分析は必ず並列で実行（トークン効率）
- **コンテキスト注入必須**: Step 2で各エージェントに事前取得CONTEXTを渡す（split以外）
- **DuckDB優先**: mcp__garmin-db__*ツールを使用してトークン削減
- **日本語出力**: 全ての分析は日本語で
- **データソース**: DuckDBのみ使用（raw JSONから直接抽出）
