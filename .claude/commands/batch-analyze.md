# Batch Analyze Activities

`$ARGUMENTS` からアクティビティリストJSONを読み込み、セクション分析とレポート生成を連続実行してください。

## ワークフロー

1. **JSONファイル読み込み**: `$ARGUMENTS` のパスからJSONを読み込む（デフォルト: `/tmp/batch_activity_list.json`）
2. **フィルタ**: `status: "success"` のアクティビティのみ抽出
3. **各アクティビティに対して順次実行**:
   a. コンテキスト事前取得:
      ```
      mcp__garmin-db__prefetch_activity_context(activity_id)
      ```
   b. 返却されたJSONを `CONTEXT` として保持
   c. 5つのセクション分析エージェントを**並列実行**（Task tool、CONTEXTをプロンプトに含める）
   d. 全エージェント完了後、一括登録: `uv run python -m garmin_mcp.scripts.merge_section_analyses /tmp/analysis_{activity_id}`
   e. レポート生成コマンドを実行
   f. 進捗ログ: `[N/total] Activity {id} ({date}) complete`
4. **失敗時**: エラーログを出力してスキップ、次のアクティビティへ（JSONファイルは残す）

## セクション分析エージェント（並列実行）

各アクティビティに対して、以下の5つのエージェントを**1つのメッセージで並列に**Task toolで呼び出してください。
**各エージェントのpromptに事前取得コンテキスト（CONTEXT）を含めること**（split以外）：

```
Task: efficiency-section-analyst
prompt: "Activity ID {activity_id} ({date}) のフォーム効率と心拍効率を分析してください。
事前取得コンテキスト: {CONTEXT}
結果は /tmp/analysis_{activity_id}/efficiency.json に保存してください。"

Task: environment-section-analyst
prompt: "Activity ID {activity_id} ({date}) の環境要因（気温、風速、地形）の影響を分析してください。
事前取得コンテキスト: {CONTEXT}
結果は /tmp/analysis_{activity_id}/environment.json に保存してください。"

Task: phase-section-analyst
prompt: "Activity ID {activity_id} ({date}) のフェーズ評価を実行してください。
事前取得コンテキスト: {CONTEXT}
結果は /tmp/analysis_{activity_id}/phase.json に保存してください。"

Task: split-section-analyst
prompt: "Activity ID {activity_id} ({date}) の全スプリットを詳細分析してください。
結果は /tmp/analysis_{activity_id}/split.json に保存してください。"

Task: summary-section-analyst
prompt: "Activity ID {activity_id} ({date}) のアクティビティタイプ判定と総合評価を生成してください。
事前取得コンテキスト: {CONTEXT}
結果は /tmp/analysis_{activity_id}/summary.json に保存してください。"
```

## レポート生成

全エージェント完了後、以下のコマンドを実行：

```bash
uv run python -m garmin_mcp.reporting.report_generator_worker {activity_id} {date}
```

## 注意事項

- **コンテキスト制約**: 1回の会話で10件程度が目安。超える場合はJSONを分割して複数回実行
- **並列実行必須**: セクション分析は必ず5つ同時にTask toolで呼び出す
- **コンテキスト注入必須**: 各エージェントに事前取得CONTEXTを渡す（split以外）
- **DuckDB優先**: mcp__garmin-db__* ツールを使用（エージェント内で自動）
- **日本語出力**: 全ての分析は日本語で
- **エラー耐性**: 1件の失敗で全体を止めない
