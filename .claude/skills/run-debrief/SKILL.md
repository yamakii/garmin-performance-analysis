---
name: run-debrief
description: Post-run coaching debrief for one activity — diagnoses why a run felt harder than the HR suggests, why form (GCT / cadence / vertical oscillation) slipped, or why a specific split degraded, attributing causes in a fixed order (intensity → terrain → weather + start time → recovery → form) before answering. Use when the user asks about how a completed run went (例:「今日のランは心拍以上に疲れた」「フォームの崩れの原因は？」「split 5 で毎回悪くなるのは地形？」「今日の上下動は他の日と比べてどう？」). Argument is the activity date YYYY-MM-DD (defaults to today).
argument-hint: [YYYY-MM-DD]
---

# Run Debrief（ラン後の振り返り相談）

対象日 `$ARGUMENTS`（省略時は today）のランについて、ユーザーの体感や気づきに **データで根拠を付けて**答えてください。
口調は落ち着いた丁寧なコーチ（自然な です・ます）。数値は残し、表現だけ柔らかくします。

このスキルは `/analyze-activity`（5 セクションの保存分析）の代わりではありません。会話で聞かれた 1 点を、過去の誤帰属の教訓を踏まえて診断するための手順です。

## Step 0: 準備

```
ToolSearch(query="select:mcp__garmin-db__get_activity_by_date,mcp__garmin-db__get_splits_comprehensive,mcp__garmin-db__get_splits_elevation,mcp__garmin-db__get_weather_data,mcp__garmin-db__get_form_evaluations,mcp__garmin-db__get_form_efficiency_summary,mcp__garmin-db__get_split_time_series_detail,mcp__garmin-db__get_time_range_detail,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation,mcp__garmin-db__get_performance_trends")
```

`get_activity_by_date(date=<対象日>)` で activity_id を取り、同日に複数アクティビティ（ラン＋補強）があればランを選びます。

## Step 1: 質問タイプ別の基本セット（1 ターンで並列）

| 質問タイプ | 必ず取る | 追加で取る |
|---|---|---|
| 「心拍以上に疲れた」「ペースが速すぎた？」 | `get_performance_trends`（pace/HR/drift）、`get_splits_comprehensive(statistics_only=True)`、`get_weather_data`、`get_recovery_status(date=<対象日>)`、`get_wellness_baseline_deviation(date=<対象日>)` | 比較対象ラン（直近の同種ラン）の `get_activity_by_date` + `get_weather_data` |
| 「フォームが崩れた」「GCT/ケイデンス/上下動が悪い」 | `get_form_evaluations`、`get_form_efficiency_summary`、`get_splits_elevation`、`get_weather_data` | 区間指定で `get_time_range_detail(metrics=[ground_contact_time, cadence, heart_rate], statistics_only=True)` |
| 「split N で悪くなる」「このコースのこの区間」 | `get_splits_elevation`、`get_split_time_series_detail(split_number=N, statistics_only=True)`、比較用に良い split も 1 つ | `get_weather_data`（風向・気温） |
| 「今日の◯◯は他の日と比べてどう？」 | 当日と比較日の `get_form_evaluations` / `get_form_efficiency_summary` | `get_form_baseline_trend(activity_id, activity_date)` |

## Step 2: 帰属の順序（この順に潰す。飛ばさない）

過去の誤帰属（暑熱に帰したが地形が主因、暑さの比較で気象を見ていなかった、等）を防ぐため、原因候補は **必ずこの順**で確認し、上位で説明できるなら下位に帰属しない:

1. **強度差**: 比較対象ランとのペース差・平均 HR 差・HR drift。20 s/km 速く HR +2〜3 bpm 高ければ、まず強度差で疲労を説明する
2. **地形**: `get_splits_elevation` で該当 split の獲得/損失標高。登坂 +10 m 超の split のペース低下・GCT 悪化は地形が主因。暑熱・耐久の判定は **同一地形（平坦同士・登坂同士）の HR 比較**で行う
3. **気象 ＋ 開始時刻**: `get_weather_data` の気温・湿度・風と、アクティビティの開始時刻（早朝/日中）。記録気温は開始時点のスナップショットなので、2 時間超のランでは終盤はさらに高いと扱う（下限値）。30℃ 超では decoupling を耐久性の判定に使わない（thermal drift で汚染）
4. **回復**: `get_recovery_status` / `get_wellness_baseline_deviation` の当日朝の値。睡眠不足・HRV 割れがあれば GCT・ケイデンスの鈍化と結び付けて説明できる
5. **フォーム固有**: 上記で説明が付かない残差のみをフォームの問題として扱う

## Step 3: フォーム指標の読み方（星に釣られない）

- 星評価の % 帯は指標ごとの回帰モデル σ（1.3〜3 %）を考慮していないため、**★3 でも誤差範囲**のことがある。`get_form_evaluations` の期待値と実測の差を **σ 換算**（何 σ か）してから「弱点」と呼ぶ
- 1 本の星より **符号の連続**（数ラン続けて同方向にずれているか）を信頼する
- 手動ラップの GPS 断片（距離 0.4 km 未満）はペース・ケイデンスの外れ値になるので、per-split の比較・回帰から除外する。サブ km の低ケイデンス lap は意図的な歩行/回復であり、エラーではない
- 上下動を意識して走った日など、ユーザーが介入を申告した日は、当日を「異常」ではなく「介入の効果検証」として他日と比較する

## Step 4: 回答

- 冒頭で結論を 1〜2 文（主因は何か、ユーザーの体感と一致するか）
- 根拠は小さな表（区間 / 標高 / ペース / HR / GCT など、論点に必要な列だけ）
- ユーザーが先に仮説を述べている場合、その仮説に寄せず **独立に判定してから一致/不一致を明示**する
- 次回に向けた提案は 1 つ。目的を達しているランに「失敗」「成功条件」の言葉を使わない（維持目標・改善余地として述べる）
- 質問が「保存分析をやり直したい」に及ぶ場合は `/analyze-activity <date>` を案内する（このスキルは DuckDB に書かない）
