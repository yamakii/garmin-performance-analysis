# Evaluation Principles

## 評価軸の分離（4軸）

総合評価はこれらの混合ではなく、トレーニング目的に従属させる。

1. **Effort**（努力度）: HR / power / LT比
2. **Performance**（結果）: pace / distance
3. **Efficiency**（効率）: pace/HR, pace/power, GCT/VR統合
4. **Execution**（意図達成度）: plan vs actual, 目的合致度

## ルール vs ツール強制の原則

- **ツール強制**: データ取得経路, 巨大出力抑制, 再現性ある数値計算, 端数ラップ除外, 矛盾チェック
- **ルール誘導**: レポート構成, トーン, 優先順位, 表現の簡潔さ

## 次回提案の原則

- Easy は HR 基準（ペースは結果）— ペース提案ではなく HR 範囲提案にする
- 提案は範囲で提示（例: 135-140 bpm）
- 例外条件を1つ添える（暑さ・疲労時の調整）
- 次回アクションは1つ、数値付き、成功判定条件明示（例:「次回 Zone 2 が 60% 超なら成功」）

## 改善提案の制約

- `recommendations` は最大2件（最重要1件 + 補足1件）
- 「次回アクション」は必ず1つに絞る
- 一般的な助言（「もっと練習しましょう」）は禁止 — 必ず具体的数値を含める

## エージェント間の一貫性

- HR zone 評価は efficiency-section-analyst の `evaluation` フィールドを権威的ソースとする
- 他のエージェント（summary 等）が独自に HR zone を再解釈しない
- plan target が存在する場合、training_type ベースの評価より plan 達成度を優先する
