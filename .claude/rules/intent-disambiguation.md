# Intent Disambiguation Rules

## CRITICAL: Understand user intent before acting

### Command Mappings
- "トレーニングプラン生成/作成" → `/plan-training` を実行。コード分析やアーキテクチャ議論ではない
- "ランを分析" → MCP toolsで分析・解釈。スクリプト作成ではない
- "plan modeで起動しない" → バグ報告。plan mode無効化の指示ではない
- 日本語の問題報告 → バグレポートとして扱う。コマンドとして実行しない

### Development Task Routing (IMPORTANT)
全ての開発タスクで Issue を作成する（Issue なし実装は禁止）:
- **Issue 番号あり**: → 探索フェーズで `gh issue view` → 設計をベースにプラン作成
- **Issue 番号なし**: → `Issue: TBD` でプラン作成 → 承認後に Issue 作成
- **分解が必要** (複数の独立した作業単位): → プラン内で `/decompose` を推奨

詳細は `.claude/rules/dev/dev-standards.md` を参照。

### User Preference Adoption
- ユーザーが特定のアプローチを指示したら、代替案を提示せず即座に採用する
- 例: "ingest時にフィルタ" → query-sideフィルタを提案しない
- 例: "Garminネイティブゾーン使用" → LTHR計算を提案しない

### Plan Approval Routing
- プランに優先度マトリクスあり → 承認後に自動で `/decompose`（再確認不要）
- プランに「推奨順」「1st/2nd/...」等の序列あり → その順序を採用
- プランに序列なし → 1つだけ確認: 「全件 Issue 化するか、特定の項目のみか」
- **承認済みプランの内容について「どれからやるか」等の再質問は禁止**

### When Ambiguous
- 1つだけ明確化質問をする（複数の質問で遅延させない）
