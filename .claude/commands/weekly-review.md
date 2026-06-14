# Weekly Review Command

**レビュー対象トレーニング週 W**（=これからこなすプラン週）の Garmin プランを、**直前の完了週 W-1 の実績**と過去レビュー・目標を踏まえて **コーチ視点でレビュー** し、DuckDB に保存してください。

レビューの単位は「対象週 W」1つに固定します。保存キー（`week_start_date`/`week_end_date`）は **W の月〜日** なので、実行日が変わっても同じ W であれば同一レコードを UPSERT で更新します（実行日でレビューがずれません）。

専用エージェントには委任しません。**メインセッションが直接オーケストレーション**し、LLM のコーチ判断をそのまま使います。週の任意のタイミングで実行可能です。

## 引数

`{{arg1}}` で **対象週 W** を決めます（W は常に月曜開始〜日曜終了）。

- **省略時（スマート既定）**: today の曜日で対象週を切り替える
  - today が **木・金・土・日** → 対象週 W = **翌週**（今週は概ね消化済みなので、先を計画してレビュー）
  - today が **月・火・水** → 対象週 W = **今週**（週の頭。今いる週をレビュー）
- `{{arg1}}` = `this` → W = today を含む週
- `{{arg1}}` = `next` → W = today を含む週の **翌週**
- `{{arg1}}` = `YYYY-MM-DD` → W = その日を含む週

実績材料は常に **W の直前の完了週 W-1（月〜日）** を主軸とし、**W が進行中（today が W 内）なら today までに W で実走した分**を「今週ここまで」として補足的に加味します。

例:
- today = 日曜 2026-06-14・引数なし → **W = 翌週 2026-06-15〜2026-06-21**、実績 = W-1 = 2026-06-08〜2026-06-14
- today = 火曜 2026-06-16・引数なし → **W = 今週 2026-06-15〜2026-06-21**、実績 = W-1 = 2026-06-08〜2026-06-14 ＋ 6/15・6/16 の実走（W 進行中分）
- `{{arg1}}` = `this`（today = 火 2026-06-16）→ W = 2026-06-15〜2026-06-21
- `{{arg1}}` = `next`（today = 火 2026-06-16）→ W = 2026-06-22〜2026-06-28
- `{{arg1}}` = 2026-06-16 → W = 2026-06-15〜2026-06-21

## ワークフロー

1. **対象週 W を確定**: 引数（または today の曜日）から W の月曜（`week_start_date`）・日曜（`week_end_date`）、W-1 の月曜（`prev_mon`）・日曜（`prev_sun`）を算出
2. **実績収集**: W-1（月〜日）を主軸に各日 `get_activity_by_date` で activity_id を集め、`get_performance_trends` 等で実績を把握。W が進行中なら today までの W の実走も加味
3. **W の Garmin プラン取得**: `get_garmin_scheduled_workouts(week_start_date, week_end_date)`
4. **コンテキスト読込**: `get_athlete_profile()`（目標）+ `get_weekly_review()`（直近の過去レビュー）
5. **コーチ視点でレビュー生成**（このコマンドの核）
6. **レビューを表示** → `save_weekly_review(review)` で保存 → 完了報告

## 実行手順

### Step 1: 対象週 W を確定

`{{arg1}}` と today から **対象週 W** を決定し、その月〜日と直前週 W-1 の月〜日を算出してください:

- 引数なし: today が木〜日なら W = 翌週、月〜水なら W = 今週
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

**profile が未登録の場合**は、レビューを生成せず「先に `/set-goal` を実行して目標を登録してください」とユーザーに促して停止してください。

### Step 5: コーチ視点でレビューを生成（このコマンドの核）

以下の **評価方針** に従い、対象週 W の各ワークアウトを評価してください。

#### 評価方針

- **目標観点を最優先**: ユーザーの目標は **回復力・筋持久力・故障再発防止**。スピードはすでに到達済みのため、**高強度（Anaerobic / インターバル / レペティション）の価値は低い**。スピード偏重のセッションは慎重に扱う。
- **各ワークアウトを判定**:
  - ✅ = 目標に合致
  - 🟡 = 条件付き（やり方次第で可。注意点を添える）
  - 🔴 = 目標と不整合・故障再発リスク
- **ロング走の有無を最重要チェック**: ロング走はマラソン筋持久力の核。**対象週 W プランにロング走が無ければ必ず指摘**し、`overall` でも触れる。
- **暑熱期の管理**: 気温・湿度が高い時期は、ペース目標ではなく **心拍／努力度（RPE）で管理する** よう助言する。
- **過去レビューとの連続性**: `get_weekly_review()` の前回指摘がどうなったか（改善した／継続課題か）に言及する。
- **中間レースの扱い**: 新潟など priority=B の中間レースは、**全力 PB を狙わず制御された練習として扱う** 方針との整合をチェックする。profile の goals に中間レースがあれば、対象週 W プランがそれを過度に意識した高強度になっていないか確認する。

#### 判定結果の言語

- 日本語で出力、**コーチ的トーン**、具体的な数値を添える。
- 体言止めを避け、自然な文体で1-2文/ポイント。

### Step 6: レビューを表示

レビュー結果を以下の形式でユーザーに表示してください。冒頭に **対象週 W（プラン）と実績週 W-1** を明示する一文を入れてください（例: 「対象週 W = 2026-06-15〜2026-06-21 のプランを、実績週 W-1 = 2026-06-08〜2026-06-14 の実績で評価します」）:

- **実績サマリー（W-1 主軸、W 進行中分は補足）**: 走行距離・回数・強度分布・心拍規律・ハイライト
- **対象週 W プランの評価**（表形式）:

  | 日付 | セッション | 判定 | コメント |
  |------|-----------|------|---------|
  | 2026-06-17 | Anaerobic Capacity | 🔴 | 目標（筋持久力）と不整合。高強度の価値は低い |
  | ... | ... | ... | ... |

- **目標との整合（goal_alignment）**: 対象週 W プラン全体が目標にどれだけ沿っているか
- **recommendations**（最大2件、次回アクションは具体的に）
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

- `week_start_date` / `week_end_date` は **対象週 W の月曜・日曜**（Step 1 で確定したもの。これが保存キー）。同じ W は実行日が違っても同一レコードを UPSERT 更新する。
- `review_data.plan_week_start` は **W の月曜**（= week_start_date）。`review_data.actuals_week_start` は **W-1 の月曜**（= prev_mon）。これにより保存レコードが「どの週のプランをどの週の実績で評価したか」を自己説明的に持つ。
- `review_date` は実行日（today）。
- `this_week` は実績サマリー（W-1 主軸、W 進行中分は補足）を格納する（キー名は互換のため `this_week` のまま）。
- `garmin_next_week` は Step 3 で取得した **対象週 W** のプランを `{date, title, type}` に整形（`type` は `item_type` を使う。キー名は互換のため `garmin_next_week` のまま）。

### Step 8: 完了報告

保存完了をユーザーに報告してください。どの対象週 W のプランをどの実績週 W-1 で評価したかを一言添え、レビューは **後日 Web で参照可能** になる旨も添えてください（Web 表示は Phase 2 で対応予定）。

## 重要事項

- **週アンカーは対象週 W（プラン週）**: 保存キーは W の月〜日。同じ W は実行日が変わっても同一レコードを UPSERT 更新する。
- **専用エージェント不使用**: メインセッションが直接実行する（LLM のコーチ判断をそのまま使う）。
- **日本語出力**: 全てのレビュー・コメントは日本語、コーチ的トーン、具体的な数値を添える。
- **recommendations は最大2件**、次回アクションは具体的に絞る。
- **ロング走の有無を必ずチェック**: マラソン筋持久力の核のため、欠落していれば指摘する。
- **目標観点を最優先**: 回復力・筋持久力・故障再発防止。高強度の価値は低い前提で評価する。
- **profile 未登録時**: `/set-goal` の実行を促して停止する。
- **任意タイミング実行可**: W が途中でも、W-1 の実績 ＋ W 進行中分でレビューする。
- **データソース**: DuckDB のみ（`mcp__garmin-db__*` ツール経由）。
