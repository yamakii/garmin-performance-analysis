# Weekly Review Command

今週の実績と過去レビュー・目標を踏まえ、Garmin に登録された来週プランを **コーチ視点でレビュー** し、DuckDB に保存してください。

専用エージェントには委任しません。**メインセッションが直接オーケストレーション**し、LLM のコーチ判断をそのまま使います。週の任意のタイミングで実行可能です（今週がまだ途中でも、その時点の実績でレビューします）。

## 引数

- `{{arg1}}`: 基準日（YYYY-MM-DD 形式）。**省略時は today**。
  - **今週** = `{{arg1}}` を含む週（月曜開始〜日曜終了）
  - **来週** = その翌週（月曜〜日曜）

例: `{{arg1}}` = 2026-06-14（日曜）の場合、今週 = 2026-06-08〜2026-06-14、来週 = 2026-06-15〜2026-06-21。

## ワークフロー

1. **週の境界を確定**: `{{arg1}}`（省略時は today）から今週の月曜（`week_start_date`）・日曜（`week_end_date`）、来週の月曜（`next_mon`）・日曜（`next_sun`）を算出
2. **今週の実績収集**: 各日 `get_activity_by_date` で activity_id を集め、`get_performance_trends` 等で実績を把握
3. **来週 Garmin 予定取得**: `get_garmin_scheduled_workouts(next_mon, next_sun)`
4. **コンテキスト読込**: `get_athlete_profile()`（目標）+ `get_weekly_review()`（直近の過去レビュー）
5. **コーチ視点でレビュー生成**（このコマンドの核）
6. **レビューを表示** → `save_weekly_review(review)` で保存 → 完了報告

## 実行手順

### Step 1: 週の境界を確定

`{{arg1}}`（省略時は today）を基準に以下を算出してください:

- `week_start_date` = 今週の月曜（基準日を含む週の月曜）
- `week_end_date` = 今週の日曜
- `next_mon` = 来週の月曜（= week_end_date の翌日）
- `next_sun` = 来週の日曜

確定した4つの日付をユーザーに一言で提示してから次に進んでください。

### Step 2: 今週の実績収集

`week_start_date` 〜 `week_end_date`（または基準日まで）の各日について、MCP ツールで実績を集めてください（Bash 許可不要）:

```
# 各日について（月〜基準日）
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
mcp__garmin-db__analyze_performance_trends(metric="pace", start_date=week_start_date, end_date=week_end_date, activity_ids=[...])
```

これらから今週の **走行距離・ラン回数・強度分布・心拍規律（HR discipline）・ハイライト** をまとめてください。

### Step 3: 来週 Garmin 予定の取得

```
mcp__garmin-db__get_garmin_scheduled_workouts(start_date=next_mon, end_date=next_sun)
```

返却は `[{date, title, item_type, training_plan_id, training_plan_name, workout_uuid}]` の配列です。これが **レビュー対象** の来週プランです。

### Step 4: コンテキスト読込（目標・過去レビュー）

```
mcp__garmin-db__get_athlete_profile()    # goals / retrospectives / 現フェーズ
mcp__garmin-db__get_weekly_review()       # 引数なし = 直近の過去レビュー
```

**profile が未登録の場合**は、レビューを生成せず「先に `/set-goal` を実行して目標を登録してください」とユーザーに促して停止してください。

### Step 5: コーチ視点でレビューを生成（このコマンドの核）

以下の **評価方針** に従い、来週の各ワークアウトを評価してください。

#### 評価方針

- **目標観点を最優先**: ユーザーの目標は **回復力・筋持久力・故障再発防止**。スピードはすでに到達済みのため、**高強度（Anaerobic / インターバル / レペティション）の価値は低い**。スピード偏重のセッションは慎重に扱う。
- **各ワークアウトを判定**:
  - ✅ = 目標に合致
  - 🟡 = 条件付き（やり方次第で可。注意点を添える）
  - 🔴 = 目標と不整合・故障再発リスク
- **ロング走の有無を最重要チェック**: ロング走はマラソン筋持久力の核。**来週プランにロング走が無ければ必ず指摘**し、`overall` でも触れる。
- **暑熱期の管理**: 気温・湿度が高い時期は、ペース目標ではなく **心拍／努力度（RPE）で管理する** よう助言する。
- **過去レビューとの連続性**: `get_weekly_review()` の前回指摘がどうなったか（改善した／継続課題か）に言及する。
- **中間レースの扱い**: 新潟など priority=B の中間レースは、**全力 PB を狙わず制御された練習として扱う** 方針との整合をチェックする。profile の goals に中間レースがあれば、来週プランがそれを過度に意識した高強度になっていないか確認する。

#### 判定結果の言語

- 日本語で出力、**コーチ的トーン**、具体的な数値を添える。
- 体言止めを避け、自然な文体で1-2文/ポイント。

### Step 6: レビューを表示

レビュー結果を以下の形式でユーザーに表示してください:

- **今週の実績サマリー**: 走行距離・回数・強度分布・心拍規律・ハイライト
- **来週プランの評価**（表形式）:

  | 日付 | セッション | 判定 | コメント |
  |------|-----------|------|---------|
  | 2026-06-17 | Anaerobic Capacity | 🔴 | 目標（筋持久力）と不整合。高強度の価値は低い |
  | ... | ... | ... | ... |

- **目標との整合（goal_alignment）**: 来週プラン全体が目標にどれだけ沿っているか
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

- `week_start_date` は **今週の月曜**（Step 1 で確定したもの）。
- `review_date` は実行日（today）。
- `garmin_next_week` は Step 3 で取得した予定を `{date, title, type}` に整形（`type` は `item_type` を使う）。

### Step 8: 完了報告

保存完了をユーザーに報告してください。レビューは **後日 Web で参照可能** になる旨を添えてください（Web 表示は Phase 2 で対応予定）。

## 重要事項

- **専用エージェント不使用**: メインセッションが直接実行する（LLM のコーチ判断をそのまま使う）。
- **日本語出力**: 全てのレビュー・コメントは日本語、コーチ的トーン、具体的な数値を添える。
- **recommendations は最大2件**、次回アクションは具体的に絞る。
- **ロング走の有無を必ずチェック**: マラソン筋持久力の核のため、欠落していれば指摘する。
- **目標観点を最優先**: 回復力・筋持久力・故障再発防止。高強度の価値は低い前提で評価する。
- **profile 未登録時**: `/set-goal` の実行を促して停止する。
- **任意タイミング実行可**: 今週が途中でも、その時点の実績でレビューする。
- **データソース**: DuckDB のみ（`mcp__garmin-db__*` ツール経由）。
