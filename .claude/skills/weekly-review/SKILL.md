---
name: weekly-review
description: Coach-perspective weekly review of the Garmin training plan for a target week W, weighing the prior completed week's results, past reviews, and goals, then saved to DuckDB. Use when the user asks for a weekly training review. Optional argument is the target week; with none, a smart default picks the current or next week based on today.
argument-hint: [target week]
---

# Weekly Review Command

**レビュー対象トレーニング週 W**（=これからこなすプラン週）の Garmin プランを、**直前の完了週 W-1 の実績**と過去レビュー・目標を踏まえて **コーチ視点でレビュー** し、DuckDB に保存してください。

レビューの単位は「対象週 W」1つに固定します。保存キー（`week_start_date`/`week_end_date`）は **W の月〜日** なので、実行日が変わっても同じ W のレビューとして扱われます（実行日でレビューがずれません）。同じ W で複数回実行した場合は**上書きせず各実行を新しい版（バージョン）として追記**し、最新版を正規（canonical）として扱います。過去版も履歴として保持され、Web の詳細ページで切り替えて閲覧できます。

専用エージェントには委任しません。**メインセッションが直接オーケストレーション**し、LLM のコーチ判断をそのまま使います。週の任意のタイミングで実行可能です。

## 引数

`$ARGUMENTS` で **対象週 W** を決めます（W は常に月曜開始〜日曜終了）。

- **省略時（スマート既定）**: today の曜日で対象週を切り替える
  - today が **日曜** → 対象週 W = **翌週**（今週は消化済みなので、先を計画してレビュー）
  - today が **月・火・水・木・金・土** → 対象週 W = **今週**（今いる週をレビュー）
- `$ARGUMENTS` = `this` → W = today を含む週
- `$ARGUMENTS` = `next` → W = today を含む週の **翌週**
- `$ARGUMENTS` = `YYYY-MM-DD` → W = その日を含む週

実績材料は常に **W の直前の完了週 W-1（月〜日）** を主軸とし、**W が進行中（today が W 内）なら today までに W で実走した分**を「今週ここまで」として補足的に加味します。

例:
- today = 日曜 2026-06-14・引数なし → **W = 翌週 2026-06-15〜2026-06-21**、実績 = W-1 = 2026-06-08〜2026-06-14
- today = 火曜 2026-06-16・引数なし → **W = 今週 2026-06-15〜2026-06-21**、実績 = W-1 = 2026-06-08〜2026-06-14 ＋ 6/15・6/16 の実走（W 進行中分）
- `$ARGUMENTS` = `this`（today = 火 2026-06-16）→ W = 2026-06-15〜2026-06-21
- `$ARGUMENTS` = `next`（today = 火 2026-06-16）→ W = 2026-06-22〜2026-06-28
- `$ARGUMENTS` = 2026-06-16 → W = 2026-06-15〜2026-06-21

## ワークフロー

1. **対象週 W を確定**: 引数（または today の曜日）から W の月曜（`week_start_date`）・日曜（`week_end_date`）、W-1 の月曜（`prev_mon`）・日曜（`prev_sun`）を算出
2. **実績収集**: W-1（月〜日）を主軸に各日 `get_activity_by_date` で activity_id を集め、`get_performance_trends` 等で実績を把握。W が進行中なら today までの W の実走も加味
3. **W の Garmin プラン取得**: `get_garmin_scheduled_workouts(week_start_date, week_end_date)`
4. **コンテキスト読込**: `get_athlete_profile()`（目標）+ `get_weekly_review()`（直近の過去レビュー）
5. **コーチ視点でレビュー生成**（このコマンドの核。目標逆算フェーズ分析 ＋ 具体的処方を含む）
6. **レビューを表示**（フェーズギャップ ＋ 具体値付き評価）→ `save_weekly_review(review)` で保存 → 完了報告

## 実行手順

### Step 1: 対象週 W を確定

`$ARGUMENTS` と today から **対象週 W** を決定し、その月〜日と直前週 W-1 の月〜日を算出してください:

- 引数なし: today が日曜なら W = 翌週、月〜土なら W = 今週
- `this`: W = today を含む週
- `next`: W = today を含む週の翌週
- `YYYY-MM-DD`: W = その日を含む週

算出する日付:

- `week_start_date` = **W の月曜**（保存キー）
- `week_end_date` = **W の日曜**（保存キー）
- `prev_mon` = **W-1 の月曜**（= week_start_date の7日前）
- `prev_sun` = **W-1 の日曜**（= week_start_date の前日）

確定した対象週 W（week_start_date〜week_end_date）と実績週 W-1（prev_mon〜prev_sun）、および「W が進行中か（today が W 内か）」をユーザーに一言で提示してから次に進んでください。

### Step 2: 実績収集（W-1 主軸 ＋ W 進行中分）

実績の主軸は **直前の完了週 W-1（`prev_mon`〜`prev_sun`）** です。各日について MCP ツールで実績を集めてください（Bash 許可不要）:

```
# W-1 の各日について（prev_mon〜prev_sun）
mcp__garmin-db__get_activity_by_date(date="YYYY-MM-DD")
```

**W が進行中の場合**（today が `week_start_date`〜`week_end_date` 内）は、W の月曜から today までの各日も同様に収集し、「今週ここまで」の実走として加味してください:

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
mcp__garmin-db__analyze_performance_trends(metric="pace", start_date=prev_mon, end_date=prev_sun, activity_ids=[...])
```

走行距離・ラン回数・強度分布・心拍規律（HR discipline）・ハイライトは **主に W-1 をベースに評価** し、W 進行中分は「今週ここまで」の補足として扱ってください。

#### 補強（strength）の収集

ラン実績とは別に、**補強（筋トレ/補強）セッション**を DuckDB から収集してください。期間は W-1（`prev_mon`〜`prev_sun`）を主軸とし、**W が進行中なら W の月曜〜today** も加味します（ラン実績と同じ期間方針）:

```
mcp__garmin-db__get_strength_sessions(start_date=prev_mon, end_date=prev_sun)
# W が進行中ならもう一度: start_date=week_start_date, end_date=today
```

返却は `{activity_id, activity_date, start_time_local, activity_name, active_duration_seconds, elapsed_duration_seconds, avg_heart_rate, max_heart_rate, calories, active_sets, total_sets, category_counts, ...}` の配列です。`category_counts` は `{"CRUNCH":4,"PLANK":7,...}` の形で、ACTIVE セットのカテゴリ別本数（=体幹中心か等、補強の中身）を表します。

収集する観点: **補強の回数・実施日・所要時間（`active_duration_seconds`）・HR・セット数（`active_sets`）・カテゴリ構成（`category_counts`）**。

- **補強は DB のみから読む（Garmin 非アクセス）**。取り込み（`ingest_strength_sessions`）はこのコマンドでは呼ばない。
- 補強には **ペース/フォーム評価を適用しない**（`get_performance_trends` 等のラン用ツールは補強 activity に使わない）。回復・補強遵守・故障予防の文脈でのみ扱う。
- 補強が0件の期間でも問題ありません。空配列ならそのまま「補強記録なし」として扱います。

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

`goals` の各レース（A=本命さいたま / B=中間 新潟）について、**対象週 W の月曜（`week_start_date`）時点での残り週数**を求めます:

- `race_date` が確定している場合（例: 新潟シティマラソン 2026-10-11）:
  - `weeks_to_race = ceil((race_date − week_start_date) / 7)`（整数。週単位に切り上げ）
  - 例: W 月曜 = 2026-06-15、race_date = 2026-10-11 → 約 17 週
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
- **暑熱期の管理**: 気温・湿度が高い時期は、ペース目標ではなく **心拍／努力度（RPE）で管理する** よう助言する。
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
      "gap": "..."
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

- `week_start_date` / `week_end_date` は **対象週 W の月曜・日曜**（Step 1 で確定したもの。これが保存キー）。同じ W で再実行すると上書きせず**新しい版を追記**し、最新版が canonical（過去版は履歴として保持）。
- `review_data.plan_week_start` は **W の月曜**（= week_start_date）。`review_data.actuals_week_start` は **W-1 の月曜**（= prev_mon）。これにより保存レコードが「どの週のプランをどの週の実績で評価したか」を自己説明的に持つ。
- `review_date` は実行日（today）。
- `this_week` は実績サマリー（W-1 主軸、W 進行中分は補足）を格納する（キー名は互換のため `this_week` のまま）。
- `garmin_next_week` は Step 3 で取得した **対象週 W** のプランを `{date, title, type}` に整形（`type` は `item_type` を使う。キー名は互換のため `garmin_next_week` のまま）。
- `periodization` は Step 5-A の目標逆算フェーズ分析の結果を格納する:
  - `weeks_to_a_race` / `weeks_to_b_race` は **整数 or null**（null = race_date 未確定で算出不能）。`a_race` / `b_race` はレース名。
  - `expected_phase` は W にあるべきマクロフェーズ/テーマ（日本語短文）。`garmin_phase` は Garmin Coach 実プランのフェーズ/構成傾向（日本語短文）。`gap` は両者のギャップ（日本語短文、A=さいたま / B=新潟 の観点を含める）。

### Step 8: 完了報告

保存完了をユーザーに報告してください。どの対象週 W のプランをどの実績週 W-1 で評価したかを一言添え、レビューは **Web で参照可能**（一覧は週ごと最新版、詳細ページで同一週の過去版を切り替えて閲覧）になる旨も添えてください。同じ W で再実行した場合は新しい版が追記された旨も伝えてください。

## 重要事項

- **週アンカーは対象週 W（プラン週）**: 保存キーは W の月〜日。同じ W の再実行は上書きせず**新しい版を追記**し、最新版を canonical として扱う（過去版は履歴として保持され、Web で閲覧可能）。
- **専用エージェント不使用**: メインセッションが直接実行する（LLM のコーチ判断をそのまま使う）。
- **日本語出力**: 全てのレビュー・コメントは日本語、コーチ的トーン、具体的な数値を添える。
- **目標逆算フェーズ分析を必ず行う**: race_date（null 可）から残り週数を算出し、あるべきフェーズ vs Garmin プランのギャップを `periodization` に格納する。
- **具体的処方を必須化**: 各セッション評価・recommendations に時間/距離/HR ゾーン(bpm) または ペースの具体値を含める。曖昧表現は禁止。HR ゾーンは `get_current_fitness_summary` の Garmin native zones から引用する。
- **recommendations は最大2件**、次回アクションは具体的に絞る。
- **ロング走の有無を必ずチェック**: マラソン筋持久力の核のため、欠落していれば指摘する。
- **目標観点を最優先**: 回復力・筋持久力・故障再発防止。高強度の価値は低い前提で評価する。
- **profile 未登録時**: `/set-goal` の実行を促して停止する。
- **任意タイミング実行可**: W が途中でも、W-1 の実績 ＋ W 進行中分でレビューする。
- **データソース**: DuckDB のみ（`mcp__garmin-db__*` ツール経由）。
