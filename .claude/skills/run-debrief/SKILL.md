---
name: run-debrief
description: Post-run coaching consultation about one completed run — works through the questions the run raised and what the fixed run report cannot say, from the athlete's block, goals and own history, exploring the DB (query_db / get_db_catalog) rather than following a fixed recipe. Use when the user asks about or reports on a completed run (例:「今日のランは心拍以上に疲れた」「フォームの崩れの原因は？」「split 5 で毎回悪くなるのは地形？」「今日の28kmの振り返りをしたい」「このロングはさいたまに向けてどう？」). Argument is the activity date YYYY-MM-DD (defaults to today).
argument-hint: [YYYY-MM-DD]
---

# Run Debrief（ラン後の振り返り相談）

対象日 `$ARGUMENTS`（省略時は today）のランについて、走者と一緒に考えます。目的は、ランで生じた疑問や、
ランレポートの固定された枠では言えなかったことに、より広い視点のコーチとして答えることです。
レポートは走者が Web で既に見ているので、価値はその外側にあります。口調は落ち着いた丁寧なコーチ（自然な です・ます）。

## Step 0: 準備

```
ToolSearch(query="select:mcp__garmin-db__get_activity_by_date,mcp__garmin-db__get_run_report,mcp__garmin-db__get_current_standing,mcp__garmin-db__get_coaching_rules,mcp__garmin-db__get_activity_context,mcp__garmin-db__save_activity_context,mcp__garmin-db__get_db_catalog,mcp__garmin-db__query_db,mcp__garmin-db__get_race_readiness,mcp__garmin-db__get_durability_trend,mcp__garmin-db__get_long_run_progression_gate,mcp__garmin-db__get_splits_comprehensive,mcp__garmin-db__get_weather_data,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation")
```

問いが求めれば、ほかの `mcp__garmin-db__*` もその場で ToolSearch してよい（この一覧は出発点で、境界ではない）。

`get_activity_by_date(date=<対象日>)` で activity_id を取り（同日に補強などがあればランを選ぶ）、同じターンで
`get_coaching_rules(scopes=["debrief", "conversation"])`、`get_current_standing(on_date=<対象日>)`、
`get_run_report(activity_id)`、`get_activity_context(activity_ids=[...])` を読みます。

## Step 1: 走者が何を決めたい・知りたいのか

走者の問いや報告から、本当に知りたいこと・決めたいことを掴みます（`.claude/rules/intent-disambiguation.md` の
Hypothesis-First Questions）。レポートは事実として使い、言い直しません。

## Step 2: 問いを立て、DB で確かめる

答える前に「このランがこの走者の今にとって何を意味するかを言うには、何を知る必要があるか」を考えます。
問いは**このランと走者の問いから**立て、毎回同じ観点（ブロック・週・目標・履歴…）を順に並べることはしません。

立てた問いは確かめに行きます。`get_db_catalog` で何がどこにあるかを見て、`query_db` で走者自身の履歴
（比べられる過去のラン・レース、指標の推移、ブロックやレビューに書かれた判断）を引き、専用ツールは近道として使います。
問いに答えが出るか、データでは決まらないと分かるまで続けます。

## Step 3: 一緒に答える

- 判断・反論への対応、走者ルールと述べられた事情の扱いは `.claude/rules/analysis/analysis-standards.md` §3 に従う
- このスキルが DuckDB に書くのは `save_activity_context` だけ。保存分析をやり直したいときは `/analyze-activity <date>` を案内する
