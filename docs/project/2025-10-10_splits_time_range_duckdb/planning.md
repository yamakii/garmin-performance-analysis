# 計画: DuckDB Splits Table Time Range Enhancement

## Git Worktree情報
- **Worktree Path**: `../garmin-splits_time_range_duckdb/`
- **Branch**: `feature/splits_time_range_duckdb`
- **Base Branch**: `main`

## 要件定義

### 目的
DuckDBのsplitsテーブルに時間範囲情報（`duration_seconds`, `start_time_gmt`）を追加し、TimeSeriesDetailExtractorがDuckDBから効率的に時間範囲を取得できるようにする。

### 解決する問題

**現在の課題:**
1. TimeSeriesDetailExtractorが`performance.json`から`start_time_s`/`end_time_s`を読み込もうとしているが、これらのフィールドが存在しない
2. 時間範囲計算がTimeSeriesDetailExtractor内で行われており、データアクセスパターンが非効率
3. raw data（splits.json）には`duration`と`startTimeGMT`が存在するが、DuckDBに保存されていない

**解決策:**
- raw dataから`duration`（秒）と`startTimeGMT`を抽出してDuckDBに保存
- TimeSeriesDetailExtractorがDuckDBから時間範囲を取得
- 累積時間計算により各splitの`start_time_s`/`end_time_s`を算出

### ユースケース
1. **TimeSeriesDetailExtractor**: split番号から時間範囲（start_time_s, end_time_s）を効率的に取得
2. **IntervalAnalyzer**: ワークアウト/リカバリー区間の時間範囲を正確に特定
3. **FormAnomalyDetector**: 異常検出時の正確なタイムスタンプ情報を提供
4. **Future RAG Queries**: 時間ベースのクエリ（例: "15分～30分の区間を分析"）を可能にする

---

## 設計

### アーキテクチャ

```
GarminIngestWorker
  ↓ collect_data()
raw/activity/{activity_id}/splits.json (lapDTOs)
  ↓ save_data()
SplitsInserter (inserters/splits.py)
  ↓ extract duration & startTimeGMT
DuckDB splits table (duration_seconds, start_time_gmt added)
  ↓ query
TimeSeriesDetailExtractor._get_split_time_range()
  ↓ calculate start_time_s/end_time_s via cumulative sum
time_series_data extraction from activity_details.json
```

### データモデル

**DuckDB Schema (Modified):**
```sql
CREATE TABLE splits (
    activity_id BIGINT,
    split_index INTEGER,
    distance DOUBLE,
    duration_seconds DOUBLE,           -- NEW: from lapDTOs[i].duration
    start_time_gmt VARCHAR,            -- NEW: from lapDTOs[i].startTimeGMT
    role_phase VARCHAR,
    pace_str VARCHAR,
    pace_seconds_per_km DOUBLE,
    heart_rate INTEGER,
    hr_zone VARCHAR,
    cadence DOUBLE,
    cadence_rating VARCHAR,
    power DOUBLE,
    power_efficiency VARCHAR,
    stride_length DOUBLE,
    ground_contact_time DOUBLE,
    vertical_oscillation DOUBLE,
    vertical_ratio DOUBLE,
    elevation_gain DOUBLE,
    elevation_loss DOUBLE,
    terrain_type VARCHAR,
    environmental_conditions VARCHAR,
    wind_impact VARCHAR,
    temp_impact VARCHAR,
    environmental_impact VARCHAR,
    PRIMARY KEY (activity_id, split_index),
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);
```

**Raw Data Structure (splits.json):**
```json
{
  "activityId": 20636804823,
  "lapDTOs": [
    {
      "startTimeGMT": "2025-10-09T12:50:00.0",
      "distance": 1000.0,
      "duration": 387.504,
      "averageHR": 127,
      ...
    }
  ]
}
```

### API/インターフェース設計

**1. SplitsInserter Modification (inserters/splits.py):**
```python
def insert_splits(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
    raw_splits_file: str | None = None,  # NEW: path to raw splits.json
) -> bool:
    """
    Insert split_metrics from performance.json into DuckDB splits table.

    NEW: Extracts duration_seconds and start_time_gmt from raw splits.json

    Args:
        performance_file: Path to performance.json
        activity_id: Activity ID
        db_path: Optional DuckDB path
        raw_splits_file: Path to raw/activity/{activity_id}/splits.json
    """
    # Load performance.json (existing split_metrics)
    # Load raw splits.json (NEW)
    # Match lapDTOs[i] with split_metrics[i] by split_number (1-based)
    # Extract duration and startTimeGMT from lapDTOs
    # INSERT with additional duration_seconds, start_time_gmt fields
```

**2. TimeSeriesDetailExtractor Modification (time_series_detail.py):**
```python
def _get_split_time_range(
    self, split_number: int, activity_id: int
) -> tuple[int, int]:
    """Get time range (start_time_s, end_time_s) for a specific split.

    NEW: Queries DuckDB splits table for duration_seconds,
         calculates cumulative time for start_time_s/end_time_s.

    Args:
        split_number: Split number (1-based index).
        activity_id: Activity ID.

    Returns:
        Tuple of (start_time_s, end_time_s).

    Algorithm:
        1. Query splits table for all splits of activity_id (ordered by split_index)
        2. Calculate cumulative duration: start_time_s[i] = sum(duration_seconds[0:i])
        3. end_time_s[i] = start_time_s[i] + duration_seconds[i]
        4. Return (start_time_s[split_number], end_time_s[split_number])
    """
```

**3. GarminDBReader Enhancement (db_reader.py):**
```python
def get_split_time_ranges(self, activity_id: int) -> list[dict[str, Any]]:
    """Get time ranges for all splits of an activity.

    NEW: Returns list of {split_index, duration_seconds, start_time_s, end_time_s}

    Returns:
        [
            {
                "split_index": 1,
                "duration_seconds": 387.504,
                "start_time_s": 0,
                "end_time_s": 387
            },
            ...
        ]
    """
```

---

## 実装フェーズ

### Phase 1: DuckDB Schema Update & Verification
**目的:** db_writer.pyのスキーマが`duration_seconds`と`start_time_gmt`を含むことを確認

**実装内容:**
- db_writer.py `_ensure_tables()` メソッドでsplitsテーブルスキーマを確認
- 既に`duration_seconds`と`start_time_gmt`が含まれている（✅ 確認済み）

**テスト内容:**
- Unit test: db_writerがsplitsテーブルを正しく作成することを確認

### Phase 2: SplitsInserter Enhancement (TDD)
**目的:** inserters/splits.pyをraw splits.jsonから`duration`と`startTimeGMT`を抽出するように修正

**実装内容:**
1. `insert_splits()`に`raw_splits_file`パラメータを追加
2. raw splits.jsonからlapDTOsを読み込み
3. lapDTOs[i]とsplit_metrics[i]をsplit_numberでマッチング（1-based index）
4. INSERT時に`duration_seconds`と`start_time_gmt`を追加

**テスト内容:**
- Unit test: 正しいraw splits.jsonから`duration`と`startTimeGMT`を抽出
- Unit test: lapDTOs[i]とsplit_metrics[i]が正しくマッチング
- Unit test: DuckDBに`duration_seconds`と`start_time_gmt`が保存される
- Integration test: GarminIngestWorker経由でsplitsテーブルに正しくINSERT

### Phase 3: GarminDBReader Enhancement (TDD)
**目的:** db_reader.pyに`get_split_time_ranges()`メソッドを追加

**実装内容:**
1. `get_split_time_ranges(activity_id)`メソッド実装
2. DuckDBからactivity_idのsplitsを取得（ORDER BY split_index）
3. cumulative sumで各splitのstart_time_s/end_time_sを計算

**テスト内容:**
- Unit test: 正しいactivity_idで全splitsを取得
- Unit test: cumulative時間計算が正確
- Unit test: 返り値の構造が正しい（split_index, duration_seconds, start_time_s, end_time_s）

### Phase 4: TimeSeriesDetailExtractor Refactoring (TDD)
**目的:** _get_split_time_range()をDuckDBベースに書き換え

**実装内容:**
1. `_get_split_time_range(split_number, activity_id)`シグネチャ変更
2. GarminDBReader.get_split_time_ranges()を呼び出し
3. split_numberに対応する(start_time_s, end_time_s)を返す
4. performance_dataパラメータを削除（不要になる）

**テスト内容:**
- Unit test: 正しいsplit_numberで時間範囲を取得
- Unit test: 不正なsplit_number（< 1 or > max_splits）でValueError
- Integration test: get_split_time_series_detail()が正しく動作

### Phase 5: GarminIngestWorker Integration
**目的:** save_data()でraw splits.jsonパスをSplitsInserterに渡す

**実装内容:**
1. `save_data()`メソッド内でraw splits.jsonパスを構築
2. `insert_splits()`呼び出し時に`raw_splits_file`を渡す

**テスト内容:**
- Integration test: 新規activityで全パイプライン（collect_data → save_data → DuckDB INSERT）が動作
- Integration test: TimeSeriesDetailExtractorがDuckDBから正しく時間範囲を取得

### Phase 6: Database Migration
**目的:** 既存のsplitsテーブルデータを再生成

**実装内容:**
1. Migration script作成: `tools/scripts/migrate_splits_time_range.py`
2. 全activityに対してsplitsテーブルを再INSERT（duration_seconds, start_time_gmtを含む）
3. Dry-run mode, verify mode実装

**テスト内容:**
- Integration test: Migration scriptが正しく動作
- Performance test: 100 activities × 10 splitsのmigrationが1分以内に完了

---

## テスト計画

### Unit Tests

**Phase 1: db_writer.py**
- [ ] `_ensure_tables()` がsplitsテーブルを正しく作成する
- [ ] splitsテーブルに`duration_seconds`と`start_time_gmt`カラムが存在する

**Phase 2: inserters/splits.py**
- [ ] `insert_splits()` がraw splits.jsonを読み込める
- [ ] lapDTOs[i]から`duration`と`startTimeGMT`を正しく抽出
- [ ] lapDTOs[i]とsplit_metrics[i]が正しくマッチング（1-based index）
- [ ] DuckDBに`duration_seconds`と`start_time_gmt`が保存される
- [ ] 不正なraw_splits_fileパスでエラーハンドリング

**Phase 3: db_reader.py**
- [ ] `get_split_time_ranges()` が正しいactivity_idで全splitsを取得
- [ ] cumulative時間計算が正確（5 splitsでテスト）
- [ ] 返り値の構造が正しい（split_index, duration_seconds, start_time_s, end_time_s）
- [ ] 存在しないactivity_idで空リストを返す

**Phase 4: time_series_detail.py**
- [ ] `_get_split_time_range()` が正しいsplit_numberで時間範囲を取得
- [ ] split_number < 1 でValueError
- [ ] split_number > max_splits でValueError
- [ ] DuckDBから取得したデータが正しく変換される

### Integration Tests

**Phase 2-5: Full Pipeline**
- [ ] GarminIngestWorker経由でsplitsテーブルに正しくINSERT
- [ ] 新規activity（20636804823）で全パイプライン（collect_data → save_data → DuckDB INSERT）が動作
- [ ] TimeSeriesDetailExtractorがDuckDBから正しく時間範囲を取得
- [ ] get_split_time_series_detail()がactivity_details.jsonから正しくデータ抽出

**Phase 6: Migration**
- [ ] Migration scriptが全activityに対して正しく動作
- [ ] Dry-run modeが変更をコミットしない
- [ ] Verify modeがmigration結果を検証

### Performance Tests

**Phase 6: Migration Performance**
- [ ] 100 activities × 10 splits（1000レコード）のmigrationが1分以内に完了
- [ ] DuckDB query performance: `get_split_time_ranges()` が10ms以内に完了（10 splits）
- [ ] TimeSeriesDetailExtractor performance: split時間範囲取得が5ms以内に完了

---

## 受け入れ基準

- [ ] 全Unit Testsがパスする（Phase 1-4）
- [ ] 全Integration Testsがパスする（Phase 2-6）
- [ ] 全Performance Testsがパスする（Phase 6）
- [ ] カバレッジ85%以上（新規追加コード）
- [ ] Pre-commit hooks（Black, Ruff, Mypy）がパスする
- [ ] Migration scriptが全activityで正常動作する
- [ ] TimeSeriesDetailExtractorがDuckDBから時間範囲を取得できる
- [ ] CLAUDE.mdが更新されている（DuckDB splitsテーブルスキーマ、TimeSeriesDetailExtractorの動作説明）
- [ ] planning.mdに実装進捗が記録されている

---

## 既知の課題と対策

### 課題1: lapDTOsとsplit_metricsのマッチング精度
**詳細:** raw splits.jsonのlapDTOs配列とperformance.jsonのsplit_metrics配列の要素数が異なる場合がある（最終splitが1km未満など）

**対策:**
- lapIndex（1-based）をsplit_numberとマッチング
- 要素数が異なる場合はwarning logを出力
- 最終splitは必ず処理（距離が1km未満でも）

### 課題2: Migration時のデータ整合性
**詳細:** 既存のsplitsテーブルデータを削除して再INSERTする際、外部キー制約（activities.activity_id）が影響する可能性

**対策:**
- Migration scriptでDELETEとINSERTをトランザクション内で実行
- Verify modeで再INSERT後のレコード数を確認
- Dry-run modeで変更内容をプレビュー

### 課題3: start_time_gmtのタイムゾーン処理
**詳細:** `startTimeGMT`は文字列形式（"2025-10-09T12:50:00.0"）でタイムゾーン情報が暗黙的にGMT

**対策:**
- DuckDBにはVARCHAR型で保存（タイムゾーン変換なし）
- 将来的にTIMESTAMP型に変換する場合はISO 8601形式を維持
- ドキュメントにタイムゾーンがGMTであることを明記

---

## 実装進捗

### Phase 1: DuckDB Schema Update & Verification ✅ COMPLETED
- [x] Schema確認: db_writer.pyのsplitsテーブルに5カラム追加（duration_seconds, start_time_gmt, start_time_s, end_time_s, intensity_type）
- [x] inserters/splits.py実装: raw splits.json（lapDTOs）から時間範囲データ抽出
- [x] Unit test作成・実行: test_insert_splits_with_time_range_columns（6テスト全パス）
- [x] Code quality: Black, Ruff, Mypy全パス
- [x] Commit: `8f90db5 feat(db): add time range columns to splits table`

**Phase 1結果:**
- 5つの新カラムをsplitsテーブルに追加（duration_seconds, start_time_gmt, start_time_s, end_time_s, intensity_type）
- round()による四捨五入でstart_time_s/end_time_sを整数値化
- 累積時間計算により各splitの時間範囲を正確に算出
- 全6テストがパス、pre-commit hooksもクリア

### Phase 2: SplitsInserter Enhancement
- [ ] Red: Failing test作成
- [ ] Green: Minimal implementation
- [ ] Refactor: Code quality improvement
- [ ] Unit tests完了

### Phase 3: GarminDBReader Enhancement
- [ ] Red: Failing test作成
- [ ] Green: Minimal implementation
- [ ] Refactor: Code quality improvement
- [ ] Unit tests完了

### Phase 4: TimeSeriesDetailExtractor Refactoring
- [ ] Red: Failing test作成
- [ ] Green: Minimal implementation
- [ ] Refactor: Code quality improvement
- [ ] Unit tests完了

### Phase 5: GarminIngestWorker Integration
- [ ] Integration test作成
- [ ] Implementation
- [ ] Integration tests完了

### Phase 6: Database Migration
- [ ] Migration script作成
- [ ] Dry-run mode実装
- [ ] Verify mode実装
- [ ] Migration実行
- [ ] Performance tests完了

---

## 次のステップ

1. **Planning完了確認**: このplanning.mdの内容を確認し、不足している情報があれば追加
2. **tdd-implementer起動**: Phase 1から順次TDDサイクルで実装
3. **進捗管理**: planning.mdの「実装進捗」セクションを随時更新
4. **completion-reporter起動**: 全Phaseが完了したら完了レポートを作成
