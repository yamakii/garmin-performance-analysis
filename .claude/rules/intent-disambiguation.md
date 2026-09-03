# Intent Disambiguation Rules

## CRITICAL: Understand user intent before acting

### Command Mappings
- "ランを分析" → MCP toolsで分析・解釈。スクリプト作成ではない
- "plan modeで起動しない" → バグ報告。plan mode無効化の指示ではない
- 日本語の問題報告 → バグレポートとして扱う。コマンドとして実行しない

### Development Task Routing (IMPORTANT)
全ての開発タスクで Issue を作成する（Issue なし実装は禁止）:
- **Issue 番号あり**: → 探索フェーズで `mcp__github__issue_read` (method="get") → 設計をベースにプラン作成
- **Issue 番号なし**: → `Issue: TBD` でプラン作成 → 承認後に Issue 作成
- **分解が必要** (複数の独立した作業単位): → プラン内で `/decompose` を推奨

**プラン承認後の実装は既定で `/implement <issue番号>`**（**単発 Issue でも Epic でも**）。承認時に `design-approved` を付与してから起動する。手動の developer 委任＋`/ship` は例外（L3／Workflow 不可／docs・rules の skip 微修正）で、**「単発だから手動」と判断しない**。

詳細は `.claude/rules/dev/dev-reference.md` を参照。

### User Preference Adoption
- ユーザーが特定のアプローチを指示したら、代替案を提示せず即座に採用する
- 例: "ingest時にフィルタ" → query-sideフィルタを提案しない
- 例: "Garminネイティブゾーン使用" → LTHR計算を提案しない

### Hypothesis-First Questions（仮説先行の質問）
- ユーザーが自分の理解・仮説を述べてから質問した場合（例:「ロングを3週伸ばしたら翌週カットバックだと思うが、どうすべき？」）、**先にデータで独立に判定**し、回答の冒頭で「ご理解と一致 / ここが不一致（何がどう違うか）」を明示する
- 仮説に寄せた結論を先に決めてから根拠を探さない。不一致のときは遠慮せず根拠を示して指摘する（「客観的で合理的な判断になっていますか？」と確認された 2026-08-16 の再発防止）
- 「User Preference Adoption」（実装アプローチの指示は即採用）とは別物: **事実・判断の問い**には独立判定、**やり方の指示**には即採用
- コーチング系スキル（`/daily-checkin`, `/run-debrief`）にも同じ手順が組み込まれている。会話全般でも適用する

### Plan Approval Routing
- プランに優先度マトリクスあり → 承認後に自動で `/decompose`（再確認不要）
- プランに「推奨順」「1st/2nd/...」等の序列あり → その順序を採用
- プランに序列なし → 1つだけ確認: 「全件 Issue 化するか、特定の項目のみか」
- **承認済みプランの内容について「どれからやるか」等の再質問は禁止**

### When Ambiguous
- 1つだけ明確化質問をする（複数の質問で遅延させない）
