---
name: schedule-workout
description: Register prescribed running sessions onto the Garmin Connect calendar as [MCP] custom workouts (ceiling-governed HR, delete→recreate) — one day, or a whole week's saved prescriptions in one confirmed batch — after checking the day's existing schedule and the recovery gate; also tidies stale [MCP] workouts. Use when the user asks to put a run or a week of runs on Garmin (例:「今日のロングランをガーミンのワークアウトに登録して」「今週の練習をまとめて Garmin に入れて」「[MCP] ワークアウトを掃除して」). Argument is the target date YYYY-MM-DD (defaults to today), `week [YYYY-MM-DD]`, or `cleanup`.
argument-hint: [YYYY-MM-DD | week [YYYY-MM-DD] | cleanup]
---

# Schedule Workout（Garmin カレンダーへの処方登録）

保存済みの週次処方（`weekly_prescriptions`）を Garmin カレンダーに登録します。

| `$ARGUMENTS` | モード | 動作 |
|---|---|---|
| 省略 or `YYYY-MM-DD` | 単日 | その日の処方行だけを登録（Step 1 → Step 2） |
| `week [YYYY-MM-DD]` | 週まとめ | その週の登録可能な処方を **1 回の確認**で一括登録（Step 2） |
| `cleanup` | 掃除のみ | 登録せず Step 3 だけ実行 |

処方からステップへの変換（上限だけの心拍、質練だけの前後、流しの構成、`registered_bookend_minutes` の記録）と、
登録前の古い [MCP] 項目の掃除はツールが行います。手でステップを組み直さないでください。
**Garmin への書き込みは必ず確認の後**です。

## Step 0: 準備

```
ToolSearch(query="select:mcp__garmin-db__get_weekly_prescriptions,mcp__garmin-db__get_training_blocks,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation,mcp__garmin-db__schedule_weekly_prescriptions,mcp__garmin-db__cleanup_generated_workouts")
```

## Step 1: 単日モードの材料

同じターンで並列に呼びます:

- `get_weekly_prescriptions(date=<対象日>)`: その日の処方行。**無ければ「先に `/weekly-review` を実行してください」と伝えて止まる**（このスキルで処方を作らない）
- `get_recovery_status(date=<対象日>)` と `get_wellness_baseline_deviation(date=<対象日>)`: `recommendation` が `rest` / `easy`、またはベースライン逸脱が adverse なら、Step 2 の確認で「処方どおり登録 / 見送り」を聞く

## Step 2: 計画 → 確認 → 登録

1. **週開始日を解決**: `get_training_blocks(on_date=<対象日>)` の `week_start_date`。週モードで処方が空なら `/weekly-review` を促して止まる
2. **計画を取得**: `schedule_weekly_prescriptions(week_start_date=<週開始日>[, prescription_ids=[<単日の行>]])`（`dry_run` 既定 True。何も書かない）
3. **表で見せる**: `items` を「日付 / タイトル / 本体（時間 or 距離）/ HR 上限 / 同日の既存 Garmin 項目」の表にする。`skipped` は理由付きで 1 行に、`existing_same_day` が空でない日は競合として明示する（ツールは同名 [MCP] しか置き換えないので、Garmin Coach / 手動の予定は残る）。対象に today が入るなら当日の回復ゲートの結果も添える
4. **確認は 1 回だけ**: `AskUserQuestion` で「登録する / 一部を除外して登録する / 見送る」。同日の Garmin Coach / 手動の予定を残すか差し替えるかもここで聞く
5. **登録**: 同じ引数に `dry_run=False` を付けて呼ぶ。ツールが登録した行の台帳（`status="registered"`、Garmin の id）も更新する
6. **報告**: `registered` を日付順に、`failed` は理由付きで（その行だけ `prescription_ids` で再実行できる）。返り値の `cleanup` に解除・削除やエラーがあれば 1 行添える

## Step 3: 掃除だけしたいとき（`cleanup`）

`cleanup_generated_workouts(dry_run=True)` で過去日付の [MCP] 予定と予定の無い [MCP] テンプレートを列挙し、空でなければ内容を見せてから `dry_run=False` で実行します。手動・Garmin Coach のワークアウトには触りません。登録の後にこれを呼ぶ必要はありません（登録時に同じ掃除が走る）。

## やらないこと

- 週次レビュー・処方の生成（`/weekly-review`）
- 確認なしの Garmin 書き込み
- Garmin Coach / 手動の予定の削除（競合は報告するだけ）
- Garmin 側の HR ゾーン設定やプロフィール変更
