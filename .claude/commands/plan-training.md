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

生成されたプランを週ごとに見やすく表示：

```
## プランレビュー

**目標**: 復帰プラン（8週間）
**VDOT**: 42.5 | **週間走行距離**: 15.0km → 19.5km

### Week 1 (RECOVERY) - 15.0km
| 曜日 | タイプ | 距離 | ペース目標 |
|------|--------|------|-----------|
| 火   | イージー | 5.4km | 6:00-5:00/km |
| 木   | イージー | 5.4km | 6:00-5:00/km |
| 日   | ロング   | 4.5km | 6:00-5:00/km |

### 診断コメント
- ✅ 強度: 最初2週はイージーのみで安全
- ✅ ボリューム進行: +10%以下/週で適切
- ⚠️ 注意: 痛みが出たら即座に中断を推奨
```

### Step 5: ユーザー承認

AskUserQuestionで承認を求める：
- **承認**: 次のステップへ
- **修正依頼**: パラメータ調整して再生成
- **キャンセル**: 終了

### Step 6: Garmin Connectアップロード

承認後、DBに保存済みのプランをGarmin Connectにアップロード＋スケジュール：

```
upload_workouts_to_garmin(plan_id="...")
schedule_workouts_on_garmin(plan_id="...")
```

## 重要事項

- **return_to_run**: 閾値走・インターバルなし。テンポもBASEフェーズから
- **fitness**: BASEフェーズから開始（BUILDではない）
- **race_***: 標準的なBASE→BUILD→PEAK→TAPERピリオダイゼーション
- **低ボリューム**: quality距離は週間ボリュームの20%でスケーリング
- **日本語出力**: プランの説明は日本語
