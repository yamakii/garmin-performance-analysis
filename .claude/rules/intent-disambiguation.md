# Intent Disambiguation Rules

## Understand user intent before acting

### Command Mappings
- "ランを分析" → MCP toolsで分析・解釈。スクリプト作成ではない
- 日本語の問題報告 → バグレポートとして扱う。コマンドとして実行しない

### Development Task Routing
コードを変える開発タスクは Issue を作成してから実装する（例外: `.claude/rules/` `.claude/skills/` `docs/` `CLAUDE.md` だけの skip レベル変更は Issue 不要、PR 本文が記録。Worktree + PR は必須）:
- **Issue 番号あり**: → 探索フェーズで `mcp__github__issue_read` (method="get") → 設計をベースにプラン作成
- **Issue 番号なし**: → `Issue: TBD` でプラン作成 → 承認後に Issue 作成
- **分解が必要** (複数の独立した作業単位): → プラン内で `/decompose` を推奨

**プランの要否と粒度は `implementation-workflow.md` Phase 0 の Tier 判定**（`design-approved` の Issue はそれ自体がプラン / リスク条件に当たればフル＝plan mode で承認 / それ以外は軽量プランを示して進む）。**プラン確定後の実装は既定で「そのセッションが worktree で実装 → PR → マージ」**（同 Phase 1 のチェックリスト）。確定時に Issue へ `design-approved` を付与する。`/implement <epic>` は **`implementation-workflow.md` の起動条件（依存ティア 2 段以上、または依存の無い 4 件以上でファイル非共有）を満たすとき**に使う。

詳細は `.claude/rules/dev/dev-reference.md` を参照。

### User Preference Adoption
- ユーザーが特定のアプローチを指示したら、代替案を提示せず即座に採用する
- 例: "ingest時にフィルタ" → query-sideフィルタを提案しない
- 例: "Garminネイティブゾーン使用" → LTHR計算を提案しない

### Hypothesis-First Questions（仮説先行の質問）
- ユーザーが自分の理解・感触を述べてから質問したら、**まず質問の意図を捉える**。字面ではなく、何を知りたい・決めたいのかを掴み、回答の冒頭で一文にして受け止める。読みが割れるときは 1 つだけ確認する（→ When Ambiguous）
- **ランで見えたことの報告**には、まず目標とプランにとっての意味を述べ、裏付けはその後に置く。**原因や判断の提案**はデータで確かめ、仮説に寄せた結論を先に決めない。どちらも `analysis-standards.md` §3 の4段で組み立てる
- **伝え方は相手を否定しない**: 一致・不一致の判定ラベルや「仮説にとらわれず」等の宣言を付けない。感触と合う部分は活かし、食い違う部分は根拠と一緒に補足として加える
- 「User Preference Adoption」とは別物: やり方の指示は即採用、事実・判断の問いは上の手順
- 会話全般とコーチング系スキル（`/coach`, `/daily-checkin`, `/run-debrief`, `/weekly-review`）の共通手順。スキルはこの節にリンクする

### Plan Approval Routing
- プランに優先度マトリクスあり → 承認後に自動で `/decompose`（再確認不要）
- プランに「推奨順」「1st/2nd/...」等の序列あり → その順序を採用
- プランに序列なし → 1つだけ確認: 「全件 Issue 化するか、特定の項目のみか」
- **承認済みプランの内容について「どれからやるか」等の再質問は禁止**

### When Ambiguous
- 1つだけ明確化質問をする（複数の質問で遅延させない）
