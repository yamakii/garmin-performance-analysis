---
name: run-debrief
description: Post-run coaching debrief for one activity — diagnoses why a run felt harder than the HR suggests, why form (GCT / cadence / vertical oscillation) slipped, or why a specific split degraded, attributing causes in a fixed order (intensity → terrain → stated circumstances → weather + start time → recovery → form) before answering. Use when the user asks about how a completed run went (例:「今日のランは心拍以上に疲れた」「フォームの崩れの原因は？」「split 5 で毎回悪くなるのは地形？」「今日の上下動は他の日と比べてどう？」). Argument is the activity date YYYY-MM-DD (defaults to today).
argument-hint: [YYYY-MM-DD]
---

# Run Debrief（ラン後の振り返り相談）

対象日 `$ARGUMENTS`（省略時は today）のランについて、ユーザーの体感や気づきに **データで根拠を付けて**答えてください。
口調は落ち着いた丁寧なコーチ（自然な です・ます）。会話で聞かれた 1 点を診断する手順で、保存されるコーチレビュー（`/analyze-activity`）の代わりではありません。

## Step 0: 準備

```
ToolSearch(query="select:mcp__garmin-db__get_activity_by_date,mcp__garmin-db__get_run_report,mcp__garmin-db__get_splits_comprehensive,mcp__garmin-db__get_splits_elevation,mcp__garmin-db__get_weather_data,mcp__garmin-db__get_form_evaluations,mcp__garmin-db__get_form_baseline_trend,mcp__garmin-db__get_split_time_series_detail,mcp__garmin-db__get_time_range_detail,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation,mcp__garmin-db__get_performance_trends,mcp__garmin-db__save_activity_context,mcp__garmin-db__get_coaching_rules,mcp__garmin-db__get_current_standing")
```

`get_activity_by_date(date=<対象日>)` で activity_id を取り（同日に補強などがあればランを選ぶ）、同じターンで
`get_coaching_rules(scopes=["debrief", "conversation"])` と `get_current_standing(on_date=<対象日>)` を読みます。走者ルールと走者が述べた事情の扱いは
`.claude/rules/analysis/analysis-standards.md` §3 に従います。

## Step 1: まず run report を 1 本読む（必須・ここから始める）

```
mcp__garmin-db__get_run_report(activity_id=<対象ラン>)
```

このランで何が起きたかの決定的なソースはこれ 1 本です（Web のラン詳細も run note も同じ dict を読む）。
起点は **処方と実際のずれ**（`plan`）と **本人の通常の範囲から外れているか**（`signals`）の 2 つで、
`moments` / `recurrence` / `conditions` / `athlete_context` / `vs_previous` がそれを補います。

## Step 2: 質問タイプ別の追加取得（report で足りないときだけ・1 ターンで並列）

| 質問タイプ | report の次に取る | さらに必要なら |
|---|---|---|
| 「心拍以上に疲れた」「ペースが速すぎた？」 | `get_performance_trends`、`get_splits_comprehensive(statistics_only=True)`、`get_weather_data`、`get_recovery_status(date=<対象日>)`、`get_wellness_baseline_deviation(date=<対象日>)` | 直近の同種ランの `get_activity_by_date` + `get_weather_data` |
| 「フォームが崩れた」「GCT/ケイデンス/上下動が悪い」 | `get_form_evaluations`、`get_splits_comprehensive`、`get_splits_elevation`、`get_weather_data` | `get_time_range_detail(metrics=[ground_contact_time, cadence, heart_rate], statistics_only=True)` |
| 「split N で悪くなる」 | `get_splits_elevation`、`get_split_time_series_detail(split_number=N, statistics_only=True)`、比較用に良い split も 1 つ | `get_weather_data`（風向・気温） |
| 「今日の◯◯は他の日と比べてどう？」 | 当日と比較日の `get_form_evaluations` | `get_form_baseline_trend(activity_id, activity_date)` |

## Step 3: 帰属の順序（この順に潰す。飛ばさない）

原因候補は**必ずこの順**で確認し、上位で説明できるなら下位に帰属しません:

1. **強度差**: 比較対象ランとのペース差・平均 HR 差・HR drift
2. **地形**: 該当 split の獲得/損失標高。暑熱・耐久の判定は同一地形（平坦同士・登坂同士）の HR 比較で行う
3. **申告された事情**: `athlete_context` の荷物・通勤・前日の流しの持ち越し。事情で説明し、フォームや体力の変化として読まない。事情は原因の説明であって改善点ではない
4. **気象 ＋ 開始時刻**: 記録気温は開始時点のスナップショットで、終盤が暑くなるか涼しくなるかは開始時刻で決まる。暑い日の decoupling は気温だけで捨てず、条件に対してペースを落としていたか（強度）で比べられるかを判断する
5. **回復**: 当日朝の `get_recovery_status` / `get_wellness_baseline_deviation`
6. **フォーム固有**: 上記で説明が付かない残差だけ

## Step 4: 指標の読み方

- 所見は `signals` の outside かつ adverse だけ（読み方の正本は analysis-standards §2・§3）。1 本のランより `streak` と `recurrence` を信頼する
- `form_evaluations` の星は表示用のレガシー値で、単一ランの判定には使わない。期待値と実測値を見るために読む
- ユーザーが走り方の介入を申告した日は、その日を「異常」ではなく「介入の効果検証」として他日と比べる

## Step 5: 回答

- 冒頭で結論を 1〜2 文（主因は何か）。根拠は論点に必要な列だけの小さな表
- 判断の組み立て・確信度・反論への対応は analysis-standards §3、ユーザーが先に仮説を述べているときは `.claude/rules/intent-disambiguation.md` の Hypothesis-First Questions に従う
- 次回に向けた提案は 1 つ
- 保存分析をやり直したいときは `/analyze-activity <date>` を案内する（このスキルが DuckDB に書くのは `save_activity_context` だけ）
