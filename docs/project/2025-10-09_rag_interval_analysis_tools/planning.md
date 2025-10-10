# 計画: RAG Interval Analysis Tools

**プロジェクト日付**: 2025-10-09
**プロジェクト名**: rag_interval_analysis_tools
**既存プロジェクト**: docs/project/2025-10-05_rag_system/ (Phase 2完了)

---

## Git Worktree情報
- **Worktree Path**: `../garmin-rag_interval_analysis_tools/`
- **Branch**: `feature/rag_interval_analysis_tools`
- **Base Branch**: `main`

---

## 要件定義

### 目的

インターバルトレーニングの詳細分析を可能にする3つの新RAGツールを実装し、activity_details.jsonの秒単位メトリクス（26種類）を活用した高度な分析機能を提供する。

### 解決する問題

**現在の課題:**

1. **インターバルトレーニング分析の欠如**
   - Work/Recovery比較ができない
   - インターバル間の疲労蓄積が定量化できない
   - Recovery効率（心拍・ペース回復速度）が可視化できない

2. **秒単位詳細データの未活用**
   - activity_details.jsonに26種類の秒単位メトリクスが存在
   - 現在はsplits（1kmラップ）レベルの分析のみ
   - フォーム変化の細かな検出ができない

3. **フォーム異常検出の不足**
   - 標高変化とGCT/VO/VR変化の相関が不明
   - ペース急変時のフォーム崩れが検出できない
   - 疲労によるフォーム悪化パターンが分析できない

### ユースケース

#### UC1: インターバルトレーニング分析
```
User: "10/2のインターバルトレーニングのWork/Recovery比較を教えて"

System (get_interval_analysis):
- Work区間: 平均ペース 4:10/km, 平均HR 175 bpm, GCT 210ms
- Recovery区間: 平均ペース 5:30/km, 平均HR 145 bpm, GCT 225ms
- Recovery効率: HR回復速度 30 bpm/分, ペース回復95%
- 疲労蓄積: 最終インターバルでWork HR +8 bpm (疲労検出)
```

#### UC2: 特定splitの秒単位詳細分析
```
User: "9/22の3km地点の詳細データを秒単位で見たい"

System (get_split_time_series_detail):
- Split 3 (2000-3000m) の秒単位データ取得
- 1000秒分のHR/ペース/GCT/VO/VR時系列
- 異常値検出: 2500m地点でGCT +15ms (標高+8m上昇と相関)
```

#### UC3: フォーム異常検出と原因分析
```
User: "最近のランでフォームが崩れた箇所を特定して"

System (detect_form_anomalies):
- 9/22: Split 5でGCT +12ms異常 (原因: 標高+12m急上昇)
- 9/28: Split 8でVO +2cm異常 (原因: ペース 4:30→5:15急減)
- 10/2: Split 9でVR +1.5%異常 (原因: 疲労、HR Drift 16%)
```

---

## 設計

### アーキテクチャ

#### データフロー
```
activity_details.json (26メトリクス × 1398秒)
    ↓
RAG Query Tools (新規3ツール)
    ↓
時系列分析・異常検出・インターバル分解
    ↓
Garmin DB MCP Server (新規3エンドポイント)
    ↓
分析結果返却
```

#### コンポーネント配置
```
tools/rag/queries/
├── interval_analysis.py       # [NEW] インターバル分析
├── time_series_detail.py      # [NEW] 秒単位時系列取得
└── form_anomaly_detector.py   # [NEW] フォーム異常検出

servers/garmin_db_server.py    # [UPDATE] 3ツール追加
```

#### 既存RAGシステムとの統合
- **Phase 0-2完了済み**: データインベントリ、トレンド分析、フィルタリング
- **Phase 3計画済み**: 多変量相関分析（wellness_metrics統合）
- **本プロジェクト**: Phase 2.5相当（activity_details.json活用）

### データモデル

#### activity_details.json構造
```json
{
  "activityId": 20615445009,
  "measurementCount": 26,
  "metricsCount": 1398,
  "metricDescriptors": [
    {"metricsIndex": 0, "key": "sumDuration"},
    {"metricsIndex": 1, "key": "directVerticalOscillation"},
    {"metricsIndex": 3, "key": "directHeartRate"},
    {"metricsIndex": 4, "key": "directRunCadence"},
    {"metricsIndex": 5, "key": "directSpeed"},
    {"metricsIndex": 7, "key": "directVerticalRatio"},
    {"metricsIndex": 12, "key": "directElevation"},
    {"metricsIndex": 19, "key": "directGroundContactTime"}
  ],
  "activityDetailMetrics": [
    {
      "metrics": [0, 7.9, 10000, 162, 180, 29, 0, 9.2, ...]
    }
  ]
}
```

#### 主要メトリクス（26種類中、分析重要度高）
| Index | Key | Unit | 用途 |
|-------|-----|------|------|
| 1 | directVerticalOscillation | cm | フォーム効率 |
| 3 | directHeartRate | bpm | 心拍応答・疲労 |
| 4 | directRunCadence | spm | ケイデンス安定性 |
| 5 | directSpeed | m/s | ペース変化 |
| 7 | directVerticalRatio | % | フォーム効率 |
| 12 | directElevation | m | 地形影響 |
| 19 | directGroundContactTime | ms | フォーム効率 |

#### インターバル区間定義（新規）
```python
@dataclass
class IntervalSegment:
    segment_type: str  # "work", "recovery", "warmup", "cooldown"
    start_time: int    # 開始秒
    end_time: int      # 終了秒
    avg_pace: float    # 平均ペース (min/km)
    avg_hr: int        # 平均心拍 (bpm)
    avg_gct: float     # 平均GCT (ms)
    avg_vo: float      # 平均VO (cm)
    avg_vr: float      # 平均VR (%)
```

#### フォーム異常検出結果（新規）
```python
@dataclass
class FormAnomaly:
    timestamp: int           # 異常検出時刻（秒）
    split_number: int        # 対応するsplit番号
    metric_name: str         # "GCT", "VO", "VR"
    value: float             # 異常値
    baseline: float          # ベースライン値
    deviation: float         # 偏差（標準偏差単位）
    probable_cause: str      # "elevation_change", "pace_change", "fatigue"
    correlation_data: dict   # 相関データ（標高、ペース、HR）
```

### API/インターフェース設計

#### 1. get_interval_analysis

**目的**: インターバルトレーニングのWork/Recovery区間を自動検出し、各区間のパフォーマンスを比較分析

**インターフェース**:
```python
class IntervalAnalyzer:
    def get_interval_analysis(
        self,
        activity_id: int,
        pace_threshold_factor: float = 1.3,  # Recovery/Workペース比（デフォルト1.3倍以上でRecovery）
        min_work_duration: int = 180,        # Work区間最小秒数（3分）
        min_recovery_duration: int = 60      # Recovery区間最小秒数（1分）
    ) -> Dict:
        """
        Returns:
        {
            "activity_id": 20615445009,
            "interval_type": "classic_intervals",  # or "fartlek", "tempo", "progressive"
            "segments": [
                {
                    "segment_number": 1,
                    "segment_type": "warmup",
                    "start_time": 0,
                    "end_time": 600,
                    "duration_seconds": 600,
                    "avg_pace_min_per_km": 5.5,
                    "avg_hr_bpm": 145
                },
                {
                    "segment_number": 2,
                    "segment_type": "work",
                    "start_time": 600,
                    "end_time": 900,
                    "duration_seconds": 300,
                    "avg_pace_min_per_km": 4.1,
                    "avg_hr_bpm": 175,
                    "avg_gct_ms": 210,
                    "avg_vo_cm": 7.8,
                    "avg_vr_percent": 8.5
                },
                {
                    "segment_number": 3,
                    "segment_type": "recovery",
                    "start_time": 900,
                    "end_time": 1080,
                    "duration_seconds": 180,
                    "avg_pace_min_per_km": 5.8,
                    "avg_hr_bpm": 148,
                    "hr_recovery_rate_bpm_per_min": 27,  # (175-148)/(180/60)
                    "pace_recovery_percent": 92           # (5.8/4.1 - 1) * 100
                }
            ],
            "work_recovery_comparison": {
                "work_count": 5,
                "avg_work_pace": 4.15,
                "avg_recovery_pace": 5.65,
                "avg_work_hr": 174,
                "avg_recovery_hr": 147,
                "avg_hr_recovery_rate": 25,
                "fatigue_indicators": {
                    "last_work_hr_increase": 8,  # 最終Workで+8 bpm
                    "work_pace_degradation": 5,  # 最終Workで+5秒/km
                    "gct_degradation_ms": 6      # 最終Workで+6ms
                }
            }
        }
        """
```

**アルゴリズム**:
1. 秒単位ペースデータ取得（directSpeed）
2. 移動平均（30秒窓）でノイズ除去
3. ペース閾値でWork/Recovery分離
4. 区間統合（最小持続時間未満を統合）
5. 各区間のメトリクス集計

#### 2. get_split_time_series_detail

**目的**: 特定split（1kmラップ）の秒単位詳細データを取得し、細かな変化を可視化

**インターフェース**:
```python
class TimeSeriesDetailExtractor:
    def get_split_time_series_detail(
        self,
        activity_id: int,
        split_number: int,               # 1-based split番号
        metrics: List[str] = None        # 取得メトリクス（Noneなら全て）
    ) -> Dict:
        """
        Returns:
        {
            "activity_id": 20615445009,
            "split_number": 3,
            "start_distance_m": 2000,
            "end_distance_m": 3000,
            "start_time_s": 475,
            "end_time_s": 730,
            "duration_s": 255,
            "time_series": [
                {
                    "timestamp": 475,
                    "distance_m": 2000,
                    "hr_bpm": 168,
                    "speed_mps": 3.92,
                    "pace_min_per_km": 4.25,
                    "gct_ms": 215,
                    "vo_cm": 7.9,
                    "vr_percent": 8.3,
                    "elevation_m": 45.2,
                    "cadence_spm": 182
                },
                # ... 255 data points
            ],
            "statistics": {
                "hr_avg": 170, "hr_std": 4.2, "hr_min": 165, "hr_max": 178,
                "pace_avg": 4.18, "pace_std": 0.08,
                "gct_avg": 218, "gct_std": 5.3,
                "elevation_gain": 12, "elevation_loss": 3
            },
            "anomalies": [
                {
                    "timestamp": 650,
                    "metric": "GCT",
                    "value": 230,
                    "z_score": 2.3,
                    "note": "標高+8m上昇と相関"
                }
            ]
        }
        """
```

**データ取得ロジック**:
1. performance.jsonからsplit距離範囲取得
2. activity_details.jsonのmetricDescriptors解析
3. 該当時間範囲のactivityDetailMetrics抽出
4. メトリクス変換（factor適用、単位変換）
5. 統計値計算・異常値検出

#### 3. detect_form_anomalies

**目的**: フォームメトリクス（GCT/VO/VR）の異常を検出し、標高・ペース・疲労との相関から原因を特定

**インターフェース**:
```python
class FormAnomalyDetector:
    def detect_form_anomalies(
        self,
        activity_id: int,
        metrics: List[str] = ["GCT", "VO", "VR"],
        z_threshold: float = 2.0,        # 異常判定閾値（標準偏差）
        context_window: int = 30         # 前後コンテキスト（秒）
    ) -> Dict:
        """
        Returns:
        {
            "activity_id": 20615445009,
            "anomalies_detected": 8,
            "anomalies": [
                {
                    "anomaly_id": 1,
                    "timestamp": 2545,
                    "split_number": 3,
                    "metric": "GCT",
                    "value": 230,
                    "baseline": 215,
                    "deviation_ms": 15,
                    "z_score": 2.8,
                    "severity": "medium",  # low/medium/high
                    "probable_cause": "elevation_change",
                    "cause_details": {
                        "elevation_change_5s": 8,    # 5秒間で+8m
                        "elevation_correlation": 0.82,
                        "pace_change_5s": -0.05,      # ほぼ変化なし
                        "hr_change_5s": 2             # わずかな上昇
                    },
                    "context": {
                        "before_30s": {"gct_avg": 213, "elevation": 45},
                        "after_30s": {"gct_avg": 225, "elevation": 53}
                    }
                },
                {
                    "anomaly_id": 2,
                    "timestamp": 3200,
                    "split_number": 4,
                    "metric": "VO",
                    "value": 9.5,
                    "baseline": 7.8,
                    "deviation_cm": 1.7,
                    "z_score": 3.1,
                    "severity": "high",
                    "probable_cause": "pace_change",
                    "cause_details": {
                        "pace_change_10s": 0.5,       # 10秒で0.5分/km遅く
                        "pace_correlation": 0.91,
                        "elevation_change_10s": 1,    # ほぼ平坦
                        "hr_spike": 5
                    }
                }
            ],
            "summary": {
                "gct_anomalies": 3,
                "vo_anomalies": 4,
                "vr_anomalies": 1,
                "elevation_related": 5,
                "pace_related": 2,
                "fatigue_related": 1
            },
            "recommendations": [
                "上り坂でGCT悪化が顕著 → 上り坂練習強化を推奨",
                "ペース急変時にVO増加 → ペース変化を緩やかに"
            ]
        }
        """
```

**異常検出アルゴリズム**:
1. フォームメトリクス時系列取得
2. ローリング平均・標準偏差計算（60秒窓）
3. Z-score計算で異常検出
4. 前後コンテキストで原因推定:
   - 標高変化 > 5m → "elevation_change"
   - ペース変化 > 15秒/km → "pace_change"
   - HR Drift > 10% → "fatigue"
5. 相関係数計算で確度評価

### MCPツール統合

#### servers/garmin_db_server.py 追加内容

```python
# list_tools() に追加
Tool(
    name="get_interval_analysis",
    description="Analyze interval training Work/Recovery segments with fatigue detection",
    inputSchema={
        "type": "object",
        "properties": {
            "activity_id": {"type": "integer"},
            "pace_threshold_factor": {"type": "number", "default": 1.3},
            "min_work_duration": {"type": "integer", "default": 180},
            "min_recovery_duration": {"type": "integer", "default": 60}
        },
        "required": ["activity_id"]
    }
),
Tool(
    name="get_split_time_series_detail",
    description="Get second-by-second detailed metrics for a specific 1km split",
    inputSchema={
        "type": "object",
        "properties": {
            "activity_id": {"type": "integer"},
            "split_number": {"type": "integer"},
            "metrics": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["activity_id", "split_number"]
    }
),
Tool(
    name="detect_form_anomalies",
    description="Detect form metric anomalies and identify causes (elevation/pace/fatigue)",
    inputSchema={
        "type": "object",
        "properties": {
            "activity_id": {"type": "integer"},
            "metrics": {"type": "array", "items": {"type": "string"}, "default": ["GCT", "VO", "VR"]},
            "z_threshold": {"type": "number", "default": 2.0},
            "context_window": {"type": "integer", "default": 30}
        },
        "required": ["activity_id"]
    }
)

# call_tool() に追加
elif name == "get_interval_analysis":
    from tools.rag.queries.interval_analysis import IntervalAnalyzer
    analyzer = IntervalAnalyzer()
    result = analyzer.get_interval_analysis(
        activity_id=arguments["activity_id"],
        pace_threshold_factor=arguments.get("pace_threshold_factor", 1.3),
        min_work_duration=arguments.get("min_work_duration", 180),
        min_recovery_duration=arguments.get("min_recovery_duration", 60)
    )
    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

# (同様に他2ツール)
```

---

## テスト計画

### Unit Tests

#### test_interval_analysis.py
- [ ] **test_segment_detection_classic_intervals**: 古典的インターバル（5×1000m）を正しく検出
- [ ] **test_segment_detection_fartlek**: ファルトレク（変動ペース）を検出
- [ ] **test_work_recovery_metrics_calculation**: Work/Recovery区間のメトリクス正確性
- [ ] **test_hr_recovery_rate_calculation**: 心拍回復速度計算（bpm/分）
- [ ] **test_fatigue_detection**: 最終インターバルでの疲労検出
- [ ] **test_edge_case_no_intervals**: インターバルなし（定常走）の場合
- [ ] **test_edge_case_warmup_cooldown**: ウォームアップ/クールダウン区間の正しい分類

#### test_time_series_detail.py
- [x] **test_split_range_extraction**: Split番号から正しい時間範囲を抽出
- [x] **test_metric_descriptor_parsing**: 26メトリクスの正しい解析
- [x] **test_unit_conversion**: Factor適用と単位変換の正確性
- [x] **test_statistics_calculation**: 平均・標準偏差・最大最小計算
- [x] **test_anomaly_detection_in_split**: Split内異常値の検出
- [x] **test_missing_metrics_handling**: 欠損メトリクスの適切な処理
- [x] **test_edge_case_split_out_of_range**: 存在しないsplit番号のエラー処理
- [x] **test_get_split_time_series_detail_integration**: 統合テスト（full pipeline）

#### test_form_anomaly_detector.py
- [ ] **test_z_score_anomaly_detection**: Z-scoreベース異常検出の精度
- [ ] **test_elevation_correlation**: 標高変化とGCT/VO相関の検出
- [ ] **test_pace_correlation**: ペース変化とフォーム悪化の相関
- [ ] **test_fatigue_correlation**: HR Driftとフォーム悪化の相関
- [ ] **test_cause_classification**: 原因分類の正確性（3カテゴリ）
- [ ] **test_context_window_extraction**: 前後30秒コンテキストの正確性
- [ ] **test_multiple_metrics_anomaly**: 複数メトリクス同時異常の検出
- [ ] **test_edge_case_no_anomalies**: 異常なしの場合の適切な応答

### Integration Tests

#### test_interval_analysis_integration.py
- [ ] **test_real_interval_activity**: 実際のインターバルトレーニングデータでエンドツーエンド
- [ ] **test_mcp_tool_integration**: MCPツール経由での呼び出し
- [ ] **test_performance_json_integration**: performance.jsonとの整合性
- [ ] **test_activity_details_json_loading**: activity_details.json読み込み

#### test_time_series_integration.py
- [ ] **test_all_splits_extraction**: 全Split（1-10）の一括取得
- [ ] **test_cross_split_anomaly**: Split境界をまたぐ異常検出
- [ ] **test_metrics_consistency**: performance.jsonとactivity_details.jsonの一貫性

#### test_form_anomaly_integration.py
- [ ] **test_full_activity_scan**: アクティビティ全体のスキャン
- [ ] **test_elevation_profile_correlation**: 標高プロファイルとの統合
- [ ] **test_report_generation**: レポート生成への統合

### Performance Tests

- [ ] **test_large_activity_processing**: 15km超（15,000秒）のデータ処理が3秒以内
- [ ] **test_memory_usage**: 1アクティビティ処理のメモリ使用量 < 50MB
- [ ] **test_concurrent_requests**: 5アクティビティ並列処理が10秒以内
- [ ] **test_interval_detection_speed**: インターバル検出が1秒以内
- [ ] **test_anomaly_detection_speed**: 異常検出が2秒以内

---

## 受け入れ基準

### 機能要件
- [ ] **3つのRAGツールが実装され、MCPサーバーに統合されている**
- [ ] **get_interval_analysis**: Work/Recovery区間を自動検出し、疲労指標を算出
- [ ] **get_split_time_series_detail**: 秒単位データを正確に抽出・変換
- [ ] **detect_form_anomalies**: 異常検出と原因分類（3カテゴリ）が動作

### データ品質
- [ ] **activity_details.jsonの26メトリクス全てが正しく解析される**
- [ ] **単位変換（factor適用）が正確に動作する**
- [ ] **欠損データが適切に処理される（None/0埋め）**

### パフォーマンス
- [ ] **1アクティビティ処理が3秒以内（15km活動）**
- [ ] **メモリ使用量が50MB未満**
- [ ] **並列処理で性能劣化がない**

### テスト
- [ ] **全Unit Testsがパスする（21テスト）**
- [ ] **全Integration Testsがパスする（7テスト）**
- [ ] **全Performance Testsがパスする（5テスト）**
- [ ] **カバレッジ85%以上**

### コード品質
- [ ] **Black, Ruff, Mypy チェックがパスする**
- [ ] **Pre-commit hooksがパスする**
- [ ] **型アノテーションが完全**

### ドキュメント
- [ ] **CLAUDE.md に新RAGツールが追加記載されている**
- [ ] **各ツールのdocstringが完備されている**
- [ ] **completion_report.md が作成されている**
- [ ] **既存RAGプロジェクト（2025-10-05_rag_system）との関係が明記されている**

---

## 実装フェーズ

### Phase 1: データローダー実装（2日）✅ **完了 (2025-10-10)**

**目標**: activity_details.jsonを効率的に読み込み、メトリクスを変換する基盤を構築

**タスク**:
1. ✅ **ActivityDetailsLoader クラス実装**
   - ✅ `load_activity_details(activity_id)`: JSON読み込み
   - ✅ `parse_metric_descriptors()`: 26メトリクスのマッピング生成
   - ✅ `extract_time_series(metric_names, start_time, end_time)`: 時系列抽出
   - ✅ `apply_unit_conversion(metric_index, raw_value)`: 単位変換

2. ✅ **ユニットテスト**
   - ✅ test_activity_details_loader.py: 10テスト実装
   - ✅ 基本読み込み、メトリクス解析、単位変換、エラー処理
   - ✅ カバレッジ: 97% (目標85%を超過)

3. ✅ **サンプルデータ検証**
   - ✅ フィクスチャデータ作成（tests/fixtures/）
   - ✅ 公開リポジトリ対応（実データ依存なし）

**成果物**:
- ✅ `tools/rag/loaders/activity_details_loader.py` (184行)
- ✅ `tests/rag/loaders/test_activity_details_loader.py` (172行)
- ✅ `tests/fixtures/data/raw/activity/12345678901/activity_details.json`

**テスト結果**:
- 10 passed, 0 failed, 0 skipped
- Coverage: 97%
- コード品質: Black ✅, Ruff ✅, Mypy ✅

---

### Phase 2: インターバル分析実装（3日）✅ **Phase 2.1完了 (2025-10-10)**

**目標**: get_interval_analysis ツールを完成させる

**タスク**:
1. ✅ **IntervalAnalyzer クラス実装**
   - ✅ `detect_intervals()`: Work/Recovery区間自動検出
   - ✅ `analyze_interval_metrics()`: 各区間のメトリクス集計
   - ✅ `detect_fatigue()`: 疲労蓄積検出
   - ✅ `calculate_recovery_speed()`: HR回復速度計算

2. ✅ **ユニットテスト**
   - ✅ test_interval_analysis.py: 6テストケース実装
   - ✅ Work/Recovery検出、メトリクス集計、疲労検出、HR回復
   - ✅ エッジケース対応（定常走、warmup/cooldown付き）
   - ✅ カバレッジ: 85%

3. ✅ **フィクスチャデータ作成**
   - ✅ 公開リポジトリ対応（実データ依存なし）
   - ✅ 全テストfixture化完了（177 passed, 0 skipped）

**成果物**:
- ✅ `tools/rag/queries/interval_analysis.py` (224行)
- ✅ `tests/rag/queries/test_interval_analysis.py` (360行、7テスト）

**テスト結果**:
- 6 passed, 0 failed, 0 skipped
- Coverage: 85%
- コード品質: Black ✅, Ruff ✅, Mypy ✅
- コミット: `da52422`, `a6321c8`

**追加作業完了**:
- ✅ 全9つのskipped testをfixture化
- ✅ 最終テスト結果: 177 passed, 0 skipped, 4 deselected

---

### Phase 3: 時系列詳細取得実装（2日）✅ **完了 (2025-10-10)**

**目標**: get_split_time_series_detail ツールを完成させる

**タスク**:
1. ✅ **TimeSeriesDetailExtractor クラス実装**
   - ✅ `_get_split_time_range()`: Split番号から時間範囲取得
   - ✅ `_extract_time_series_data()`: 秒単位データ抽出
   - ✅ `_calculate_statistics()`: 統計値計算
   - ✅ `_detect_split_anomalies()`: Split内異常検出
   - ✅ `get_split_time_series_detail()`: 統合API

2. ✅ **ユニットテスト**
   - ✅ test_time_series_detail.py: 8テストケース実装
   - ✅ Split範囲抽出、メトリクス解析、単位変換、統計計算
   - ✅ 異常検出、欠損データ処理、エッジケース対応
   - ✅ カバレッジ: 89% (目標85%を超過)

3. ✅ **フィクスチャデータ作成**
   - ✅ performance.json fixture (12345678901.json)
   - ✅ 公開リポジトリ対応（実データ依存なし）

**成果物**:
- ✅ `tools/rag/queries/time_series_detail.py` (279行)
- ✅ `tests/rag/queries/test_time_series_detail.py` (348行、8テスト）
- ✅ `tests/fixtures/data/performance/12345678901.json`

**テスト結果**:
- 8 passed, 0 failed, 0 skipped
- Coverage: 89%
- コード品質: Black ✅, Ruff ✅, Mypy ✅
- コミット: `ff064ec`

---

### Phase 4: フォーム異常検出実装（3日）

**目標**: detect_form_anomalies ツールを完成させる

**タスク**:
1. **FormAnomalyDetector クラス実装**
   - `_calculate_rolling_stats()`: ローリング統計（60秒窓）
   - `_detect_anomalies_by_zscore()`: Z-score異常検出
   - `_analyze_anomaly_causes()`: 原因分析（標高/ペース/疲労）
   - `_extract_context()`: 前後コンテキスト取得
   - `_generate_recommendations()`: 改善提案生成

2. **相関分析ロジック**
   - 標高変化との相関係数計算
   - ペース変化との相関係数計算
   - HR Driftとの相関計算

3. **ユニットテスト**
   - test_zscore_detection.py: 異常検出精度
   - test_cause_analysis.py: 原因分類精度
   - test_correlation.py: 相関計算精度

4. **実データ検証**
   - 上り坂/下り坂データでの検証
   - 疲労蓄積データでの検証

**成果物**:
- `tools/rag/queries/form_anomaly_detector.py`
- `tests/rag/queries/test_form_anomaly_detector.py`

---

### Phase 5: MCPサーバー統合（1日）

**目標**: 3ツールをGarmin DB MCPサーバーに統合

**タスク**:
1. **servers/garmin_db_server.py 更新**
   - Tool定義追加（3ツール）
   - call_tool() ハンドラー追加
   - エラーハンドリング

2. **統合テスト**
   - test_mcp_interval_analysis.py
   - test_mcp_time_series.py
   - test_mcp_form_anomaly.py

3. **エンドツーエンドテスト**
   - 実アクティビティでMCP経由呼び出し
   - Claude Code UIからの動作確認

**成果物**:
- `servers/garmin_db_server.py` (更新)
- `tests/integration/test_rag_interval_tools_mcp.py`

---

### Phase 6: ドキュメント・完了報告（1日）

**目標**: プロジェクト完了と知識の記録

**タスク**:
1. **CLAUDE.md 更新**
   - RAG Tools セクションに3ツール追加
   - 使用例追加
   - activity_details.json メトリクス表追加

2. **completion_report.md 作成**
   - テスト結果まとめ
   - カバレッジレポート
   - パフォーマンステスト結果
   - 受け入れ基準チェック

3. **既存RAGプロジェクトとの関係記録**
   - docs/project/2025-10-05_rag_system/project_plan.md に本プロジェクト追記
   - Phase 2.5相当としての位置づけ明記

**成果物**:
- `CLAUDE.md` (更新)
- `docs/project/2025-10-09_rag_interval_analysis_tools/completion_report.md`
- `docs/project/2025-10-05_rag_system/project_plan.md` (更新)

---

## リスクと対策

### リスク1: activity_details.jsonの欠損
**詳細**: 古いアクティビティでactivity_details.jsonが存在しない可能性
**対策**:
- ファイル存在チェックを必須に
- 欠損時は明確なエラーメッセージ
- performance.jsonへのフォールバック（精度低下を通知）

### リスク2: メトリクスの不整合
**詳細**: Garmin APIのメトリクス仕様変更でインデックスずれ
**対策**:
- metricDescriptorsのkey名でマッピング（インデックス直接参照避ける）
- バリデーションテストで26メトリクス全て確認
- 不明メトリクスは警告ログ出力

### リスク3: パフォーマンス劣化
**詳細**: 26メトリクス × 1400秒のデータ処理が重い
**対策**:
- 必要メトリクスのみ抽出（不要なデータ読み込まない）
- NumPy配列で効率的処理
- メモリプロファイリングで監視

### リスク4: インターバル検出精度
**詳細**: ファルトレクなど変動ペースで誤検出
**対策**:
- 複数の検出アルゴリズム用意（ペース閾値、機械学習ベース）
- ユーザー調整可能なパラメータ提供
- 検出結果の信頼度スコア算出

### リスク5: 既存RAGシステムとの競合
**詳細**: Phase 3計画（wellness_metrics）との機能重複
**対策**:
- Phase 3は「なぜ」（外部要因）、本PJは「何が」（内部変化）と分離
- データソース明確化（wellness vs activity_details）
- 将来的な統合インターフェース設計

---

## 関連プロジェクト

### 既存RAGシステム（2025-10-05_rag_system）
- **Phase 0**: データインベントリ（完了）
- **Phase 1**: DuckDB拡張ツール（完了）
- **Phase 2**: トレンド分析フィルタリング（完了）
- **Phase 3**: 多変量相関分析（計画済み、wellness_metrics統合）

### 本プロジェクトの位置づけ
- **Phase 2.5相当**: activity_details.json活用による内部変化分析
- **Phase 3との違い**:
  - Phase 3 = 外部要因（睡眠、ストレス、体重） → 「なぜ」
  - Phase 2.5 = 内部変化（秒単位フォーム、インターバル） → 「何が」
- **統合の方向性**: Phase 4で両者を統合した総合分析

---

## 次のステップ

1. **tdd-implementer エージェント起動**
   ```bash
   Task: tdd-implementer
   prompt: "docs/project/2025-10-09_rag_interval_analysis_tools/planning.md に基づいて、Phase 1から順にTDDサイクルで実装してください。"
   ```

2. **Phase 1開始前の準備**
   - activity_details.json サンプルデータ確認
   - 26メトリクスの単位・factor一覧作成
   - performance.json との整合性確認用スクリプト作成

3. **実装優先順位**
   1. ActivityDetailsLoader（基盤）
   2. TimeSeriesDetailExtractor（単純、依存少ない）
   3. IntervalAnalyzer（中程度複雑）
   4. FormAnomalyDetector（最複雑）
   5. MCPサーバー統合

---

**最終更新**: 2025-10-09
**作成者**: Claude Code (project-planner agent)
**ステータス**: 計画完了、実装待ち
