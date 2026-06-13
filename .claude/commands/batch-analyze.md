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
   c. 2つのセクション分析エージェント（unified + split）を**並列実行**（Task tool、unified にCONTEXTをプロンプトに含める）
   d. 全エージェント完了後、一括登録: `uv run python -m garmin_mcp.scripts.merge_section_analyses /tmp/analysis_{activity_id}`
   e. レポート生成コマンドを実行
   f. 進捗ログ: `[N/total] Activity {id} ({date}) complete`
4. **失敗時**: エラーログを出力してスキップ、次のアクティビティへ（JSONファイルは残す）

## セクション分析エージェント（並列実行）

各アクティビティに対して、以下の2つのエージェント（unified + split）を**1つのメッセージで並列に**Task toolで呼び出してください。
**unified-section-analyst のpromptに事前取得コンテキスト（CONTEXT）を含めること**（split は不要）：

```
Task: unified-section-analyst
prompt: "Activity ID {activity_id} ({date}) の efficiency / phase / environment / summary の4セクションを分析してください。
事前取得コンテキスト: {CONTEXT}
結果は /tmp/analysis_{activity_id}/efficiency.json, /tmp/analysis_{activity_id}/phase.json, /tmp/analysis_{activity_id}/environment.json, /tmp/analysis_{activity_id}/summary.json の4ファイルに保存してください。"

Task: split-section-analyst
prompt: "Activity ID {activity_id} ({date}) の全スプリットを詳細分析してください。
結果は /tmp/analysis_{activity_id}/split.json に保存してください。"
```

**注意**: unified-section-analyst が efficiency / phase / environment / summary の4 JSON を生成する（旧4エージェントを統合）。

## レポート生成

全エージェント完了後、以下のコマンドを実行：

```bash
uv run python -m garmin_mcp.reporting.report_generator_worker {activity_id} {date}
```

## 注意事項

- **コンテキスト制約**: 1回の会話で10件程度が目安。超える場合はJSONを分割して複数回実行
- **並列実行必須**: セクション分析は必ず2つ（unified + split）同時にTask toolで呼び出す
- **コンテキスト注入必須**: unified-section-analyst に事前取得CONTEXTを渡す（split は不要）
- **DuckDB優先**: mcp__garmin-db__* ツールを使用（エージェント内で自動）
- **日本語出力**: 全ての分析は日本語で
- **エラー耐性**: 1件の失敗で全体を止めない
