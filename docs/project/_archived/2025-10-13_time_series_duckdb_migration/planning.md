# 計画: time_series_duckdb_migration

**GitHub Issue**: #6

## プロジェクト情報
- **プロジェクト名**: `time_series_duckdb_migration`
- **作成日**: `2025-10-13`
- **完了日**: `2025-10-13`
- **ステータス**: 完了

---

## 要件定義

### 目的

activity_details.jsonの秒単位時系列データ（26メトリクス×1000-2000秒）を完全DuckDB化し、以下を実現する：

1. **トークン効率の大幅改善**: MCPツールでの12.4k tokens消費を90%削減（→1k以下）
2. **クエリ速度の向上**: DuckDB SQLによる高速集計・統計計算
3. **データ管理の一元化**: JSON直接アクセスからDuckDB統合アクセスへ移行
4. **RAGツールの最適化**: 時系列データアクセスの標準化

### 解決する問題

**現状の課題:**

1. **非効率なデータアクセス**:
   - activity_details.jsonを毎回全文ロード（26メトリクス×2000+秒）
   - MCPツール経由で12.4k tokensを消費
   - JSON解析とメトリクス抽出のオーバーヘッド

2. **データ管理の分散**:
   - splitsデータ: DuckDB (`splits` table)
   - 時系列データ: JSON直接アクセス
   - 統一的なクエリインターフェースが欠如

3. **スケーラビリティの限界**:
   - 103アクティビティ×平均1500秒 = 約155,000データポイント
   - JSON解析による遅延（特にバッチ処理）
   - 統計計算をPython側で実行（SQL側で実行可能）

4. **既存ツールへの影響**:
   - `get_split_time_series_detail`: 12.4k tokens消費
   - `get_time_range_detail`: 同様の非効率性
   - `detect_form_anomalies`: JSON依存による速度低下

### ユースケース

1. **Split詳細分析**: 特定1km splitの秒単位メトリクス取得（HR, pace, cadence, GCT, VO, VR）
2. **時間範囲クエリ**: 任意時間範囲（例: warmup 0-300s, Work interval 500-800s）のメトリクス抽出
3. **フォーム異常検出**: GCT/VO/VRの時系列からZ-scoreベース異常検出
4. **統計計算**: SQL側でのAVG, STDDEV, MIN, MAX計算（Python側での後処理排除）
5. **バッチ分析**: 複数アクティビティの時系列データ横断クエリ

---

## 設計

### アーキテクチャ

**データフロー:**

```
GarminIngestWorker.process_activity(activity_id)
  ↓
collect_data() → activity_details.json (raw data)
  ↓
save_data() → 7 existing inserters + NEW: TimeSeriesMetricsInserter
  ↓
DuckDB (time_series_metrics table)
  ↓
MCP Tools (get_split_time_series_detail, get_time_range_detail, detect_form_anomalies)
  ↓
Section Analysts / Report Generation
```

**Before vs After:**

| Component | Before | After |
|-----------|--------|-------|
| Data Source | activity_details.json (JSON) | DuckDB (time_series_metrics) |
| Access Method | ActivityDetailsLoader | DuckDB SQL query |
| Token Usage | 12.4k tokens/query | <1k tokens/query (90%削減) |
| Statistics | Python (statistics.mean, std) | SQL (AVG, STDDEV) |
| Query Speed | Slow (JSON parse) | Fast (indexed SQL) |

### データモデル

**新規テーブル: `time_series_metrics`**

```sql
CREATE TABLE IF NOT EXISTS time_series_metrics (
    activity_id BIGINT NOT NULL,
    timestamp_s INTEGER NOT NULL,

    -- Cumulative metrics
    sum_moving_duration DOUBLE,       -- sumMovingDuration (seconds, factor: 1000.0)
    sum_duration DOUBLE,               -- sumDuration (seconds, factor: 1000.0)
    sum_elapsed_duration DOUBLE,       -- sumElapsedDuration (seconds, factor: 1000.0)
    sum_distance DOUBLE,               -- sumDistance (meters, factor: 100.0)
    sum_accumulated_power DOUBLE,      -- sumAccumulatedPower (watts)

    -- Direct metrics - Core performance
    heart_rate DOUBLE,                 -- directHeartRate (bpm)
    speed DOUBLE,                      -- directSpeed (m/s, factor: 0.1)
    grade_adjusted_speed DOUBLE,       -- directGradeAdjustedSpeed (m/s, factor: 0.1)
    cadence DOUBLE,                    -- directRunCadence (spm)
    power DOUBLE,                      -- directPower (watts)

    -- Direct metrics - Form efficiency
    ground_contact_time DOUBLE,        -- directGroundContactTime (ms)
    vertical_oscillation DOUBLE,       -- directVerticalOscillation (cm)
    vertical_ratio DOUBLE,             -- directVerticalRatio (dimensionless)
    stride_length DOUBLE,              -- directStrideLength (cm)
    vertical_speed DOUBLE,             -- directVerticalSpeed (m/s, factor: 0.1)

    -- Direct metrics - Environment & GPS
    elevation DOUBLE,                  -- directElevation (meters, factor: 100.0)
    air_temperature DOUBLE,            -- directAirTemperature (Celsius)
    latitude DOUBLE,                   -- directLatitude (decimal degrees)
    longitude DOUBLE,                  -- directLongitude (decimal degrees)

    -- Direct metrics - Body & Device
    available_stamina DOUBLE,          -- directAvailableStamina
    potential_stamina DOUBLE,          -- directPotentialStamina
    body_battery DOUBLE,               -- directBodyBattery
    performance_condition DOUBLE,      -- directPerformanceCondition

    -- Cadence variants (stored for completeness)
    fractional_cadence DOUBLE,         -- directFractionalCadence
    double_cadence DOUBLE,             -- directDoubleCadence

    PRIMARY KEY (activity_id, timestamp_s)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_time_series_activity ON time_series_metrics(activity_id);
CREATE INDEX IF NOT EXISTS idx_time_series_timestamp ON time_series_metrics(activity_id, timestamp_s);
```

**Design Decisions:**

1. **Timestamp as Integer**: `timestamp_s` は開始からの経過秒数（0, 1, 2, ...）
   - sumDurationから計算（factor: 1000.0で除算）
   - Split time range query: `WHERE timestamp_s BETWEEN start_time_s AND end_time_s`

2. **26 Metrics Mapping**: activity_details.jsonの全メトリクスを格納
   - メトリクス名の正規化: `directHeartRate` → `heart_rate`
   - Unit conversion適用: factor考慮（例: speed × 0.1, elevation ÷ 100.0）

3. **NULL値許容**: 一部メトリクスは特定時点で欠損する可能性
   - 例: powerはデバイスによって記録なし
   - 例: GPSロスト時のlatitude/longitude

4. **Composite Primary Key**: `(activity_id, timestamp_s)`でユニーク性保証

5. **インデックス最適化**:
   - `activity_id`: 単一アクティビティ全取得
   - `(activity_id, timestamp_s)`: 時間範囲クエリ

### API/インターフェース設計

#### 1. TimeSeriesMetricsInserter

```python
# tools/database/inserters/time_series_metrics.py

def insert_time_series_metrics(
    activity_details_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert time series metrics from activity_details.json to DuckDB.

    Args:
        activity_details_file: Path to raw/activity/{activity_id}/activity_details.json
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: get_default_db_path())

    Returns:
        True if successful, False otherwise

    Process:
        1. Load activity_details.json
        2. Parse metricDescriptors for name->index mapping
        3. Extract activityDetailMetrics array
        4. Convert each data point:
           - Extract timestamp_s from sumDuration
           - Apply unit conversions (factors)
           - Map metric names to normalized column names
        5. Batch insert (~1000-2000 rows/activity)
        6. Handle duplicates (DELETE before INSERT)
    """
    pass
```

#### 2. GarminIngestWorker Integration

```python
# tools/ingest/garmin_worker.py

class GarminIngestWorker:
    def save_data(self, activity_id: int, date: str) -> dict:
        """Save processed data to DuckDB using inserters."""
        # ... existing code ...

        # NEW: Insert time series metrics
        from tools.database.inserters.time_series_metrics import (
            insert_time_series_metrics,
        )

        activity_details_file = (
            self.base_path / "raw" / "activity" / str(activity_id) / "activity_details.json"
        )

        if activity_details_file.exists():
            success = insert_time_series_metrics(
                activity_details_file=str(activity_details_file),
                activity_id=activity_id,
            )
            if success:
                logger.info(f"Inserted time series metrics for activity {activity_id}")
            else:
                logger.error(f"Failed to insert time series metrics for activity {activity_id}")
        else:
            logger.warning(f"activity_details.json not found for activity {activity_id}")

        # ... existing code ...
```

#### 3. MCP Tool Refactoring

**Before (JSON-based):**

```python
# tools/rag/queries/time_series_detail.py (OLD)

def extract_metrics(self, activity_id, start_time, end_time, metrics):
    # Load entire activity_details.json (12.4k tokens)
    activity_details = self.loader.load_activity_details(activity_id)
    # Parse metric descriptors
    metric_map = self.loader.parse_metric_descriptors(...)
    # Extract time series
    time_series = self.loader.extract_time_series(...)
    # Filter by time range
    filtered = [point for point in time_series if start_time <= point['timestamp_s'] <= end_time]
    # Calculate statistics (Python)
    stats = {
        "mean": statistics.mean(values),
        "std": statistics.stdev(values),
        # ...
    }
    return result  # 12.4k tokens returned
```

**After (DuckDB-based):**

```python
# tools/rag/queries/time_series_detail.py (NEW)

def extract_metrics_from_db(self, activity_id, start_time, end_time, metrics):
    """
    Extract time series metrics from DuckDB with SQL-based statistics.

    Returns:
        {
            "activity_id": int,
            "time_range": {"start_time_s": int, "end_time_s": int},
            "metrics": [str],
            "statistics": {
                "heart_rate": {"avg": float, "std": float, "min": float, "max": float},
                # ... other metrics
            },
            "data_points": int,
            "anomalies": [...]  # Optional: z-score based
        }
    """
    import duckdb
    from tools.database.db_reader import GarminDBReader

    db_reader = GarminDBReader()
    conn = duckdb.connect(str(db_reader.db_path), read_only=True)

    # Build SQL query for statistics
    metric_columns = ", ".join(metrics)
    stats_sql = ", ".join([
        f"AVG({m}) as {m}_avg, STDDEV({m}) as {m}_std, MIN({m}) as {m}_min, MAX({m}) as {m}_max"
        for m in metrics
    ])

    query = f"""
    SELECT
        {stats_sql},
        COUNT(*) as data_points
    FROM time_series_metrics
    WHERE activity_id = ?
      AND timestamp_s BETWEEN ? AND ?
    """

    result = conn.execute(query, [activity_id, start_time, end_time]).fetchone()
    conn.close()

    # Format result (compact, <1k tokens)
    return format_statistics_result(result, metrics)
```

**Token Reduction:**
- Before: 12.4k tokens (full time series returned)
- After: <1k tokens (statistics only)
- Reduction: ~90%

#### 4. DuckDB Query Helper Functions

```python
# tools/database/db_reader.py

class GarminDBReader:
    def get_time_series_statistics(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
    ) -> dict:
        """Get statistics for specified metrics in time range."""
        pass

    def get_time_series_raw(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
        limit: int | None = None,
    ) -> list[dict]:
        """Get raw time series data (for detailed analysis)."""
        pass

    def detect_anomalies_sql(
        self,
        activity_id: int,
        metrics: list[str],
        z_threshold: float = 2.0,
    ) -> list[dict]:
        """Detect anomalies using SQL-based z-score calculation."""
        pass
```

---

## 実装フェーズ

### Phase 1: DuckDB Schema & Inserter (2日)

**Goal**: time_series_metricsテーブル作成とデータ挿入機能実装

**Tasks:**
1. ✅ **Schema設計完了** (planning.md)
2. **Inserter実装**: `tools/database/inserters/time_series_metrics.py`
   - `insert_time_series_metrics()` 関数実装
   - activity_details.json解析ロジック
   - 26メトリクスのunit conversion実装
   - timestamp_s計算（sumDuration / 1000.0）
   - バッチインサート（1000-2000 rows）
3. **GarminDBWriter統合**: `_ensure_tables()` にスキーマ追加
4. **Unit Tests**:
   - `tests/database/inserters/test_time_series_metrics.py`
   - メトリクス変換テスト
   - バッチインサートテスト
   - 重複処理テスト

**Acceptance Criteria:**
- [ ] time_series_metricsテーブルがDuckDBに作成される
- [ ] 1アクティビティの時系列データ（~1500行）を挿入できる
- [ ] Unit conversion正確（speed × 0.1, elevation ÷ 100.0）
- [ ] 全Unit Tests pass

### Phase 2: GarminIngestWorker Integration (1日)

**Goal**: 既存データパイプラインにInserter統合

**Tasks:**
1. **save_data()修正**: TimeSeriesMetricsInserter呼び出し追加
2. **エラーハンドリング**: activity_details.json不在時の処理
3. **ログ追加**: 挿入成功/失敗の記録
4. **Integration Tests**:
   - `tests/ingest/test_garmin_worker_time_series.py`
   - 完全パイプラインテスト（API → DuckDB）

**Acceptance Criteria:**
- [ ] process_activity()実行時、time_series_metricsに自動挿入
- [ ] activity_details.json不在でもエラーで停止しない
- [ ] Integration Tests pass

### Phase 3: Migration Script (1日)

**Goal**: 既存103アクティビティの時系列データをDuckDB化

**Tasks:**
1. **スクリプト作成**: `tools/scripts/migrate_time_series_to_duckdb.py`
   - 全アクティビティのactivity_details.jsonを走査
   - TimeSeriesMetricsInserterで一括挿入
   - 進捗表示（tqdm）
   - エラーハンドリング（スキップして継続）
2. **Dry-run mode**: `--dry-run` オプション
3. **検証機能**: 挿入後のデータ整合性確認
4. **実行**: 103アクティビティ全てを移行

**Acceptance Criteria:**
- [ ] 103アクティビティ全てがtime_series_metricsに挿入完了
- [ ] 挿入エラー0件（または記録されたエラーを修正）
- [ ] データ整合性確認: 各アクティビティのデータポイント数が一致

### Phase 4: MCP Tool Refactoring (2日)

**Goal**: RAGツールをDuckDBベースに書き換え、トークン削減実現

**Tasks:**

**4.1 get_split_time_series_detail書き換え**
- tools/rag/queries/time_series_detail.py の `extract_metrics()` をDuckDB版に置き換え
- SQL統計計算実装
- 異常検出ロジックをSQL化（z-score計算）
- テスト: `tests/rag/queries/test_time_series_detail_db.py`

**4.2 get_time_range_detail書き換え**
- 同様にDuckDBクエリに変更
- 任意時間範囲のクエリ最適化

**4.3 detect_form_anomalies最適化**
- tools/rag/queries/form_anomaly_detector.py の一部をDuckDB化
- 候補: 統計計算とフィルタリングをSQL側で実行
- 異常検出アルゴリズムはPythonで保持（複雑なロジック）

**4.4 GarminDBReader拡張**
- `get_time_series_statistics()` 実装
- `get_time_series_raw()` 実装
- `detect_anomalies_sql()` 実装（オプション）

**Acceptance Criteria:**
- [ ] get_split_time_series_detail のトークン使用量が90%削減（12.4k → <1k）
- [ ] 統計計算がSQL側で実行される（AVG, STDDEV, MIN, MAX）
- [ ] 既存の分析結果と互換性維持（結果が同等）
- [ ] 全RAGツールテストがpass

### Phase 5: Documentation & Cleanup (1日)

**Goal**: ドキュメント更新と後方互換性整理

**Tasks:**
1. **CLAUDE.md更新**:
   - DuckDBスキーマセクションに `time_series_metrics` 追加
   - MCPツールセクション更新（トークン削減実績）
   - Data Processing Architectureに時系列データフロー追加

2. **docs/spec/ 作成**:
   - `docs/spec/time_series_metrics_schema.md`: テーブル仕様詳細
   - `docs/spec/mcp_tools_token_optimization.md`: トークン最適化実績
   - `docs/spec/mapping.md`: CLAUDE.md ↔ spec/ のマッピング定義

3. **後方互換性検討**:
   - ActivityDetailsLoaderは保持（生JSONアクセスが必要な場合用）
   - 旧MCPツールの非推奨化（Deprecation警告）
   - レガシーコードパス削除の計画（Phase 6以降）

4. **Code cleanup**:
   - 未使用import削除
   - Type hints完全化
   - Docstring整備

**Acceptance Criteria:**
- [ ] CLAUDE.md が最新仕様を反映
- [ ] docs/spec/ が完備（3ファイル）
- [ ] Code quality checks pass (Black, Ruff, Mypy)

---

## テスト計画

### Unit Tests

**Phase 1: Inserter Tests** (`tests/database/inserters/test_time_series_metrics.py`)
- [ ] `test_insert_time_series_metrics_success`: 正常挿入
- [ ] `test_metric_name_conversion`: directHeartRate → heart_rate 変換
- [ ] `test_unit_conversion_speed`: speed × 0.1 適用確認
- [ ] `test_unit_conversion_elevation`: elevation ÷ 100.0 適用確認
- [ ] `test_timestamp_calculation`: sumDuration → timestamp_s 計算
- [ ] `test_batch_insert_performance`: 2000行挿入が1秒以内
- [ ] `test_duplicate_handling`: 既存データDELETE後INSERT
- [ ] `test_null_handling`: 欠損メトリクスがNULLで挿入
- [ ] `test_invalid_json`: JSONエラー時の例外処理

**Phase 2: GarminIngestWorker Tests** (`tests/ingest/test_garmin_worker_time_series.py`)
- [ ] `test_save_data_with_time_series`: save_data()がtime_series挿入呼び出し
- [ ] `test_save_data_missing_activity_details`: activity_details.json不在でもエラー回避

**Phase 4: RAG Tool Tests** (`tests/rag/queries/test_time_series_detail_db.py`)
- [ ] `test_extract_metrics_from_db_statistics`: SQL統計計算が正確
- [ ] `test_extract_metrics_token_reduction`: 返却データが<1k tokens
- [ ] `test_db_vs_json_compatibility`: DuckDB版とJSON版が同じ統計値
- [ ] `test_anomaly_detection_sql`: SQL異常検出が正確

### Integration Tests

**Full Pipeline Test** (`tests/integration/test_time_series_pipeline.py`)
- [ ] `test_end_to_end_pipeline`: activity_details.json → DuckDB → MCP Tool
  - GarminIngestWorker.process_activity() 実行
  - time_series_metricsテーブル確認
  - get_split_time_series_detail() 実行
  - 結果の正確性検証

**Migration Test** (`tests/scripts/test_migrate_time_series.py`)
- [ ] `test_migration_dry_run`: Dry-runモードで実行、エラーなし
- [ ] `test_migration_single_activity`: 1アクティビティ移行成功
- [ ] `test_migration_integrity`: 移行後データポイント数一致

### Performance Tests

**Token Usage Test**
- [ ] `test_mcp_tool_token_usage`: get_split_time_series_detail のトークン使用量測定
  - Before (JSON): 12.4k tokens
  - After (DuckDB): <1k tokens
  - Target: 90%削減達成

**Query Speed Test**
- [ ] `test_query_speed_comparison`:
  - JSON parse + extract: ベースライン測定
  - DuckDB SQL query: 比較測定
  - Target: 5倍以上高速化

**Batch Insert Test**
- [ ] `test_bulk_insert_performance`:
  - 103アクティビティ（~155,000行）の一括挿入
  - Target: 5分以内完了

---

## 受け入れ基準

### Functional Requirements
- [ ] time_series_metricsテーブルが26メトリクス全てを格納
- [ ] 103アクティビティ全てがDuckDBに挿入完了（~155,000行）
- [ ] GarminIngestWorker.process_activity()で自動的に時系列データ挿入
- [ ] get_split_time_series_detail がDuckDBから統計情報を返す
- [ ] get_time_range_detail がDuckDBから任意時間範囲データを返す

### Performance Requirements
- [ ] MCPツールのトークン使用量が90%削減（12.4k → <1k）
- [ ] DuckDBクエリが5倍以上高速（vs JSON parse）
- [ ] バッチインサート（2000行）が1秒以内

### Quality Requirements
- [ ] 全Unit Tests pass（既存342 + 新規20+ = 362+ tests）
- [ ] 全Integration Tests pass
- [ ] Code coverage 80%以上（新規コード）
- [ ] Pre-commit hooks pass（Black, Ruff, Mypy）

### Documentation Requirements
- [ ] CLAUDE.md が最新仕様を反映
- [ ] docs/spec/ が完備（3ファイル: schema, optimization, mapping）
- [ ] 各関数にdocstring完備

### Data Integrity Requirements
- [ ] 移行後データポイント数がactivity_details.jsonと一致
- [ ] Unit conversion正確性検証（サンプル10件手動確認）
- [ ] NULL値処理が適切（欠損メトリクス）

---

## 制約・考慮事項

### Technical Constraints

1. **activity_details.jsonは保持**:
   - Raw data sourceとして維持
   - DuckDBは派生データ（再生成可能）
   - 部分再取得（force_refetch）時にDuckDBも再挿入

2. **データ二重管理の整合性**:
   - activity_details.json 更新 → DuckDB再挿入必須
   - GarminIngestWorker.process_activity() で自動同期
   - マイグレーションスクリプトで整合性確認機能

3. **スキーマ拡張性**:
   - 新メトリクス追加時: ALTER TABLE対応
   - メトリクス名変更時: カラムエイリアス対応
   - バージョン管理: スキーマバージョン番号検討（Phase 6以降）

4. **後方互換性**:
   - ActivityDetailsLoaderは削除しない（生JSON必要な場合用）
   - 旧MCPツールに非推奨警告追加
   - レガシーコード削除は慎重に（Phase 6以降）

### Performance Considerations

1. **DuckDB ファイルサイズ**:
   - 現状: splits (103活動×平均10 splits) = ~1,000行
   - 追加: time_series (103活動×平均1500秒) = ~155,000行
   - 予想増加: ~50MB → 実測必要

2. **インデックスオーバーヘッド**:
   - PRIMARY KEY: (activity_id, timestamp_s)
   - INDEX: activity_id, (activity_id, timestamp_s)
   - Write速度への影響: バッチインサート推奨

3. **クエリ最適化**:
   - 統計計算はSQL側で実行（AVG, STDDEV）
   - Time rangeクエリはインデックス利用
   - LIMIT句で大量データ取得を制限

### Data Migration Risks

1. **既存103アクティビティの移行失敗リスク**:
   - Mitigation: Dry-runモード必須
   - Mitigation: エラー時はスキップして継続
   - Mitigation: 失敗アクティビティのログ記録

2. **activity_details.json不在アクティビティ**:
   - 対応: bulk_fetch_activity_details.pyで事前取得
   - 対応: 不在時はWARNINGログのみ（エラーで停止しない）

3. **メトリクス欠損への対応**:
   - 一部デバイスはpower非記録 → NULL許容
   - GPS欠損時のlatitude/longitude → NULL許容

### Testing Strategy

1. **Fixture準備**:
   - テスト用activity_details.json（tests/fixtures/raw/activity/{id}/）
   - 既存20636804823を活用
   - 追加: メトリクス欠損パターンのfixture作成

2. **Token測定方法**:
   - tiktoken ライブラリでトークン数計測
   - Before/After比較を自動化
   - CI/CDでリグレッション検出

3. **パフォーマンステスト環境**:
   - 本番相当データ（103アクティビティ）
   - ローカル環境での実測
   - CI/CDでは軽量版テスト

---

## プロジェクトタイムライン

| Phase | 期間 | 主要成果物 |
|-------|------|-----------|
| Phase 1 | 2日 | TimeSeriesMetricsInserter, Schema, Unit Tests |
| Phase 2 | 1日 | GarminIngestWorker統合, Integration Tests |
| Phase 3 | 1日 | Migration Script, 103アクティビティ移行完了 |
| Phase 4 | 2日 | MCP Tool Refactoring, トークン削減実現 |
| Phase 5 | 1日 | Documentation, Code Cleanup |
| **Total** | **7日** | **完全DuckDB化達成** |

---

## 成功指標

### Quantitative Metrics
- ✅ トークン削減率: 90%以上（12.4k → <1k）
- ✅ クエリ速度向上: 5倍以上
- ✅ データ完全性: 103/103アクティビティ移行成功
- ✅ テストカバレッジ: 80%以上（新規コード）

### Qualitative Metrics
- ✅ コード可読性向上: SQL vs Python処理の分離明確化
- ✅ 保守性向上: データアクセスの標準化
- ✅ スケーラビリティ: 1000+アクティビティへの拡張容易性

---

## 次のステップ（Phase 6以降）

1. **スキーマバージョン管理**: Alembic導入検討
2. **レガシーコード削除**: ActivityDetailsLoader非推奨化、最終削除
3. **追加最適化**: Parquet export、BI連携
4. **新機能**: 時系列データのバッチ分析、トレンド可視化
