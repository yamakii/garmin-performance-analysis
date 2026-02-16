# Training Plan Generator

対話型のトレーニングプラン作成を行います。

## ワークフロー

### Step 1: ヒアリング

AskUserQuestionを使って以下を確認：

1. **目標**: 復帰(return_to_run) / フィットネス(fitness) / レース(race_5k, race_10k, race_half, race_full)
2. **期間**: 何週間のプラン（4〜24週）
3. **週の走行回数**: 3〜6回
4. **制約**: レース日程、怪我の状況、時間的制約など

### Step 2: 自動診断

MCP経由で直近のフィットネスデータを取得し現状分析：

```
mcp__garmin-db__analyze_performance_trends(metric="pace", start_date="直近1ヶ月", end_date="今日", activity_ids=[])
mcp__garmin-db__get_vo2_max_data(直近のactivity_id)
```

現在の走力レベル（VDOT推定、週間走行距離、トレーニング構成）を把握。

### Step 2.5: 診断レポート

`generate_training_plan` 実行時に診断レポートが自動生成・保存される。
保存先: `result/diagnostics/YYYY-MM-DD_fitness_diagnostic.md`

生成後、レポートの要約をユーザーに提示：
- 通常時: 現在のVDOT、週間走行距離、トレーニング構成
- ギャップ検知時: 休養期間、休養前ベースライン、復帰後の実績

ファイルパスも案内し、後で参照可能であることを伝える。

### Step 3: プラン生成

ヒアリング結果と診断データから `generate_training_plan` を呼び出し：

```
generate_training_plan(
  goal_type="return_to_run",  # or fitness, race_5k, etc.
  total_weeks=8,
  runs_per_week=3,
  ...
)
```

### Step 4: レビュー提示

生成されたプランを週ごとに見やすく表示。
HR zonesデータがある場合、easy/long_runはHR目標 + 時間ベースで表示する。

**return_to_runプラン（HR zones利用時）:**
```
## プランレビュー

**目標**: 復帰プラン（8週間）
**VDOT**: 42.5 | **週間走行距離**: 15.0km → 19.5km

### Week 1 (RECOVERY) - 15.0km
| 曜日 | タイプ | 目標 | 終了条件 |
|------|--------|------|----------|
| 火   | イージー | HR 111-135bpm | 30分 |
| 木   | イージー | HR 111-135bpm | 30分 |
| 日   | ロング   | HR 111-135bpm | 50分 |

### 診断コメント
- ✅ 強度: 最初2週はイージーのみで安全
- ✅ ボリューム進行: +10%以下/週で適切
- ⚠️ 注意: 痛みが出たら即座に中断を推奨
```

**fitness/raceプラン（HR zones利用時、quality workoutあり）:**
```
### Week 3 (BASE) - 25.0km
| 曜日 | タイプ | 目標 | 終了条件 |
|------|--------|------|----------|
| 火   | イージー | HR 111-135bpm | 30分 |
| 水   | テンポ   | 4:15-4:25/km | 8.0km |
| 金   | イージー | HR 111-135bpm | 30分 |
| 日   | ロング   | HR 111-135bpm | 55分 |
```

**HR zonesがない場合（従来形式）:**
```
### Week 1 (RECOVERY) - 15.0km
| 曜日 | タイプ | 距離 | ペース目標 |
|------|--------|------|-----------|
| 火   | イージー | 5.4km | 6:00-5:00/km |
| 木   | イージー | 5.4km | 6:00-5:00/km |
| 日   | ロング   | 4.5km | 6:00-5:00/km |
```

### Step 5: ユーザー承認

AskUserQuestionで承認を求める：
- **承認**: 次のステップへ
- **修正依頼**: パラメータ調整して再生成
- **キャンセル**: 終了

### Step 6: Garmin Connectアップロード

承認後、DBに保存済みのプランをGarmin Connectにアップロード＋スケジュール：

```
upload_workout_to_garmin(plan_id="...")
```

同一構造のワークアウトは1回だけアップロードし、複数日にスケジュールされる（重複排除）。
例: 週3回のイージーランが全週同じ内容 → 1ワークアウトをアップロード + 各日にスケジュール。

## 重要事項

- **return_to_run**: 全フェーズeasy/long_runのみ（テンポ・インターバルなし）
- **fitness**: BASEフェーズから開始（BUILDではない）
- **race_***: 標準的なBASE→BUILD→PEAK→TAPERピリオダイゼーション
- **低ボリューム**: quality距離は週間ボリュームの20%でスケーリング
- **HR目標ルール**:
  - HRゾーンデータがある場合 → easy/long_runはHR目標(bpm) + 時間(分)で表示
  - HRゾーンデータがない場合 → 全ワークアウトをペース(min/km) + 距離(km)で表示
- **重複排除**: 同一構造のワークアウトは1つだけGarminにアップロードし、該当する全日程にスケジュール
- **日本語出力**: プランの説明は日本語
