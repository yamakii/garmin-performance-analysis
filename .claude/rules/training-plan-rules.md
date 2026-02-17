# Training Plan Rules

## Volume Progression Safety
- 初週volume: 直近の実績 median weekly volume の ±10% 以内
- 週間増加量: 15% warning / 25% hard reject (save_training_plan自動検証)
- gap_detected=true の場合: recent_runs の距離をベースラインに使用（gap前平均ではない）

## Schedule Constraints
- 日付が正しい曜日に割り当てられているか必ず検証
- 3日連続ランニング禁止
- HR zone targetはGarmin native zones内に収まること

## Execution Intent
- "プラン生成" = `/plan-training` コーチワークフローを実行
- コード分析・レビュー・アーキテクチャ議論ではない
