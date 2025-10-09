# 計画: GarminIngestWorker リファクタリング

## 要件定義

### 目的
GarminIngestWorkerの以下の問題を解決し、保守性と信頼性を向上させる：
1. `process_activity_by_date`の実装が`process_activity`と乖離している問題の解決
2. Cache-first approachの優先順位を正しく実装（DuckDB → raw_data → API）
3. 新旧raw_dataフォーマット両方に対応する柔軟なデータ抽出ロジックの実装

### 解決する問題

#### 0. raw_dataディレクトリ構造の改善（新規）
**現状:**
- すべてのAPIレスポンスを1つのJSONファイルに統合: `data/raw/{activity_id}_raw.json`
- API毎の個別キャッシュが不可能
- 一部APIのみ再取得できない

**問題点:**
- 1つのAPIが失敗すると全体が失敗扱いになる
- 特定のAPIレスポンスのみ更新できない（例: weatherデータだけ再取得）
- デバッグ時にどのAPIデータが欠損しているか分かりにくい
- 新フォーマット（2.1MB）のストレージコストが高い

**新構造:**
```
data/raw/activity/{activity_id}/
├── activity_details.json      # get_activity_details() (1.1MB with maxpoly=0)
├── splits.json                # get_activity_splits()
├── weather.json               # get_activity_weather()
├── gear.json                  # get_activity_gear()
├── hr_zones.json              # get_activity_hr_in_timezones()
├── vo2_max.json               # get_max_metrics()
└── lactate_threshold.json     # get_lactate_threshold()
```

**メリット:**
- API毎の個別キャッシュが可能
- 部分的な再取得が可能（例: `weather.json`のみ削除して再実行）
- APIエラーの影響が局所化（1つのAPIが失敗しても他のデータは保存される）
- デバッグが容易（欠損ファイルで即座に判別）
- `weight_cache/raw/`構造と一貫性

#### 1. process_activity_by_dateの実装乖離
**現状:**
- `process_activity_by_date`が独自実装になっており、dateからactivity_idを解決した後、`process_activity`と同じ処理になるべきところが乖離している
- 重複ロジックの保守コストが高い

**問題点:**
- バグ修正が両方に必要になる
- 実装の一貫性が保証されない
- コードの複雑性が増す

#### 2. Cache-first approachの優先順位エラー
**現状の優先順位（間違い）:**
1. raw_data (キャッシュファイル)
2. Garmin API

**正しい優先順位:**
1. DuckDB (最優先、完全なデータが存在)
2. raw_data (キャッシュファイル、APIコール不要)
3. Garmin API (最終手段、レート制限あり)

**各段階でスキップできる処理:**
- **DuckDBから取得できた場合**: activity_id取得、raw_data処理、performance.json登録、体組成登録、すべてスキップ可能
- **raw_dataが存在する場合**: APIコール不要、raw_dataからの加工とDuckDB登録のみ実行
- **APIから取得する場合**: raw_data取得、データ加工、DuckDB登録すべて実行

#### 3. raw_dataフォーマットの変化への非対応
**旧フォーマット (20594901208_raw.json, 31KB, 1,042行):**
```json
{
  "activity": { "summaryDTO": { "trainingEffect": 2.4, ... }, ... },
  "splits": { "lapDTOs": [...] },
  "weather": {...},
  "gear": [...],
  "hr_zones": [...],
  "training_effect": {
    "aerobicTrainingEffect": 2.4,
    "anaerobicTrainingEffect": 0.0,
    ...
  },
  "vo2_max": [],
  "lactate_threshold": {...},
  "weight": {...}
}
```

**新フォーマット (20615445009_raw.json, 2.1MB, 85,217行):**
```json
{
  "activity": {
    "activityDetailMetrics": [1,398個の秒単位メトリクス],  // チャートデータ
    "geoPolylineDTO": { "polyline": [2,771個のGPSポイント] },  // ポリラインデータ
    "metricDescriptors": [26個のメトリクス定義],
    "measurementCount": 26,
    "metricsCount": 1398,
    "totalMetricsCount": 2771
    // summaryDTOが存在しない
  },
  "splits": { "lapDTOs": [...] },
  "weather": {...},
  "gear": [...],
  "hr_zones": [...],
  // training_effectキーが消失（activity内に含まれている可能性）
  "vo2_max": [],
  "lactate_threshold": {...},
  "weight": {...}
}
```

**サイズ急増の原因:**
- **チャートデータ**: `activityDetailMetrics` 1,398秒分 × 26メトリクス = 36,348データポイント（約1.0MB）
- **ポリラインデータ**: `geoPolylineDTO.polyline` 2,771 GPSポイント（約1.0MB）
- **合計**: 2.1MB（旧フォーマットの65倍）

**問題点:**
- `training_effect`キーが新フォーマットに存在しない
- `activity.summaryDTO`が新フォーマットに存在しない
- training_effectデータの抽出ロジックが旧フォーマット専用になっている（`collect_data`の180-193行目）
- 新フォーマットでtraining_effectがどこに格納されているか不明
- チャートデータとポリラインデータが常に含まれストレージコストが高い

**対策:**
- APIパラメータで制御: `get_activity_details(activity_id, maxchart=2000, maxpoly=0)`
  - `maxchart=2000`: チャートデータ保持（グラフ描画・詳細分析用）
  - `maxpoly=0`: ポリラインデータ無効化（GPS軌跡不要）
  - 削減効果: 2.1MB → 1.1MB（約50%削減）

### ユースケース

1. **DuckDBから既存データ取得**
   - ユーザーが既に処理済みのactivity_idを再処理
   - DuckDBにデータが存在する場合、すぐに完了（ファイルI/O・APIコールなし）

2. **raw_dataキャッシュから処理**
   - ユーザーが新しいactivity_idを処理（raw_dataは既に存在）
   - APIコール不要、raw_dataからperformance.json生成とDuckDB登録のみ実行
   - 新旧フォーマット両方に対応

3. **Garmin APIから新規取得**
   - ユーザーが完全に新しいactivity_idを処理（キャッシュなし）
   - API呼び出し、raw_data保存、performance.json生成、DuckDB登録すべて実行

4. **日付ベースのアクティビティ処理**
   - ユーザーが日付を指定してアクティビティを処理
   - activity_id解決後、上記1-3のいずれかのフローを実行

---

## 設計

### アーキテクチャ

#### 1. データソース階層化
```
┌──────────────────────────────────────────────────────────────┐
│ GarminIngestWorker.process_activity(activity_id, date)       │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
         ┌─────────────────────────────────────┐
         │ 1. Try DuckDB (最優先)              │
         │    get_performance_section()         │
         │    → 全セクション取得済み？          │
         └─────────────────────────────────────┘
                           │ No
                           ▼
         ┌─────────────────────────────────────┐
         │ 2. Try raw_data cache               │
         │    activity/{id}/*.json exists?     │
         │    → load_from_cache()              │
         │    → extract_from_raw_data()        │
         └─────────────────────────────────────┘
                           │ No
                           ▼
         ┌─────────────────────────────────────┐
         │ 3. Fetch from Garmin API            │
         │    collect_data() (API毎保存)       │
         │    → extract_from_raw_data()        │
         │    → save_data()                    │
         └─────────────────────────────────────┘
```

#### 2. 新旧フォーマット対応データ抽出
```python
class RawDataExtractor:
    """
    新旧raw_dataフォーマット両方に対応する抽出器
    """

    def extract_training_effect(self, raw_data: dict) -> dict:
        """
        Extract training effect from raw_data (old/new format compatible)

        Priority:
        1. Top-level training_effect key (old format)
        2. activity.summaryDTO (old format)
        3. activity.metricDescriptors (new format) - need investigation
        """
        # Old format (top-level key)
        if "training_effect" in raw_data:
            return raw_data["training_effect"]

        # Old format (summaryDTO)
        summary = raw_data.get("activity", {}).get("summaryDTO", {})
        if summary:
            return {
                "aerobicTrainingEffect": summary.get("trainingEffect"),
                "anaerobicTrainingEffect": summary.get("anaerobicTrainingEffect"),
                "aerobicTrainingEffectMessage": summary.get("aerobicTrainingEffectMessage"),
                "anaerobicTrainingEffectMessage": summary.get("anaerobicTrainingEffectMessage"),
                "trainingEffectLabel": summary.get("trainingEffectLabel"),
            }

        # New format (metricDescriptors) - need investigation
        # TODO: Investigate how to extract from metricDescriptors
        return {}
```

#### 3. process_activity統合設計
```python
def process_activity_by_date(self, date: str) -> dict[str, Any]:
    """
    Process activity by date (delegate to process_activity)

    Steps:
    1. Resolve activity_id from date (Garmin API or DuckDB)
    2. Delegate to process_activity(activity_id, date)
    """
    # Step 1: Try DuckDB for activity_id lookup
    activity_id = self._resolve_activity_id_from_duckdb(date)

    if not activity_id:
        # Step 2: Try Garmin API
        activity_id = self._resolve_activity_id_from_api(date)

    # Step 3: Delegate to unified process_activity
    return self.process_activity(activity_id, date)
```

### データモデル

#### DuckDB Schema (既存)
```sql
-- activities table
CREATE TABLE IF NOT EXISTS activities (
    activity_id INTEGER PRIMARY KEY,
    date DATE NOT NULL,
    activity_name TEXT,
    location_name TEXT,
    weight_kg DOUBLE,
    weight_source TEXT,
    weight_method TEXT,
    distance_km DOUBLE,
    duration_seconds DOUBLE,
    avg_pace_seconds_per_km DOUBLE,
    avg_heart_rate DOUBLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- performance_data table (JSON columns)
CREATE TABLE IF NOT EXISTS performance_data (
    activity_id INTEGER PRIMARY KEY,
    basic_metrics TEXT,  -- JSON
    heart_rate_zones TEXT,  -- JSON
    split_metrics TEXT,  -- JSON
    efficiency_metrics TEXT,  -- JSON
    training_effect TEXT,  -- JSON
    power_to_weight TEXT,  -- JSON
    vo2_max TEXT,  -- JSON
    lactate_threshold TEXT,  -- JSON
    form_efficiency_summary TEXT,  -- JSON
    hr_efficiency_analysis TEXT,  -- JSON
    performance_trends TEXT,  -- JSON (deprecated, use performance_trends table)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### raw_data Format Detection
```python
def detect_format(raw_data: dict) -> str:
    """
    Detect raw_data format (old/new)

    Returns:
        "old" or "new"
    """
    activity = raw_data.get("activity", {})

    # Old format has summaryDTO
    if "summaryDTO" in activity:
        return "old"

    # New format has metricDescriptors
    if "metricDescriptors" in activity:
        return "new"

    return "unknown"
```

### API/インターフェース設計

#### 1. 新しいメソッド
```python
class GarminIngestWorker:
    def _check_duckdb_cache(self, activity_id: int) -> dict[str, Any] | None:
        """
        Check if activity data exists in DuckDB.

        Returns:
            Complete performance data dict if all sections exist, None otherwise
        """
        pass

    def _resolve_activity_id_from_duckdb(self, date: str) -> int | None:
        """
        Resolve activity_id from DuckDB by date.

        Returns:
            activity_id if found, None otherwise
        """
        pass

    def _resolve_activity_id_from_api(self, date: str) -> int:
        """
        Resolve activity_id from Garmin API by date.

        Raises:
            ValueError: If no activity or multiple activities found
        """
        pass

    def extract_from_raw_data(self, raw_data: dict) -> tuple[pd.DataFrame, dict]:
        """
        Extract parquet DataFrame and performance_data from raw_data.

        Handles both old and new format.

        Returns:
            (DataFrame, performance_data dict)
        """
        pass
```

#### 2. 修正されるメソッド
```python
def process_activity(self, activity_id: int, date: str) -> dict[str, Any]:
    """
    Process activity through cache-first pipeline.

    Pipeline:
    1. Check DuckDB cache → return if complete
    2. Check raw_data cache → extract_from_raw_data() + save_data()
    3. Fetch from API → collect_data() + extract_from_raw_data() + save_data()
    4. Calculate 7-day median weight for W/kg
    5. Insert into DuckDB with weight data
    """
    pass

def process_activity_by_date(self, date: str) -> dict[str, Any]:
    """
    Process activity by date (delegate to process_activity).

    Steps:
    1. Resolve activity_id from DuckDB or Garmin API
    2. Delegate to process_activity(activity_id, date)
    """
    pass

def collect_data(self, activity_id: int) -> dict[str, Any]:
    """
    Collect activity data with per-API cache-first strategy.

    **IMPORTANT**: This method ONLY handles raw_data caching, NOT DuckDB caching.
    DuckDB caching is handled in process_activity().

    New structure: data/raw/activity/{activity_id}/{api_name}.json

    Cache priority (per API):
    1. Check data/raw/activity/{activity_id}/{api_name}.json
    2. If missing, fetch from Garmin Connect API and save to individual file

    API files:
    - activity_details.json (maxchart=2000, maxpoly=0)
    - splits.json
    - weather.json
    - gear.json
    - hr_zones.json
    - vo2_max.json
    - lactate_threshold.json
    """
    pass

def load_from_cache(self, activity_id: int) -> dict[str, Any] | None:
    """
    Load cached raw_data from directory structure.

    Returns:
        Complete raw_data dict if all required files exist, None otherwise
    """
    pass
```

---

## テスト計画

### Unit Tests

#### 1. フォーマット検出テスト
- [ ] `test_detect_format_old`: 旧フォーマット検出（summaryDTO存在）
- [ ] `test_detect_format_new`: 新フォーマット検出（metricDescriptors存在）
- [ ] `test_detect_format_unknown`: 不明フォーマット検出

#### 2. training_effect抽出テスト
- [ ] `test_extract_training_effect_old_toplevel`: 旧フォーマット（top-level key）
- [ ] `test_extract_training_effect_old_summary`: 旧フォーマット（summaryDTO）
- [ ] `test_extract_training_effect_new`: 新フォーマット（metricDescriptors調査後）
- [ ] `test_extract_training_effect_missing`: データなし時の挙動

#### 3. DuckDBキャッシュチェックテスト
- [ ] `test_check_duckdb_cache_complete`: 全セクション存在時
- [ ] `test_check_duckdb_cache_partial`: 一部セクションのみ存在時
- [ ] `test_check_duckdb_cache_missing`: データなし時

#### 4. activity_id解決テスト
- [ ] `test_resolve_activity_id_from_duckdb_found`: DuckDBで発見
- [ ] `test_resolve_activity_id_from_duckdb_not_found`: DuckDBで未発見
- [ ] `test_resolve_activity_id_from_api_single`: API単一アクティビティ
- [ ] `test_resolve_activity_id_from_api_multiple`: API複数アクティビティ（エラー）
- [ ] `test_resolve_activity_id_from_api_none`: APIアクティビティなし（エラー）

### Integration Tests

#### 1. パイプライン統合テスト
- [ ] `test_process_activity_duckdb_hit`: DuckDBキャッシュヒット（ファイルI/O・APIコールなし）
- [ ] `test_process_activity_raw_data_hit`: raw_dataキャッシュヒット（APIコールなし）
- [ ] `test_process_activity_api_fetch`: API新規取得（全パイプライン実行）
- [ ] `test_process_activity_by_date_delegation`: process_activity_by_dateがprocess_activityに正しく委譲

#### 2. 新旧フォーマット統合テスト
- [ ] `test_process_activity_old_format`: 旧フォーマット（20594901208_raw.json）でパイプライン実行
- [ ] `test_process_activity_new_format`: 新フォーマット（20615445009_raw.json）でパイプライン実行
- [ ] `test_training_effect_extraction_both_formats`: 両フォーマットでtraining_effect抽出成功

### Performance Tests

- [ ] `test_duckdb_cache_performance`: DuckDBキャッシュヒット時のレスポンス時間 < 100ms
- [ ] `test_raw_data_cache_performance`: raw_dataキャッシュヒット時のレスポンス時間 < 500ms
- [ ] `test_api_fetch_performance`: API新規取得時のレスポンス時間 < 5s（ネットワーク依存）

### Edge Case Tests

- [ ] `test_corrupted_raw_data`: 破損したraw_dataファイル時の挙動
- [ ] `test_missing_training_effect_both_formats`: training_effectが両フォーマットで存在しない場合
- [ ] `test_duckdb_partial_data`: DuckDBに一部データのみ存在する場合の再処理
- [ ] `test_concurrent_access`: 複数プロセスからの同時アクセス時の挙動

---

## 受け入れ基準

- [ ] 全テストがパスする（Unit, Integration, Performance, Edge Case）
- [ ] カバレッジ80%以上
- [ ] Pre-commit hooksがパスする（Black, Ruff, Mypy）
- [ ] 既存の`process_activity`と`process_activity_by_date`の機能が完全に維持される
- [ ] DuckDBキャッシュヒット時のパフォーマンス改善が確認できる（ベンチマーク比較）
- [ ] 新旧フォーマット両方で同じ出力が得られる（training_effect除く）
- [ ] ドキュメントが更新されている（CLAUDE.md, docstring）

---

## 実装フェーズ

### Phase 0: データ構造マイグレーション
**目的:** raw_dataを新ディレクトリ構造に移行し、API毎の個別キャッシュを可能にする

1. **新ディレクトリ構造の設計**
   - `data/raw/activity/{activity_id}/` 構造定義
   - API毎のファイル命名規則定義

2. **マイグレーションスクリプト実装**
   - `tools/migrate_raw_data_structure.py` 作成
   - 既存`{activity_id}_raw.json`を新構造に分割
   - 旧ファイルを`data/archive/raw/`にアーカイブ

3. **GarminIngestWorker.collect_data() リファクタリング**
   - API毎のキャッシュチェック実装
   - 個別ファイル保存ロジック実装
   - APIパラメータ調整: `get_activity_details(id, maxchart=2000, maxpoly=0)`
   - エラーハンドリング（一部APIが失敗しても継続）

4. **GarminIngestWorker.load_from_cache() 新規実装**
   - ディレクトリから全APIファイルをロード
   - 必須ファイルチェック
   - 統合された`raw_data` dictを返却

5. **Unit Tests作成**
   - `test_collect_data_per_api_cache`: API毎キャッシュ動作
   - `test_load_from_cache_complete`: 全ファイル存在時
   - `test_load_from_cache_partial`: 一部ファイル欠損時
   - `test_migrate_raw_data_structure`: マイグレーション動作

### Phase 1: 調査・準備 ✅ 完了
1. ✅ 新フォーマット（20615445009_raw.json）のtraining_effect格納場所調査
   - 結論: 新フォーマットでも `activity.summaryDTO.trainingEffect` は必ず存在
2. ✅ DuckDB reader/writerの既存実装確認
3. ✅ テストデータ準備（旧フォーマット・新フォーマット各1件）

### Phase 2: DuckDBキャッシュ機能実装 ✅ 完了 (Commit: fde7984)
1. ✅ `_check_duckdb_cache()` 実装 (`garmin_worker.py` 142-193行目)
2. ✅ `process_activity()` にDuckDBキャッシュチェック追加 (1331-1414行目)
3. ✅ Unit Tests作成・実行
   - `tests/unit/test_garmin_worker_duckdb_cache.py`: 4テスト
   - `tests/integration/test_garmin_worker_duckdb_integration.py`: 2テスト
   - 全6テストPASSED

### Phase 3: 新旧フォーマット対応 ✅ 完了
**初回実装** (Commit: 390f750)
1. ✅ `RawDataExtractor` クラス実装 (`garmin_worker.py` 58-158行目)
   - `detect_format()`: activity_details.json構造から新旧判定
   - `extract_training_effect()`: 統一的な抽出ロジック
   - `extract_from_raw_data()`: 新旧フォーマット対応抽出インターフェース
2. ✅ `extract_training_effect()` 実装（新旧フォーマット対応）
   - Phase 1調査結果: 新旧両方で `summaryDTO.trainingEffect` 使用可能
3. ✅ `extract_from_raw_data()` 実装
4. ✅ Unit Tests作成・実行
   - `tests/unit/test_raw_data_extractor.py`: 9テスト (フォーマット検出、抽出ロジック)
   - `tests/integration/test_raw_data_extractor_integration.py`: 3テスト (実データ検証)
   - 全12テストPASSED

**簡素化リファクタリング** (Commit: e4b97b2)
- Phase 1調査結果に基づき不要なロジックを削除:
  - ❌ `detect_format()` メソッド削除（新旧判定不要）
  - ❌ トップレベル `training_effect` キー対応削除（レガシー）
  - ✅ `extract_training_effect()` を `summaryDTO` のみに簡素化
  - ✅ `extract_from_raw_data()` を簡素化
- 不要なテスト削除: 12テスト → 7テスト（全てパス）
  - 削除: detect_format 3テスト、top-level key 2テスト
- コード削減: 165行削減
- 結論: 新旧フォーマットで統一的な抽出ロジックを実現

## Phase 4: process_activity_by_date統合 ✅
1. `_resolve_activity_id_from_duckdb()` 実装
2. `_resolve_activity_id_from_api()` 実装
3. `process_activity_by_date()` リファクタリング（委譲実装）
4. Integration Tests作成・実行

### Phase 5: テスト・ドキュメント
1. 全Integration Tests実行
2. Performance Tests実行・ベンチマーク
3. Edge Case Tests実行
4. CLAUDE.md更新（新ディレクトリ構造、APIパラメータ）
5. Docstring更新

---

## リスク・課題

### 高リスク
1. **新フォーマットのtraining_effect抽出方法が不明**
   - 対策: Phase 1で徹底調査、最悪の場合は新フォーマットでtraining_effect=Noneとする

2. **DuckDBの一部データのみ存在する場合の挙動**
   - 対策: 完全性チェック実装、不完全な場合は再処理

3. **既存raw_dataファイルのマイグレーション失敗**
   - 対策: マイグレーション前に全ファイルバックアップ、テスト環境で事前検証

### 中リスク
4. **既存コードの複雑性**
   - 対策: 段階的リファクタリング、既存機能の完全なテストカバレッジ

5. **パフォーマンス劣化の可能性**
   - 対策: Performance Tests必須、ベンチマーク比較

6. **API毎のキャッシュ実装によるコード複雑化**
   - 対策: ヘルパーメソッド分離、明確なエラーハンドリング

### 低リスク
7. **並行アクセス時のDuckDB競合**
   - 対策: read_only接続使用、必要に応じてロック機構追加

8. **APIパラメータ変更によるGarmin側挙動変化**
   - 対策: Phase 0で`maxpoly=0`のテスト、問題あればロールバック可能に

---

## 参考資料

- `tools/ingest/garmin_worker.py`: 現在の実装
- `tools/database/db_reader.py`: DuckDB読み取り実装
- `tools/database/db_writer.py`: DuckDB書き込み実装
- `data/raw/20594901208_raw.json`: 旧フォーマットサンプル（31KB）
- `data/raw/20615445009_raw.json`: 新フォーマットサンプル（2.1MB）
- `CLAUDE.md`: Performance.json Structure (Phase 1, 2 Enhanced)
