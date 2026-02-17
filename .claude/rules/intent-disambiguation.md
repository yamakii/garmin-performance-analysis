# Intent Disambiguation Rules

## CRITICAL: Understand user intent before acting

### Command Mappings
- "トレーニングプラン生成/作成" → `/plan-training` を実行。コード分析やアーキテクチャ議論ではない
- "ランを分析" → MCP toolsで分析・解釈。スクリプト作成ではない
- "plan modeで起動しない" → バグ報告。plan mode無効化の指示ではない
- 日本語の問題報告 → バグレポートとして扱う。コマンドとして実行しない

### User Preference Adoption
- ユーザーが特定のアプローチを指示したら、代替案を提示せず即座に採用する
- 例: "ingest時にフィルタ" → query-sideフィルタを提案しない
- 例: "Garminネイティブゾーン使用" → LTHR計算を提案しない

### When Ambiguous
- 1つだけ明確化質問をする（複数の質問で遅延させない）
