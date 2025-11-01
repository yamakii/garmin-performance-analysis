# 計画: Remove performance.json Generation (DuckDB-First Architecture)

## プロジェクト情報
- **プロジェクト名**: `remove_performance_json`
- **作成日**: `2025-10-14`
- **ステータス**: 計画中
- **GitHub Issue**: [#24](https://github.com/yamakii/garmin-performance-analysis/issues/24)

## 要件定義

### 目的
現在の3層データパイプライン（Raw → Performance JSON → DuckDB）を2層に簡略化し（Raw → DuckDB）、ストレージ効率、処理速度、保守性を向上させる。performance.json生成を完全に削除し、DuckDBを唯一のデータソースとする。

### 解決する問題

**現状の課題:**
1. **データ重複によるストレージ無駄**: performance.jsonとDuckDBの両方に同一データを保存（~50%の無駄）
2. **2回のデータ処理オーバーヘッド**: Raw → JSON変換 + JSON → DuckDB挿入
3. **データ整合性リスク**: JSONとDuckDBの内容が乖離する可能性
4. **保守コストの増加**: 2つのデータ形式（JSON + DuckDB）を維持
5. **テストの複雑性**: JSONベースのテストとDuckDBベースのテストが混在

**根本原因:**
- 歴史的経緯: DuckDB導入前にperformance.json形式でデータを保存していた
- 段階的移行: DuckDBを導入したが、performance.json生成を残したまま
- 後方互換性: 一部のテストがperformance.jsonに依存

### ユースケース

1. **データ取得の一元化**
   - すべてのデータ取得をDuckDBから実行
   - JSONファイル読み込みの排除
   - MCP Server経由での効率的なアクセス

2. **ストレージ削減**
   - performance.json削除により~50%のディスク使用量削減
   - data/performance/ディレクトリの完全削除

3. **処理速度向上**
   - JSONシリアライゼーション処理の排除
   - 直接DuckDB挿入による高速化

4. **保守性向上**
   - データ形式の一元化（DuckDBのみ）
   - テストの簡略化（DuckDBベースのみ）

---

## 設計

### アーキテクチャ変更

#### Before (Current):
```
Raw Data (API) → Performance JSON → DuckDB → Analysis
                     ↓
              (Test dependencies)
```

**Data Flow:**
1. `GarminIngestWorker.process_activity()` → API呼び出し
2. `create_parquet_dataset()` → performance.json生成 (11 sections)
3. `GarminDBWriter.insert_*()` → performance.jsonから読み込み → DuckDB挿入
4. Analysis & Report → DuckDBから取得

**Storage:**
- `data/raw/{activity_id}/`: 8 API response files
- `data/performance/{activity_id}.json`: 11 sections (~500KB/activity)
- `data/database/garmin.duckdb`: Normalized tables

#### After (Target):
```
Raw Data (API) → DuckDB → Analysis
                    ↓
            (Direct insertion)
```

**Data Flow:**
1. `GarminIngestWorker.process_activity()` → API呼び出し
2. `GarminDBWriter.insert_*()` → Raw dataから直接DuckDB挿入
3. Analysis & Report → DuckDBから取得

**Storage:**
- `data/raw/{activity_id}/`: 8 API response files (unchanged)
- `data/database/garmin.duckdb`: Normalized tables (unchanged)
- ❌ `data/performance/`: **DELETED**

### 影響分析

#### 変更が必要なファイル

**Core Processing:**
1. `tools/ingest/garmin_worker.py` (`GarminIngestWorker` class)
   - `process_activity()`: performance.json生成呼び出しを削除
   - `collect_data()`: 変更不要（Raw data取得のみ）

2. `tools/ingest/create_parquet_dataset.py` (`create_parquet_dataset()`)
   - **完全削除**: performance.json生成ロジック
   - 11セクション生成コード（splits, heart_rate_zones, form_efficiency, etc.）

**Database Inserters (8 files):**
3. `tools/database/inserters/activity_inserter.py`
   - `insert_activity()`: performance.json読み込み → Raw dataから直接取得
4. `tools/database/inserters/splits_inserter.py`
   - `insert_splits()`: performance.json読み込み → splits.jsonから直接取得
5. `tools/database/inserters/form_efficiency_inserter.py`
   - `insert_form_efficiency()`: performance.json読み込み → activity_details.jsonから計算
6. `tools/database/inserters/hr_efficiency_inserter.py`
   - `insert_hr_efficiency()`: performance.json読み込み → heart_rate_zones.jsonから計算
7. `tools/database/inserters/heart_rate_zones_inserter.py`
   - `insert_heart_rate_zones()`: performance.json読み込み → heart_rate_zones.jsonから直接取得
8. `tools/database/inserters/vo2_max_inserter.py`
   - `insert_vo2_max()`: performance.json読み込み → vo2_max.jsonから直接取得
9. `tools/database/inserters/lactate_threshold_inserter.py`
   - `insert_lactate_threshold()`: performance.json読み込み → lactate_threshold.jsonから直接取得
10. `tools/database/inserters/performance_trends_inserter.py`
    - `insert_performance_trends()`: performance.json読み込み → 複数Raw dataから計算

**Time Series Inserter:**
11. `tools/database/inserters/time_series_inserter.py`
    - `insert_time_series_metrics()`: activity_details.jsonから直接取得（変更不要の可能性）

**Tests:**
12. `tests/test_create_parquet_dataset.py` → **完全削除**
13. `tests/database/inserters/test_*_inserter.py` (8 files)
    - performance.jsonベースのフィクスチャ → Raw dataベースに変更
    - テストデータ準備方法の変更
14. `tests/integration/test_garmin_worker.py`
    - performance.json生成確認テスト → DuckDB挿入確認に変更

**Scripts:**
15. `tools/scripts/regenerate_duckdb.py`
    - performance.json読み込み → Raw dataから直接処理
    - `--force-refetch-performance` オプション削除

#### 利点 (Benefits)

1. **ストレージ削減**: ~50% less disk usage (performance.json削除)
2. **処理速度向上**: JSONシリアライゼーション排除による高速化
3. **データ整合性**: 単一データソース（DuckDB）による整合性保証
4. **保守性向上**: データ形式の一元化、コードの簡略化
5. **テスト簡略化**: DuckDBベースのテストのみ

#### 課題 (Challenges)

1. **Raw dataパース複雑化**: performance.jsonの中間抽象化レイヤーが消失
   - **対策**: Inserter内でパースロジックをカプセル化
2. **後方互換性**: 既存のperformance.jsonに依存するコードが動作しなくなる
   - **対策**: 段階的移行（Phase 1-2でInserter対応、Phase 3で削除）
3. **テストデータ準備**: performance.jsonベースのフィクスチャが使えなくなる
   - **対策**: Raw dataベースのフィクスチャを作成（小規模なJSONサンプル）
4. **デバッグ難易度**: 中間データ（performance.json）がなくなる
   - **対策**: DuckDB直接クエリ、MCPツール活用

### データモデル

#### DuckDB Schema (変更なし)

```sql
-- Existing tables (no schema changes)
CREATE TABLE activities (
    activity_id INTEGER PRIMARY KEY,
    date DATE NOT NULL,
    activity_name TEXT,
    activity_type TEXT,
    distance_km REAL,
    duration_s INTEGER,
    avg_pace_min_per_km REAL,
    avg_hr INTEGER,
    -- ... (other fields)
);

CREATE TABLE splits (
    activity_id INTEGER,
    split_number INTEGER,
    distance_km REAL,
    duration_s INTEGER,
    pace_min_per_km REAL,
    avg_hr INTEGER,
    -- ... (other fields)
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

-- Other tables: form_efficiency, heart_rate_zones, hr_efficiency,
--               performance_trends, vo2_max, lactate_threshold, time_series_metrics
```

**重要:** DuckDBスキーマは変更しない。データの取得元のみ変更。

### API/インターフェース設計

#### GarminIngestWorker

**Before:**
```python
class GarminIngestWorker:
    def process_activity(self, activity_id: int, date: str, force_refetch: dict | None = None):
        # 1. Fetch raw data
        self.collect_data(activity_id, force_refetch)

        # 2. Generate performance.json
        create_parquet_dataset(activity_id, date)

        # 3. Insert to DuckDB
        self.db_writer.insert_activity(activity_id, date)
        # ... (other inserters)
```

**After:**
```python
class GarminIngestWorker:
    def process_activity(self, activity_id: int, date: str, force_refetch: dict | None = None):
        # 1. Fetch raw data
        self.collect_data(activity_id, force_refetch)

        # 2. Insert to DuckDB (directly from raw data)
        self.db_writer.insert_activity(activity_id, date)
        # ... (other inserters)
```

#### Inserters

**Before:**
```python
class ActivityInserter:
    def insert_activity(self, activity_id: int, date: str):
        # Read from performance.json
        performance_path = get_performance_file_path(activity_id)
        with open(performance_path) as f:
            data = json.load(f)

        # Extract activity section
        activity_data = data["activity"]

        # Insert to DuckDB
        self.conn.execute("INSERT INTO activities ...", activity_data)
```

**After:**
```python
class ActivityInserter:
    def insert_activity(self, activity_id: int, date: str):
        # Read from raw data (activity_details.json)
        raw_path = get_raw_file_path(activity_id, "activity_details")
        with open(raw_path) as f:
            raw_data = json.load(f)

        # Extract and transform
        activity_data = self._extract_activity_from_raw(raw_data)

        # Insert to DuckDB
        self.conn.execute("INSERT INTO activities ...", activity_data)

    def _extract_activity_from_raw(self, raw_data: dict) -> dict:
        """Extract activity data from raw API response."""
        # Parsing logic (previously in create_parquet_dataset)
        return {
            "activity_id": raw_data["activityId"],
            "activity_name": raw_data["activityName"],
            # ... (other fields)
        }
```

**Key Design Principle:**
- Inserter内でRaw dataパースロジックをカプセル化
- `_extract_*_from_raw()` ヘルパーメソッドで変換処理を実装
- 既存のDuckDB挿入ロジックは変更不要

---

## 実装フェーズ

### Phase 1: ActivityInserter Refactoring (~3 hours)
**Goal:** `ActivityInserter`をperformance.json依存からRaw data直接読み込みに移行

**Tasks:**
1. `ActivityInserter._extract_activity_from_raw()` 実装
   - `activity_details.json`から必要フィールドを抽出
   - performance.jsonの`activity`セクションと同等のデータを生成
2. `ActivityInserter.insert_activity()` リファクタリング
   - performance.json読み込み削除
   - Raw data読み込みに変更
3. 単体テスト更新
   - performance.jsonフィクスチャ → Raw dataフィクスチャ
   - 既存のテストケースすべて動作確認

**Acceptance Criteria:**
- `ActivityInserter`がRaw dataから直接データを取得
- 既存の単体テストすべて合格
- DuckDBに挿入されるデータが変更前と同一

**Related Files:**
- `tools/database/inserters/activity_inserter.py`
- `tests/database/inserters/test_activity_inserter.py`

### Phase 2: Other Inserters Refactoring (~6 hours)
**Goal:** 残り7つのInserterをRaw data直接読み込みに移行

**Tasks:**
1. **SplitsInserter** (~1 hour)
   - `_extract_splits_from_raw()`: splits.jsonから直接取得
   - テスト更新
2. **FormEfficiencyInserter** (~1 hour)
   - `_extract_form_efficiency_from_raw()`: activity_details.jsonから計算
   - GCT, VO, VRの平均値計算ロジック実装
   - テスト更新
3. **HrEfficiencyInserter** (~1 hour)
   - `_extract_hr_efficiency_from_raw()`: heart_rate_zones.jsonから計算
   - Zone distribution計算ロジック実装
   - テスト更新
4. **HeartRateZonesInserter** (~1 hour)
   - `_extract_heart_rate_zones_from_raw()`: heart_rate_zones.jsonから直接取得
   - テスト更新
5. **Vo2MaxInserter** (~0.5 hour)
   - `_extract_vo2_max_from_raw()`: vo2_max.jsonから直接取得
   - テスト更新
6. **LactateThresholdInserter** (~0.5 hour)
   - `_extract_lactate_threshold_from_raw()`: lactate_threshold.jsonから直接取得
   - テスト更新
7. **PerformanceTrendsInserter** (~1 hour)
   - `_extract_performance_trends_from_raw()`: 複数Raw dataから計算
   - Pace consistency, HR drift計算ロジック実装
   - テスト更新

**Acceptance Criteria:**
- 全Inserterが performance.json 依存から脱却
- 全単体テスト合格
- DuckDBに挿入されるデータが変更前と同一

**Related Files:**
- `tools/database/inserters/splits_inserter.py`
- `tools/database/inserters/form_efficiency_inserter.py`
- `tools/database/inserters/hr_efficiency_inserter.py`
- `tools/database/inserters/heart_rate_zones_inserter.py`
- `tools/database/inserters/vo2_max_inserter.py`
- `tools/database/inserters/lactate_threshold_inserter.py`
- `tools/database/inserters/performance_trends_inserter.py`
- `tests/database/inserters/test_*_inserter.py` (7 files)

### Phase 3: Remove Performance JSON Generation (~2 hours)
**Goal:** performance.json生成コードを完全削除

**Tasks:**
1. `create_parquet_dataset.py` 完全削除
   - 11セクション生成ロジック削除
   - `create_parquet_dataset()`関数削除
2. `GarminIngestWorker.process_activity()` 更新
   - `create_parquet_dataset()` 呼び出し削除
   - コメント更新
3. `test_create_parquet_dataset.py` 完全削除
4. 統合テスト更新
   - `test_garmin_worker.py`: performance.json生成確認テスト削除
   - DuckDB挿入確認テストに変更

**Acceptance Criteria:**
- `create_parquet_dataset.py` 削除
- `GarminIngestWorker` がperformance.json生成を呼び出さない
- 全統合テスト合格

**Related Files:**
- `tools/ingest/create_parquet_dataset.py` (DELETE)
- `tools/ingest/garmin_worker.py`
- `tests/test_create_parquet_dataset.py` (DELETE)
- `tests/integration/test_garmin_worker.py`

### Phase 4: Update Scripts & Documentation (~1.5 hours)
**Goal:** スクリプトとドキュメントを更新

**Tasks:**
1. `regenerate_duckdb.py` 更新
   - performance.json読み込み削除
   - Raw dataから直接処理
   - `--force-refetch-performance` オプション削除
2. `CLAUDE.md` 更新
   - アーキテクチャ図更新（2層パイプライン）
   - Data Processing Pipeline セクション更新
   - Directory Structure セクション更新（`data/performance/`削除）
3. `README.md` 更新（存在する場合）
   - データフロー図更新

**Acceptance Criteria:**
- `regenerate_duckdb.py` がRaw dataから処理
- CLAUDE.md が新アーキテクチャを反映
- ドキュメントが最新状態

**Related Files:**
- `tools/scripts/regenerate_duckdb.py`
- `CLAUDE.md`
- `README.md` (if exists)

---

## テスト計画

### Unit Tests

#### ActivityInserter (Phase 1)
- [ ] `test_extract_activity_from_raw_success` - Raw dataから正常抽出
- [ ] `test_extract_activity_from_raw_missing_fields` - 欠損フィールド処理
- [ ] `test_insert_activity_from_raw_data` - Raw dataから挿入成功
- [ ] `test_insert_activity_data_integrity` - データ整合性確認（変更前と同一）

#### SplitsInserter (Phase 2)
- [ ] `test_extract_splits_from_raw_success` - splits.jsonから正常抽出
- [ ] `test_insert_splits_from_raw_data` - Raw dataから挿入成功
- [ ] `test_insert_splits_data_integrity` - データ整合性確認

#### FormEfficiencyInserter (Phase 2)
- [ ] `test_extract_form_efficiency_from_raw_success` - activity_details.jsonから計算
- [ ] `test_insert_form_efficiency_from_raw_data` - Raw dataから挿入成功
- [ ] `test_form_efficiency_calculation_accuracy` - GCT/VO/VR計算精度確認

#### HrEfficiencyInserter (Phase 2)
- [ ] `test_extract_hr_efficiency_from_raw_success` - heart_rate_zones.jsonから計算
- [ ] `test_insert_hr_efficiency_from_raw_data` - Raw dataから挿入成功
- [ ] `test_hr_zone_distribution_accuracy` - Zone分布計算精度確認

#### HeartRateZonesInserter (Phase 2)
- [ ] `test_extract_heart_rate_zones_from_raw_success` - heart_rate_zones.jsonから抽出
- [ ] `test_insert_heart_rate_zones_from_raw_data` - Raw dataから挿入成功

#### Vo2MaxInserter (Phase 2)
- [ ] `test_extract_vo2_max_from_raw_success` - vo2_max.jsonから抽出
- [ ] `test_insert_vo2_max_from_raw_data` - Raw dataから挿入成功

#### LactateThresholdInserter (Phase 2)
- [ ] `test_extract_lactate_threshold_from_raw_success` - lactate_threshold.jsonから抽出
- [ ] `test_insert_lactate_threshold_from_raw_data` - Raw dataから挿入成功

#### PerformanceTrendsInserter (Phase 2)
- [ ] `test_extract_performance_trends_from_raw_success` - 複数Raw dataから計算
- [ ] `test_insert_performance_trends_from_raw_data` - Raw dataから挿入成功
- [ ] `test_performance_trends_calculation_accuracy` - Pace consistency/HR drift計算精度

### Integration Tests

#### GarminIngestWorker (Phase 3)
- [ ] `test_process_activity_without_performance_json` - performance.json生成なしで処理成功
- [ ] `test_process_activity_duckdb_insertion` - DuckDB挿入確認
- [ ] `test_process_activity_end_to_end` - Raw data取得 → DuckDB挿入 完全フロー

#### Regenerate DuckDB Script (Phase 4)
- [ ] `test_regenerate_duckdb_from_raw_data` - Raw dataから再生成成功
- [ ] `test_regenerate_duckdb_without_performance_dir` - performance.jsonなしで動作

### Performance Tests

- [ ] `test_insertion_speed_comparison` - JSONシリアライゼーション排除による速度向上確認
  - **Target:** 10-20% faster insertion
- [ ] `test_storage_reduction` - ストレージ削減確認
  - **Target:** ~50% less disk usage (performance.json削除)
- [ ] `test_duckdb_query_performance` - DuckDBクエリ性能維持確認
  - **Target:** 変更前と同等

### Backward Compatibility Tests

- [ ] `test_raw_data_availability` - Raw dataが存在することを確認
- [ ] `test_no_performance_json_dependency` - performance.json依存がないことを確認
- [ ] `test_mcp_tools_still_work` - MCP Serverツールが動作することを確認

---

## 受け入れ基準

### Functionality
- [ ] 全Inserterがperformance.json依存から脱却
- [ ] Raw dataから直接DuckDB挿入が動作
- [ ] performance.json生成コード完全削除
- [ ] `create_parquet_dataset.py` 削除
- [ ] `test_create_parquet_dataset.py` 削除
- [ ] DuckDBに挿入されるデータが変更前と同一

### Code Quality
- [ ] 全テストがパスする (unit, integration, performance)
- [ ] カバレッジ80%以上維持（既存と同等）
- [ ] Black formatting passes
- [ ] Ruff linting passes
- [ ] Mypy type checking passes

### Performance
- [ ] ストレージ削減: ~50% less disk usage
- [ ] 処理速度: 10-20% faster insertion
- [ ] DuckDBクエリ性能: 変更前と同等

### Documentation
- [ ] CLAUDE.md更新（アーキテクチャ図、Data Processing Pipeline）
- [ ] Directory Structure更新（`data/performance/`削除）
- [ ] 全Inserterの docstrings 更新
- [ ] スクリプトのヘルプメッセージ更新

### Backward Compatibility
- [ ] Raw dataベースのテストが動作
- [ ] MCP Serverツールが動作（DuckDB経由）
- [ ] 既存のanalysisワークフローが動作

---

## リスク管理

### High Priority Risks

1. **データ整合性リスク**
   - **Risk:** Raw dataからの変換ロジックにバグがあり、DuckDBデータが不正確
   - **Mitigation:** Phase 1-2で各Inserterのデータ整合性テスト実施
   - **Fallback:** 変更前後でDuckDBダンプを比較、不一致があれば修正

2. **テストカバレッジ低下**
   - **Risk:** performance.jsonベースのテストを削除し、カバレッジが低下
   - **Mitigation:** Raw dataベースのテストを先に作成してからperformance.json削除
   - **Fallback:** カバレッジが80%未満なら追加テスト作成

3. **Raw dataパース複雑化**
   - **Risk:** performance.jsonの中間抽象化がなくなり、パースロジックが複雑化
   - **Mitigation:** Inserter内で`_extract_*_from_raw()`ヘルパーメソッドにカプセル化
   - **Fallback:** 共通のparserクラスを作成（必要に応じて）

### Medium Priority Risks

4. **既存ワークフロー破壊**
   - **Risk:** performance.jsonに依存する未知のコードが存在
   - **Mitigation:** Phase 3でGrep検索、performance.json参照を全検索
   - **Fallback:** 依存コードを発見したらRaw data読み込みに修正

5. **スクリプト互換性**
   - **Risk:** `regenerate_duckdb.py` がperformance.json前提で動作
   - **Mitigation:** Phase 4で完全にRaw data処理に書き換え
   - **Fallback:** 一時的にperformance.json生成オプションを残す（非推奨）

### Low Priority Risks

6. **ドキュメント更新漏れ**
   - **Risk:** CLAUDE.md以外にperformance.json言及が残る
   - **Mitigation:** Phase 4でGrep検索、"performance.json"を全検索
   - **Fallback:** 発見次第修正

---

## 関連プロジェクト

### 直接関連
- **#23 Granular DuckDB Regeneration** (Active)
  - **関係**: 本プロジェクトの完了後、#23の実装が簡略化される
  - **理由**: performance.json生成がなくなるため、部分再生成がRaw dataベースで統一される

### 間接関連
- **#7 Multi-Agent Analysis (Completed)**
  - **関係**: MCP Serverツールが引き続き動作することを確認
- **#3 Token Optimization (Completed)**
  - **関係**: DuckDBベースのtoken最適化が引き続き有効
- **#12 DuckDB Storage (Completed)**
  - **関係**: 本プロジェクトの基盤（DuckDB導入プロジェクト）

---

## マイルストーン

### Milestone 1: Core Inserters Refactored (Phase 1-2 完了)
- **期限**: Phase 2完了後
- **成果物**:
  - 全8 Insertersが Raw data 直接読み込み
  - 全単体テスト合格
  - データ整合性確認完了

### Milestone 2: Performance JSON Removed (Phase 3 完了)
- **期限**: Phase 3完了後
- **成果物**:
  - `create_parquet_dataset.py` 削除
  - `test_create_parquet_dataset.py` 削除
  - 全統合テスト合格

### Milestone 3: Documentation & Scripts Updated (Phase 4 完了)
- **期限**: Phase 4完了後
- **成果物**:
  - CLAUDE.md更新
  - `regenerate_duckdb.py` 更新
  - 全ドキュメント最新化

---

## 完成基準

### Definition of Done
- [ ] 全フェーズ完了 (Phase 1-4)
- [ ] 全受け入れ基準達成
- [ ] 全テスト合格 (unit, integration, performance)
- [ ] コード品質チェック合格 (Black, Ruff, Mypy)
- [ ] ドキュメント更新 (CLAUDE.md, docstrings, スクリプトヘルプ)
- [ ] performance.json生成コード完全削除
- [ ] data/performance/ディレクトリ削除
- [ ] ストレージ削減確認 (~50%)
- [ ] 処理速度向上確認 (10-20%)
- [ ] Planning document更新（完了ノート）
- [ ] Completion report生成

### Success Metrics
- **Primary Metric:** ストレージ削減 (~50% less disk usage)
- **Secondary Metric:** 処理速度向上 (10-20% faster insertion)
- **Tertiary Metric:** コード簡略化 (2つのデータ形式 → 1つ)

### Post-Launch Activities
- [ ] 既存のperformance.jsonファイルを削除（オプション）
- [ ] data/performance/ディレクトリを削除
- [ ] 関連プロジェクト (#23) にフィードバック
- [ ] GitHub Issue #24 にクローズ報告
