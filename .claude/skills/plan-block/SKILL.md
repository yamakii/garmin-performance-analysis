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
- **日付は `YYYY-MM-DD`**。`start_date <= end_date` が必須（違反すると保存が ValueError で失敗する）
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

### Step 3: 全件を提示して承認を得る

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
