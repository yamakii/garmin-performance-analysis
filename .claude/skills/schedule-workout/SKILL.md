---
name: schedule-workout
description: Register one prescribed running session from the latest weekly review onto the Garmin Connect calendar as an [MCP] custom workout (ceiling-governed HR, delete→recreate), after checking the day's existing schedule and the recovery gate; also tidies stale [MCP] workouts. Use when the user asks to put a run on Garmin (例:「今日のロングランをガーミンのワークアウトに登録して」「今週のロングを Garmin に入れて」「[MCP] ワークアウトを掃除して」). Argument is the target date YYYY-MM-DD (defaults to today) or `cleanup`.
argument-hint: [YYYY-MM-DD | cleanup]
---

# Schedule Workout（Garmin カレンダーへの処方登録）

`$ARGUMENTS`（省略時は today）の日に走るセッションを、**直近の週次レビューの処方**から組み立てて
`schedule_custom_workout` で Garmin カレンダーに登録します。`cleanup` を渡した場合は登録せず掃除だけ行います。

## Step 0: 準備

```
ToolSearch(query="select:mcp__garmin-db__get_weekly_review,mcp__garmin-db__get_garmin_scheduled_workouts,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation,mcp__garmin-db__schedule_custom_workout,mcp__garmin-db__cleanup_generated_workouts")
```

## Step 1: 材料を 1 ターンで並列取得

| ツール | 引数 | 読むもの |
|---|---|---|
| `get_weekly_review` | 引数なし | 対象日を含む週の処方（ロング走の時間/距離、HR 上限、回復ゲートの条件、カットバック判定） |
| `get_garmin_scheduled_workouts` | `start_date=<対象日>`, `end_date=<対象日>` | 同日に既にある予定（Garmin Coach / 手動 / 既存 [MCP]） |
| `get_recovery_status` | `date=<対象日>` | recommendation（rest/easy なら登録前に確認） |
| `get_wellness_baseline_deviation` | `date=<対象日>` | 週次レビューの回復ゲート（RHR/HRV の条件）を満たすか |

週次レビューが対象日の週を指していない（`week_start_date`〜`week_end_date` に対象日が含まれない）場合は、
`get_weekly_review(week_start_date=<対象日の週の開始日>)` で取り直します。それでも無ければ「先に `/weekly-review` を実行してください」と伝えて止まります。

## Step 2: 処方 → steps への変換（規約）

- **タイトル**: 内容と根拠が一目で分かる短い日本語（例: `ロング19km 新潟ラダー1段目 (Z2上限153)`）。`[MCP] ` 接頭辞はツールが自動付与するので書かない。同名の既存 [MCP] は delete→recreate される
- **構成**: ロング/イージーは `warmup`（1 km または 10 分）→ `run`（本体）→ `cooldown`（1 km または 5〜10 分）。本体は処方が「時間」なら `duration_minutes`、「距離」なら `distance_m`
- **HR ターゲット（最重要）**: Z2 / イージー / ロングは **`hr_high` のみ**（上限で統治）。`hr_low` は**書かない** — 走行中に下回りようのない床 80bpm がツール側で自動補完され、上限だけが時計に届く（下限アラートは鳴らない）。自分で低い下限値を置く必要はない。下限アラートが鳴るとユーザーがペースを上げてしまい、暑熱・登坂で緩める意図が壊れる
- **`hr_low` を置くのは質練だけ**（マラソンペース走・テンポ・閾値）。下限を維持すること自体が目的のときのみ
- HR 上限値は週次レビューの処方 or Garmin native zone の上限（計算式禁止）。処方に数値が無ければ `get_heart_rate_zones_detail` の Zone 2 上限を使う

## Step 3: ゲート確認と登録

1. 同日に **Garmin Coach / 手動の予定**がある場合は、上書きせずユーザーに「両方残す / 差し替える」を確認する（[MCP] 同名は自動差し替えなので確認不要）
2. `recovery_status.recommendation` が `rest` / `easy`、または週次レビューの回復ゲートを満たさない場合は **登録前に一言確認**する（処方どおり登録 / 短縮版に変更 / 見送り）
3. 問題なければ `schedule_custom_workout(date, title, steps)` を 1 回呼ぶ
4. 返り値の `workout_id` / `schedule_id` / `replaced_workout_ids` を確認し、ユーザーに「日付・タイトル・本体の量・HR 上限・回復ゲートの結果」を短く報告する

## Step 4: 掃除（`cleanup` 引数、または登録後に 1 回）

```
mcp__garmin-db__cleanup_generated_workouts(dry_run=True)
```

過去日付の [MCP] 予定と、予定の無い [MCP] テンプレートが列挙されます。**空でなければ内容を見せてから** `dry_run=False` で実行します。
手動・Garmin Coach のワークアウトには触りません。

## やらないこと

- 週次レビューの生成（`/weekly-review`）。処方が無いときにこのスキル内で処方を捏造しない
- 複数日の一括登録（週次レビューの処方は原則ロング 1 本。他の日は Garmin Coach に任せる）
- Garmin 側の HR ゾーン設定やプロフィール変更
