---
name: schedule-workout
description: Register prescribed running sessions onto the Garmin Connect calendar as [MCP] custom workouts (ceiling-governed HR, delete→recreate) — one day, or a whole week's saved prescriptions in one confirmed batch — after checking the day's existing schedule and the recovery gate; also tidies stale [MCP] workouts. Use when the user asks to put a run or a week of runs on Garmin (例:「今日のロングランをガーミンのワークアウトに登録して」「今週の練習をまとめて Garmin に入れて」「[MCP] ワークアウトを掃除して」). Argument is the target date YYYY-MM-DD (defaults to today), `week [YYYY-MM-DD]`, or `cleanup`.
argument-hint: [YYYY-MM-DD | week [YYYY-MM-DD] | cleanup]
---

# Schedule Workout（Garmin カレンダーへの処方登録）

保存済みの週次処方（`weekly_prescriptions`）を Garmin カレンダーに登録します。モードは 3 つです。

| `$ARGUMENTS` | モード | 動作 |
|---|---|---|
| 省略 or `YYYY-MM-DD` | 単日 | その日の処方 1 本を `schedule_custom_workout` で登録（Step 1-3） |
| `week [YYYY-MM-DD]` | 週まとめ | その週の登録可能な処方を `schedule_weekly_prescriptions` で **1 回の確認**で一括登録（Step W） |
| `cleanup` | 掃除のみ | 登録せず Step 4 だけ実行 |

**掃除は登録のたびにツール側で自動実行されます**（#1065）。`schedule_custom_workout` /
`schedule_weekly_prescriptions(dry_run=False)` は、アップロードの前に「過去日付の [MCP] 予定を解除 →
予定の無い [MCP] テンプレートを削除」を実行し、結果を `cleanup` として返します。掃除の失敗で登録が
止まることはありません。`cleanup` 引数（Step 4）は**登録せずに掃除だけしたいとき**に使います。

**Garmin への書き込みは必ず確認の後**（Autonomy Boundaries）。週モードでも確認は 1 回だけです。

## Step 0: 準備

```
ToolSearch(query="select:mcp__garmin-db__get_weekly_prescriptions,mcp__garmin-db__update_prescription_status,mcp__garmin-db__get_training_blocks,mcp__garmin-db__get_weekly_review,mcp__garmin-db__get_garmin_scheduled_workouts,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation,mcp__garmin-db__schedule_custom_workout,mcp__garmin-db__schedule_weekly_prescriptions,mcp__garmin-db__cleanup_generated_workouts")
```

## Step 1: 材料を 1 ターンで並列取得（単日モード）

| ツール | 引数 | 読むもの |
|---|---|---|
| `get_weekly_prescriptions` | `date=<対象日>` | その日の処方行（`prescription_id`, `title`, `target_minutes`/`target_km`, `hr_low`/`hr_high`, `status`） |
| `get_garmin_scheduled_workouts` | `start_date=<対象日>`, `end_date=<対象日>` | 同日に既にある予定（Garmin Coach / 手動 / 既存 [MCP]） |
| `get_recovery_status` | `date=<対象日>` | recommendation（rest/easy なら登録前に確認） |
| `get_wellness_baseline_deviation` | `date=<対象日>` | 週次レビューの回復ゲート（RHR/HRV の条件）を満たすか |

処方行が無い場合のみ `get_weekly_review` の散文から組み立てます（`prescription_id` が無いので Step 3-5 の status 更新は省略）。
どちらも無ければ「先に `/weekly-review` を実行してください」と伝えて止まります。

## Step 2: 処方 → steps への変換（規約）

- **タイトル**: 内容と根拠が一目で分かる短い日本語（例: `ロング19km 新潟ラダー1段目 (Z2上限153)`）。処方行の `title` をそのまま使ってよい。`[MCP] ` 接頭辞はツールが自動付与するので書かない。同名の既存 [MCP] は delete→recreate される
- **構成**: ロング/イージー/リカバリーは **`run` 1 ステップだけ**（前後のウォームアップ/クールダウンを付けない）。全体がウォームアップ強度で上限統治なので、別ステップを足すと時計が処方より多く要求し、ロングランのラダー（19→22→25km は当日総量の定義）が崩れる。本体は処方が「時間」なら `duration_minutes`、「距離」なら `distance_m`
- **前後を付けるのは質練だけ**（閾値・テンポ・ストライド）: `warmup` 10 分 → `run`（本体）→ `cooldown` 5 分。この 15 分は `reconcile_prescriptions` の判定でも許容される（`target_minutes` は本体のみの分数で処方する）
- **HR ターゲット（最重要）**: Z2 / イージー / ロングは **`hr_high` のみ**（上限で統治）。`hr_low` は**書かない** — 走行中に下回りようのない床 80bpm がツール側で自動補完され、上限だけが時計に届く（下限アラートは鳴らない）。自分で低い下限値を置く必要はない。下限アラートが鳴るとユーザーがペースを上げてしまい、暑熱・登坂で緩める意図が壊れる
- **`hr_low` を置くのは質練だけ**（マラソンペース走・テンポ・閾値）。下限を維持すること自体が目的のときのみ
- HR 上限値は処方の `hr_high` or Garmin native zone の上限（計算式禁止）。処方に数値が無ければ `get_heart_rate_zones_detail` の Zone 2 上限を使う

> 週モードではこの変換をツール側がコードで行います（同じ規約: ロング/イージー/リカバリーは本体 1 ステップ、質練のみ 10 分 warmup → 本体 → 5 分 cooldown、`hr_high` は上限のみ、strides は 5x20秒）。手で steps を書き直さないでください。

## Step 3: ゲート確認と登録（単日モード）

1. 同日に **Garmin Coach / 手動の予定**がある場合は、上書きせずユーザーに「両方残す / 差し替える」を確認する（[MCP] 同名は自動差し替えなので確認不要）
2. `recovery_status.recommendation` が `rest` / `easy`、または週次レビューの回復ゲートを満たさない場合は **登録前に一言確認**する（処方どおり登録 / 短縮版に変更 / 見送り）
3. 問題なければ `schedule_custom_workout(date, title, steps)` を 1 回呼ぶ
4. 返り値の `workout_id` / `schedule_id` / `replaced_workout_ids` / `cleanup` を確認する（`cleanup` は登録前に自動実行された掃除の結果。`error` や `failed_delete` が空でなければ報告に添える）
5. 処方行がある場合は `update_prescription_status(prescription_id, status="registered", garmin_workout_id=<workout_id>, garmin_schedule_id=<schedule_id>)` を呼び、台帳を Garmin と一致させる（これを飛ばすと `/daily-checkin` や月次ビューが「未登録」と表示し続ける）
6. ユーザーに「日付・タイトル・本体の量・HR 上限・回復ゲートの結果」を短く報告する。`cleanup` で解除・削除された項目があれば 1 行添える

## Step W: 週まとめ登録（`week [YYYY-MM-DD]`）

日付は週内のどの日でもかまいません（省略時は today）。

1. **週開始日を解決**: `get_training_blocks(on_date=<対象日>)` の `week_start_date` を使う（athlete_profile の週開始曜日に従う）
2. **処方を確認**: `get_weekly_prescriptions(week_start_date=<週開始日>)` で行を読む。空なら「先に `/weekly-review` を実行してください」と伝えて止まる
3. **計画を取得**: `schedule_weekly_prescriptions(week_start_date=<週開始日>)`（`dry_run` 既定 True。Garmin には何も書かない）
4. **表で見せる**: `items` を `日付 / タイトル / 本体（時間 or 距離）/ HR 上限 / 同日の既存 Garmin 項目` の表にする。`skipped`（休養・筋トレ・登録済みなど）は理由付きで 1 行にまとめる。`existing_same_day` が空でない日は競合として明示する（ツールは同名 [MCP] しか置き換えないので、Garmin Coach / 手動の予定は残る）。`would_cleanup`（登録時に自動で解除・削除される過去の [MCP] 項目）が空でなければ 1 行添える
5. **確認は 1 回だけ**: `AskUserQuestion` で「登録する / 一部を除外して登録する / 見送る」を聞く。一部除外なら残す行の `prescription_id` を集める
6. **登録**: `schedule_weekly_prescriptions(week_start_date=<週開始日>, dry_run=False[, prescription_ids=[...]])`。ツールが 1 件ずつ登録し、成功した行に `garmin_workout_id` / `garmin_schedule_id` / `status="registered"` を記録する（`update_prescription_status` を別途呼ぶ必要はない）
7. **報告**: `registered` を日付順に列挙し、`failed` があれば理由付きで示して「その行だけ再実行できます」と添える（`prescription_ids` に失敗分だけ渡す）。既に登録済みの行を上書きしたいときも、その `prescription_id` を明示的に渡す。`cleanup`（登録前に自動実行された掃除）で解除・削除された項目、および `error` / `failed_unschedule` / `failed_delete` があれば 1 行で添える

**当日分の回復ゲートは単日モードと同じ**: 対象週に today が含まれるなら `get_recovery_status(date=<today>)` を確認し、`rest` / `easy` なら Step W-5 の確認でその旨を添える（週全体を止める必要はない）。

## Step 4: 掃除だけしたいとき（`cleanup` 引数）

```
mcp__garmin-db__cleanup_generated_workouts(dry_run=True)
```

過去日付の [MCP] 予定と、予定の無い [MCP] テンプレートが列挙されます。**空でなければ内容を見せてから** `dry_run=False` で実行します。
手動・Garmin Coach のワークアウトには触りません。

**登録の後にこれを呼ぶ必要はありません**: 同じ掃除が登録の直前にツール側で自動実行され、結果は `cleanup` に入っています（#1065）。
このモードは「今週は何も登録しないが古い [MCP] を消したい」ときのためのものです。

## やらないこと

- 週次レビューの生成（`/weekly-review`）。処方が無いときにこのスキル内で処方を捏造しない
- 確認なしの Garmin 書き込み（`dry_run=False` は必ず確認の後）
- Garmin Coach / 手動の予定の削除（競合は報告するだけ。消すのはユーザーの判断）
- Garmin 側の HR ゾーン設定やプロフィール変更
