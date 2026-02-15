# Batch Analyze Activities

`$ARGUMENTS` からアクティビティリストJSONを読み込み、セクション分析とレポート生成を連続実行してください。

## ワークフロー

1. **JSONファイル読み込み**: `$ARGUMENTS` のパスからJSONを読み込む（デフォルト: `/tmp/batch_activity_list.json`）
2. **フィルタ**: `status: "success"` のアクティビティのみ抽出
3. **各アクティビティに対して順次実行**:
   a. 5つのセクション分析エージェントを**並列実行**（Task tool）
   b. 全エージェント完了後、レポート生成コマンドを実行
   c. 進捗ログ: `[N/total] Activity {id} ({date}) complete`
4. **失敗時**: エラーログを出力してスキップ、次のアクティビティへ

## セクション分析エージェント（並列実行）

各アクティビティに対して、以下の5つのエージェントを**1つのメッセージで並列に**Task toolで呼び出してください：

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

## レポート生成

全エージェント完了後、以下のコマンドを実行：

```bash
uv run python -m garmin_mcp.reporting.report_generator_worker {activity_id} {date}
```

## 注意事項

- **コンテキスト制約**: 1回の会話で10件程度が目安。超える場合はJSONを分割して複数回実行
- **並列実行必須**: セクション分析は必ず5つ同時にTask toolで呼び出す
- **DuckDB優先**: mcp__garmin-db__* ツールを使用（エージェント内で自動）
- **日本語出力**: 全ての分析は日本語で
- **エラー耐性**: 1件の失敗で全体を止めない
