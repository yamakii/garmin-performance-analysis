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

1. **対象週 W を確定**: `get_athlete_profile().week_start_day`（既定=月曜）を読み、引数（または today）から W の開始日（`week_start_date`）・終了日（`week_end_date`）、W-1 の開始日（`prev_start`）・終了日（`prev_end`）を算出
2. **実績収集**: W-1（開始日〜終了日）を主軸に各日 `get_activity_by_date` で activity_id を集め、`get_performance_trends` 等で実績を把握。W が進行中なら today までの W の実走も加味。あわせて `get_load_trend`/`get_acwr` で複数週の負荷トレンド（週量ランプ・ACWR・連続 build 週数）を収集し、カットバック周期を判定。さらに `get_recovery_trend`/`get_recovery_status` で RHR/HRV/睡眠/training readiness を収集し、回復の質を負荷と複合で講評
3. **W の Garmin プラン取得**: `get_garmin_scheduled_workouts(week_start_date, week_end_date)`
4. **コンテキスト読込**: `get_athlete_profile()`（目標）+ `get_weekly_review()`（直近の過去レビュー）
5. **コーチ視点でレビュー生成**（このコマンドの核。目標逆算フェーズ分析 ＋ 具体的処方を含む）
6. **レビューを表示**（フェーズギャップ ＋ 具体値付き評価）→ `save_weekly_review(review)` で保存 → 完了報告

## 実行手順

### Step 1: 対象週 W を確定

まず **週の開始曜日** を取得します（これが日付算出の基準）:

```
mcp__garmin-db__get_athlete_profile()   # 返却に week_start_day（0=月〜6=日）があれば採用
```

- `week_start_day` が **存在すればその曜日**を週の開始曜日とする（例: `0`=月曜始まり、`6`=日曜始まり）。
- `week_start_day` が **無い／null**（設定未登録）の場合は **`0`（月曜始まり）にフォールバック**する。

次に `$ARGUMENTS` と today から **対象週 W** を決定し、設定した開始曜日に基づいて W と直前週 W-1 の開始日・終了日を算出してください:

- 引数なし: today が **週の最終日**（= 開始曜日の前日。既定では日曜）なら W = 翌週、それ以外なら W = 今週
- `this`: W = today を含む週
- `next`: W = today を含む週の翌週
- `YYYY-MM-DD`: W = その日を含む週

「ある日付 D を含む週の開始日」は、`D` から **`(D.weekday() - week_start_day) mod 7` 日だけ遡った日** です（既定 `week_start_day=0` ならその週の月曜）。算出する日付:

- `week_start_date` = **W の開始日**（保存キー。曜日 = `week_start_day`）
- `week_end_date` = **W の終了日**（保存キー。= week_start_date の6日後）
- `prev_start` = **W-1 の開始日**（= week_start_date の7日前）
- `prev_end` = **W-1 の終了日**（= week_start_date の前日）

確定した対象週 W（week_start_date〜week_end_date）と実績週 W-1（prev_start〜prev_end）、設定した開始曜日（既定=月曜）、および「W が進行中か（today が W 内か）」をユーザーに一言で提示してから次に進んでください。

### Step 2: 実績収集（W-1 主軸 ＋ W 進行中分）

#### Step 2-0: 差分キャッチアップ（実績を読む前に1回）

実績を読み始める前に、**DB を最新化するため catch_up_ingest を1回だけ呼んでください**（ランニング・体重・補強の未取込分を today まで差分取込）:

```
mcp__garmin-db__catch_up_ingest(end_date=today)
```

**日次運用なら差分は小さく、Garmin 呼び出しはわずかです（内部スロットル済み）**。これ以降の `get_activity_by_date` / `get_strength_sessions` / `get_current_fitness_summary` 等は**すべて DB 読取**（Garmin 非アクセス）で、最新化されたデータを読みます。

#### Step 2-1: 各日の実績収集

実績の主軸は **直前の完了週 W-1（`prev_start`〜`prev_end`）** です。各日について MCP ツールで実績を集めてください（Bash 許可不要）:

```
# W-1 の各日について（prev_start〜prev_end）
mcp__garmin-db__get_activity_by_date(date="YYYY-MM-DD")
```

**W が進行中の場合**（today が `week_start_date`〜`week_end_date` 内）は、W の開始日から today までの各日も同様に収集し、「今週ここまで」の実走として加味してください:

```
# W 進行中分（week_start_date〜today）※ W が進行中のときのみ
mcp__garmin-db__get_activity_by_date(date="YYYY-MM-DD")
```

activity_id が取得できた日について、詳細を取得します:

```
mcp__garmin-db__get_performance_trends(activity_id)   # pace_consistency, hr_drift, run_phase{avg_pace, avg_hr}
```

暑熱期や高湿度でペース解釈が必要な場合のみ、天候も取得します:

```
mcp__garmin-db__get_weather_data(activity_id)         # 気温・湿度
```

週全体の俯瞰として、直近1週間のフィットネスサマリーを取得します:

```
mcp__garmin-db__get_current_fitness_summary(lookback_weeks=1)   # vdot, hr_zones, weekly_volume, recent_runs
```

期間トレンド（ペース・心拍の推移）が必要なら、収集した activity_ids を渡して取得します:

```
mcp__garmin-db__analyze_performance_trends(metric="pace", start_date=prev_start, end_date=prev_end, activity_ids=[...])
```

走行距離・ラン回数・強度分布・心拍規律（HR discipline）・ハイライトは **主に W-1 をベースに評価** し、W 進行中分は「今週ここまで」の補足として扱ってください。

#### 補強（strength）の収集

ラン実績とは別に、**補強（筋トレ/補強）セッション**を DuckDB から収集してください。期間は W-1（`prev_start`〜`prev_end`）を主軸とし、**W が進行中なら W の開始日〜today** も加味します（ラン実績と同じ期間方針）:

```
mcp__garmin-db__get_strength_sessions(start_date=prev_start, end_date=prev_end)
# W が進行中ならもう一度: start_date=week_start_date, end_date=today
```

返却は `{activity_id, activity_date, start_time_local, activity_name, active_duration_seconds, elapsed_duration_seconds, avg_heart_rate, max_heart_rate, calories, active_sets, total_sets, category_counts, ...}` の配列です。`category_counts` は `{"CRUNCH":4,"PLANK":7,...}` の形で、ACTIVE セットのカテゴリ別本数（=体幹中心か等、補強の中身）を表します。

収集する観点: **補強の回数・実施日・所要時間（`active_duration_seconds`）・HR・セット数（`active_sets`）・カテゴリ構成（`category_counts`）**。

- **補強は DB のみから読む（Garmin 非アクセス）**。最新化は Step 2-0 の catch_up_ingest が冒頭で一括して済ませているため、この収集ステップで個別の取り込みは呼ばない。
- 補強には **ペース/フォーム評価を適用しない**（`get_performance_trends` 等のラン用ツールは補強 activity に使わない）。回復・補強遵守・故障予防の文脈でのみ扱う。
- 補強が0件の期間でも問題ありません。空配列ならそのまま「補強記録なし」として扱います。

#### Step 2-2: 負荷トレンド収集（複数週・カットバック周期判定の材料）

**W-1 単独では「積み上げ何週目か／カットバックの番か」が分かりません。** ロング・週量の伸長可否を周期で判断するため、複数週の負荷トレンドを必ず収集してください（catch_up 後の DB 読取・Garmin 非アクセス）:

```
mcp__garmin-db__get_load_trend(lookback_weeks=10, end_date=today)
mcp__garmin-db__get_acwr(end_date=today)
```

- `get_load_trend` は `weeks`（古い→新しい）配列を返し、各要素は `{week_start, load_km(その週の総距離), acwr, status}`。週量ランプ（例: 19.94→28.82→30.99km）と ACWR 推移をこの系列から読む。
- `get_acwr` は `{acute_load_7d, chronic_load_28d_weekly, acwr, status}`。`status` は undertraining(<0.8) / optimal(0.8-1.3) / caution(1.3-1.5) / high_risk(>1.5) / insufficient_data。いずれも距離ベース・HR 非依存。
- この2つの結果は **Step 5-A の「カットバック周期サブ分析」** で使います。

#### Step 2-3: 回復指標収集（RHR / HRV / 睡眠 / training readiness）

**負荷（ACWR）だけでは「積み過ぎが回復で吸収できているか」が分かりません。** 先週の回復の質を講評に織り込むため、回復トレンドと当日の回復ステータスを収集してください（catch_up 後の DB 読取・Garmin 非アクセス）:

```
mcp__garmin-db__get_recovery_trend(weeks=8)
mcp__garmin-db__get_recovery_status()        # 引数なし = daily_wellness の最新日
mcp__garmin-db__get_wellness_baseline_deviation()  # 個人ベースライン逸脱（#555）
```

- `get_recovery_trend` は `{weeks, rhr, hrv, series}` を返す。
  - `rhr` = `{median_7d, median_30d, rhr_trend}`。`rhr_trend` は 7日中央値が 30日中央値より **2bpm 以上低ければ `improving`（回復良好）**、**3bpm 以上高ければ `fatigued`（疲労蓄積）**、それ以外は `stable`。
  - `hrv` = `{latest_ms, status, hrv_below_baseline_days, under_recovery}`。`under_recovery` は **HRV ベースライン割れが 2夜以上連続**で `true`。これと `get_acwr` の高値を **AND して「積み過ぎ・回復不足」を判定**する。
  - `series` は `[{date, resting_hr, hrv_overnight_ms}]`（日付昇順）。中央値・HRV は欠損時 null（デバイスオフ日はスキップ）。
- `get_recovery_status` は `{date, recommendation, score, reasons, training_readiness, body_battery_high, sleep_score}`。`recommendation` は rest/easy/moderate/quality/unknown。デバイスオフ日（readiness も sleep も無し）は `unknown`。
- `get_wellness_baseline_deviation`（#555）は HRV / readiness / RHR の **個人ベースラインからの z 逸脱**を返す。これを使い、逸脱が出ている指標と**何日連続で割れているか**を把握し、Step 5-A-5 で early-warning ノート（逸脱の帰結＋予防アクション）を出す。
- これらは **Step 5-A-5 の「回復サブ分析」** と Step 6 の回復講評で使います。
- **データ欠損時**: `rhr.median_7d` / `hrv.latest_ms` などが軒並み null、または `recommendation = unknown` の場合は、回復データ不足として扱い、講評では「回復データ不足のため負荷ベースで講評」と明示する（破綻させない）。

### Step 3: W の Garmin プランの取得

```
mcp__garmin-db__get_garmin_scheduled_workouts(start_date=week_start_date, end_date=week_end_date)
```

返却は `[{date, title, item_type, training_plan_id, training_plan_name, workout_uuid}]` の配列です。これが **レビュー対象** の対象週 W プランです。

### Step 4: コンテキスト読込（目標・過去レビュー）

```
mcp__garmin-db__get_athlete_profile()    # goals / retrospectives / 現フェーズ
mcp__garmin-db__get_weekly_review()       # 引数なし = 直近の過去レビュー
```

`get_athlete_profile()` の `goals` は `{race_name, race_date, priority, goal_type, distance_km, target_time_seconds, status, notes}` の配列です。`race_date` は **null になり得ます**（本命さいたまのように開催日が未確定の場合）。各レースの `priority`（A=本命 / B=中間）と `race_date` を控えておき、Step 5-A のフェーズ逆算で使ってください。

**profile が未登録の場合**は、レビューを生成せず「先に `/set-goal` を実行して目標を登録してください」とユーザーに促して停止してください。

### Step 5: コーチ視点でレビューを生成（このコマンドの核）

以下の **評価方針** に従い、対象週 W の各ワークアウトを評価してください。

#### Step 5-A: 目標逆算フェーズ分析（必須）

対象週 W に「本来あるべきトレーニングフェーズ」を目標から逆算し、Garmin Coach の実プランとのギャップを言語化します。

**1. 各レースの残り週数を算出**

`goals` の各レース（A=本命さいたま / B=中間 新潟）について、**対象週 W の開始日（`week_start_date`）時点での残り週数**を求めます:

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

**3. Garmin Coach 実プランとのギャップを言語化**

Step 3 で取得した対象週 W プラン（`training_plan_name` / `training_plan_id`、各セッションの `title`・`item_type`）の構成傾向を、上で導いた「あるべきフェーズ」と比較し、**ギャップを短文で言語化**します。観点例:

- フェーズの前倒し（まだ有酸素ベース期なのに専門的な質練やレース刺激が多い 等）
- 質練比重の偏り（高強度/無酸素セッションが過多で、Z2 ベースやロング走が不足）
- ロング走の有無・位置づけ（あるべき局面なのにロング走が無い／距離が不足）

ギャップは **A=さいたま視点 / B=新潟視点で分けて** 言及してください。この結果は Step 6 の表示と Step 7 の `periodization` フィールドに反映します。

**4. カットバック周期サブ分析（必須）— トレンドで increase/deload を判定**

Step 2-2 の `get_load_trend` / `get_acwr` を使い、対象週 W が **積み上げを続ける番か、カットバック（deload）の番か**を判定します。ロング・週量の伸長可否は **2つのゲート両方** で決めます:

1. **進行ゲート**（脚が崩れていないか）: 直近ロングの後半で GCT+10ms 以上 / ケイデンス5以上低下 / ペース大幅低下が無ければ「伸ばせる条件」を満たす（[[long-run-progression-two-gates]]）。
2. **カットバック周期ゲート**: `get_load_trend.weeks` から以下を算出する。
   - **連続 build 週数**: 直近で週量（`load_km`）が概ね非減少（前週比プラス〜横ばい）で積み上がっている連続週数。
   - **最後のカットバック週からの経過**: 前週比 −30〜40% 以上に落ちた週からの経過週数。
   - **ACWR / status**: caution(≥1.3) は ramp 過多の注意、high_risk(>1.5) は強い警告。
   - これを「**カットバック2-3週ごと・週まるごと −30〜40%**」ルールと照合する。

**判定**: 次のいずれかなら `cutback_due = true`（= W は deload の番）とする:
- 連続 build 週数が **3週以上**、または
- ACWR `status` が **caution / high_risk**（≥1.3）、かつ週量や最長ロングが直近ピークを更新した直後

**重要**: 進行ゲートが GREEN（脚は崩れていない）でも、`cutback_due = true` なら **deload を優先**する。新ピーク直後＋3週連続 build で「もう1週積む」助言をしてはいけない（2026-06-21 の見落としを構造的に防ぐための分岐）。`cutback_due = true` のときの W への処方は: 週量 −30〜40%、ロングは短縮（直近ロングから −25〜35%）、質ゼロ、休養を1日増やす。`cutback_due = false`（直近にカットバック済み／ACWR optimal で連続2週以内）なら、進行ゲート GREEN を条件に小刻みな漸進（時間 +5〜10% 程度、+10〜15% を上限）を許可する。

この結果は Step 6 の表示と Step 7 の `periodization.load_trend` に反映します。

**5. 回復サブ分析（必須）— 負荷×回復の複合講評**

Step 2-3 の `get_recovery_trend` / `get_recovery_status` を使い、**先週の回復の質**を要約し、負荷（ACWR）と回復（HRV/RHR）の **両面で複合講評** します。負荷だけ・回復だけで判断せず、必ず掛け合わせて読みます:

- **RHR トレンド要約**: `rhr.rhr_trend` を「改善（`improving`）／安定（`stable`）／疲労蓄積（`fatigued`）」として、`median_7d` vs `median_30d` の bpm を添えて要約する。
- **HRV ベースライン割れ要約**: `hrv.hrv_below_baseline_days`（割れ日数）と `hrv.under_recovery` を要約する。
- **負荷×回復の複合判定**（Step 5-A-4 の ACWR/status と掛け合わせる）:
  - **ACWR 高（caution/high_risk, ≥1.3）× HRV `under_recovery=true`（または RHR `fatigued`）** → 「**積み過ぎ・回復不足**」。`cutback_due` 判定を補強し、deload を強く推す。
  - **ACWR 適正（optimal）× RHR `improving`（または HRV 正常）** → 「**順調に吸収できている**」。進行ゲート GREEN なら小刻みな漸進を許可する根拠にする。
  - **ACWR 適正 × HRV `under_recovery=true` / RHR `fatigued`** → 負荷は妥当でも回復が追いついていない。睡眠・生活要因を疑い、質練の前倒しを避ける。
- **睡眠スコアの扱い**: `get_recovery_status.sleep_score` が低い週（おおむね <60）は **回復不足の主因候補** として言及し、`recommendation`（rest/easy 等）と整合させる。
- **データ欠損週**: `recommendation = unknown`、または RHR/HRV 中央値が軒並み null の場合は、「**回復データ不足のため負荷ベースで講評**」と明示し、ACWR/週量だけで講評を成立させる（回復を黙って無視しない）。
- **個人ベースライン逸脱の early-warning ノート（必須）**: Step 2-3 の `get_wellness_baseline_deviation`（#555）の個人ベースライン逸脱（HRV / readiness / RHR の個人比 z 逸脱）と、`hrv.under_recovery` / `hrv.hrv_below_baseline_days`（HRV ベースライン割れ日数）を取り込み、**逸脱の帰結（consequence）＋予防アクション**を1〜2文の early-warning ノートとして出す。逸脱が無ければ「ベースライン内」と明示し、ノートは出さない。例:
  - **HRV ベースライン割れ2日連続**（`under_recovery=true`）→ 「質練を −1〜2週見送り検討、easy を HR 下限で踏む」
  - **RHR `fatigued` × ACWR caution（≥1.3）** → 「翌週は deload を強く推奨（週量 −30〜40%・質ゼロ）」
  - **readiness の個人比 z が連日マイナス逸脱** → 「睡眠・生活ストレスを疑い、高強度を前倒ししない」
  - この early-warning ノートは Step 7 の `recovery.early_warning_flag`（逸脱ありで `true`）と `recovery.early_warning_note`（帰結＋予防アクションの短文。逸脱なしは null）に反映する。

この結果は Step 6 の「回復の質」表示と Step 7 の `recovery` フィールドに反映します。

#### 評価方針

- **目標観点を最優先**: ユーザーの目標は **回復力・筋持久力・故障再発防止**。スピードはすでに到達済みのため、**高強度（Anaerobic / インターバル / レペティション）の価値は低い**。スピード偏重のセッションは慎重に扱う。
- **各ワークアウトを判定**:
  - ✅ = 目標に合致
  - 🟡 = 条件付き（やり方次第で可。注意点を添える）
  - 🔴 = 目標と不整合・故障再発リスク
- **具体的処方を必須化**: 各セッションの評価コメントと `recommendations` には、**時間(分)・距離(km目安)・心拍ゾーン(bpm) または ペース** の具体値を必ず含める。「もっと走りましょう」「ベースを増やす」等の **曖昧な表現は禁止**（既存 analysis-standards の方針を本コマンドで強化）。
  - **HR ゾーンの出典**: `get_current_fitness_summary` の `hr_zones`（Garmin native）から bpm 範囲を引用する。計算式（220−年齢 等）でゾーンを作らない。zone が取れない場合のみ努力度（RPE）で代替し、その旨を明記する。
  - **処方の具体例**（W の各セッション種別に応じて、実際の bpm はその時の `hr_zones` から差し込む）:
    - 「ロング走: Z2(例 141-152bpm)で 60-75 分(≈9-11km)、暑熱なら時間優先でペースは見ない」
    - 「Base: 40-50 分 Z2」
    - 「流し: 100m×4-6 本（疾走 20-25 秒 / 休 60 秒 jog）」
    - 「テンポ: 閾値心拍域で 15-20 分（暑熱時はペース固定せず心拍上限で）」
- **ロング走の有無を最重要チェック**: ロング走はマラソン筋持久力の核。**対象週 W プランにロング走が無ければ必ず指摘**し、`overall` でも触れる。欠落時の代替提案も具体値（時間/距離/HR）で添える。
- **伸長可否はトレンドで判定（W-1 単独で決めない）**: ロング・週量を「来週も伸ばすか」は、進行ゲート（脚崩れ）だけでなく **Step 5-A-4 のカットバック周期** も必ず照合する。`cutback_due = true`（3週連続 build／ACWR caution+・新ピーク直後）なら、進行ゲートが GREEN でも **deload を優先**して処方する（[[long-run-progression-two-gates]]）。
- **暑熱期の管理**: 気温・湿度が高い時期は、ペース目標ではなく **心拍／努力度（RPE）で管理する** よう助言する。
- **回復の質を負荷と複合で講評**: Step 5-A-5 の回復サブ分析を踏まえ、**負荷（ACWR）と回復（RHR/HRV/睡眠）を掛け合わせて** 講評する。RHR `fatigued` や HRV `under_recovery` が ACWR caution+ と重なれば「積み過ぎ・回復不足」として deload を優先。ACWR optimal × RHR `improving` なら「順調に吸収」として漸進を許可する根拠にする。睡眠スコアが低い週は回復不足の主因候補として言及する。回復データ欠損週は「回復データ不足のため負荷ベースで講評」と明示する（[[user-running-goal]] の回復力重視に直結）。
- **過去レビューとの連続性**: `get_weekly_review()` の前回指摘がどうなったか（改善した／継続課題か）に言及する。
- **中間レースの扱い**: 新潟など priority=B の中間レースは、**全力 PB を狙わず制御された練習として扱う** 方針との整合をチェックする。profile の goals に中間レースがあれば、対象週 W プランがそれを過度に意識した高強度になっていないか確認する。
- **補強（strength）の考慮**: Step 2 で収集した補強セッションを、主に **Execution（補強メニュー遵守）** と **回復・故障予防** の観点で考慮する。ユーザー目標（**回復力・筋持久力重視／故障歴あり**, [[user-running-goal]]）に直結するため、補強の継続は積極評価する。
  - **補強がある週**: 頻度（回数）と **週内配置**（ラン高強度日と同日/連続に重なっていないか）にコメントする。`category_counts` から中身（体幹中心か等）に触れ、回復・故障予防に資するかを一言添える。高強度ランと補強が重なって回復を圧迫している場合は配置調整を助言する。
  - **補強が無い週**: 「今週は補強記録なし」と明示し、故障予防・筋持久力の観点から補強の空白を指摘する（破綻させない）。
  - 補強には **ペース/フォーム/強度分布の評価を適用しない**。`recommendations` で補強に触れる場合も、ラン処方の具体値（HR ゾーン等）とは切り分けて回復・遵守の文脈で記述する。

#### 判定結果の言語

- 日本語で出力、**コーチ的トーン**、具体的な数値を添える。
- 体言止めを避け、自然な文体で1-2文/ポイント。

### Step 6: レビューを表示

レビュー結果を以下の形式でユーザーに表示してください。冒頭に **対象週 W（プラン）と実績週 W-1** を明示する一文を入れてください（例: 「対象週 W = 2026-06-15〜2026-06-21 のプランを、実績週 W-1 = 2026-06-08〜2026-06-14 の実績で評価します」）:

- **実績サマリー（W-1 主軸、W 進行中分は補足）**: 走行距離・回数・強度分布・心拍規律・ハイライト
- **目標逆算フェーズ vs Garmin プランのギャップ（periodization）**: Step 5-A の結果を提示する。
  - 各レースの **残り週数**（A=さいたま：未確定なら「概算/未確定」、B=新潟：確定週数）
  - W に **本来あるべきフェーズ/テーマ**（`expected_phase`）
  - Garmin Coach の **実フェーズ/構成傾向**（`garmin_phase`、`training_plan_name` に言及）
  - 両者の **ギャップ**（`gap`、A=さいたま視点 / B=新潟視点で分けて）
  - **負荷トレンド / カットバック判定**（`load_trend`、Step 5-A-4）: 週量ランプ（直近数週の `load_km`）・ACWR/status・連続 build 週数を示し、**今週が積み上げか deload か**（`cutback_due`）を明示する。`cutback_due = true` なら W への処方を deload（週量 −30〜40%・ロング短縮・質ゼロ）として表に反映する。
- **先週の回復の質（recovery、Step 5-A-5）**: RHR トレンド（`improving`/`stable`/`fatigued` と `median_7d` vs `median_30d` の bpm）、HRV ベースライン割れ日数（`hrv_below_baseline_days`）と `under_recovery`、当日の `recommendation` / 睡眠スコアを示し、**負荷×回復の複合判定**（ACWR 高×HRV割れ→「積み過ぎ・回復不足」、ACWR 適正×RHR改善→「順調に吸収」）を一文で明示する。回復データ欠損週は「回復データ不足のため負荷ベースで講評」と明示する。
- **対象週 W プランの評価**（表形式）。コメントには時間/距離/HR ゾーン(bpm) または ペースの具体値を含める:

  | 日付 | セッション | 判定 | コメント |
  |------|-----------|------|---------|
  | 2026-06-17 | Anaerobic Capacity | 🔴 | 目標（筋持久力）と不整合。Z2(141-152bpm) 40-50 分の Base に置換を推奨 |
  | ... | ... | ... | ... |

- **目標との整合（goal_alignment）**: 対象週 W プラン全体が目標にどれだけ沿っているか
- **recommendations**（最大2件、次回アクションは具体的に。**時間/距離/HR ゾーン(bpm) または ペースの具体値を必ず含める**）
- **overall**: 総評（ロング走の有無への言及を含む）

### Step 7: DuckDB に保存

表示内容を以下の `review` JSON に組み立て、保存してください:

```
mcp__garmin-db__save_weekly_review(review)
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
    "garmin_next_week": [
      {"date": "YYYY-MM-DD", "title": "...", "type": "..."}
    ],
    "periodization": {
      "weeks_to_a_race": null,
      "a_race": "さいたまマラソン",
      "weeks_to_b_race": 17,
      "b_race": "新潟シティマラソン",
      "expected_phase": "有酸素ベース/筋持久力構築期",
      "garmin_phase": "...",
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

- `week_start_date` / `week_end_date` は **対象週 W の開始日・終了日**（Step 1 で `week_start_day` に基づき確定したもの。これが保存キー）。同じ W で再実行すると上書きせず**新しい版を追記**し、最新版が canonical（過去版は履歴として保持）。保存キーは日付そのものなので、開始曜日を変更しても過去レコードとの互換は保たれる。
- `review_data.plan_week_start` は **W の開始日**（= week_start_date）。`review_data.actuals_week_start` は **W-1 の開始日**（= prev_start）。これにより保存レコードが「どの週のプランをどの週の実績で評価したか」を自己説明的に持つ。
- `review_date` は実行日（today）。
- `this_week` は実績サマリー（W-1 主軸、W 進行中分は補足）を格納する（キー名は互換のため `this_week` のまま）。
- `garmin_next_week` は Step 3 で取得した **対象週 W** のプランを `{date, title, type}` に整形（`type` は `item_type` を使う。キー名は互換のため `garmin_next_week` のまま）。
- `periodization` は Step 5-A の目標逆算フェーズ分析の結果を格納する:
  - `weeks_to_a_race` / `weeks_to_b_race` は **整数 or null**（null = race_date 未確定で算出不能）。`a_race` / `b_race` はレース名。
  - `expected_phase` は W にあるべきマクロフェーズ/テーマ（日本語短文）。`garmin_phase` は Garmin Coach 実プランのフェーズ/構成傾向（日本語短文）。`gap` は両者のギャップ（日本語短文、A=さいたま / B=新潟 の観点を含める）。
  - `load_trend` は Step 5-A-4 のカットバック周期サブ分析の結果。`consecutive_build_weeks`（整数）/ `last_cutback_weeks_ago`（整数 or null）/ `acwr`（数値 or null）/ `acwr_status`（文字列）/ `cutback_due`（bool）/ `weekly_ramp`（直近数週の `{week, load_km}` 配列）。`cutback_due=true` のときは `expected_phase` を deload として記述し、`recommendations` / `verdict` も deload 処方（週量 −30〜40%・ロング短縮・質ゼロ）に揃える。
- `recovery` は Step 5-A-5 の回復サブ分析の結果。`rhr_trend`（`improving`/`stable`/`fatigued`）/ `rhr_median_7d` / `rhr_median_30d`（bpm、null 可）/ `hrv_below_baseline_days`（整数、null 可）/ `hrv_under_recovery`（bool）/ `sleep_score`（null 可）/ `recommendation`（`get_recovery_status` の go/no-go）/ `load_recovery_verdict`（負荷×回復の複合講評の短文）/ `data_available`（bool）/ `early_warning_flag`（bool）/ `early_warning_note`（str or null）。回復データ欠損週は `data_available=false` とし、`load_recovery_verdict` を「回復データ不足のため負荷ベースで講評」とする。`hrv_under_recovery=true` かつ ACWR caution+ のときは `load_recovery_verdict` を「積み過ぎ・回復不足」とし、`recommendations` / `verdict` を deload 処方に揃える。`early_warning_flag` は Step 5-A-5 の個人ベースライン逸脱の early-warning ノート（`get_wellness_baseline_deviation` の逸脱や HRV ベースライン割れ）が出た場合に `true`、`early_warning_note` にその帰結＋予防アクションの短文を入れる。逸脱が無ければ `early_warning_flag=false`・`early_warning_note=null`。

### Step 8: 完了報告

保存完了をユーザーに報告してください。どの対象週 W のプランをどの実績週 W-1 で評価したかを一言添え、レビューは **Web で参照可能**（一覧は週ごと最新版、詳細ページで同一週の過去版を切り替えて閲覧）になる旨も添えてください。同じ W で再実行した場合は新しい版が追記された旨も伝えてください。

## 重要事項

- **週の開始曜日は設定駆動**: Step 1 で `get_athlete_profile().week_start_day`（`0`=月〜`6`=日、既定=月曜）を読み、W / W-1 の開始日・終了日をその曜日基準で算出する。`week_start_day` が無い／null なら **月曜始まりにフォールバック**する。月曜開始をハードコードしない。
- **週アンカーは対象週 W（プラン週）**: 保存キーは W の開始日〜終了日（開始曜日は `get_athlete_profile().week_start_day`、既定=月曜）。同じ W の再実行は上書きせず**新しい版を追記**し、最新版を canonical として扱う（過去版は履歴として保持され、Web で閲覧可能）。
- **専用エージェント不使用**: メインセッションが直接実行する（LLM のコーチ判断をそのまま使う）。
- **日本語出力**: 全てのレビュー・コメントは日本語、コーチ的トーン、具体的な数値を添える。
- **目標逆算フェーズ分析を必ず行う**: race_date（null 可）から残り週数を算出し、あるべきフェーズ vs Garmin プランのギャップを `periodization` に格納する。
- **具体的処方を必須化**: 各セッション評価・recommendations に時間/距離/HR ゾーン(bpm) または ペースの具体値を含める。曖昧表現は禁止。HR ゾーンは `get_current_fitness_summary` の Garmin native zones から引用する。
- **recommendations は最大2件**、次回アクションは具体的に絞る。
- **ロング走の有無を必ずチェック**: マラソン筋持久力の核のため、欠落していれば指摘する。
- **トレンドで判定（W-1 単独で increase/cutback を決めない）**: Step 2-2 の `get_load_trend`/`get_acwr` で複数週の負荷ランプ・ACWR・連続 build 週数を必ず収集し、Step 5-A-4 でカットバック周期を判定する。進行ゲート（脚崩れ）が GREEN でも `cutback_due=true` なら deload を優先（[[long-run-progression-two-gates]]）。
- **回復指標を負荷と複合で講評**: Step 2-3 の `get_recovery_trend`/`get_recovery_status` で RHR トレンド・HRV ベースライン割れ・睡眠スコア・training readiness を必ず収集し、Step 5-A-5 で **負荷（ACWR）×回復（HRV/RHR）の複合講評**を行う。ACWR 高×HRV割れ→「積み過ぎ・回復不足」、ACWR 適正×RHR改善→「順調に吸収」。睡眠スコアが低い週は回復不足の主因候補として言及。回復データ欠損週は「回復データ不足のため負荷ベースで講評」と明示する。
- **目標観点を最優先**: 回復力・筋持久力・故障再発防止。高強度の価値は低い前提で評価する。
- **profile 未登録時**: `/set-goal` の実行を促して停止する。
- **任意タイミング実行可**: W が途中でも、W-1 の実績 ＋ W 進行中分でレビューする。
- **データソース**: DuckDB のみ（`mcp__garmin-db__*` ツール経由）。
