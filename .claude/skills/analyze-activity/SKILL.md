---
name: analyze-activity
description: Analyze a single running activity end-to-end — ingest the data, prefetch context, run the section-analysis agents in parallel, and store results in DuckDB for the Web app. Use when the user asks to analyze a run / activity for a date (例:「ランを分析」「10/15のアクティビティを分析」). Argument is the target date YYYY-MM-DD; defaults to today.
argument-hint: [YYYY-MM-DD]
---

# Analyze Activity Command

日付 $ARGUMENTS のアクティビティの完全な分析を、**`analyze-activity` dynamic workflow** に委譲して実行してください。

**引数なしの場合は today（実行日）を対象日とします。**

## なぜ workflow か

分析は `fetch → temp file → セクション並列分析 → proofread → DuckDB 登録` の決定論的パイプライン。
これを単一エージェントで直列に回すと遅く（特に efficiency/phase/environment/summary の4節を1コンテキストで
直列生成するのがボトルネック）、トークンも肥大する。`analyze-activity` workflow は **5セクションを並列**で分析し、
**CONTEXT をファイルに退避**して各エージェントのコンテキストを「自節分のみ」に抑える。

## 実行手順

**Workflow tool を起動するだけ**です（このスキルの指示が Workflow 呼び出しの明示的オプトインに相当します）:

```
Workflow(name="analyze-activity", args={"date": "$ARGUMENTS"})
```

- `$ARGUMENTS` が空のときは `args` を省略（workflow 内で today を解決）するか `{"date": "<today YYYY-MM-DD>"}` を渡す。
- workflow は背景で次を実行する:
  1. **Fetch**: `catch_up_ingest`（ラン・体重・補強の差分取込）＋ `ingest_activity`（当日ラン）＋
     `prefetch_activity_context` を **stdout→file** で `context.json` に退避（CONTEXT は会話に載らない）
  2. **Analyze**: efficiency / phase / environment / split を**並列**、その後 summary（兄弟 JSON を読んで整合）
  3. **Finalize**: proofreader で日本語校正 → `merge_section_analyses` で DuckDB 一括登録（成功時 temp 自動削除）

## 戻り値の扱い

workflow の戻り値に応じてユーザーへ報告:

- `status: "done"` → `succeeded` / `failed` セクションを報告。`failed` が空なら「全5セクション登録完了」。
  一部 `failed` があれば該当セクション名と `errors` を伝える。
- `status: "no_run"` → その日にランニング activity が無かった。`catch_up_summary`（差分取込の有無）を一言報告して正常終了。

## 重要事項

- **キャッチアップは取り込みのみ**: ランニング・体重・補強の未取込分を対象日まで埋めるだけ。補強・体重には section 分析を行わない
- **分析は当日のラン1件のみ**: キャッチアップで埋めた過去分は取り込むだけ
- **DuckDB 優先 / 日本語出力 / データソースは DuckDB**（workflow 内のエージェントが遵守）
- **閲覧**: 分析結果は Web 版（`packages/garmin-web`）が DuckDB から描画する（Markdown レポートは生成しない）

## 関連ファイル（保守用）

- workflow 本体: `.claude/workflows/analyze-activity.js`（純粋ロジックは `// >>> testable` ブロック、テストは `.claude/workflows/tests/analyze-activity.test.mjs`）
- セクションエージェント: `.claude/agents/unified-section-analyst.md`（節別モード対応）, `.claude/agents/split-section-analyst.md`
- 校正: `.claude/agents/proofreader.md`
- スクリプト: `garmin_mcp.scripts.prefetch_activity_context`, `garmin_mcp.scripts.merge_section_analyses`
