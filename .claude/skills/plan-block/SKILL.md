---
name: plan-block
description: Interactively register or update the mid-term training plan (mesocycle blocks and the long-run ladder) into DuckDB, read later by the weekly review, daily check-in and analysis. Use when the user wants to set or revise the training block plan / long-run ladder (「ブロック計画」「ロング階段」). The Web app is read-only, so registration happens here.
---

# ブロック計画コマンド

あなたはランニングコーチのアシスタントです。選手の**中期計画（メソサイクル・ブロック）**を対話で登録/更新します。Web アプリは参照専用のため、登録/更新はこの CLI が担います。

この内容は `save_training_blocks` で DuckDB の `training_blocks` に保存され、週次レビュー・デイリーチェックイン・分析から参照されます。散文（`focus_notes`）ではなく構造化データとして持つことが目的です。

## 重要事項

- **日本語で対話・出力**する
- **洗い替え方式**: `training_blocks` は user_id 単位で**全件まるごと置き換え**られる。1 ブロックだけ直す場合も「変更しないブロックを含めた全件」を渡すこと（取りこぼすと消える）
- **日付は `YYYY-MM-DD`**。`start_date <= end_date` が必須（違反すると保存は `{"error": ...}` を返し、何も書き込まれない。次の Step の前に `error` を確認する）
- **phase** は `base` / `build` / `peak` / `taper` / `race` / `recovery` / `cutback` のいずれか
- **ロング階段（long_run_ladder）は週 1 エントリ**。各ステップは `week_start`（週の開始日）と、`target_km` / `target_minutes` の**どちらか一方だけ**を持つ（両方 or どちらも無しは保存エラー）
- **このスキルは日々のワークアウトを作らない**。曜日ごとの処方は週次レビュー（`save_weekly_prescriptions`）の担当。ここはあくまで「どの週にロングを何 km まで伸ばすか」までの粒度
- **Garmin には一切書き込まない**（カレンダー登録は `/schedule-workout` の担当）
- **質問は段階的に**: `AskUserQuestion` を一度に詰め込みすぎず、項目ごとに小分けして聞く

## ワークフロー

### Step 1: 現状の読み込みと表示

MCP ツールで既存のブロック計画を取得する（Bash 許可不要）：

```
mcp__garmin-db__get_training_blocks()
```

返却は `{blocks, active_block, ladder_step, on_date, week_start_date}`。`blocks` を以下のように表形式で要約表示する。未登録（`blocks` が空配列）なら「**未登録です**」と明示する。

```markdown
## 現在のブロック計画

| # | フェーズ | 期間 | タイトル | 質練/週 | 減量モード |
|---|----------|------|----------|---------|------------|
| 1 | build | 2026-08-24 〜 2026-09-20 | 新潟ラダー (19→28km) | 1 | 維持 |

### ロング階段（現ブロック）
| 週開始 | 目標 | 種別 | メモ |
|--------|------|------|------|
| 2026-08-31 | 19.0km | build | ラダー1段目 |
| 2026-09-07 | 22.0km | build | ラダー2段目 |

**今週のステップ**: 22.0km（前週 19.0km → 次週 25.0km）
```

この返却内容を**ベース**として保持する。以降の対話で変更がなかったブロックはこの値をそのまま流用する。

### Step 2: 対話で編集内容を収集

`AskUserQuestion` を使い、段階的に収集する。想定される編集操作：

- **ブロック追加**: 新しいフェーズ（例: テーパー、レース週、リカバリー）を末尾/途中に足す
- **ブロック修正**: 期間・目的・質練本数・減量モード・カットバック規則を直す
- **ブロック分割**: 1 ブロックを 2 つに割る（例: build を build + cutback に分ける）
- **ロング階段の編集**: 週ごとの目標距離/時間・HR 上限・種別（`build` / `hold` / `cutback` / `race` / `taper`）を直す

各ブロックで確認する項目：

- `phase`: `base` / `build` / `peak` / `taper` / `race` / `recovery` / `cutback`
- `title`: 短い呼び名（例: 「新潟ラダー (19→28km)」）
- `start_date` / `end_date`: 期間（`YYYY-MM-DD`）
- `purpose`: 一文でこのブロックの狙い
- `weight_mode`: `絞る` / `維持` / 指定なし
- `quality_sessions_per_week`: 0〜2（質練の本数）
- `quality_types`: 質練の種類（例: `["threshold_cruise", "strides"]`）
- `long_run_ladder`: 週ごとのステップ配列（下記）
- `cutback_rule`: カットバックの発火条件（例: `{"trigger": "long_run_streak>=3", "long_run_pct": -35, "volume_pct": -25}`）
- `notes`: 補足（任意）

ロング階段のステップ：

```json
{
  "week_start": "2026-09-07",
  "target_km": 22.0,
  "target_minutes": null,
  "hr_ceiling": 150,
  "kind": "build",
  "note": "ラダー2段目"
}
```

`target_km` と `target_minutes` は**排他**。暑熱期など時間で管理する週は `target_minutes` を使い `target_km` を `null` にする。

### Step 2.5: アンカーなしの対案（大きな計画判断のときだけ）

登録済みの計画から考え始めると、選手が考え直しを求めていても小さな手直しで終わりやすい（既存案がアンカーになる）。
大きな判断では、既存の計画を見ない別のエージェントにゼロから計画を組ませ、Step 3 で 2 つの案を並べて選手に選んでもらう。

**起動条件**（どれか 1 つに当たれば実行する）:

- 変更が**ブロック境界**に触れる（ブロックの追加・分割・削除、`start_date` / `end_date` の移動、`phase` の付け替え）
- **ロング階段**の組み方を変える（ピーク距離・伸ばす段数・据え置き/カットバックの置き方）
- **質練の構成**を変える（`quality_sessions_per_week` / `quality_types`）
- 選手が**見直し・考え直し**を求めた（「見直したい」「ゼロから考えたい」「そもそもこの計画でいいか」など）

どれにも当たらない小修正（メモ・タイトルの修正、1 段だけの HR 上限の修正など）では実行しない。

**手順**:

1. `mcp__garmin-db__get_athlete_profile()` から **`goals` の行だけ**を取り出す（`{race_name, race_date, priority, goal_type, distance_km, target_time_seconds, status, notes}`。`notes` はその目標自身の成功条件として残す）。`current_focus` / `focus_notes` / `retrospectives` は転記しない。
2. 下の**ブリーフ**の `{...}` を埋めて `Agent(subagent_type="general-purpose")` を 1 回呼ぶ（新しいエージェント定義は作らない）。ブリーフには **Step 1 の現行計画・選手が Step 2 で出した編集案・メインセッションの見立てを一切入れない**。
3. 返ってきた JSON を控え、Step 3 で並べて示す。`tools_called` に「読まないもの」が混ざっていたら、その対案は使わず理由を添えて選手に伝える（アンカーが外れていないため）。

**ブリーフ（テンプレート）**:

````markdown
あなたはランニングコーチです。下の目標に向けた中期計画（フェーズ・ロング階段・週量）を、既存の計画を一切見ずにゼロから組んでください。

## 目標（athlete_goals の行をそのまま転記）
{goal_rows_json}

## 基準
- today: {YYYY-MM-DD}
- 計画期間: {plan_start} 〜 {最も遠い目標の race_date}
- 週の開始曜日: {week_start_day}（0=月曜）

## 使ってよいデータ（これ以外のツール・テーブルは読まない）
- mcp__garmin-db__get_load_trend(lookback_weeks=16)
- mcp__garmin-db__get_acwr()
- mcp__garmin-db__get_post_event_window()
- mcp__garmin-db__get_recovery_trend(weeks=8)
- mcp__garmin-db__get_long_run_progression_gate(activity_id=<下の export で得た直近ロングの activity_id>)
- mcp__garmin-db__export(format="csv", query=<次の SQL のみ>)。返った handle の CSV は Read で読む
  SELECT activity_id, activity_date, total_distance_km, total_time_seconds, avg_heart_rate
  FROM activities
  WHERE activity_date >= '{today の 16 週前}' AND total_distance_km >= 15
  ORDER BY activity_date

## 読まないもの
- get_training_blocks / prefetch_weekly_review_context / get_weekly_review / get_weekly_prescriptions / get_garmin_scheduled_workouts
- get_athlete_profile（目標は上に転記済み。focus_notes / retrospectives / current_focus は読まない）
- 上の SQL 以外の export（training_blocks / weekly_reviews / athlete_profile 系のテーブルを含む）

## 進め方
1. まず **requirements** を立てる: レース当日までに何ができている必要があるか（最長ロング、週量、レース前に必要なロングの本数、テーパーの長さなど）を、目標と一般的なトレーニング原則から根拠付きで列挙する。
2. 測定データで**現在地**を確かめる: 直近の週量と最長ロング、ACWR、レース後の保護期間、回復トレンド、直近ロングの伸長ゲート。
3. requirements から**逆算**して phases / ladder / weekly_volume を組む（現在地から requirements まで、無理のない伸ばし方とカットバックで届くか）。届かないときは、届かないことをそのまま requirements の `feasible: false` に書く。
4. 選んだ一つひとつに理由を付ける。

## 出力（JSON を 1 つだけ返す）
{
  "requirements": [{"id": "R1", "statement": "...", "basis": "...", "feasible": true}],
  "phases": [{"phase": "base|build|peak|taper|race|recovery|cutback", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "purpose": "...", "quality_sessions_per_week": 0, "quality_types": []}],
  "ladder": [{"week_start": "YYYY-MM-DD", "target_km": 0.0, "target_minutes": null, "kind": "build|hold|cutback|race|taper"}],
  "weekly_volume": [{"week_start": "YYYY-MM-DD", "target_km": 0.0}],
  "rationale_per_choice": [{"choice": "...", "reason": "...", "requirement_ids": ["R1"]}],
  "tools_called": ["get_load_trend", "..."]
}
`ladder` は週 1 エントリで、`target_km` と `target_minutes` はどちらか一方だけを持つ。
````

### Step 3: 全件を提示して承認を得る

**Step 2.5 を実行したとき**は、全件の提示より先に 2 つの案を並べ、**違いだけ**をその理由と一緒に示して選手に選んでもらう。同じ項目は表に入れず「その他は同じ」と一行で書く。

```markdown
## 2 つの案の違い

| 項目 | 案 A（登録計画＋今回の編集） | 案 B（アンカーなしの対案） | B の理由 |
|------|------------------------------|----------------------------|----------|
| ロングのピーク | 28km（9/27 週） | 30km（10/4 週） | R2: レース前に 30km を 1 本（rationale_per_choice より） |
| テーパー | 2 週 | 3 週 | R4: … |

その他は同じ。どちらで進めますか？（A / B / 一部を組み合わせる）
```

- 「B の理由」は `rationale_per_choice` の `reason` と `requirement_ids` から引く。A 側の理由が会話や登録計画の `purpose` / `notes` にあればそれも添える。どちらかを推して決めない（選ぶのは選手）
- `feasible: false` の requirement があれば、表の下に一文で示す（どちらの案でも届かない前提があるため）
- 選ばれた案（組み合わせを含む）を `save_training_blocks` の形（`phase` の値、週 1 エントリのラダー、`target_km` / `target_minutes` の排他）に直してから、下の全件提示に進む

組み立てた**全ブロック**（変更していないブロックも含む）を Step 1 と同じ表形式で提示し、変更点を箇条書きで添える。

- 「洗い替えのため、以下の全件で置き換えます」と明示する
- 変更点は「何を → 何に」の形で示す（例: 「9/14 週のロング 25km → 28km」）
- 「この内容で保存します。よろしいですか？」と確認する
- 修正要望があれば該当箇所を直して再提示し、承認まで繰り返す

### Step 4: 保存

承認を得たら、MCP ツールで保存する（Bash 許可不要）：

```
mcp__garmin-db__save_training_blocks(blocks=<全ブロックのリスト>)
```

`blocks` のリスト順がそのまま表示順（`sequence`）になる。既存行は全件置換され、保存のたびに全体のスナップショットがバージョンとして追記される。

### Step 5: 結果の要約表示

保存後、結果を要約表示する：

```markdown
## 保存完了

- **ブロック数**: [count] 件
- **バージョン**: version_id=[version_id]（以前の計画は履歴として復元可能）
- **現在アクティブ**: [active_block.title]（[start_date] 〜 [end_date]）
- **今週のロング階段**: [current.target_km]km

本データは週次レビュー・デイリーチェックイン・分析から参照されます。
```

`count` と `version_id` は `save_training_blocks` の返り値。アクティブブロックと今週のステップは保存後に `get_training_blocks()` を再取得して確認する。
