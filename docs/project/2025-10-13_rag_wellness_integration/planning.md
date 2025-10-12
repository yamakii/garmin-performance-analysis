# RAG Wellness Integration Project

**作成日**: 2025-10-13
**プロジェクト名**: rag_wellness_integration
**ステータス**: 計画中（API検証待ち）
**元プロジェクト**: 2025-10-05_rag_system Phase 3より抽出

---

## プロジェクト概要

### 目的

Garmin Wellness API（睡眠、ストレス、Body Battery、Training Readiness）を統合し、多変量相関分析により「なぜパフォーマンスが変化したか」という因果関係の質問に回答可能にする。

### 背景

- 2025-10-05_rag_system Phase 3として計画されていた
- 2025-10-10_rag_unified_plan Phase 1-5完了により、基本RAG機能は実装済み
- Wellness統合は独立したプロジェクトとして切り出し

### 前提条件

- ✅ Phase 1-5完了（インターバル分析、トレンド分析、類似検索）
- ⏸️ Garmin Wellness API可用性検証（未実施）

---

## Phase 0: API検証（必須、1-2日）

### 目標

Garmin Wellness APIのデータ取得可能性を検証し、プロジェクト実施可否を判断する。

### 検証項目

1. **API可用性**
   - Sleep API（睡眠スコア、REM/Deep睡眠）
   - Stress API（ストレスレベル、休息時間）
   - Body Battery API（エネルギー充電/消費）
   - Training Readiness API（トレーニング準備スコア、HRV）

2. **データ品質**
   - 過去60-90日間のデータ取得可否
   - データ完全性（欠損率）
   - データ精度（異常値の有無）

3. **レート制限**
   - APIコール数制限
   - バックフィル時の制約

### 成功基準

- ✅ 全4つのAPIからデータ取得可能
- ✅ データ完全性 >60%（過去60日間）
- ✅ レート制限が実用範囲内（1日1000コール以上）

### 失敗時の対応

- API可用性<60%: プロジェクト中止または大幅縮小
- データ品質不十分: 分析精度低下の警告付きで実施

---

## Phase 1-5: 実装計画（API検証成功後）

**詳細仕様**: `docs/project/_archived/2025-10-05_rag_system/phase3_specifications.md` を参照

### Phase 1: データ収集基盤（3日）

- WellnessDataCollector実装
- DuckDB wellness_metrics, training_load_history テーブル作成
- 60-90日分データバックフィル

### Phase 2: Training Load計算（2日）

- TrainingLoadCalculator実装
- TSS（Training Stress Score）計算
- 累積負荷（7/14/30日）計算

### Phase 3: 相関分析エンジン（3日）

- CorrelationAnalyzer実装
- Pearson相関係数計算
- 統計的有意性検定（p-value）
- 多変量分析

### Phase 4: MCP統合（2日）

- `analyze_performance_why` MCPツール追加
- 「なぜ」質問への回答機能

### Phase 5: 検証・ドキュメント（3日）

- ユーザーフィードバック収集
- 精度検証（>80%目標）
- ドキュメント作成

**合計見積もり**: 13日

---

## 期待される機能

### 「なぜ」質問の例

1. **なぜ今日のペースが遅かったのか？**
   - 相関: 睡眠スコア62（-18pt） → ペース-3.2%
   - 相関: ストレスレベル68（+15pt） → ペース-2.1%

2. **なぜ疲労が蓄積しているのか？**
   - 相関: 7日間TSS 580（+23%高い）
   - 相関: Body Battery回復率 72%（-15%低い）
   - 警告: オーバートレーニングパターンに類似

3. **ベストパフォーマンスの条件は？**
   - 睡眠スコア: 85-92（現在78 → +7-14pt必要）
   - ストレスレベル: 25-35（現在48 → -13-23pt必要）
   - Body Battery: 85-95（現在68 → +17-27pt必要）

---

## リスク管理

### リスク1: API可用性不足

- **確率**: 高（未検証）
- **影響**: プロジェクト中止
- **対策**: Phase 0で早期検証

### リスク2: データ品質低下

- **確率**: 中
- **影響**: 分析精度低下
- **対策**: データ品質レポート、信頼度スコア表示

### リスク3: 実装期間超過

- **確率**: 中
- **影響**: 13日 → 18日程度
- **対策**: 段階的実装、優先度管理

---

## 次のステップ

### 即座のアクション

1. **Phase 0開始**: Garmin Wellness API検証
2. **検証結果に基づいた判断**: 実施/中止/縮小を決定
3. **実施判断後**: TDD実装開始（project-planner → tdd-implementer）

### 推奨コマンド（Phase 0完了後）

```bash
# Phase 1-5実装開始
Task: tdd-implementer
prompt: "docs/project/2025-10-13_rag_wellness_integration/planning.md のPhase 1から実装を開始してください。API検証が完了し、実施可能と判断されました。"
```

---

## 関連ドキュメント

- **詳細仕様**: `docs/project/_archived/2025-10-05_rag_system/phase3_specifications.md`
- **元プロジェクト**: `docs/project/_archived/2025-10-05_rag_system/`
- **基本RAGツール**: `docs/project/_archived/2025-10-10_rag_unified_plan/`

---

**最終更新**: 2025-10-13
**作成者**: Claude Code
**ステータス**: API検証待ち
**次のアクション**: Phase 0 API検証実施
