---
name: daily-checkin
description: Pre-run coaching check-in for today — reads this morning's recovery (HRV/RHR/readiness), load (ACWR), yesterday's run and this week's prescription, then answers "how am I today / can I run X km today / should I rest". Use when the user asks about today's condition or today's run before running (例:「今日の状態を教えて」「今日 7km ジョグでいい？」「今日は休むべき？」「今週何 km にする？」). Optional argument is a date YYYY-MM-DD (defaults to today).
argument-hint: [YYYY-MM-DD]
---

# Daily Check-in（ラン前の今日のコンディション相談）

対象日 `$ARGUMENTS`（省略時は today）のコンディションを **固定のツールセットを 1 ターンで並列取得**して判定し、
落ち着いた丁寧なコーチの口調（自然な です・ます）で答えてください。

このスキルの目的は「毎回ツールを選び直さない」「登録済みプランを背骨にする」「回復データの取り込み漏れをなくす」の 3 点です。

## Step 0: 準備（1 回の ToolSearch でまとめてロード）

```
ToolSearch(query="select:mcp__garmin-db__catch_up_ingest,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation,mcp__garmin-db__get_acwr,mcp__garmin-db__get_recovery_trend,mcp__garmin-db__get_activity_by_date,mcp__garmin-db__get_garmin_scheduled_workouts,mcp__garmin-db__get_weekly_prescriptions,mcp__garmin-db__get_weekly_review,mcp__garmin-db__get_load_trend")
```

## Step 1: 今朝の wellness を取り込む（必須・単独ステップ）

今朝の HRV/RHR/睡眠は日次同期より先にユーザーが質問することが多く、取り込み前だと `get_recovery_status` が **前日**の値を返します。
write 系なので他の read より先に単独で実行します:

```
mcp__garmin-db__catch_up_ingest(domains=["wellness"], end_date=<対象日>)
```

## Step 2: 固定セットを 1 ターンで並列取得

以下を **同じターンで並列に** 呼びます（順番待ちしない）:

| ツール | 引数 | 読むもの |
|---|---|---|
| `get_recovery_status` | `date=<対象日>` | recommendation（rest/easy/moderate/quality/unknown）、readiness、sleep、body battery |
| `get_wellness_baseline_deviation` | `date=<対象日>` | HRV / readiness / RHR の個人ベースライン z と adverse フラグ |
| `get_acwr` | `end_date=<対象日>` | acute/chronic、acwr、status |
| `get_recovery_trend` | `weeks=2` | RHR 7d/30d 中央値、HRV 連続割れ、under_recovery |
| `get_activity_by_date` | `date=<前日>` と `date=<対象日>` | 直近ラン（距離・時間・ペース・HR）、今日すでに走ったか |
| `get_garmin_scheduled_workouts` | `start_date=<対象日>`, `end_date=<対象日+6>` | 今日〜1 週間の予定（[MCP] 登録分を含む） |
| `get_weekly_prescriptions` | `date=<対象日>` | **今日の処方**（session_type / target_km / target_minutes / hr_high / rationale / status）。これが判定の背骨 |
| `get_weekly_review` | 引数なし | 今週の文脈（カットバック判定・回復ゲート・recommendations の言い回し）。処方の**背景**として読む |

`get_load_trend(lookback_weeks=6)` は「今週何 km」「ロングを伸ばしていいか」など**週単位の量**を聞かれたときだけ追加します。
週全体の並び（今日以外の日）が論点なら `get_weekly_prescriptions(week_start_date=<今週の開始日>)` に切り替えます。
`get_athlete_profile` は `get_weekly_prescriptions` と `get_weekly_review` がどちらも空のとき、または目標・フェーズ自体が論点のときだけ読みます（focus_notes は長大なので毎日は読まない）。

## Step 3: 判定の組み立て

1. **背骨は今日の構造化処方**。`get_weekly_prescriptions(date=<対象日>)` の行（`session_type` / `target_km` / `target_minutes` / `hr_high` / `rationale`）を出発点にし、`get_weekly_review` の recommendations・カットバック判定・回復ゲートをその背景として重ねる。処方と矛盾する提案をする場合は、その旨と理由を明示する（黙って別案を出さない）
   - 処方が **空**（その日に行が無い / 週がまだ処方されていない）なら「今週はまだ処方が登録されていません」と明示し、`get_weekly_review` の週次方針で代替する。`/weekly-review` の実行を1文で促してよい
   - 行の `status` が `done` / `replaced` なら **今日はすでに消化済み**として扱い、追加で走るかどうかの相談に切り替える
2. **回復ゲートを読む順**: `recovery_status.recommendation` → `baseline_deviation.overall_flag`（adverse なら理由） → `recovery_trend.hrv.under_recovery` と `acwr.status` の AND（両方点灯で「積み過ぎ」）
3. **今日の距離・強度の答えは帯で出す**（例: 6〜8 km、HR 上限 150）。ぴったりの数字に意味を持たせない
4. **暑熱期（気温 28℃ 以上が見込まれる時期）**: HR 上限（ceiling）で管理し、ペースは結果として扱う。HR floor や「涼しい朝に効率テスト」を提案しない
5. **ユーザーが仮説を先に述べていても**、まずデータから独立に判定し、「ご理解と一致しています / ここが違います」を明示する。相手の案に寄せた結論を先に決めない
6. **数値の出典を明記**（例: 「HRV 71ms、30 日平均 63±5」）。ゾーン境界は Garmin native zones（`get_heart_rate_zones_detail` 等）のみ。計算式は使わない

## Step 4: 回答フォーマット

- 冒頭 1〜2 文で結論（走ってよい/抑える/休む、距離帯、HR 上限）
- 回復指標の小さな表（指標 / 今日 / ベースライン / 判定）
- 今日の処方との対応（処方のどこに沿っているか。ずらす場合はどうずらすか）
- 注意点は最大 2 つ、次のアクションは 1 つ
- 目的を達しているランや状態に対して「成功条件」「合否」の表現は使わない（維持目標・改善余地として述べる）

## やらないこと

- 週次レビューの生成・保存（それは `/weekly-review`）
- Garmin カレンダーへの登録（それは `/schedule-workout`）
- ラン後のフォーム・疲労の原因分析（それは `/run-debrief`）
