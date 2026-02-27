# Analyze Activity Command

日付 {{arg1}} のアクティビティの完全な分析を実行してください。

## ワークフロー

1. **データ収集**: ingest_activity MCP ツール
2. **コンテキスト事前取得**: MCP ツールで prefetch（Bash許可不要）
3. **セクション分析**: 5つのエージェントを並列実行（事前取得コンテキスト付き）
4. **結果登録**: merge script でDuckDBに一括登録
5. **レポート生成**: report-generator-worker で最終レポート作成

## 実行手順

### Step 1: データ収集

MCPツールでデータ収集・DuckDB格納を実行してください（Bash許可不要）：

```
mcp__garmin-db__ingest_activity(date="{{arg1}}")
```

返却された `activity_id` と `date` を取得してください。

tempフォルダパスは `ANALYSIS_TEMP_DIR=/tmp/analysis_{activity_id}` として以降使用。
（ディレクトリはエージェントの Write tool が自動作成します）

### Step 1.5: コンテキスト事前取得（MCP ツール）

MCPツールで事前取得コンテキストを取得してください（Bash許可不要）：

```
mcp__garmin-db__prefetch_activity_context(activity_id)
```

返却されたJSONを `CONTEXT` として保持してください。

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

### Step 2.1: エラーハンドリング（部分結果判定）

5エージェント完了後、成功/失敗を集計してください：

- **5/5 成功**: Step 2.5 へ進む（通常フロー）
- **4/5 成功**: 失敗セクション名をユーザーに通知し、成功した結果のみで続行。レポートに「{section_type} セクションは取得できませんでした」と記載。
- **3/5 以下**: レポート生成を中止。全エラー内容をユーザーに報告して停止。

### Step 2.5: 分析結果のDuckDB登録（Merge）

エラーハンドリング通過後、1コマンドで一括登録：

```bash
uv run python -m garmin_mcp.scripts.merge_section_analyses /tmp/analysis_{activity_id}
```

- 全 `.json` を読み込み→DuckDBに一括挿入→成功時にtempフォルダ自動削除
- 失敗時: JSONファイルは残る（`--keep` で明示的に残すことも可能）
- 4/5 モードの場合、存在する `.json` のみが登録される

### Step 3: レポート生成

全てのセクション分析（または部分結果）が登録されたら、最終レポートを生成してください：

```bash
uv run python -m garmin_mcp.reporting.report_generator_worker {activity_id} {date}
```

## 重要事項

- **並列実行必須**: セクション分析は必ず並列で実行（トークン効率）
- **コンテキスト注入必須**: Step 2で各エージェントに事前取得CONTEXTを渡す（split以外）
- **DuckDB優先**: mcp__garmin-db__*ツールを使用してトークン削減
- **日本語出力**: 全ての分析は日本語で
- **データソース**: DuckDBのみ使用（raw JSONから直接抽出）
