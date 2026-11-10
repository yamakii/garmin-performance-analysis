---
name: weekly-review
description: Coach-perspective weekly review of the Garmin training plan for a target week W, weighing the prior completed week's results, past reviews, and goals, then saved to DuckDB. Use when the user asks for a weekly training review. Optional argument is the target week; with none, a smart default picks the current or next week based on today.
argument-hint: [target week]
---

# Weekly Review Command

**レビュー対象トレーニング週 W**（=これからこなすプラン週）の処方を、**直前の完了週 W-1 の実績**と過去レビュー・目標を踏まえて **コーチ視点で組み**、DuckDB に保存してください。W が進行中（today が W 内）なら、today までに W で実走した分を「今週ここまで」として補足的に加味します。

保存キーは W の開始日・終了日（週の開始曜日は `athlete_profile.week_start_day`、0=月〜6=日、無ければ月曜）。同じ W で再実行すると**上書きせず新しい版として追記**し、最新版が正になります。専用エージェントには委任せず、メインセッションが直接オーケストレーションします。

## Step 1: 差分キャッチアップ ＋ コンテキスト一括取得

```
mcp__garmin-db__catch_up_ingest(end_date=today)                          # write。処方と実績の突き合わせもここで走る
mcp__garmin-db__prefetch_weekly_review_context(target=$ARGUMENTS)       # None | "this" | "next" | "YYYY-MM-DD"
```

バンドルは read 系ツール（`get_athlete_profile` / `get_performance_trends` / `get_load_trend` / `get_acwr` / `get_recovery_trend` / `get_recovery_status` / `get_wellness_baseline_deviation` / `get_strength_sessions` / `get_hiking_sessions` / `get_energy_balance` / `get_training_blocks` / `get_weekly_prescriptions` / `get_garmin_scheduled_workouts` ほか）の結果を 1 往復で返し、W の確定もツールに任せます。各キーは null-on-error なので、欠けたキーは「取得できなかった」と講評に明示して続けます。確定した W・W-1・`week_in_progress` を一言で示してから次に進みます。

同じターンで、走者が述べた事情と走者専用のルールを読みます（扱い方は `.claude/rules/analysis/analysis-standards.md` §3）:

```
mcp__garmin-db__get_activity_context(start_date=prev_start, end_date=week_end_date)
mcp__garmin-db__get_coaching_rules(scopes=["planning", "conversation"])
```

## Step 2: 実績・負荷・回復を読む

バンドルの値は**決定的に算出済みなので再計算しない**（判定の閾値はツール側が正本）。読む場所:

- **実績**: `activities[]`（W-1 主軸、`current_week` は補足）。走行距離・回数・強度分布・心拍規律・ハイライトを W-1 で評価する。補強・山行（`strength` / `hiking`）は別ドメインで、週間距離・ACWR・フォーム評価に含めず、ラン用の解釈（ペース・フォーム）を適用しない。回復・故障予防・週全体の負荷の文脈でだけ扱う。0 件なら「補強記録なし」と書く
- **フィットネス**: `fitness_summary`（Garmin native `hr_zones`、`gap_detected=true` なら `recent_runs` を基準にする）
- **負荷**: `load_trend`（`weeks` / `long_run` / `volume`）と `acwr`（`reason_ja` 付き）
- **回復**: `recovery.trend`（`rhr_trend`, `hrv_under_recovery` 相当の `under_recovery`）、`recovery.status`（`recommendation`, 睡眠, training readiness）、`recovery.baseline_deviation`、`recovery.long_run_recovery_cost`
- **症状**: `symptoms`（`status.flag` と `reason_ja`）
- **体重・収支**: `energy_balance`

## Step 3: W のブロックとラダー段（レビュー骨格）

**レビューの骨格は登録済みメゾサイクルとその週のロング走ラダー段**（`/plan-block` で登録したものが正。Garmin Coach の適応プランは正ではない）。

- **`training_block`**: `block`（null なら「ブロック未登録」として `/plan-block` を一文で促し、負荷・回復ベースで続ける）、`ladder_step`（`current` が W のロング目標。`previous` / `next` と比べて伸長段・据え置き段・カットバック段を判断。null なら「W はラダー未定義」）、`weeks_to_block_end`、`quality_sessions_per_week` / `quality_types`（W の質練枠）、`weight_mode`
- **`prescriptions_prev_week`**: W-1 の処方と遵守状況 `adherence`（そのまま引用。`prescribed=0` なら「W-1 は処方なし」）
- **`prescriptions_current_week`**: W に登録済みの処方（正本）。W を改訂するときは散文ではなくこの行を起点に差分を組む
- **`garmin_conflicts`**: Garmin カレンダーのうちブロックと衝突する項目だけ（`quality_on_long_day` / `second_quality_session` / `quality_in_cutback_week`）。**空なら Garmin には触れない**。`scheduled_workouts` が null（live 取得失敗）のときだけ `get_garmin_scheduled_workouts(start_date, end_date)` を直接呼んで目視で補う

## Step 4: 目標・過去レビュー

`goals_with_weeks_to_race[]`（`weeks_to_race` 算出済み。null は開催日未確定で、0 扱いにせず「概算/未確定」と書く）、`athlete_profile`（`current_focus` / `focus_notes` / `retrospectives`）、`past_review`（前回指摘との連続性に使う）を読みます。**profile が未登録**（`current_focus` が null かつ目標が空）なら、レビューを生成せず `/set-goal` を促して停止します。

## Step 5: コーチ視点でレビューを生成

### 5-A: 目標逆算フェーズ分析

**0. アンカーなしの対案（節目の週だけ）**: 次のどれかに当たる週だけ、既存計画を見ない別エージェントに W からレースまでの計画をゼロから組ませ、2 案を並べて選手に選んでもらう。

- ブロック / フェーズの境界（`weeks_to_block_end = 0`、または `block.start_date` が W 内）
- レースの直後（`load_trend.long_run.event_window.last_event.date` が W-1 内）
- レース戦略の判断（W 内にレースがある、または選手がペース配分を相談している）

通常週では実行しない。ブリーフと手順は `/plan-block` の **Step 2.5** をそのまま使う（ここに再掲しない）。この skill 固有の差分: 目標行は `goals_with_weeks_to_race[]` から転記し、バンドルの他のキーはブリーフに入れない／計画期間は W〜最も遠い `race_date`／戦略判断で起動したらレース当日のペース配分を requirements に加える／結果は Step 6 のギャップの直後に `/plan-block` Step 3 と同じ「2 つの案の違い」表で示す／**選手が選ぶまで W の処方は確定しない**（ブロックが変わるなら登録は `/plan-block` で）。

**1. W にあるべきフェーズ**: 残り週数と重点（`current_focus` / `focus_notes`）から判断する。`focus_notes` が時期ごとの局面や質練の本数を定めていればそれに従い、無ければ次を既定とする:

- 概ね 12 週超 → 有酸素ベース/筋持久力構築期（ロング漸増、Z2 中心、質練は週 1 まで）
- 概ね 6〜12 週 → 筋持久力＋マラソンペース耐性期
- 概ね 5 週以内 → 専門的耐久＋テーパー期（ロングをピークから漸減、総量を落とす）

A / B レースで残り週数が大きく違うときは、直近のレースを優先しつつ本命 A の土台と矛盾しないテーマにする。

**2. 登録ブロックとのギャップ**: `training_block` を上の「あるべきフェーズ」と比べ、ギャップを A / B レース視点に分けて短文で言語化する（ブロックの長さとレースの整合、ラダー段と 5-A-3 のゲートの整合、質練枠と強度配分）。比較対象は Garmin ではなくブロック。`garmin_conflicts` があれば衝突項目だけを 1〜2 文で指摘し、削除・置換の具体案を添える。

**3. 積み上げか deload か**: ロング・週量の伸長可否は 2 つのゲートで決める。

- **進行ゲート**: `load_trend.long_run.gate`（`get_long_run_progression_gate` の verdict / recommendation）と `recovery.long_run_recovery_cost.cost_flag`。`cost_flag = true` なら W はロングを伸ばさず同距離で反復する。`insufficient_data` は「翌朝コストは未評価」と書く
- **カットバック周期**: 次のいずれかで `cutback_due = true`
  - `load_trend.long_run.cutback_due_long_run`（ロング連続伸長。主ゲート）
  - `load_trend.long_run.cutback_due_event_window`（レース後の保護期間中に上限超過。主ゲート）
  - `load_trend.volume.consecutive_build_weeks` が 3 以上
  - `acwr.status` が caution / high_risk（≥1.3）で、週量か最長ロングが直近ピークを更新した直後
- `cutback_due = true` は、進行ゲートや回復指標が緑でも**上書きしない**（腱・骨のストレスはそれらに現れない）。代わりに発動したゲートの理由（`cutback_reason_ja` / `acwr.reason_ja` / `event_window` / 連続 build 週数）を引用する
- **deload 処方**: ロングを直近ピーク比 −30〜40%、週量 −20〜30%、質ゼロ、休養 +1 日。`cutback_due = false` なら進行ゲート GREEN を条件に小刻みな漸進（時間 +5〜10%、上限 +10〜15%）
- 保護期間中（`event_window.in_window = true`）は W のロングを `ceiling_km` 以下に収める（deload と競合したら小さい方）。`verdict = insufficient_data` なら上限を作れない旨を書き、直近の確定済みピーク以内に留める

**4. 回復 — 負荷×回復の複合講評**: 負荷だけ・回復だけで判断せず掛け合わせて読む。

- ACWR caution 以上 × HRV `under_recovery` または RHR `fatigued` → 「積み過ぎ・回復不足」。deload を強く推す
- ACWR optimal × RHR `improving`（または HRV 正常）→ 「順調に吸収」。漸進を許す根拠にする
- ACWR optimal × 回復が追いつかない → 睡眠・生活要因を疑い、質練の前倒しを避ける
- 睡眠スコアが低い週（おおむね <60）は回復不足の主因候補として触れる
- 回復データが欠けた週（`recommendation = unknown` や中央値が軒並み null）は「回復データ不足のため負荷ベースで講評」と明示する
- **症状**: `status.flag = true` なら処方を修正する（該当部位に負荷が乗る種別を落とし、ロングは直近のクリーンな距離で頭打ち、質練ゼロ。`reason_ja` を引用）。これは `cutback_due` と同格で、回復指標が緑でも優先する。W-1 に記録が無ければ「症状記録なし」と書く（黙って省かない。記録を促さない）
- **early-warning**: 個人ベースライン逸脱（`baseline_deviation`）や HRV ベースライン割れ（`under_recovery`）があれば、その帰結と予防アクション（例: 質練を 1〜2 週見送る、deload を推す、高強度を前倒ししない）を 1〜2 文のノートにする。逸脱が無ければ「ベースライン内」とだけ書く

**5. 体重・収支**: `energy_balance` と `weight_mode` を使う（目標帯の正本は `analysis/energy_balance.py`）。`window.status = ok` なら `target.verdict` を週平均の収支と目標帯の関係として一文で述べ、体重の推移（`weight.recent_median_kg` / `slope_kg_per_week`）を添える。`calibration.status` が食い違いを示すときはそれも一文で添える。記録が不足・途切れ（`insufficient` / `no_logging` / `lapsed`）や `energy_balance` が null のときは「摂取記録が不足のため体重のみで判断」と書く。途切れへの言及はこの節で 1 回だけ。

`days[]` のうち窓内で `intake_status = "suspect_low"` の日があれば、**1 つの質問にまとめて**記録が全部入っているかを聞き、答えを日ごとに `save_intake_confirmation(date, status="complete"|"incomplete", note=<本人の言葉>)` で保存する（答えが無ければ保存しない）。保存したら `get_energy_balance(end_date=<energy_balance.end_date>, window_days=7)` を読み直して講評を組む。

### 5-B: 評価方針（W の処方の組み方）

- **重点を最優先**: `current_focus` / `focus_notes` に照らして評価する。重点が高強度の優先度を下げているなら、スピード偏重のセッションは慎重に扱う
- **W の各日を処方する**（Garmin の予定を採点するのではない）: ブロックのフェーズ・ラダー段・質練枠・5-A の判定から曜日ごとに 1 行を組み、判定を付ける（✅ = ブロック通り / 🟡 = 条件付き / 🔴 = ブロックと矛盾するので置き換えた・避けた）
- **具体値を必須にする**: 各行と `recommendations` に時間（分）・距離（km）・心拍（bpm）またはペースを入れる。心拍は `fitness_summary.hr_zones` から引く
- **連続ランを制限する**: 週 3〜4 回なら 3 日連続にしない、週 5 回なら 4 日連続にしない、週 6 回なら 1 日は休養にし高強度を連続させない
- **ロング走は必ず 1 本**: `ladder_step.current` の目標を（deload なら短縮して）入れる。ラダー未定義の週は直近ロングと進行ゲートから具体値を決め、その旨を `overall` で触れる
- **暑い時期も心拍上限で管理**し、ペースは結果として扱う
- **前回指摘との連続性**: `past_review` の指摘がどうなったか（改善／継続課題）に触れる
- **中間レース（priority B）**は全力 PB を狙わず制御された練習として扱い、W がそれを過度に意識した高強度になっていないか確かめる
- **補強**は頻度と週内配置（高強度ランと同日・連続になっていないか）、`category_counts` の中身に触れる
- 散文は日本語で、ポイントごとに 1〜2 文。**散文に絵文字を書かない**（判定の記号は処方行の `rating` だけ。散文に絵文字があると保存が拒否される）

## Step 6: レビューを表示

冒頭に「対象週 W（プラン）を実績週 W-1 で評価する」旨の一文を入れ、次の順で示します:

1. **実績サマリー**（W-1 主軸、W 進行中分は補足）
2. **W のブロックとラダー段**（ブロック名・フェーズ・残り週数、ラダー `previous → current → next`、質練枠）
3. **W-1 の処方遵守**（「処方 N 本中 done / replaced / skipped」、ずれの理由を一文）
4. **目標逆算フェーズと登録ブロックのギャップ**（5-A-1/2。残り週数、あるべきフェーズ、ブロック、ギャップ、Garmin 衝突があれば。対案を出した週はその直後に表）
5. **負荷トレンドと積み上げ / deload の判定**（5-A-3。ロング連続伸長週数を主軸に、週量ランプ・ACWR を添える。保護期間中は上限 km）
6. **先週の回復の質**（5-A-4。RHR・HRV・睡眠・training readiness、負荷×回復の複合判定、症状、ロングの翌朝コスト、early-warning）
7. **体重・収支**（5-A-5。`suspect_low` の質問はここで）
8. **対象週 W の処方**（表。各行が Step 7 で保存する 1 件の処方になる）

   | 日付 | セッション | 判定 | コメント |
   |------|-----------|------|---------|
   | 2026-09-08 | イージー 35 分 | ✅ | Z2 ジョグ。HR 150 を超えないように。35 分は当日の総量 |
   | 2026-09-13 | ロング 25km | ✅ | ラダー 3 段目。HR 150 を超えないように、暑ければ時間優先で 150 分目安 |

9. **goal_alignment**、**recommendations**（最大 2 件、具体値つき）、**overall**（ロング走への言及を含む）

## Step 7: DuckDB に保存（レビュー → 構造化処方）

**2 段で保存します**。日別プランの正本は処方行だけで、レビュー JSON は背景の散文です。

```
mcp__garmin-db__save_weekly_review(review)   # -> {status, user_id, week_start_date, review_id}
```

```json
{
  "week_start_date": "YYYY-MM-DD",
  "week_end_date": "YYYY-MM-DD",
  "review_date": "YYYY-MM-DD",
  "review_data": {
    "plan_week_start": "YYYY-MM-DD",
    "actuals_week_start": "YYYY-MM-DD",
    "this_week": {"volume_km": 0.0, "run_count": 0, "intensity_distribution": {}, "hr_discipline": "...", "highlights": ["..."]},
    "prev_week_adherence": {"prescribed": 5, "done": 3, "replaced": 1, "skipped": 1, "pending": 0},
    "garmin_next_week": [{"date": "YYYY-MM-DD", "title": "...", "type": "..."}],
    "block_alignment": "ビルド期 3 週目、ラダー 3 段目 (25km)。あるべきフェーズと整合",
    "garmin_conflicts": [{"date": "YYYY-MM-DD", "garmin_title": "...", "reason": "..."}],
    "periodization": {
      "weeks_to_a_race": null, "a_race": "<A レース名>", "weeks_to_b_race": 17, "b_race": "<B レース名>",
      "expected_phase": "...", "block_phase": "build", "ladder_step_km": 25.0, "weeks_to_block_end": 2, "gap": "...",
      "load_trend": {
        "long_run_build_weeks": 3, "cutback_due_long_run": true, "consecutive_build_weeks": 3,
        "last_cutback_weeks_ago": null, "acwr": 1.43, "acwr_status": "caution",
        "cutback_due_event_window": false, "cutback_due": true,
        "weekly_ramp": [{"week": "YYYY-MM-DD", "load_km": 31.0, "longest_run_sec": 6000}]
      }
    },
    "recovery": {
      "rhr_trend": "stable", "rhr_median_7d": 48, "rhr_median_30d": 50,
      "hrv_below_baseline_days": 1, "hrv_under_recovery": false, "sleep_score": 72,
      "recommendation": "easy", "load_recovery_verdict": "順調に吸収", "data_available": true,
      "early_warning_flag": false, "early_warning_note": null,
      "symptom_flag": false, "symptom_note": "症状記録なし",
      "long_run_recovery_cost": {"activity_id": 0, "criteria_fired": 2, "cost_flag": true, "insufficient_data": false}
    },
    "weight_tracking": {"recent_median_kg": null, "trend": "...", "flag": "...", "energy": {"...": "下記の 6 キー"}},
    "goal_alignment": "...",
    "recommendations": ["...", "..."],
    "overall": "..."
  },
  "agent_name": "weekly-review",
  "agent_version": "1.0"
}
```

- **バンドルの値は再計算せずそのまま転記する**: `prev_week_adherence` ← `prescriptions_prev_week.adherence`、`garmin_conflicts` ← 同名キー（`garmin_next_week` は衝突項目だけを `{date, title, type}` に整形）、`periodization.load_trend` の各値 ← `load_trend.long_run` / `load_trend.volume` / `acwr`、`block_phase` / `ladder_step_km` / `weeks_to_block_end` ← `training_block`（ラダーが分ベースなら `ladder_step_km` は null）、`recovery.symptom_flag` ← `symptoms.status.flag`、`recovery.long_run_recovery_cost` ← バンドルの同名キーから 4 項目（ロングが無ければ null）、`weight_tracking.recent_median_kg` ← `energy_balance.weight.recent_median_kg`、`weight_tracking.energy` ← `window.mean_balance_kcal` / `window.paired_days` / `window.required_days` / `target.verdict` / `target.calibration_status` / `logging.lapsed`（`energy_balance` が null なら null）
- 言葉で書くもの: `block_alignment`、`expected_phase`、`gap`、`load_recovery_verdict`、`early_warning_note`（逸脱なしは null）、`symptom_note`（null にしない）、`weight_tracking.trend` / `flag`、`goal_alignment`、`recommendations`、`overall`。`cutback_due` や「積み過ぎ・回復不足」・`cost_flag` の結論は、`expected_phase` / `recommendations` / 処方行を同じ向きに揃える
- `plan_week_start` は W の開始日、`actuals_week_start` は W-1 の開始日、`review_date` は today

**次に、Step 6 の処方表を構造化して保存します**（`save_weekly_review` が返した `review_id` を必ず渡す）:

```
mcp__garmin-db__save_weekly_prescriptions(week_start_date=<W の開始日>, prescriptions=[...], review_id=<review_id>)
```

```json
{"date":"2026-09-13","session_type":"long","purpose":"long_easy","allowances":{"walk":true},
 "title":"ロング25km ラダー3段目","target_km":25.0,"target_minutes":null,"hr_high":150,"hr_low":null,
 "rating":"✅","rationale":"ラダー3段目。進行ゲート緑。補給の歩きは可。"}
{"date":"2026-09-10","session_type":"easy","purpose":"easy","target_km":null,"target_minutes":35,"hr_high":150,"hr_low":null,
 "workout":{"template":"easy_strides","params":{"minutes":35,"hr_high":150,"reps":4}},
 "rating":"✅","rationale":"脚の回転を保つ神経筋刺激。35分は流しを含む当日の総量。"}
```

`session_type` / `purpose` / `allowances` / `workout` テンプレートの語彙・組み合わせ・パラメータの正本は `save_weekly_prescriptions` のツール説明で、合わない値は保存時に拒否されます。ここでは次の規約だけを守ります:

- 各行の判定 = `rating`、コメント = `rationale`（ラダー段・カットバック判定・回復ゲートのどれに従ったかを 1 文）。レビュー JSON 側には保存しない
- `purpose` は一般的なコーチングのカテゴリで、選手ごとの事情（ラダー段・レース名）は `title` / `rationale` に書く。**登録済みレースの当日は `purpose="race"`** を必ず入れる
- 質練と流しは `workout` のテンプレートで書く（流しは `easy_strides`）。心拍は bpm の整数で、`hr_zones` から換算する
- easy / long は **HR 上限だけ**を入れる（`hr_low` は null。下限は質練だけ）
- **`target_minutes` の定義**: `long` / `easy` / `recovery` は**その日走る全体（総量）**。W/U ＋本体＋C/D に分けた**本体だけの分数を入れてはいけない**。`threshold` / `tempo` は**本体のみ**の分数（前後 15 分はツールが足す）。`target_km` はどのセッションでも全体の距離
- **タイトル・コメントは `target_minutes` と別の総量を名乗らない**（表示・時計・判定が同じ数字を指すこと）
- 休養日も `session_type="rest"` の行として含める。同じ W の再保存は新しいバッチとして追記され、**新しいバッチは新しいレビュー版とペアで保存**する（同じ `review_id` で 2 度目のバッチは拒否される）

## Step 7.5: 週の途中でプランを改訂するとき

処方だけを保存し直すことはできません（散文と処方がずれるため）。プランを改訂するときは:

1. 改訂後の方針で `save_weekly_review(review)` を呼び、`review_data.revision_note` に改訂理由を 1 文入れる。返った新しい `review_id` を控える
2. `save_weekly_prescriptions(week_start_date, prescriptions=[改訂後の全日分], review_id=<新しい review_id>)`
3. 返り値の `needs_reregistration` があるときだけ、ユーザーに確認してから `schedule_weekly_prescriptions(week_start_date=<W>, dry_run=False)` でカレンダーを揃える（返り値の扱いは `/schedule-workout`）

どの行をどう変えたかと理由を一言で報告します。

## Step 8: 未生成トレンドの生成 ＋ 完了報告

`get_pending_trend_period(end_date=today)` を呼び、`null` 以外が返ったら `Workflow(name="trend-narration", args=pending)` を起動します。完了通知で `saved` を確かめてから再度問い合わせ、`null` になるまで古い順に繰り返します。停止条件: `null` / `saved` が true でない / 同じ期間が再び返る / 起動が 4 回に達した。失敗はその期間と理由を報告し、自動リトライはしません。

**完了報告**: どの W をどの W-1 で評価したか、保存した処方の件数（`count`）、Web で参照できること（同じ W の再実行は新しい版）、生成したトレンド期間と `saved` の成否を伝えます。
