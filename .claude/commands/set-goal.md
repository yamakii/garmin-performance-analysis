# 目標設定コマンド

あなたはランニングコーチのアシスタントです。選手の**目標（本命/中間レース）・現フェーズの重点・昨季の振り返り**を対話で登録/更新します。Web アプリは参照専用のため、登録/更新はこの CLI が担います。

この内容は `save_athlete_profile` で DuckDB に保存され、`/plan-training` や週次レビューなど他の機能から参照されます。

## 重要事項

- **日本語で対話・出力**する
- **洗い替え方式**: goals / retrospectives は user_id 単位で**全件まるごと置き換え**られる。更新時は「変更しない項目も含めて全件」を profile に詰めて保存すること（既存の goals/retrospectives を取りこぼすと消える）
- **target_time_seconds は秒の整数**。`4:30:00` のような入力は秒に変換する（4:30:00 → 16200、3:30:00 → 12600、1:45:00 → 6300）
- **race_date は `YYYY-MM-DD`** 形式
- **priority**: `A`=本命, `B`=中間, `C`=その他
- **質問は段階的に**: `AskUserQuestion` を一度に詰め込みすぎず、項目ごとに小分けして聞く（`analyze-activity.md` / `plan-training.md` の流儀に合わせる）

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
- `focus_notes`: 補足メモ（自由記述。今意識していること・制約・故障状況など）

#### 2d. 昨季の振り返り

「昨季の振り返りを登録/更新しますか？」と確認する。登録する場合は以下を収集する：

- `season_label`: シーズン名（例: 「2025 秋シーズン」）
- `period_start` / `period_end`: 振り返り対象期間（`YYYY-MM-DD`、任意。分かる範囲で）
- `narrative`: 振り返りの本文（うまくいった点・課題・経過の所感）
- `key_learnings`: 次に活かす学び（簡潔に）

既存の振り返りを残したまま新シーズン分を**追加**する場合は、既存分も含めて全件を `retrospectives` に詰める（洗い替えのため）。

### Step 3: profile dict の組み立てと最終確認

収集内容を以下の構造に組み立てる。**Step 1 で取得した既存の goals / retrospectives のうち変更しない分も必ず含める**（洗い替えのため）。

```json
{
  "user_id": "default",
  "current_focus": "BASE 期・有酸素基盤構築",
  "focus_notes": "膝に違和感あり。週3回・低強度中心で様子見",
  "goals": [
    {
      "race_name": "東京マラソン",
      "race_date": "2026-03-01",
      "priority": "A",
      "goal_type": "marathon",
      "distance_km": 42.195,
      "target_time_seconds": 16200,
      "status": "active",
      "notes": "サブ4.5 が目標"
    },
    {
      "race_name": "ハーフ調整レース",
      "race_date": "2026-01-18",
      "priority": "B",
      "goal_type": "half",
      "distance_km": 21.0975,
      "target_time_seconds": 7200,
      "status": "active",
      "notes": ""
    }
  ],
  "retrospectives": [
    {
      "season_label": "2025 秋シーズン",
      "period_start": "2025-09-01",
      "period_end": "2025-12-31",
      "narrative": "走行距離は積めたが LT 走の頻度が不足した",
      "key_learnings": "週1回のテンポ走を固定化する"
    }
  ]
}
```

組み立てた内容を**ユーザーに表示して承認を得る**。以下の点を明示する：

- 目標タイムは「4:30:00（= 16200 秒）」のように人が読める形式と秒数を併記する
- 「この内容で保存します。よろしいですか？」と確認する
- 修正要望があれば該当箇所を直して再提示し、承認まで繰り返す

### Step 4: 保存

承認を得たら、MCP ツールで保存する（Bash 許可不要）：

```
mcp__garmin-db__save_athlete_profile(profile=<組み立てた profile dict>)
```

profile 行は `user_id` で upsert され、goals / retrospectives は `user_id` 単位で全件置換される。

### Step 5: 結果の要約表示

保存後、登録結果を要約表示する：

```markdown
## 保存完了

- **現フェーズ**: [current_focus]
- **目標レース**: [goal_count] 件（本命 A: [race_name] / 中間 B: N 件）
- **昨季の振り返り**: [retrospective_count] 件

`/plan-training` で本データを基にプランを作成できます。
```

`goal_count` は `goals` の件数、`retrospective_count` は `retrospectives` の件数。保存内容と一致することを念のため確認する。
