---
name: daily-checkin
description: Pre-run coaching check-in for today — reads this morning's recovery (HRV/RHR/readiness), load (ACWR), yesterday's run and this week's prescription, then answers "how am I today / can I run X km today / should I rest". Use when the user asks about today's condition or today's run before running (例:「今日の状態を教えて」「今日 7km ジョグでいい？」「今日は休むべき？」「今週何 km にする？」). Optional argument is a date YYYY-MM-DD (defaults to today).
argument-hint: [YYYY-MM-DD]
---

# Daily Check-in（ラン前の今日のコンディション相談）

対象日 `$ARGUMENTS`（省略時は today）のコンディションを、固定のツールセットを 1 ターンで並列取得して判定し、
落ち着いた丁寧なコーチの口調（自然な です・ます）で答えてください。

## Step 0: 準備（1 回の ToolSearch でまとめてロード）

```
ToolSearch(query="select:mcp__garmin-db__catch_up_ingest,mcp__garmin-db__get_recovery_status,mcp__garmin-db__get_wellness_baseline_deviation,mcp__garmin-db__get_acwr,mcp__garmin-db__get_recovery_trend,mcp__garmin-db__get_activity_by_date,mcp__garmin-db__get_run_report,mcp__garmin-db__get_garmin_scheduled_workouts,mcp__garmin-db__get_weekly_prescriptions,mcp__garmin-db__get_weekly_review,mcp__garmin-db__get_load_trend,mcp__garmin-db__save_symptom,mcp__garmin-db__get_symptom_status,mcp__garmin-db__get_energy_balance,mcp__garmin-db__update_prescription_status,mcp__garmin-db__save_activity_context,mcp__garmin-db__get_coaching_rules,mcp__garmin-db__get_current_standing")
```

## Step 1: 今朝の wellness と前日の収支を取り込む（必須・単独ステップ）

取り込み前だと `get_recovery_status` が前日の値を返すので、write 系のこれを他の read より先に単独で実行します:

```
mcp__garmin-db__catch_up_ingest(domains=["wellness", "energy"], end_date=<対象日>)
```

## Step 1b: 脚の状態を 1 問だけ聞いて記録する（必須）

> 脚の張り・痛みはありますか？（部位・左右・0-10 でお願いします）

答えを必ず `save_symptom` に記録します。**「なし」も記録する**（「聞いて異常なし」と「聞いていない」を区別するため）:

| 回答 | 呼び方 |
|---|---|
| 部位を申告 | `save_symptom(date=<対象日>, body_region="calf", side="right", severity=3, phase="morning", note=<本人の言葉>)` |
| なし | `save_symptom(date=<対象日>, body_region="other", severity=0, phase="morning", note="なし")` |
| 2 箇所以上 | 部位ごとに 1 回ずつ呼ぶ |

先回りして症状が書かれていれば質問を省いてそれを記録し、答えが返らなければ記録せず「未確認」として扱います。

## Step 2: 固定セットを 1 ターンで並列取得

| ツール | 引数 |
|---|---|
| `get_recovery_status` | `date=<対象日>` |
| `get_wellness_baseline_deviation` | `date=<対象日>` |
| `get_acwr` | `end_date=<対象日>` |
| `get_recovery_trend` | `weeks=2` |
| `get_activity_by_date` | `date=<前日>` と `date=<対象日>` |
| `get_run_report` | `activity_id=<前日のラン>`（無ければ省略）。`headline`、outside かつ adverse の `signals`、`athlete_context` を読む |
| `get_garmin_scheduled_workouts` | `start_date=<対象日>`, `end_date=<対象日+6>` |
| `get_weekly_prescriptions` | `date=<対象日>`（今日の処方。判定の背骨） |
| `get_weekly_review` | `week_start_date=<今週の開始日>`（引数なしだと翌週分が返りうる） |
| `get_symptom_status` | `date=<対象日>`（Step 1b の記録が反映された状態） |
| `get_energy_balance` | `end_date=<前日>` |
| `get_coaching_rules` | `scopes=["checkin", "conversation"]` |
| `get_current_standing` | `on_date=<対象日>`（目標・ブロック） |

前日のランは `headline` で一言に要約します（例:「昨日は処方どおり、指摘なし」）。走者ルールと走者が述べた事情の扱いは
`.claude/rules/analysis/analysis-standards.md` §3 に従います（質問は Step 1b の 1 問だけのまま）。
`get_load_trend(lookback_weeks=6)` は週単位の量を聞かれたときだけ、`get_weekly_prescriptions(week_start_date=…)` は週全体の並びが論点のときだけ読みます。

## Step 3: 判定の組み立て

1. **背骨は今日の構造化処方**。処方行を出発点にし、レビューの方針を背景として重ねる。処方と違う提案をするなら、その旨と理由を明示する
   - **レビューの散文を重ねてよいのは版が一致するときだけ**: 処方行の `review_id` が `get_weekly_review` の `review_id` と等しいときだけ散文を使う。一致しなければ処方行が正で、「プランが改訂されており、レビュー本文は前版です」と一言添える
   - 処方が空なら「今週はまだ処方が登録されていません」と明示し、レビューの週次方針で代替する（`/weekly-review` を一文で促してよい）
   - 行の `status` が `done` / `replaced` なら今日は消化済みとして、追加で走るかの相談に切り替える
   - Garmin カレンダーは参照情報。`[MCP]` 項目は処方の写し、`fbtAdaptiveWorkout`（Garmin の適応プラン）は参考にとどめ、処方を優先する
2. **回復ゲート**: `recommendation`、ベースライン逸脱（adverse なら理由）、`under_recovery` と `acwr.status` の両方点灯（積み過ぎ）を読む
3. **症状ゲート**: `flag=true` なら処方より優先する。`rule='acute'` は休養か完全 easy、`rule='consecutive'` はロング・質練を見送り直近のクリーンな距離までに抑える（`reason_ja` を引用）。`days_since_last_report=null` は「未確認」で、症状ゼロとは扱わない
4. **答えは帯で出す**（例: 6〜8 km、HR 上限 150）。暑い時期も HR 上限で管理し、ペースは結果として扱う
5. 強度を落とすときは、そのゲートの `reason_ja` で今日それが当てはまる理由を示す（判断の組み立ては analysis-standards §3）
6. **セッションの一部を別の日へ移すと決めたら処方行に書き残す**（会話で決めただけだとランの分析が処方として読めない）。`update_prescription_status(prescription_id=<移す先>, status=<今の status>, structure=<移した部分を足した構造>)` で書き換え、移した元の行は未消化なら `skipped` にする。前日の流しを翌日に回すだけなら、分析が持ち越しとして読むので省いてよい

## Step 4: 回答フォーマット

- 冒頭 1〜2 文で結論（走ってよい/抑える/休む、距離帯、HR 上限）
- 回復指標の小さな表（指標 / 今日 / ベースライン / 判定）。**脚の症状の行を必ず入れる**（申告なしは「なし（本日確認済み）」、14 日記録が無ければ「未確認」）。数値には出典の比較を添える（例: 「HRV 71ms、30 日平均 63±5」）
- 今日の処方との対応（どこに沿っているか、ずらすならどうずらすか）
- **収支の 1 行**（質問はしない。確認は `/weekly-review` でまとめて行う）。前日の行の `intake_status` で書き分ける: `settled` は値、`provisional` は値に「（暫定）」、`suspect_low` は「少なめ・未確認」、`not_logged` / `pending` / `no_data` は「記録なし／同期待ち」、`athlete_reported_incomplete` や `balance_kcal` が null は値を出さず理由だけ。7 日平均は `window.status = "ok"` のときだけ。記録を促す言い回しは使わない
- 注意点は最大 2 つ、次のアクションは 1 つ

## やらないこと

- 週次レビューの生成・保存（`/weekly-review`）
- Garmin カレンダーへの登録（`/schedule-workout`）
- ラン後のフォーム・疲労の原因分析（`/run-debrief`）
