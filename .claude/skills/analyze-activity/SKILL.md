---
name: analyze-activity
description: Analyze a single running activity end-to-end — ingest the data, prefetch the context bundle and the deterministic run report, write the one coach-review section, and store it in DuckDB for the Web app; or catch up every activity in a range that is still missing analyses. Use when the user asks to analyze a run / activity for a date, or to analyze the runs that were missed (例:「ランを分析」「10/15のアクティビティを分析」「今月の分析漏れを分析して」「直近1週間で分析できていないactivityを分析して」). Argument is the target date YYYY-MM-DD (defaults to today), or `missing [N days | YYYY-MM-DD..YYYY-MM-DD]` for catch-up mode.
argument-hint: [YYYY-MM-DD | missing [N | start..end]]
---

# Analyze Activity Command

日付 $ARGUMENTS（省略時は today）のアクティビティの分析を、**`analyze-activity` workflow** に委譲して実行してください。
workflow が取り込み → `run-note-analyst` によるコーチレビュー（`run_note`）生成 → 校正 → DuckDB 登録までを行います。
このスキルの指示が Workflow 呼び出しの明示的オプトインに相当します:

```
Workflow(name="analyze-activity", args={"date": "$ARGUMENTS"})
```

`$ARGUMENTS` が空なら `args` を省略するか `{"date": "<today>"}` を渡します。

## 戻り値の扱い

- `status: "done"` → `succeeded` に `run_note` があれば「コーチレビュー登録完了」。`failed` に入っていれば grounding ゲートの拒否理由（`errors`）をそのまま伝える。自動リトライはしない
- `status: "no_run"` → その日にランが無かった。`catch_up_summary` を一言報告して終了

分析結果は Web 版が DuckDB から描画します（Markdown レポートは作らない）。

## キャッチアップモード（`missing`）

複数日・未分析分が対象のとき（「分析漏れを分析して」「日曜と昨日のワークアウトを分析して」など）は、日付を推測せずこのモードで処理します。

1. **範囲**: `missing` 単独 → 直近 14 日、`missing 7` → 直近 N 日、`missing 2026-07-01..2026-07-31` → その範囲。日付の列挙はそれぞれを対象日にする
2. **未分析の列挙**（1 回だけ）: `mcp__garmin-db__find_unanalyzed_activities(start_date, end_date)` の結果を日付昇順の表で先に示す（0 件なら終了）
3. **直列に Workflow を起動**: DuckDB は single writer なので同時に 2 本起動しない。完了通知を受けてから次の `date` を起動する
4. 各件の報告は 1 行（日付 / activity_id / 登録可否）
5. 最後に同じ範囲で `find_unanalyzed_activities` を再実行し、残件と `errors` を報告する（自動リトライはしない）
