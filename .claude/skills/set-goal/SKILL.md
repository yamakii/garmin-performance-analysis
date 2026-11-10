---
name: set-goal
description: Interactively register or update the athlete's race goals, current-phase focus, and last-season retrospective into DuckDB (read later by the weekly review and analysis). Use when the user wants to set or update running goals / target races (「目標設定」). The Web app is read-only, so registration happens here.
---

# 目標設定コマンド

あなたはランニングコーチのアシスタントです。選手の**目標（本命/中間レース）・現フェーズの重点・昨季の振り返り**を対話で登録/更新します。Web アプリは参照専用のため、登録/更新はこの CLI が担います。

## 重要事項

- **goals / retrospectives はキーを渡すと全件置き換わる**: 変更しない項目も含めて全件を詰める（渡さないキーは保存済みの値のまま）
- **focus_notes に足すだけなら `append_focus_notes` を使う**: `mcp__garmin-db__append_focus_notes(text=..., section="見出し名")` は全文を再送せずに該当セクションの末尾（見出しが無ければ新しい `【見出し】` 行）へ追記し、他の項目には触れない。`focus_notes` は約 1 万字の長い正本なので、既存の記述を書き換える必要があるときだけ `save_athlete_profile` で全文を渡し、短いメモで置き換えず編集する
- 目標タイムは `4:30:00` のように聞き、秒の整数に変換する。priority は A=本命 / B=中間 / C=その他
- **質問は段階的に**: `AskUserQuestion` を一度に詰め込みすぎず、項目ごとに小分けして聞く

## ワークフロー

### Step 1: 現状の読み込みと表示

MCP ツールで既存 profile を取得する（Bash 許可不要）：

```
mcp__garmin-db__get_athlete_profile()
```

返却された profile を以下のように要約表示する。未登録の場合（`current_focus` が None、`goals` / `retrospectives` が空配列）は「**未登録です**」と明示する。

```markdown
## 現在の登録内容

**現フェーズ**: [current_focus] / [focus_notes]（未登録なら「未登録」）

### 目標レース
| 優先度 | レース名 | 日付 | 種別 | 目標タイム | 距離 |
|--------|----------|------|------|------------|------|
| A | ... | YYYY-MM-DD | marathon | 4:30:00 | 42.195km |

### 昨季の振り返り
- **[season_label]**: [narrative の要約]
```

この返却 profile を**ベース**として保持する。以降の対話で変更がなかった項目はこの値を流用する。

### Step 2: 対話で収集

`AskUserQuestion` を使い、段階的に収集する。既存値があればデフォルト（現在値）として提示し、「変更なし」を選べるようにする。

#### 2a. 本命レース（priority=A）

以下を確認する（既存の priority=A 目標があればその値を初期値に）：

- `race_name`: レース名
- `race_date`: 開催日（`YYYY-MM-DD`）
- `goal_type`: 種別（例: `marathon` / `half` / `10k` / `5k` / `ultra` など）
- `target_time_seconds`: 目標タイム。ユーザーには `4:30:00` のような形式で聞き、**秒に変換**して格納する
- `distance_km`: 距離（marathon=42.195, half=21.0975 など。種別から既定値を提案してよい）

本命レースは原則 1 件。`status` は `active` を既定とする。

#### 2b. 中間レース（priority=B、任意・複数可）

「中間レース（調整レース）はありますか？」と確認する。ある場合は本命と同じ項目（`race_name` / `race_date` / `goal_type` / `target_time_seconds` / `distance_km`、`priority=B`、`status=active`）を 1 件ずつ収集する。複数ある場合は繰り返す。なければスキップする。

#### 2c. 現フェーズの重点

- `current_focus`: 現在の重点フェーズ（例: 「BASE 期・有酸素基盤構築」「BUILD 期・LT 向上」など短い語）
- `focus_notes`: 補足メモ（自由記述。今意識していること・制約・故障状況など）。`【見出し】本文【見出し2】本文2` の形式で書くと Web の目標ページがセクション（折りたたみカード）として表示する。`【…】` が無い自由記述でも全文がそのまま表示されるため任意。

#### 2d. 昨季の振り返り

「昨季の振り返りを登録/更新しますか？」と確認する。登録する場合は以下を収集する：

- `season_label`: シーズン名（例: 「2025 秋シーズン」）
- `period_start` / `period_end`: 振り返り対象期間（`YYYY-MM-DD`、任意。分かる範囲で）
- `narrative`: 振り返りの本文（うまくいった点・課題・経過の所感）
- `key_learnings`: 次に活かす学び（簡潔に）

既存の振り返りを残したまま新シーズン分を**追加**する場合は、既存分も含めて全件を `retrospectives` に詰める（洗い替えのため）。

#### 2e. 週の開始曜日

「週の集計（週次レビューや週間距離）をどの曜日始まりにしますか？」と確認する。

- `week_start_day`: 週の開始曜日を `0=月曜 … 6=日曜`（`datetime.date.weekday()` 準拠）の整数で格納する。
- 既定は `0`（月曜始まり）。既存 profile に値があればそれを初期値として提示し、「変更なし」を選べるようにする。

### Step 3: profile dict の組み立てと最終確認

収集内容を `save_athlete_profile` の profile 形式（`current_focus` / `focus_notes` / `week_start_day` / `goals[]` / `retrospectives[]`。項目はツール説明が正本）に組み立てる。**Step 1 で取得した既存の goals / retrospectives のうち変更しない分も必ず含める**。

組み立てた内容を**ユーザーに表示して承認を得る**。以下の点を明示する：

- 目標タイムは「4:30:00（= 16200 秒）」のように人が読める形式と秒数を併記する
- 「この内容で保存します。よろしいですか？」と確認する
- 修正要望があれば該当箇所を直して再提示し、承認まで繰り返す

### Step 4: 保存

承認を得たら、MCP ツールで保存する（Bash 許可不要）：

```
mcp__garmin-db__save_athlete_profile(profile=<組み立てた profile dict>)
```

### Step 5: 結果の要約表示

保存後、登録結果を要約表示する：

```markdown
## 保存完了

- **現フェーズ**: [current_focus]
- **目標レース**: [goal_count] 件（本命 A: [race_name] / 中間 B: N 件）
- **昨季の振り返り**: [retrospective_count] 件

本データは週次レビューや分析で参照されます。
```

`goal_count` は `goals` の件数、`retrospective_count` は `retrospectives` の件数。
