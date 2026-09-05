---
name: weekly-review
description: Coach-perspective weekly review of the Garmin training plan for a target week W, weighing the prior completed week's results, past reviews, and goals, then saved to DuckDB. Use when the user asks for a weekly training review. Optional argument is the target week; with none, a smart default picks the current or next week based on today.
argument-hint: [target week]
---

# Weekly Review Command

**レビュー対象トレーニング週 W**（=これからこなすプラン週）の Garmin プランを、**直前の完了週 W-1 の実績**と過去レビュー・目標を踏まえて **コーチ視点でレビュー** し、DuckDB に保存してください。

レビューの単位は「対象週 W」1つに固定します。保存キー（`week_start_date`/`week_end_date`）は **W の開始日〜終了日**（週の開始曜日は `get_athlete_profile().week_start_day` に従う。既定=月曜）なので、実行日が変わっても同じ W のレビューとして扱われます（実行日でレビューがずれません）。同じ W で複数回実行した場合は**上書きせず各実行を新しい版（バージョン）として追記**し、最新版を正規（canonical）として扱います。過去版も履歴として保持され、Web の詳細ページで切り替えて閲覧できます。

専用エージェントには委任しません。**メインセッションが直接オーケストレーション**し、LLM のコーチ判断をそのまま使います。週の任意のタイミングで実行可能です。

## 引数

`$ARGUMENTS` で **対象週 W** を決めます。W の開始曜日は `get_athlete_profile().week_start_day`（既定=月曜）に従います（設定未登録なら月曜始まり）。

> **`week_start_day` の規約**: `0`=月曜 〜 `6`=日曜 の整数（Python の `date.weekday()` と同じ）。`get_athlete_profile()` に `week_start_day` が無い／null の場合は **`0`（月曜始まり）にフォールバック**します。以下「週の開始日」「週の終了日」は、この設定で決まる週境界を指します（開始日の曜日 = `week_start_day`、終了日 = 開始日の6日後）。

- **省略時（スマート既定）**: today が W 内のどこにいるかで対象週を切り替える
  - today が **週の最終日**（= 週の開始曜日の前日。既定では日曜） → 対象週 W = **翌週**（今週は消化済みなので、先を計画してレビュー）
  - today が **週の最終日以外**（既定では開始日〜終了日前日） → 対象週 W = **今週**（今いる週をレビュー）
- `$ARGUMENTS` = `this` → W = today を含む週
- `$ARGUMENTS` = `next` → W = today を含む週の **翌週**
- `$ARGUMENTS` = `YYYY-MM-DD` → W = その日を含む週

実績材料は常に **W の直前の完了週 W-1（開始日〜終了日）** を主軸とし、**W が進行中（today が W 内）なら today までに W で実走した分**を「今週ここまで」として補足的に加味します。

例（`week_start_day=0`＝既定の月曜始まり。日曜終了）:
- today = 日曜 2026-06-14（= 週の最終日）・引数なし → **W = 翌週 2026-06-15〜2026-06-21**、実績 = W-1 = 2026-06-08〜2026-06-14
- today = 火曜 2026-06-16・引数なし → **W = 今週 2026-06-15〜2026-06-21**、実績 = W-1 = 2026-06-08〜2026-06-14 ＋ 6/15・6/16 の実走（W 進行中分）
- `$ARGUMENTS` = `this`（today = 火 2026-06-16）→ W = 2026-06-15〜2026-06-21
- `$ARGUMENTS` = `next`（today = 火 2026-06-16）→ W = 2026-06-22〜2026-06-28
- `$ARGUMENTS` = 2026-06-16 → W = 2026-06-15〜2026-06-21

> `week_start_day=6`（日曜始まり・土曜終了）の例: today = 土曜 2026-06-20（= 週の最終日）・引数なし → **W = 翌週 2026-06-21〜2026-06-27**、実績 = W-1 = 2026-06-14〜2026-06-20。開始曜日が変われば各日付も同様にずれます。

## ワークフロー

1. **差分キャッチアップ ＋ コンテキスト一括取得**: `catch_up_ingest(end_date=today)` で DB を最新化（write・副作用のため prefetch とは別ステップ。処方と実績の突き合わせもここで走る）→ `prefetch_weekly_review_context(target=$ARGUMENTS)` を **1回**呼び、対象週 W の確定・W-1/W の実績・負荷/回復/補強・**W のブロックとラダー段**・W-1 の処方遵守・Garmin 衝突・目標・過去レビューを **1往復で** まとめて取得
2. **コーチ視点でレビュー生成**（このコマンドの核。目標逆算フェーズ分析 ＋ 具体的処方を含む）
3. **レビューを表示**（ブロック/ラダー段 ＋ 具体値付き評価）→ `save_weekly_review(review)` で保存 → 返ってきた `review_id` を添えて `save_weekly_prescriptions(...)` で**日別処方を構造化保存** → 完了報告

## 実行手順

### Step 1: 差分キャッチアップ ＋ コンテキスト一括取得

まず **DB を最新化** します（write・副作用があるため prefetch とは別ステップ。ランニング・体重・補強の未取込分を today まで差分取込）:

```
mcp__garmin-db__catch_up_ingest(end_date=today)
```

**日次運用なら差分は小さく、Garmin 呼び出しはわずかです（内部スロットル済み）**。`catch_up_ingest` の返却に `trend_pending`（全ドメイン成功かつ直前完了週の縦断トレンド未生成のときのみ返る `{granularity, period_start, period_end}`）があれば控えておく（Step 8 で使用）。無ければ何もしません。

`catch_up_ingest` は running ドメイン成功時に、その取込範囲の**処方と実績の突き合わせ**も行い `prescriptions_reconciled`（`{updated, done, replaced, skipped}`、失敗時 null）を返します。W-1 の遵守状況はこの結果が反映された `prescriptions_prev_week.adherence`（Step 3）から読むので、**この場で個別に照合し直す必要はありません**。

次に、**収集を1往復に集約** した `prefetch_weekly_review_context` を **1回だけ** 呼びます（`$ARGUMENTS` をそのまま `target` に渡す。省略時は `None`）:

```
mcp__garmin-db__prefetch_weekly_review_context(target=$ARGUMENTS)   # None | "this" | "next" | "YYYY-MM-DD"
```

この1発が、以前 Step 1-4 で個別に叩いていた read 系ツール（`get_athlete_profile` / 各日 `get_activity_by_date` / `get_performance_trends` / `get_weather_data` / `get_current_fitness_summary` / `get_load_trend` / `get_acwr` / `get_recovery_trend` / `get_recovery_status` / `get_wellness_baseline_deviation` / `get_strength_sessions` / `get_hiking_sessions` / `get_training_blocks` / `get_weekly_prescriptions` / `get_garmin_scheduled_workouts` / `get_weekly_review`）を **DuckDB 1往復 ＋ Garmin カレンダー1回** にまとめて返します。`target` は skill 引数と同じ規約で W を確定します（省略時のスマート既定＝today が週の最終日なら翌週・それ以外は今週、`this` / `next` / `YYYY-MM-DD` も同じ）。週の開始曜日は `athlete_profile.week_start_day`（0=月〜6=日、既定=月曜フォールバック）に従います。各コレクタは **null-on-error（additive）** なので、一部が null でも講評を破綻させないこと。

確定した対象週 W（`week_start_date`〜`week_end_date`）と実績週 W-1（`prev_start`〜`prev_end`）、開始曜日、および `week_in_progress`（today が W 内か）をユーザーに一言で提示してから次に進んでください。

### Step 2: バンドルから実績・負荷・回復・補強・山行を読む（W-1 主軸 ＋ W 進行中分）

Step 1 の `prefetch_weekly_review_context` バンドルから、以下のキーを読んで実績を把握します（**追加の MCP 呼びは原則不要**。各キーは null-on-error なので欠損は破綻させず、その旨を講評に明示する）。

- **実績（ラン）**: `activity_ids.{prev_week, current_week}` と `activities[]`（各 `{activity_id, activity_date, activity_name, distance_km, duration_seconds, performance_trends, weather}`）。走行距離・ラン回数・強度分布・心拍規律（HR discipline）・ハイライトは **主に W-1（`prev_week`）をベースに評価** し、W 進行中分（`current_week`）は「今週ここまで」の補足として扱う。`performance_trends` から pace_consistency / hr_drift / run_phase{avg_pace, avg_hr} を、暑熱・高湿度でペース解釈が要る場合のみ `weather`（気温・湿度）を読む。補強 activity にはラン用の解釈（ペース/フォーム）を適用しない。
- **フィットネスサマリー**: `fitness_summary`（vdot / Garmin native `hr_zones` / weekly_volume / recent_runs）。処方の HR ゾーン(bpm) は必ずここから引用する（計算式禁止）。
- **負荷トレンド（Step 5-A-4 のカットバック周期判定の材料）**: `load_trend.weeks`（古い→新しい、各 `{week_start, load_km(その週の総距離), acwr, status, longest_run_sec(その週の最長ラン秒。ラン無し週は null)}`）と `acwr`（`{acute_load_7d, chronic_load_28d_weekly, acwr, status}`）。`status` は undertraining(<0.8) / optimal(0.8-1.3) / caution(1.3-1.5) / high_risk(>1.5) / insufficient_data（距離ベース・HR 非依存）。週量ランプ（例: 19.94→28.82→30.99km）・ACWR 推移・連続 build 週数をこの系列から読む。
- **ロング走の連続伸長（Step 5-A-4 の主ゲート）**: `load_trend.long_run`（`{weekly_longest_sec(古い→新しい、ラン無し週は null), long_run_build_weeks(整数), cutback_due_long_run(bool)}`）。**決定的に算出済みなので再計算しない**（伸長判定 = 前週比 +3% 以上、据え置き = 前週比 75%〜103% で streak 保持、−25% 超の低下またはラン無し週でリセット。`cutback_due_long_run` = `long_run_build_weeks >= 3`）。なお最新週が進行中（`week_in_progress = true`）でロング未実施の場合、`weekly_longest_sec` の末尾は暫定値なので、確定済みの W-1 までの系列も併せて確認する。
- **回復指標（Step 5-A-5 の回復サブ分析の材料）**: `recovery.trend`（`{weeks, rhr:{median_7d, median_30d, rhr_trend}, hrv:{latest_ms, status, hrv_below_baseline_days, under_recovery}, series:[{date, resting_hr, hrv_overnight_ms}]}`。**`series` は直近14日分のみ**（「HRV 割れが2夜連続か」等の直近確認用）。中央値・`rhr_trend`・`hrv_below_baseline_days`・`under_recovery` は **8週窓で算出済みの値**なので、短い `series` から再計算しない）、`recovery.status`（`{date, recommendation, score, reasons, training_readiness, body_battery_high, sleep_score}`、`recommendation` は rest/easy/moderate/quality/unknown）、`recovery.baseline_deviation`（#555 HRV/readiness/RHR の個人ベースライン z 逸脱）。
  - `rhr_trend`: 7日中央値が 30日中央値より **2bpm 以上低ければ `improving`**、**3bpm 以上高ければ `fatigued`**、それ以外 `stable`。
  - `hrv.under_recovery`: **HRV ベースライン割れが 2夜以上連続**で `true`。これと `acwr` の高値を **AND して「積み過ぎ・回復不足」を判定**する。
  - **データ欠損時**（中央値・HRV が軒並み null、または `recommendation = unknown`）は「回復データ不足のため負荷ベースで講評」と明示する（破綻させない）。
- **山行（hiking）**: `hiking.{prev_week, current_week}`（各 `{activity_id, activity_date, duration_seconds, elapsed_duration_seconds, distance_km, elevation_gain_m, elevation_loss_m, avg_heart_rate, ...}` の配列）。山行は `activities` に入らない別ドメインなので、**週間走行距離・ACWR・フォーム評価には一切含めない**。**行動時間（`duration_seconds`）・獲得標高（`elevation_gain_m`）・平均 HR** を、**回復（脚のダメージ・疲労の持ち越し）と週全体の負荷文脈** としてのみ扱い、ラン用の解釈（ペース評価・フォーム・強度分布）は適用しない。0件なら言及不要。
- **補強（strength）**: `strength.{prev_week, current_week}`（各 `{activity_id, activity_date, active_duration_seconds, avg_heart_rate, active_sets, total_sets, category_counts, ...}` の配列。`category_counts` は `{"CRUNCH":4,"PLANK":7,...}` = ACTIVE セットのカテゴリ別本数）。**回数・実施日・所要時間（`active_duration_seconds`）・HR・セット数（`active_sets`）・カテゴリ構成** を、回復・補強遵守・故障予防の文脈でのみ扱う。0件なら「補強記録なし」。

### Step 3: W のブロックとラダー段（レビュー骨格）

**レビューの骨格は登録済みメゾサイクル（トレーニングブロック）と、その週のロング走ラダー段です**。Garmin の適応プランは骨格ではなく、**ブロックと衝突する項目だけを拾う参照材料**に降格しています（`/plan-block` で登録したブロックが正、Garmin Coach は正ではない）。

バンドルの以下のキーを読みます:

- **`training_block`**: `{block, ladder_step:{current, previous, next}, weeks_to_block_end, weight_mode, quality_sessions_per_week, quality_types}`
  - `block` は W を含むブロック（`{phase(base|build|peak|taper|race|recovery|cutback), title, start_date, end_date, purpose, weight_mode, quality_sessions_per_week, quality_types, long_run_ladder, cutback_rule, notes}`）。**null なら「ブロック未登録」**として扱い、`/plan-block` でのブロック登録を1文で促したうえで、従来どおり負荷・回復トレンドベースでレビューを続けます（停止はしない）。
  - `ladder_step.current` が **W のロング走の目標**（`{week_start, target_km または target_minutes, hr_ceiling, kind, note}`）。`previous` / `next` と比べて **今週が伸長段か据え置き段かカットバック段か**を判断します。`current` が null なら「W はラダー未定義の週」と明示する。
  - `weeks_to_block_end` は W からブロック終了までの**残り週数**（`0` = W がブロック最終週）。`quality_sessions_per_week` / `quality_types` が **W の質練枠**、`weight_mode`（絞る/維持）は体重方針です。
- **`prescriptions_prev_week`**: `{rows, adherence:{prescribed, done, replaced, skipped, pending}}`。W-1 に処方したセッションと、`catch_up_ingest` が実績と突き合わせた**遵守状況（決定的に算出済み。再計算しない）**。`rows[]` は `{date, session_type, title, target_km, target_minutes, hr_low, hr_high, status, actual_activity_id, ...}`。`prescribed=0` なら「W-1 は処方なし（初回）」と明示する。
- **`garmin_conflicts`**: `[{date, garmin_title, reason}]`。Garmin カレンダーの項目のうち **ブロックと衝突するものだけ**が決定的に抽出されています。`reason` は次の3種:
  - `quality_on_long_day`: 質練がロング走の日（週最終日）またはその前後日に置かれている
  - `second_quality_session`: ブロックの `quality_sessions_per_week` 枠を超える質練
  - `quality_in_cutback_week`: カットバック/回復/テーパー期に質練が置かれている
  - **空配列なら Garmin プランには触れない**（衝突が無いのに Garmin の項目を列挙しない）。
- **`scheduled_workouts`**（`{start_date, end_date, count, workouts:[{date, title, item_type, schedule_id, ...}]}`）は衝突の**生データ**です。`garmin_conflicts` に挙がった項目の詳細（タイトル・item_type）を引くときだけ参照し、**W プランの骨格としては使いません**。

**フォールバック**: `scheduled_workouts` が **null の場合のみ**（Garmin カレンダーの live HTTP 失敗）、直接 MCP で取得し直してください（`garmin_conflicts` も null 相当＝空になるので、衝突判定は目視で補う）:

```
mcp__garmin-db__get_garmin_scheduled_workouts(start_date=week_start_date, end_date=week_end_date)
```

### Step 4: 目標・過去レビュー（バンドルから）

バンドルの `athlete_profile`（`retrospectives` / 現フェーズ）、`goals_with_weeks_to_race[]`、`past_review`（直近の過去レビュー、無ければ null）を読みます。

- **目標はバンドル内で `goals_with_weeks_to_race[]` の1箇所だけ**にあります（重複していた `athlete_profile.goals` は除去済み）。各要素は `{race_name, race_date, priority, goal_type, distance_km, target_time_seconds, status, notes}` に **W 開始日基準の `weeks_to_race`（=`ceil((race_date − week_start_date) / 7)`、`race_date` 未確定は `null`）** を事前算出して加えたもの。`race_date` は **null になり得ます**（本命さいたまのように開催日が未確定の場合）。各レースの `priority`（A=本命 / B=中間）と `race_date` を控えて Step 5-A のフェーズ逆算で使い、Step 5-A-1 の残り週数は `weeks_to_race` をそのまま使う（null はさいたまのように未確定として扱う）。
- `past_review.review_data` には **前回指摘との連続性に使うキーだけ**が載ります（`verdict` / `recommendations` / `overall` / `goal_alignment` / `periodization` / `recovery`）。前回時点の実績サマリ（`this_week`）と前回時点のプラン（`garmin_next_week`）は、今回のバンドルに同等の最新値（`activities` / `scheduled_workouts`）があるため除去済みです。

**profile が未登録の場合**（`athlete_profile.current_focus` が null かつ `goals_with_weeks_to_race` が空）は、レビューを生成せず「先に `/set-goal` を実行して目標を登録してください」とユーザーに促して停止してください。

### Step 5: コーチ視点でレビューを生成（このコマンドの核）

以下の **評価方針** に従い、対象週 W の各ワークアウトを評価してください。

#### Step 5-A: 目標逆算フェーズ分析（必須）

対象週 W に「本来あるべきトレーニングフェーズ」を目標から逆算し、Garmin Coach の実プランとのギャップを言語化します。

**1. 各レースの残り週数を算出**

`goals_with_weeks_to_race[]` の各レース（A=本命さいたま / B=中間 新潟）について、**対象週 W の開始日（`week_start_date`）時点での残り週数**を求めます:

- `race_date` が確定している場合（例: 新潟シティマラソン 2026-10-11）:
  - `weeks_to_race = ceil((race_date − week_start_date) / 7)`（整数。週単位に切り上げ）
  - 例: W 開始日 = 2026-06-15（既定の月曜始まり）、race_date = 2026-10-11 → 約 17 週
- `race_date` が null の場合（例: さいたまマラソン、本命だが開催日 2027 年 2 月で未確定）:
  - `weeks_to_race = null` とし、レビュー文では「**約 2027 年 2 月・残り週数は概算/未確定**」と明示して扱う
  - 概算が必要なら「2027-02 中旬」を仮置きして「概算 約 N 週（未確定）」と注記する。null を黙って 0 扱いにしない

**2. W にあるべきマクロフェーズ/テーマを導出**

残り週数とユーザー重点（**回復力・筋持久力・故障再発防止／スピードは到達済み**）から、W のあるべきフェーズを判断します:

- **レースまで長い（十数週〜、概ね 12 週超）** → **有酸素ベース/筋持久力構築期**。ロング走を漸増し、低〜中強度（Z2 中心）でボリュームを積む。質練（テンポ/閾値）は週 1 を上限。
- **中盤（概ね 6〜12 週）** → **筋持久力 ＋ マラソンペース耐性期**。ロング走を維持しつつマラソンペース走/長めの閾値走を組み込む。
- **直前数週（概ね 5 週以内）** → **専門的耐久 ＋ テーパー期**。ロング走をピークから漸減、レースペース刺激を残しつつ総量を落とす。
- いずれの局面でも **スピードは到達済みなので、高強度（無酸素/インターバル/レペティション）の比重は低め** が原則。

A=さいたま（本命・長期）と B=新潟（中間・確定日）で **残り週数が大きく異なる**ため、両方の局面を踏まえて W のテーマを総合判断してください（直近の B 新潟を優先しつつ、本命 A の土台作りと矛盾しないこと）。

**3. 登録ブロックとのギャップを言語化（Garmin ではなくブロックが基準）**

Step 3 の `training_block`（`block.phase` / `block.purpose` / `ladder_step` / `weeks_to_block_end` / `quality_sessions_per_week`）を、上で導いた「あるべきフェーズ」と比較し、**ギャップを短文で言語化**します。**比較対象は Garmin Coach のプランではなく、登録済みブロックです**。観点例:

- ブロックのフェーズが目標逆算のフェーズと合っているか（`weeks_to_block_end` と残り週数の整合。ブロックがレースに対して短すぎ／長すぎないか）
- `ladder_step.current` のロング目標が、進行ゲート・カットバック判定（Step 5-A-4）と整合しているか（伸長段なのに deload が必要、等）
- 質練枠（`quality_sessions_per_week` / `quality_types`）が、あるべきフェーズの強度配分と合っているか
- ブロック未登録（`block` が null）の場合は「ブロック未登録のため逆算フェーズのみで評価」と明示し、`/plan-block` での登録を促す

ギャップは **A=さいたま視点 / B=新潟視点で分けて** 言及してください。この結果は Step 6 の表示と Step 7 の `periodization.gap`（**ブロックとのギャップ**）および `block_alignment` に反映します。

**Garmin プランの扱い**: `garmin_conflicts` が空でなければ、**衝突項目だけ**を「Garmin カレンダー側にブロックと矛盾する予定がある」として1〜2文で指摘し、削除・置換の具体案（日付・セッション種別）を添えます。空なら Garmin には言及しません。Garmin の構成傾向をフェーズ判定の根拠に使わないでください。

**4. カットバック周期サブ分析（必須）— トレンドで increase/deload を判定**

バンドルの `load_trend`（`long_run` ブロック含む）/ `acwr`（Step 2）を使い、対象週 W が **積み上げを続ける番か、カットバック（deload）の番か**を判定します。ロング・週量の伸長可否は **2つのゲート両方** で決めます:

1. **進行ゲート**（脚が崩れていないか）: 直近ロングの後半で GCT+10ms 以上 / ケイデンス5以上低下 / ペース大幅低下が無ければ「伸ばせる条件」を満たす（[[long-run-progression-two-gates]]）。
2. **カットバック周期ゲート**: 主ゲート（ロング軸）と副ゲート（週総量軸）を OR で読む。
   - **主ゲート = ロング走の連続伸長**: `load_trend.long_run.long_run_build_weeks`（`weekly_longest_sec` から決定的に算出済み）と `cutback_due_long_run`。ユーザーはロングを最優先で積むため、**軽量週でリセットされる週総量 streak ではロングのストレス蓄積を系統的に過小評価する**（実例: ロング 130→135→143 分と3週連続伸長でも週総量ベースは build 2週）。腱・骨のストレスは HRV/RHR/ACWR に現れないので、ロング軸の周期を主軸に置く。
   - **副ゲート = 週総量 / ACWR**: 週量（`load_km`）が概ね非減少で積み上がっている連続週数、前週比 −30〜40% 以上に落ちた最後のカットバック週からの経過週数、`acwr` の caution(≥1.3) / high_risk(>1.5)。
   - これを「**カットバック2-3週ごと・週まるごと −30〜40%**」ルールと照合する。

**判定**: 次のいずれかなら `cutback_due = true`（= W は deload の番）とする:
- **`cutback_due_long_run = true`（ロング連続伸長 3週以上）** — 主ゲート、または
- 週総量の連続 build 週数が **3週以上**、または
- ACWR `status` が **caution / high_risk**（≥1.3）、かつ週量や最長ロングが直近ピークを更新した直後

**重要**: 進行ゲートが GREEN（脚は崩れていない）でも、回復指標（RHR/HRV/睡眠）が全て緑でも、`cutback_due = true` を **上書きしない**（ロングの腱・骨ストレスはこれらの指標に現れないため）。新ピーク直後＋3週連続 build で「もう1週積む」助言をしてはいけない（2026-06-21 の見落としを構造的に防ぐための分岐）。`cutback_due = true` のときの W への処方は: **ロングを直近ピーク比 −30〜40% に短縮**、週量 −20〜30%、質ゼロ、休養を1日増やす。`cutback_due = false`（直近にカットバック済み／ACWR optimal で連続2週以内）なら、進行ゲート GREEN を条件に小刻みな漸進（時間 +5〜10% 程度、+10〜15% を上限）を許可する。

この結果は Step 6 の表示と Step 7 の `periodization.load_trend` に反映します。

**5. 回復サブ分析（必須）— 負荷×回復の複合講評**

バンドルの `recovery.trend` / `recovery.status`（Step 2）を使い、**先週の回復の質**を要約し、負荷（ACWR）と回復（HRV/RHR）の **両面で複合講評** します。負荷だけ・回復だけで判断せず、必ず掛け合わせて読みます:

- **RHR トレンド要約**: `rhr.rhr_trend` を「改善（`improving`）／安定（`stable`）／疲労蓄積（`fatigued`）」として、`median_7d` vs `median_30d` の bpm を添えて要約する。
- **HRV ベースライン割れ要約**: `hrv.hrv_below_baseline_days`（割れ日数）と `hrv.under_recovery` を要約する。
- **負荷×回復の複合判定**（Step 5-A-4 の ACWR/status と掛け合わせる）:
  - **ACWR 高（caution/high_risk, ≥1.3）× HRV `under_recovery=true`（または RHR `fatigued`）** → 「**積み過ぎ・回復不足**」。`cutback_due` 判定を補強し、deload を強く推す。
  - **ACWR 適正（optimal）× RHR `improving`（または HRV 正常）** → 「**順調に吸収できている**」。進行ゲート GREEN なら小刻みな漸進を許可する根拠にする。
  - **ACWR 適正 × HRV `under_recovery=true` / RHR `fatigued`** → 負荷は妥当でも回復が追いついていない。睡眠・生活要因を疑い、質練の前倒しを避ける。
- **睡眠スコアの扱い**: `recovery.status.sleep_score` が低い週（おおむね <60）は **回復不足の主因候補** として言及し、`recommendation`（rest/easy 等）と整合させる。
- **データ欠損週**: `recommendation = unknown`、または RHR/HRV 中央値が軒並み null の場合は、「**回復データ不足のため負荷ベースで講評**」と明示し、ACWR/週量だけで講評を成立させる（回復を黙って無視しない）。
- **個人ベースライン逸脱の early-warning ノート（必須）**: バンドルの `recovery.baseline_deviation`（#555）の個人ベースライン逸脱（HRV / readiness / RHR の個人比 z 逸脱）と、`hrv.under_recovery` / `hrv.hrv_below_baseline_days`（HRV ベースライン割れ日数）を取り込み、**逸脱の帰結（consequence）＋予防アクション**を1〜2文の early-warning ノートとして出す。逸脱が無ければ「ベースライン内」と明示し、ノートは出さない。例:
  - **HRV ベースライン割れ2日連続**（`under_recovery=true`）→ 「質練を −1〜2週見送り検討、easy を HR 下限で踏む」
  - **RHR `fatigued` × ACWR caution（≥1.3）** → 「翌週は deload を強く推奨（週量 −30〜40%・質ゼロ）」
  - **readiness の個人比 z が連日マイナス逸脱** → 「睡眠・生活ストレスを疑い、高強度を前倒ししない」
  - この early-warning ノートは Step 7 の `recovery.early_warning_flag`（逸脱ありで `true`）と `recovery.early_warning_note`（帰結＋予防アクションの短文。逸脱なしは null）に反映する。

この結果は Step 6 の「回復の質」表示と Step 7 の `recovery` フィールドに反映します。

#### 評価方針

- **目標観点を最優先**: ユーザーの目標は **回復力・筋持久力・故障再発防止**。スピードはすでに到達済みのため、**高強度（Anaerobic / インターバル / レペティション）の価値は低い**。スピード偏重のセッションは慎重に扱う。
- **W の各日を処方する（Garmin の予定を採点するのではない）**: ブロックのフェーズ・ラダー段・質練枠・カットバック判定から W の曜日ごとのセッションを決め、それぞれに判定を付ける:
  - ✅ = ブロック・目標に沿った処方
  - 🟡 = 条件付き（やり方次第で可。注意点を添える）
  - 🔴 = ブロック・目標と矛盾するため避ける／置き換えた（`garmin_conflicts` に挙がった Garmin 予定はここで置換案として扱う）
- **具体的処方を必須化**: 各セッションの評価コメントと `recommendations` には、**時間(分)・距離(km目安)・心拍ゾーン(bpm) または ペース** の具体値を必ず含める。「もっと走りましょう」「ベースを増やす」等の **曖昧な表現は禁止**（既存 analysis-standards の方針を本コマンドで強化）。
  - **HR ゾーンの出典**: バンドルの `fitness_summary` の `hr_zones`（Garmin native）から bpm 範囲を引用する。計算式（220−年齢 等）でゾーンを作らない。zone が取れない場合のみ努力度（RPE）で代替し、その旨を明記する。
  - **処方の具体例**（W の各セッション種別に応じて、実際の bpm はその時の `hr_zones` から差し込む）:
    - 「ロング走: Z2(例 141-152bpm)で 60-75 分(≈9-11km)、暑熱なら時間優先でペースは見ない」
    - 「Base: 40-50 分 Z2」
    - 「流し: 100m×4-6 本（疾走 20-25 秒 / 休 60 秒 jog）」
    - 「テンポ: 閾値心拍域で 15-20 分（暑熱時はペース固定せず心拍上限で）」
- **ロング走を最重要チェック**: ロング走はマラソン筋持久力の核。**`ladder_step.current` の目標（km または分）を W の処方に必ず1本入れる**（カットバック週なら短縮した形で）。ラダー段が未定義の週は、直近ロングと進行ゲートから具体値（時間/距離/HR 上限）を決めて処方し、その旨を `overall` で触れる。
- **伸長可否はトレンドで判定（W-1 単独で決めない）**: ロング・週量を「来週も伸ばすか」は、進行ゲート（脚崩れ）だけでなく **Step 5-A-4 のカットバック周期** も必ず照合する。`cutback_due = true`（**ロング連続伸長3週以上**／週総量3週連続 build／ACWR caution+・新ピーク直後）なら、進行ゲートが GREEN でも、回復指標が全て緑でも **deload を優先**して処方する（[[long-run-progression-two-gates]]）。
- **暑熱期の管理**: 気温・湿度が高い時期は、ペース目標ではなく **心拍／努力度（RPE）で管理する** よう助言する。
- **回復の質を負荷と複合で講評**: Step 5-A-5 の回復サブ分析を踏まえ、**負荷（ACWR）と回復（RHR/HRV/睡眠）を掛け合わせて** 講評する。RHR `fatigued` や HRV `under_recovery` が ACWR caution+ と重なれば「積み過ぎ・回復不足」として deload を優先。ACWR optimal × RHR `improving` なら「順調に吸収」として漸進を許可する根拠にする。睡眠スコアが低い週は回復不足の主因候補として言及する。回復データ欠損週は「回復データ不足のため負荷ベースで講評」と明示する（[[user-running-goal]] の回復力重視に直結）。
- **過去レビューとの連続性**: `get_weekly_review()` の前回指摘がどうなったか（改善した／継続課題か）に言及する。
- **中間レースの扱い**: 新潟など priority=B の中間レースは、**全力 PB を狙わず制御された練習として扱う** 方針との整合をチェックする。`goals_with_weeks_to_race[]` に中間レースがあれば、対象週 W プランがそれを過度に意識した高強度になっていないか確認する。
- **補強（strength）の考慮**: バンドルの `strength`（Step 2）で参照した補強セッションを、主に **Execution（補強メニュー遵守）** と **回復・故障予防** の観点で考慮する。ユーザー目標（**回復力・筋持久力重視／故障歴あり**, [[user-running-goal]]）に直結するため、補強の継続は積極評価する。
  - **補強がある週**: 頻度（回数）と **週内配置**（ラン高強度日と同日/連続に重なっていないか）にコメントする。`category_counts` から中身（体幹中心か等）に触れ、回復・故障予防に資するかを一言添える。高強度ランと補強が重なって回復を圧迫している場合は配置調整を助言する。
  - **補強が無い週**: 「今週は補強記録なし」と明示し、故障予防・筋持久力の観点から補強の空白を指摘する（破綻させない）。
  - 補強には **ペース/フォーム/強度分布の評価を適用しない**。`recommendations` で補強に触れる場合も、ラン処方の具体値（HR ゾーン等）とは切り分けて回復・遵守の文脈で記述する。

#### 判定結果の言語

- 日本語で出力、**コーチ的トーン**、具体的な数値を添える。
- 体言止めを避け、自然な文体で1-2文/ポイント。

### Step 6: レビューを表示

レビュー結果を以下の形式でユーザーに表示してください。冒頭に **対象週 W（プラン）と実績週 W-1** を明示する一文を入れてください（例: 「対象週 W = 2026-06-15〜2026-06-21 のプランを、実績週 W-1 = 2026-06-08〜2026-06-14 の実績で評価します」）:

- **実績サマリー（W-1 主軸、W 進行中分は補足）**: 走行距離・回数・強度分布・心拍規律・ハイライト
- **W のブロックとラダー段（レビュー骨格）**: `training_block.block.title` / `phase` と `weeks_to_block_end`（残り週数）、`ladder_step.previous → current → next` のロング目標の推移、質練枠（`quality_sessions_per_week`）を1〜2文で示す。ブロック未登録なら「ブロック未登録」と明示する。
- **W-1 の処方遵守**: `prescriptions_prev_week.adherence` を「処方 N 本中 done N / replaced N / skipped N」の形で示し、ずれた（replaced/skipped）セッションがあればその理由を実績から1文で補う。処方が無い週なら「W-1 は処方なし」と述べる。
- **目標逆算フェーズ vs 登録ブロックのギャップ（periodization）**: Step 5-A の結果を提示する。
  - 各レースの **残り週数**（A=さいたま：未確定なら「概算/未確定」、B=新潟：確定週数）
  - W に **本来あるべきフェーズ/テーマ**（`expected_phase`）
  - 登録ブロックの **フェーズ/ラダー段**（`block_alignment`、`block.title` と `ladder_step.current` に言及）
  - 両者の **ギャップ**（`gap`、A=さいたま視点 / B=新潟視点で分けて）
  - **Garmin との衝突**（`garmin_conflicts` が空でないときのみ）: 日付・タイトル・理由と置換案を1〜2文。空なら Garmin に言及しない。
  - **負荷トレンド / カットバック判定**（`load_trend`、Step 5-A-4）: **ロング連続伸長週数**（`long_run.long_run_build_weeks` と直近数週の最長ラン分）を主軸に、週量ランプ（直近数週の `load_km`）・ACWR/status・週総量の連続 build 週数を添えて示し、**今週が積み上げか deload か**（`cutback_due`）を明示する。`cutback_due = true` なら W への処方を deload（ロング直近ピーク比 −30〜40%・週量 −20〜30%・質ゼロ）として表に反映する。
- **先週の回復の質（recovery、Step 5-A-5）**: RHR トレンド（`improving`/`stable`/`fatigued` と `median_7d` vs `median_30d` の bpm）、HRV ベースライン割れ日数（`hrv_below_baseline_days`）と `under_recovery`、当日の `recommendation` / 睡眠スコアを示し、**負荷×回復の複合判定**（ACWR 高×HRV割れ→「積み過ぎ・回復不足」、ACWR 適正×RHR改善→「順調に吸収」）を一文で明示する。回復データ欠損週は「回復データ不足のため負荷ベースで講評」と明示する。
- **対象週 W の処方**（表形式）。**各行は「W にこう走る」という処方**（Garmin の予定への採点ではない）。ラダー段・質練枠・カットバック判定に沿って**曜日ごとに1行**を組み、コメントには時間/距離/HR ゾーン(bpm) または ペースの具体値を含める:

  | 日付 | セッション | 判定 | コメント |
  |------|-----------|------|---------|
  | 2026-09-13 | ロング 25km | ✅ | ラダー3段目。HR 150 を超えないように、暑ければ時間優先で 150 分目安 |
  | 2026-09-10 | 閾値 15 分 | 🟡 | 週の質練枠は1本。ロング前々日なので脚が重ければ Base 40 分へ差し替え |
  | ... | ... | ... | ... |

  判定は処方の性格を表す（✅ = ブロック通り、🟡 = 条件付き、🔴 = ブロックと矛盾するので置き換えた／避けた）。この表の各行が Step 7 で保存する **1件の処方**になります。

- **目標との整合（goal_alignment）**: 対象週 W プラン全体が目標にどれだけ沿っているか
- **recommendations**（最大2件、次回アクションは具体的に。**時間/距離/HR ゾーン(bpm) または ペースの具体値を必ず含める**）
- **overall**: 総評（ロング走の有無への言及を含む）

### Step 7: DuckDB に保存（レビュー → 構造化処方）

**2段で保存します**。まず表示内容を以下の `review` JSON に組み立てて保存し、返却された `review_id` を控えます:

```
mcp__garmin-db__save_weekly_review(review)   # -> {status, user_id, week_start_date, review_id}
```

`review` 構造:

```json
{
  "week_start_date": "YYYY-MM-DD",
  "week_end_date": "YYYY-MM-DD",
  "review_date": "YYYY-MM-DD",
  "review_data": {
    "plan_week_start": "YYYY-MM-DD",
    "actuals_week_start": "YYYY-MM-DD",
    "this_week": {
      "volume_km": 0.0,
      "run_count": 0,
      "intensity_distribution": {},
      "hr_discipline": "...",
      "highlights": ["..."]
    },
    "prev_week_adherence": {
      "prescribed": 5, "done": 3, "replaced": 1, "skipped": 1, "pending": 0
    },
    "garmin_next_week": [
      {"date": "YYYY-MM-DD", "title": "...", "type": "..."}
    ],
    "block_alignment": "新潟ビルド期3週目、ラダー3段目(25km)。あるべきフェーズと整合",
    "garmin_conflicts": [
      {"date": "YYYY-MM-DD", "garmin_title": "...", "reason": "quality_on_long_day|second_quality_session|quality_in_cutback_week"}
    ],
    "periodization": {
      "weeks_to_a_race": null,
      "a_race": "さいたまマラソン",
      "weeks_to_b_race": 17,
      "b_race": "新潟シティマラソン",
      "expected_phase": "有酸素ベース/筋持久力構築期",
      "block_phase": "build",
      "ladder_step_km": 25.0,
      "weeks_to_block_end": 2,
      "gap": "...",
      "load_trend": {
        "consecutive_build_weeks": 3,
        "last_cutback_weeks_ago": null,
        "acwr": 1.43,
        "acwr_status": "caution",
        "cutback_due": true,
        "weekly_ramp": [
          {"week": "2026-06-01", "load_km": 19.9},
          {"week": "2026-06-08", "load_km": 28.8},
          {"week": "2026-06-15", "load_km": 31.0}
        ]
      }
    },
    "recovery": {
      "rhr_trend": "improving|stable|fatigued",
      "rhr_median_7d": 48,
      "rhr_median_30d": 50,
      "hrv_below_baseline_days": 1,
      "hrv_under_recovery": false,
      "sleep_score": 72,
      "recommendation": "rest|easy|moderate|quality|unknown",
      "load_recovery_verdict": "順調に吸収|積み過ぎ・回復不足|回復データ不足のため負荷ベースで講評|...",
      "data_available": true,
      "early_warning_flag": false,
      "early_warning_note": "HRV ベースライン割れ2日連続、翌週は質練を見送り deload 推奨"
    },
    "verdict": [
      {"date": "YYYY-MM-DD", "session": "...", "rating": "✅|🟡|🔴", "comment": "..."}
    ],
    "goal_alignment": "...",
    "recommendations": ["...", "..."],
    "overall": "..."
  },
  "agent_name": "weekly-review",
  "agent_version": "1.0"
}
```

- `week_start_date` / `week_end_date` は **対象週 W の開始日・終了日**（Step 1 の prefetch が `week_start_day` に基づき確定して返したもの。これが保存キー）。同じ W で再実行すると上書きせず**新しい版を追記**し、最新版が canonical（過去版は履歴として保持）。保存キーは日付そのものなので、開始曜日を変更しても過去レコードとの互換は保たれる。
- `review_data.plan_week_start` は **W の開始日**（= week_start_date）。`review_data.actuals_week_start` は **W-1 の開始日**（= prev_start）。これにより保存レコードが「どの週のプランをどの週の実績で評価したか」を自己説明的に持つ。
- `review_date` は実行日（today）。
- `this_week` は実績サマリー（W-1 主軸、W 進行中分は補足）を格納する（キー名は互換のため `this_week` のまま）。
- `prev_week_adherence` は `prescriptions_prev_week.adherence` をそのまま転記する（再計算しない）。W-1 に処方が無ければ全て 0。
- `block_alignment` は **登録ブロックとの整合**の短文（ブロック名・フェーズ・ラダー段・残り週数に言及）。ブロック未登録なら「ブロック未登録」と記す。
- `garmin_conflicts` は バンドルの `garmin_conflicts` をそのまま転記する（**衝突のみ**。衝突が無ければ空配列）。
- `garmin_next_week` は **衝突項目だけ**を `{date, title, type}` に整形して格納する（Web 詳細ページの互換キー。衝突が無ければ空配列。Garmin の全予定を並べない）。
- `periodization` は Step 5-A の目標逆算フェーズ分析の結果を格納する:
  - `weeks_to_a_race` / `weeks_to_b_race` は **整数 or null**（null = race_date 未確定で算出不能）。`a_race` / `b_race` はレース名。
  - `expected_phase` は W にあるべきマクロフェーズ/テーマ（日本語短文）。`block_phase` / `ladder_step_km` / `weeks_to_block_end` は `training_block` の値をそのまま転記する（ラダーが分ベースなら `ladder_step_km` を null にして `expected_phase` 側に分で書く）。`gap` は **あるべきフェーズと登録ブロックのギャップ**（日本語短文、A=さいたま / B=新潟 の観点を含める。Garmin プランとのギャップではない）。
  - `load_trend` は Step 5-A-4 のカットバック周期サブ分析の結果。`long_run_build_weeks`（整数、主ゲート）/ `cutback_due_long_run`（bool、主ゲート）/ `consecutive_build_weeks`（整数）/ `last_cutback_weeks_ago`（整数 or null）/ `acwr`（数値 or null）/ `acwr_status`（文字列）/ `cutback_due`（bool、主ゲート OR 副ゲート）/ `weekly_ramp`（直近数週の `{week, load_km, longest_run_sec}` 配列）。`long_run_build_weeks` / `cutback_due_long_run` はバンドルの `load_trend.long_run` の値をそのまま転記する（再計算しない）。`cutback_due=true` のときは `expected_phase` を deload として記述し、`recommendations` / `verdict` も deload 処方（ロング直近ピーク比 −30〜40%・週量 −20〜30%・質ゼロ）に揃える。
- `recovery` は Step 5-A-5 の回復サブ分析の結果。`rhr_trend`（`improving`/`stable`/`fatigued`）/ `rhr_median_7d` / `rhr_median_30d`（bpm、null 可）/ `hrv_below_baseline_days`（整数、null 可）/ `hrv_under_recovery`（bool）/ `sleep_score`（null 可）/ `recommendation`（`recovery.status.recommendation` の go/no-go）/ `load_recovery_verdict`（負荷×回復の複合講評の短文）/ `data_available`（bool）/ `early_warning_flag`（bool）/ `early_warning_note`（str or null）。回復データ欠損週は `data_available=false` とし、`load_recovery_verdict` を「回復データ不足のため負荷ベースで講評」とする。`hrv_under_recovery=true` かつ ACWR caution+ のときは `load_recovery_verdict` を「積み過ぎ・回復不足」とし、`recommendations` / `verdict` を deload 処方に揃える。`early_warning_flag` は Step 5-A-5 の個人ベースライン逸脱の early-warning ノート（`recovery.baseline_deviation` の逸脱や HRV ベースライン割れ）が出た場合に `true`、`early_warning_note` にその帰結＋予防アクションの短文を入れる。逸脱が無ければ `early_warning_flag=false`・`early_warning_note=null`。

**次に、Step 6 の処方表と同じ内容を構造化して保存します**（`save_weekly_review` が返した `review_id` を必ず渡す。散文だけだと日次チェックインや Garmin 登録から機械的に読めないため）:

```
mcp__garmin-db__save_weekly_prescriptions(
  week_start_date=<W の開始日>,
  prescriptions=[...],
  review_id=<save_weekly_review の返り値の review_id>
)
```

`prescriptions[]` の1行 = Step 6 の表の1行:

```json
{"date":"2026-09-13","session_type":"long","title":"ロング25km 新潟ラダー3段目","target_km":25.0,
 "target_minutes":null,"hr_high":150,"hr_low":null,"rationale":"ラダー3段目。進行ゲート緑。"}
```

- `date` は **W 内の日付**（週外の日付は保存時に拒否される）。`session_type` は `long|easy|recovery|threshold|tempo|strides|rest|strength|cross` のいずれか。
- `target_km` / `target_minutes` は **時間優先のロングなら分、距離指定なら km**（両方あれば両方入れてよい。無ければ null）。
- **easy / long は HR 上限のみを入れる**（`hr_high` に上限、`hr_low` は null）。下限を入れると走行中に下限アラートで追い込むことになるため、下限は質練（閾値・テンポ）でのみ使う。
- `rationale` はその処方の根拠を1文（ラダー段・カットバック判定・回復ゲートのどれに従ったか）。
- 同じ W で再実行した場合は**新しいバッチとして追記**され、最新バッチが正になります（過去バッチは履歴として残る）。保存は日別処方が1件以上あるときだけ行い、休養日も `session_type="rest"` の行として明示的に含めてください。

### Step 8: 未生成トレンドの自動生成 ＋ 完了報告

**未生成トレンドの自動生成（`trend_pending` があるときのみ）**: Step 1 の `catch_up_ingest` 返却に `trend_pending` があった場合は、直前完了週の縦断トレンドナレーションが未生成なので、ここで自動生成します。`trend_pending`（`{granularity, period_start, period_end}`）をそのまま引数に `trend-narration` Workflow を起動してください:

```
Workflow(name="trend-narration", args=trend_pending)
```

`trend-narration` は fetch → narrate → save の3ステージで縦断トレンドを生成し DuckDB の `trend_analyses` に保存します（`saved=true` で成功）。`trend_pending` が無ければこのステップは省略します。ローカル cron の `scheduled_sync` は `trend_pending` を検出するだけで LLM ナレーション生成はできないため、weekly-review 実行がこの生成トリガーを兼ねます。

**完了報告**: 保存完了をユーザーに報告してください。どの対象週 W のプランをどの実績週 W-1 で評価したかと、**構造化保存した処方の件数**（`save_weekly_prescriptions` の `count`）を一言添え、レビューは **Web で参照可能**（一覧は週ごと最新版、詳細ページで同一週の過去版を切り替えて閲覧）になる旨も添えてください。同じ W で再実行した場合は新しい版が追記された旨も伝えてください。`trend-narration` を起動した場合は、どの期間（`period_start`〜`period_end`）のトレンドを自動生成したか（`saved` の成否）も完了報告に含めてください。

## 重要事項

- **レビューの骨格は登録ブロックとラダー段**: W のテーマ・ロング目標・質練枠は `training_block`（`/plan-block` で登録したメゾサイクル）から決める。**Garmin の適応プランは骨格ではなく、`garmin_conflicts` に挙がった衝突だけを扱う**。衝突ゼロなら Garmin に言及しない。ブロック未登録なら1文で登録を促し、負荷・回復ベースで続行する（停止しない）。
- **処方は構造化して保存する**: `save_weekly_review` → 返却 `review_id` → `save_weekly_prescriptions(week_start_date, prescriptions, review_id)` の順で必ず2段保存する。散文の verdict だけで終えない（日次チェックイン・Garmin 登録・月次ビューがこの構造化行を読む）。
- **W-1 の遵守は再計算しない**: `prescriptions_prev_week.adherence` は `catch_up_ingest` の突き合わせ結果。実績から数え直さず、そのまま引用する。
- **週の開始曜日は設定駆動**: Step 1 の `prefetch_weekly_review_context` が `athlete_profile.week_start_day`（`0`=月〜`6`=日、既定=月曜）に基づき W / W-1 の開始日・終了日を確定して返す。`week_start_day` が無い／null なら **月曜始まりにフォールバック**する。月曜開始をハードコードしない。
- **週アンカーは対象週 W（プラン週）**: 保存キーは W の開始日〜終了日（開始曜日は `get_athlete_profile().week_start_day`、既定=月曜）。同じ W の再実行は上書きせず**新しい版を追記**し、最新版を canonical として扱う（過去版は履歴として保持され、Web で閲覧可能）。
- **専用エージェント不使用**: メインセッションが直接実行する（LLM のコーチ判断をそのまま使う）。
- **日本語出力**: 全てのレビュー・コメントは日本語、コーチ的トーン、具体的な数値を添える。
- **目標逆算フェーズ分析を必ず行う**: race_date（null 可）から残り週数を算出し、あるべきフェーズ vs **登録ブロック**のギャップを `periodization` に格納する（Garmin プランとのギャップではない）。
- **具体的処方を必須化**: 各セッション評価・recommendations に時間/距離/HR ゾーン(bpm) または ペースの具体値を含める。曖昧表現は禁止。HR ゾーンはバンドルの `fitness_summary` の Garmin native zones から引用する。
- **recommendations は最大2件**、次回アクションは具体的に絞る。
- **ロング走を必ず処方する**: マラソン筋持久力の核。`ladder_step.current` の目標に沿って W に1本入れる（カットバック週は短縮形で）。
- **トレンドで判定（W-1 単独で increase/cutback を決めない）**: バンドルの `load_trend.long_run`（**主ゲート**: ロング連続伸長週数）と `load_trend.weeks`/`acwr`（副ゲート: 負荷ランプ・ACWR・週総量の連続 build 週数）を読み、Step 5-A-4 でカットバック周期を判定する。進行ゲート（脚崩れ）が GREEN でも、回復指標が全て緑でも `cutback_due=true` なら deload を優先（[[long-run-progression-two-gates]]）。
- **回復指標を負荷と複合で講評**: バンドルの `recovery.trend`/`recovery.status` で RHR トレンド・HRV ベースライン割れ・睡眠スコア・training readiness を読み、Step 5-A-5 で **負荷（ACWR）×回復（HRV/RHR）の複合講評**を行う。ACWR 高×HRV割れ→「積み過ぎ・回復不足」、ACWR 適正×RHR改善→「順調に吸収」。睡眠スコアが低い週は回復不足の主因候補として言及。回復データ欠損週は「回復データ不足のため負荷ベースで講評」と明示する。
- **目標観点を最優先**: 回復力・筋持久力・故障再発防止。高強度の価値は低い前提で評価する。
- **profile 未登録時**: `/set-goal` の実行を促して停止する。
- **任意タイミング実行可**: W が途中でも、W-1 の実績 ＋ W 進行中分でレビューする。
- **データソース**: `mcp__garmin-db__*` ツール経由。実績・負荷・回復・補強・目標・**ブロック/処方**・過去レビューは DuckDB 読取、Garmin プラン（`scheduled_workouts`）のみ Garmin カレンダーへの live アクセス（prefetch が `_safe` で null 化、null 時は Step 3 のフォールバックで直接取得）。
