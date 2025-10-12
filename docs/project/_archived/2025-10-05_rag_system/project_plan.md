# RAGシステム プロジェクト計画書

**プロジェクト名**: Garmin Running Performance RAG System
**開始日**: 2025-09-30
**現在ステータス**: Phase 2完了、Phase 3計画済み
**プロジェクトディレクトリ**: `docs/project/2025-10-05_rag_system/`

---

## 1. プロジェクト概要

### 1.1 背景

Garminランニングデータ（50件以上のアクティビティ）を活用し、過去の経緯を含めた洞察を提供するRAG（Retrieval-Augmented Generation）システムの構築。

### 1.2 目的

アドホックなクエリに対して、データに基づいた回答を提供：
- ✅ 「ここ1ヶ月で改善されたポイントは？」
- ✅ 「前回同様の練習との差は？」
- ✅ 「なぜ今日はペースが遅かった？」← Phase 3で実現
- ✅ 「最近の練習強度についてどう思うか？」

### 1.3 実装アプローチ

**段階的実装** - 小さく始めて価値を確認しながら拡張：

```
Phase 0: 現状分析 (1-2日) ✅ 完了
  ↓
Phase 1: DuckDB拡張 (1週間) ✅ 完了
  ↓
Phase 2: フィルタリング (1日) ✅ 完了
  ↓
Phase 3: 多変量相関分析 (9-13日) ← 次はここ
  ↓
Phase 4: 最適化・運用化 (2週間)
```

---

## 2. アーキテクチャ

### 2.1 データフロー

```
Garmin Connect API
  ↓ (garmin-mcp)
Raw Data (data/raw/)
  ↓ (GarminIngestWorker)
Performance Data (data/performance/, data/parquet/)
  ↓ (Database Inserters)
DuckDB (data/database/garmin_performance.duckdb)
  ↓ (RAG Query Tools)
Insights & Analysis
  ↓ (Report Generator)
Markdown Reports (result/individual/)
```

### 2.2 主要コンポーネント

#### データ層
- **DuckDBスキーマ**: `activities`, `performance_trends`, `section_analyses`
- **MCPサーバー**: `garmin-db-server` (read/write/query)

#### 分析層
- **RAG Query Tools**: `tools/rag/queries/`
  - `comparison.py`: 類似ワークアウト検索
  - `trends.py`: パフォーマンストレンド分析
  - `insights.py`: キーワードベース洞察抽出

#### ユーティリティ層
- **ActivityClassifier**: `tools/rag/utils/activity_classifier.py`
- **統計分析**: `tools/rag/analysis/stats_utils.py` (Phase 3で実装予定)

---

## 3. 実装フェーズ

### Phase 0: 現状分析とベースライン構築 ✅

**期間**: 2025-09-30 (1日)
**ステータス**: 完了

**成果物**:
- データインベントリ (`data/rag/inventory_report.json`)
- ベースライン評価レポート (`data/rag/baseline_evaluation_report.md`)
- Phase 0完了レポート (`data/rag/phase0_completion_report.md`)

**主要発見**:
- 50件のアクティビティデータ (2025-09-04 ~ 2025-10-02)
- 11個のメトリクスが利用可能
- DuckDBで効率的なクエリが可能

---

### Phase 1: DuckDB拡張ツール ✅

**期間**: 2025-10-01 ~ 2025-10-04 (4日)
**ステータス**: 完了

**実装内容**:

#### 1.1 類似ワークアウト検索
**ファイル**: `tools/rag/queries/comparison.py`

```python
class SimilarWorkoutComparer:
    def compare_similar_workouts(
        self,
        activity_id: int,
        pace_tolerance: float = 0.1,
        distance_tolerance: float = 0.1,
        terrain_match: bool = False,
        limit: int = 5
    ) -> Dict
```

**機能**:
- ペース・距離・地形での類似度計算
- パフォーマンス差分の自動解釈
- 上位5件の類似ワークアウト抽出

**MCPツール**: `mcp__garmin-db__compare_similar_workouts`

#### 1.2 パフォーマンストレンド分析
**ファイル**: `tools/rag/queries/trends.py`

```python
class PerformanceTrendAnalyzer:
    def get_performance_trends(
        self,
        metric: str,
        period: str = "1M",
        aggregation: str = "mean"
    ) -> Dict
```

**機能**:
- 10種類のメトリクス対応 (avg_pace, avg_heart_rate, cadence_stability, etc.)
- 前半vs後半の自動比較
- 改善/悪化/安定の自動判定

**MCPツール**: `mcp__garmin-db__get_performance_trends`

#### 1.3 洞察抽出（キーワードベース）
**ファイル**: `tools/rag/queries/insights.py`

```python
class InsightExtractor:
    def extract_insights(
        self,
        query_type: str,  # "improvements", "concerns", "patterns", "all"
        timeframe: str = "1M",
        section_types: Optional[List[str]] = None,
        limit: int = 50,      # ページネーション対応
        offset: int = 0
    ) -> Dict
```

**機能**:
- section_analysesからキーワード検索
- 改善点・懸念点・パターンの自動抽出
- ページネーション対応（トークン制限対策）

**MCPツール**: `mcp__garmin-db__extract_insights`

#### 1.4 Phase 1成果

**成果物**:
- `tools/rag/queries/comparison.py` (244行)
- `tools/rag/queries/trends.py` (216行)
- `tools/rag/queries/insights.py` (195行)
- `tools/rag/test_phase1.py` (包括的テスト)
- `data/rag/phase1_completion_report.md`
- `data/rag/phase1_practical_test_report.md`

**実運用テスト結果**:
- ✅ 類似ワークアウト検索: 5件中5件成功
- ✅ トレンド分析: 10メトリクス全て動作
- ⚠️ 洞察抽出: 88,932トークン（制限超過） → Phase 1.5でページネーション実装

**Phase 1.5: ページネーション実装**:
- トークン数: 88,932 → 4,005 (95.5%削減)
- デフォルトlimit=50で十分な情報量

---

### Phase 2: トレンド分析フィルタリング ✅

**期間**: 2025-10-05 (1日)
**ステータス**: 完了

**背景**: Phase 1実運用テストで2つの重大な問題を発見：
1. ケイデンス安定性67.9%改善（誤認） → Sprint/Threshold vs Base Runを混在比較
2. 気温変動の影響を考慮できない → 季節変動が大きい

**実装内容**:

#### 2.1 トレーニングタイプフィルタ
**ファイル**: `tools/rag/utils/activity_classifier.py`

```python
class ActivityClassifier:
    TYPE_KEYWORDS = {
        "Sprint": ["Sprint", "スプリント", "sprint"],
        "Anaerobic": ["Anaerobic", "無酸素", "anaerobic"],
        "Threshold": ["Threshold", "閾値", "threshold", "LT"],
        "Base": ["Base", "ベース", "基礎", "base"],
        "Long Run": ["Long Run", "ロング", "long"],
        "Recovery": ["Recovery", "リカバリー", "回復", "recovery", "Easy", "easy"]
    }

    @classmethod
    def classify(cls, activity_name: str) -> Optional[str]
```

**機能**:
- アクティビティ名から自動分類
- 日英バイリンガル対応
- 優先順位ベースのマッチング

#### 2.2 フィルタ機能拡張
**ファイル**: `tools/rag/queries/trends.py` (更新)

```python
def get_performance_trends(
    self,
    metric: str,
    period: str = "1M",
    aggregation: str = "mean",
    activity_type_filter: Optional[str] = None,        # NEW
    temperature_range: Optional[Tuple[float, float]] = None,  # NEW
    distance_range: Optional[Tuple[float, float]] = None      # NEW
) -> Dict
```

**適用されるフィルタ**:
- `activity_type_filter`: "Base", "Threshold", "Sprint", etc.
- `temperature_range`: (20.0, 25.0) = 20-25℃
- `distance_range`: (8.0, 12.0) = 8-12km

#### 2.3 MCPサーバー更新
**ファイル**: `servers/garmin_db_server.py`

- MCPツール定義更新（3パラメータ追加）
- ハンドラー更新（Array→Tuple変換）
- 後方互換性保持

#### 2.4 Phase 2成果

**成果物**:
- `tools/rag/utils/activity_classifier.py` (103行)
- `tools/rag/test_phase2_filters.py` (包括的テスト、6テストケース)
- `tools/rag/test_phase2_validation.py` (実問題検証)
- `data/rag/phase2.1_completion_report.md` (366行)
- `data/rag/phase2.1_practical_test_report.md` (415行)
- `data/rag/phase2_completion_report.md` (315行)

**解決した問題**:
| Phase 1問題 | Phase 2.1解決 | 効果 |
|------------|--------------|------|
| ケイデンス安定性67.9%改善（誤認） | `activity_type_filter="Base"` | 18.3%に補正✅ |
| 気温変動の影響未考慮 | `temperature_range=[20,27]` | 純粋効果5.5%検出✅ |
| トレーニングタイプ混在 | タイプ別フィルタリング | Base 10.4% vs Threshold 2.3%✅ |

**新たな洞察**:
- 気温1℃低下 → ペース約2秒/km改善
- トレーニングタイプ別特性の明確化
- 疲労検出成功（HR Drift 16.3% = 顕著な疲労蓄積）

**実運用テスト結果**:
- ✅ Test 1: Base Run改善点分析（ペース10.4%改善）
- ✅ Test 2: 気温統制後（5.5%改善 = 純粋効果）
- ✅ Test 3: タイプ別比較（Base vs Threshold）
- ✅ Test 4: フォーム効率改善確認（9/22 GCT★★★★★）
- ✅ Test 5: 疲労検出（10/2 HR Drift 16.3%）

**Phase 2.2について**:
- 当初計画: BM25セマンティック検索
- **決定**: スキップ（Markdownは固定テンプレート、DuckDBで十分）
- 理由: 投資対効果が低い、既存機能で十分

---

### Phase 3: 多変量相関分析（計画済み）

**期間**: 未定 (予定9-13日)
**ステータス**: 計画完了、実装未着手

**目的**: 「なぜ」に答えるための統計的相関分析

**実装予定内容**:

#### 3.1 データ収集基盤 (2-3日)
**新規テーブル**:
```sql
CREATE TABLE wellness_metrics (
    date DATE PRIMARY KEY,
    sleep_score INTEGER,
    sleep_duration_minutes INTEGER,
    deep_sleep_minutes INTEGER,
    rem_sleep_minutes INTEGER,
    avg_stress_level INTEGER,
    max_stress_level INTEGER,
    body_battery_charged INTEGER,
    body_battery_drained INTEGER,
    training_readiness_level INTEGER,
    recovery_time_hours INTEGER,
    weight_kg FLOAT,
    body_fat_percentage FLOAT
);

CREATE TABLE training_load_history (
    date DATE PRIMARY KEY,
    activity_count INTEGER,
    total_distance_km FLOAT,
    total_training_load FLOAT,
    consecutive_days INTEGER,
    rest_days_before INTEGER
);
```

**新規モジュール**:
- `tools/rag/collectors/wellness_collector.py`
  - `collect_daily_wellness(date)`: 日次ウェルネスデータ収集
  - `backfill_wellness_data(start_date, end_date)`: 過去データ一括収集

**データソース** (Garmin MCP):
- `mcp__garmin__get_sleep_data(date)`
- `mcp__garmin__get_stress_data(date)`
- `mcp__garmin__get_body_battery(start_date, end_date)`
- `mcp__garmin__get_training_readiness(date)`
- `mcp__garmin__get_body_composition(date)`

#### 3.2 相関分析エンジン (3-4日)
**新規モジュール**:
- `tools/rag/analysis/correlation_analyzer.py`

```python
class PerformanceCorrelationAnalyzer:
    def analyze_performance_factors(
        self,
        target_metric: str,  # "avg_pace", "avg_heart_rate", etc.
        period: str = "1M",
        activity_type_filter: Optional[str] = None,
        min_correlation: float = 0.3
    ) -> Dict:
        """
        Returns:
        {
            "correlations": [
                {
                    "factor": "external_temp_c",
                    "correlation": -0.72,
                    "p_value": 0.001,
                    "significance": "***",
                    "interpretation": "気温が高いほどペースが遅い"
                },
                {
                    "factor": "sleep_score",
                    "correlation": 0.45,
                    "p_value": 0.03,
                    "significance": "*"
                }
            ],
            "insights": ["気温が最も強い影響要因（r=-0.72, p<0.001）"],
            "recommendations": ["高温時はペース目標を5-10%緩める"]
        }
        """

    def identify_anomaly_causes(
        self,
        activity_id: int,
        metric: str = "avg_pace"
    ) -> Dict:
        """特定アクティビティの異常値原因特定"""

    def find_similar_conditions(
        self,
        activity_id: int,
        top_factors: int = 3
    ) -> List[Dict]:
        """同じ条件の過去アクティビティ検索"""
```

- `tools/rag/analysis/stats_utils.py`

```python
def calculate_correlation(x, y, method="pearson") -> Tuple[float, float]
def interpret_correlation(r: float, p: float) -> str
def detect_outliers(values, method="iqr") -> np.ndarray
```

#### 3.3 MCPツール統合 (1-2日)
**新規MCPツール**:
- `mcp__garmin-db__analyze_performance_factors`
- `mcp__garmin-db__identify_anomaly_causes`
- `mcp__garmin-db__collect_wellness_data`

#### 3.4 テスト・検証 (2-3日)
- 単体テスト（相関分析ロジック）
- 統合テスト（MCPツール経由）
- 実運用テスト（実際の「なぜ」質問）

#### 3.5 ドキュメント (1日)
- Phase 3完了レポート
- CLAUDE.md更新
- 使用方法ガイド

**期待される回答例**:

**Q: なぜ今日はペースが遅い？**
```
A: 睡眠スコア65点（通常80点）+ 3日連続トレーニング
   → 約30秒/km悪化
```

**Q: なぜフォーム効率が悪化？**
```
A: Body Battery消費量との強い相関（r=0.68, p<0.05）
   → 疲労でGCTが平均5ms悪化
```

**詳細**: `docs/rag/phase3_implementation_plan.md` (767行)

---

### Phase 4: 最適化・運用化（未計画）

**期間**: 未定 (予定2週間)
**ステータス**: 未計画

**候補項目**:
- 週次自動レポート
- 月次パフォーマンスサマリー
- フィルタプリセット機能
- 予測モデル（機械学習）

---

## 4. 技術スタック

### 4.1 データストレージ
- **DuckDB**: 構造化データ（高速クエリ）
- **Parquet**: カラムナーフォーマット
- **JSON**: 生データ・中間データ

### 4.2 分析ライブラリ
- **NumPy**: 数値計算
- **SciPy**: 統計分析（Phase 3）
- **Pandas**: データ操作（必要に応じて）

### 4.3 MCP統合
- **garmin-mcp**: Garmin Connect API
- **garmin-db-server**: DuckDB読み書き・RAGクエリ
- **json-utils-server**: 安全なJSON操作
- **markdown-utils-server**: Markdown操作
- **report-generator-server**: レポート生成

### 4.4 開発ツール
- **pytest**: テスト
- **ruff**: Linter
- **black**: Formatter
- **mypy**: 型チェック

---

## 5. 成功基準

### Phase 1-2（達成済み）
- ✅ 3種類のRAGクエリツール実装
- ✅ トークン消費95.5%削減（ページネーション）
- ✅ フィルタリングで誤認67.9%→18.3%補正
- ✅ 気温影響を定量化（1℃=2秒/km）
- ✅ 疲労検出成功（HR Drift 16.3%）

### Phase 3（計画）
- ✅ 10種類以上の要因との相関分析
- ✅ p値 < 0.05で統計的有意性判定
- ✅ 自然言語での洞察生成
- ✅ 異常値原因を3つ以上特定

### Phase 4（未定）
- 週次レポート自動生成
- 月次トレンド分析
- 予測精度 > 80%

---

## 6. リスクと対策

### 6.1 データ品質
**リスク**: Garminデータの欠損・不正確さ
**対策**: 欠損値処理、データ品質スコア算出

### 6.2 統計的検出力
**リスク**: サンプルサイズ不足（1ヶ月12-24件）
**対策**: 最低サンプルサイズ設定、ブートストラップ法

### 6.3 多重比較問題
**リスク**: 偽陽性率上昇
**対策**: Bonferroni補正、効果量重視

### 6.4 因果関係の誤解
**リスク**: 相関 ≠ 因果
**対策**: 「相関」「関連」という表現使用

---

## 7. ファイル構成

### 実装済みファイル

```
tools/rag/
├── queries/
│   ├── comparison.py          # Phase 1: 類似ワークアウト検索
│   ├── trends.py              # Phase 1-2: トレンド分析+フィルタ
│   └── insights.py            # Phase 1: 洞察抽出
├── utils/
│   └── activity_classifier.py # Phase 2: トレーニングタイプ分類
├── analysis/
│   ├── data_inventory.py      # Phase 0: データインベントリ
│   └── baseline_queries.py    # Phase 0: ベースラインクエリ
└── test_*.py                   # 各種テスト

data/rag/
├── inventory_report.json
├── baseline_evaluation_report.md
├── phase0_completion_report.md
├── phase1_completion_report.md
├── phase1_practical_test_report.md
├── phase1_feedback_summary.md
├── pagination_implementation_report.md
├── phase2.1_completion_report.md
├── phase2.1_practical_test_report.md
└── phase2_completion_report.md

docs/rag/
├── README.md
├── implementation_plan.md     # Phase 0-2計画
├── phase2_implementation_plan.md
└── phase3_implementation_plan.md  # Phase 3計画
```

### Phase 3で作成予定

```
tools/rag/
├── collectors/
│   └── wellness_collector.py  # ウェルネスデータ収集
└── analysis/
    ├── correlation_analyzer.py # 相関分析エンジン
    └── stats_utils.py          # 統計ユーティリティ
```

---

## 8. Git履歴

### Phase 1-2コミット
```
c921fe6 feat(rag): complete Phase 2 - performance trend filtering system
        - 35ファイル変更、7,081行追加
        - Phase 0, 1, 2全実装

f3b6f16 docs(rag): add Phase 3 implementation plan
        - Phase 3詳細計画（767行）
```

---

## 9. 参考資料

### プロジェクト内ドキュメント
- `CLAUDE.md`: システム全体概要
- `docs/rag/README.md`: RAGシステム概要
- `docs/rag/implementation_plan.md`: 詳細実装計画
- `docs/rag/phase3_implementation_plan.md`: Phase 3計画

### 完了レポート
- `data/rag/phase0_completion_report.md`
- `data/rag/phase1_completion_report.md`
- `data/rag/phase2_completion_report.md`

### 実運用テストレポート
- `data/rag/phase1_practical_test_report.md`
- `data/rag/phase2.1_practical_test_report.md`

---

## 10. 次のステップ

### Phase 3.1: データ収集基盤（2-3日）
1. DuckDBスキーマ拡張（wellness_metrics, training_load_history）
2. WellnessDataCollector実装
3. 過去1-2ヶ月のデータbackfill
4. MCPツール追加（collect_wellness_data）

### 開始前の準備
- [ ] Phase 3.1の詳細タスク分解
- [ ] wellness_metrics テーブル設計レビュー
- [ ] Garmin MCP APIテスト（睡眠、ストレスデータ取得）

---

**最終更新**: 2025-10-05
**作成者**: Claude Code
**プロジェクトステータス**: Phase 2完了、Phase 3計画済み
