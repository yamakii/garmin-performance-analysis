---
name: analyze-activity
description: Analyze a single running activity end-to-end — ingest the data, prefetch context, run the section-analysis agents in parallel, and store results in DuckDB for the Web app. Use when the user asks to analyze a run / activity for a date (例:「ランを分析」「10/15のアクティビティを分析」). Argument is the target date YYYY-MM-DD; defaults to today.
argument-hint: [YYYY-MM-DD]
---

# Analyze Activity Command

日付 $ARGUMENTS のアクティビティの完全な分析を実行してください。

**引数なしの場合は today（実行日）を対象日とします。** 以降の手順で `$ARGUMENTS` が空のときは today の日付（YYYY-MM-DD）に読み替えてください。

## ワークフロー

1. **データ収集**: ingest_activity MCP ツール（補強セッションも strength_sessions に取り込む）
2. **コンテキスト事前取得**: MCP ツールで prefetch（Bash許可不要）
3. **セクション分析**: 2つのエージェント（unified-section-analyst + split-section-analyst）を並列実行（unified は事前取得コンテキスト付き）
4. **結果登録**: merge script でDuckDBに一括登録（Web版で閲覧）

> 補強（strength_training）は **取り込みのみ**。section 分析・ペース/フォーム評価・レポートは一切行わず、unified/split agent も補強には使いません。

## 実行手順

### Step 1: データ収集

MCPツールでデータ収集・DuckDB格納を実行してください（Bash許可不要）。
以降 `$ARGUMENTS` が空の場合は today の日付（YYYY-MM-DD）を `date` として読み替えてください。

#### Step 1a: 補強（strength）セッションの取り込み

まず対象日の補強セッションを strength_sessions に取り込みます（Garminアクセス、取り込みのみ）：

```
mcp__garmin-db__ingest_strength_sessions(start_date="$ARGUMENTS", end_date="$ARGUMENTS")
```

返り値 `{inserted, updated, activity_ids}` を保持してください。`inserted + updated > 0`（補強を取り込んだ）場合のみ、サマリを取得してユーザーに一言報告：

```
mcp__garmin-db__get_strength_sessions(start_date="$ARGUMENTS", end_date="$ARGUMENTS")
```

報告例: 「補強セッションを取り込みました（N回 / active_sets X / category_counts {...}）」。補強 0 件なら何も報告不要（または「補強なし」）。
**補強には section 分析・ペース/フォーム評価を一切適用しません。** unified/split agent は補強 activity に使いません。

#### Step 1b: ランニング activity の取り込み

```
mcp__garmin-db__ingest_activity(date="$ARGUMENTS")
```

返却された `activity_id` と `date` を取得してください。

**ランなし日（補強のみ）の graceful 処理**: `ingest_activity` がランニング activity を返さない（activity_id なし）場合は、**Step 1.5〜2.5（prefetch / section分析 / merge）をスキップ**し、「ランニング activity なし。補強セッションを strength_sessions に取り込み済み（summary）」と報告して正常終了してください（エラー終了しない）。
ラン + 補強の両方がある日は、ランは通常どおり Step 1.5 以降で分析し、補強は Step 1a の取り込み + 報告のみ（分析しない）。

tempフォルダパスは `ANALYSIS_TEMP_DIR=/tmp/analysis_{activity_id}_{unix_timestamp}` として以降使用。unix_timestamp は現在時刻の秒数（例: 1709312345）。
ディレクトリは Write tool がファイル書き込み時に自動作成するため、事前の mkdir は不要。

### Step 1.5: コンテキスト事前取得（MCP ツール）

MCPツールで事前取得コンテキストを取得してください（Bash許可不要）：

```
mcp__garmin-db__prefetch_activity_context(activity_id)
```

返却されたJSONを `CONTEXT` として保持してください。

### Step 2: セクション分析（並列実行）

2つのエージェントを並列で呼び出してください。**unified-section-analyst のpromptに事前取得コンテキスト（CONTEXT）を含めること**：

```
Task: unified-section-analyst
prompt: "Activity ID {activity_id} ({date}) の efficiency / phase / environment / summary の4セクションを分析してください。
事前取得コンテキスト: {CONTEXT}
結果は {ANALYSIS_TEMP_DIR}/efficiency.json, {ANALYSIS_TEMP_DIR}/phase.json, {ANALYSIS_TEMP_DIR}/environment.json, {ANALYSIS_TEMP_DIR}/summary.json の4ファイルに保存してください。"

Task: split-section-analyst
prompt: "Activity ID {activity_id} ({date}) の全スプリットを詳細分析してください。
結果は {ANALYSIS_TEMP_DIR}/split.json に保存してください。"
```

**注意**:
- unified-section-analyst が efficiency / phase / environment / summary の4 JSON を生成する（旧4エージェントを統合）
- split-section-analyst にはCONTEXT不要（既にcomprehensive 1回で最適化済み）

### Step 2.1: エラーハンドリング（部分結果判定）

2エージェント完了後、成功/失敗を集計してください（unified は4 JSON すべてが揃って初めて成功扱い）：

- **2/2 成功**: Step 2.2 へ進む（通常フロー）
- **1/2 成功**: 失敗したエージェント名をユーザーに通知し、成功した結果のみ Step 2.2 → DuckDB に登録して続行。該当セクションが欠落している旨をユーザーに報告。
- **0/2 成功**: 分析を中止。DuckDB 登録は行わず、全エラー内容をユーザーに報告して停止。

### Step 2.2: 日本語校正パス（proofreader agent）

merge の前に、生成された JSON の日本語散文を校正してください。section 分析は稀にトークン崩れ（誤字・誤変換・活用崩れ）を出力するため、それを自動修正する品質ゲートです。

```
Task: proofreader
prompt: "{ANALYSIS_TEMP_DIR} 配下の *.json の日本語散文フィールドを校正してください。崩れ（誤字・誤変換・活用崩れ）のみを Edit で最小修正し、数値・★・キー・構造・意味は変えないでください。"
```

- **存在する `.json` のみ**を対象（4/5 モードでも可）。proofreader は崩れが無ければ何もしない
- proofreader は**散文の崩れだけ**を直す（数値・★・enum・JSON構造は保護）。詳細は `.claude/agents/proofreader.md`
- 校正完了後に Step 2.5（merge）へ進む。proofreader が失敗・skip しても、未校正のまま merge は可能（校正は best-effort の品質向上ステップ）

### Step 2.5: 分析結果のDuckDB登録（Merge）

校正パス通過後、1コマンドで一括登録：

```bash
uv run python -m garmin_mcp.scripts.merge_section_analyses {ANALYSIS_TEMP_DIR}
```

- 全 `.json` を読み込み→DuckDBに一括挿入→成功時にtempフォルダ自動削除
- 失敗時: JSONファイルは残る（`--keep` で明示的に残すことも可能）
- 4/5 モードの場合、存在する `.json` のみが登録される

DuckDB 登録の完了をもって分析は完結します。分析結果は Web 版（`packages/garmin-web`）で閲覧してください。

## 重要事項

- **補強は取り込みのみ**: 補強（strength_training）は Step 1a で strength_sessions へ取り込むだけ。section 分析・ペース/フォーム評価・レポートは行わない（unified/split agent も使わない）
- **ランなし日**: その日にランニング activity が無ければ Step 1.5〜2.5 をスキップし、補強取り込みのサマリ報告で正常終了
- **並列実行必須**: セクション分析（unified + split）は必ず並列で実行（トークン効率）
- **コンテキスト注入必須**: Step 2で unified-section-analyst に事前取得CONTEXTを渡す（split は不要）
- **DuckDB優先**: mcp__garmin-db__*ツールを使用してトークン削減
- **日本語出力**: 全ての分析は日本語で
- **データソース**: DuckDBのみ使用（raw JSONから直接抽出）
- **閲覧**: 分析結果は Web 版（`packages/garmin-web`）が DuckDB から描画する（Markdown レポートは生成しない）
