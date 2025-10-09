# 計画: DuckDB Schema Fix - Add Missing Normalized Tables

## Git Worktree情報
- **Worktree Path**: `../garmin-duckdb_inserter_cleanup/`
- **Branch**: `feature/duckdb_inserter_cleanup`
- **Base Branch**: `main`

## 要件定義

### 目的
`db_writer.py`の`_ensure_tables()`に不足している正規化テーブル（splits, form_efficiency等）のスキーマ定義を追加し、`GarminIngestWorker`からの個別inserterが正常に動作するようにする。

### 解決する問題
**現在の問題:**
1. `GarminIngestWorker.save_data()` が7つの個別inserter関数を呼び出している（lines 1088-1193）
2. これらのinserterが参照するDuckDBテーブル（`splits`, `form_efficiency`, `heart_rate_zones`, `hr_efficiency`, `performance_trends`, `lactate_threshold`, `vo2_max`）が**存在しない**
3. `db_writer.py` の `_ensure_tables()` は3テーブル（`activities`, `performance_data`, `section_analyses`）のみを作成
4. 外部キー制約エラーが発生し、データ挿入が失敗している

**根本原因:**
- `duckdb_schema_mapping.md`によれば、performance.jsonのデータは**正規化テーブル**に格納される設計
- `performance_data`テーブル（JSON格納）は**2025-10-07に削除済み**（古い設計）
- しかし、`db_writer._ensure_tables()`には正規化テーブルのスキーマ定義が**未実装**
- 個別inserter関数は存在するが、対応するテーブルが作成されないため、外部キー制約エラーが発生

### ユースケース
1. **データ収集**: `process_activity()` 実行時に外部キー制約エラーが発生しない
2. **データアクセス**: 正規化テーブルから効率的にクエリできる（集計、トレンド分析）
3. **保守性**: duckdb_schema_mapping.mdに記載された設計通りの実装

---

## 設計

### アーキテクチャ
**現在の状態（不完全）:**
```
GarminIngestWorker.save_data()
  ├── insert_splits() → splits table ❌ テーブルが存在しない
  ├── insert_form_efficiency() → form_efficiency table ❌ テーブルが存在しない
  ├── insert_heart_rate_zones() → heart_rate_zones table ❌ テーブルが存在しない
  ├── insert_hr_efficiency() → hr_efficiency table ❌ テーブルが存在しない
  ├── insert_performance_trends() → performance_trends table ❌ テーブルが存在しない
  ├── insert_lactate_threshold() → lactate_threshold table ❌ テーブルが存在しない
  └── insert_vo2_max() → vo2_max table ❌ テーブルが存在しない

db_writer._ensure_tables()
  ├── activities ✅
  ├── performance_data ✅ （削除済み設計だが残存）
  └── section_analyses ✅
```

**修正後（完全）:**
```
GarminIngestWorker.save_data()
  ├── insert_splits() → splits table ✅
  ├── insert_form_efficiency() → form_efficiency table ✅
  ├── insert_heart_rate_zones() → heart_rate_zones table ✅
  ├── insert_hr_efficiency() → hr_efficiency table ✅
  ├── insert_performance_trends() → performance_trends table ✅
  ├── insert_lactate_threshold() → lactate_threshold table ✅
  └── insert_vo2_max() → vo2_max table ✅

db_writer._ensure_tables()
  ├── activities ✅
  ├── splits ✅ NEW
  ├── form_efficiency ✅ NEW
  ├── heart_rate_zones ✅ NEW
  ├── hr_efficiency ✅ NEW
  ├── performance_trends ✅ NEW
  ├── vo2_max ✅ NEW
  ├── lactate_threshold ✅ NEW
  └── section_analyses ✅
```

### データモデル
**追加する正規化テーブル（duckdb_schema_mapping.md準拠）:**

#### 1. splits テーブル
```sql
CREATE TABLE IF NOT EXISTS splits (
    activity_id BIGINT NOT NULL,
    split_index INTEGER NOT NULL,
    distance DOUBLE,
    pace_seconds_per_km DOUBLE,
    heart_rate INTEGER,
    cadence DOUBLE,
    power DOUBLE,
    ground_contact_time DOUBLE,
    vertical_oscillation DOUBLE,
    vertical_ratio DOUBLE,
    elevation_gain DOUBLE,
    elevation_loss DOUBLE,
    terrain_type VARCHAR,
    PRIMARY KEY (activity_id, split_index),
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

#### 2. form_efficiency テーブル
```sql
CREATE TABLE IF NOT EXISTS form_efficiency (
    activity_id BIGINT PRIMARY KEY,
    gct_average DOUBLE,
    gct_min DOUBLE,
    gct_max DOUBLE,
    gct_std DOUBLE,
    gct_rating VARCHAR,
    vo_average DOUBLE,
    vo_min DOUBLE,
    vo_max DOUBLE,
    vo_std DOUBLE,
    vo_rating VARCHAR,
    vr_average DOUBLE,
    vr_min DOUBLE,
    vr_max DOUBLE,
    vr_std DOUBLE,
    vr_rating VARCHAR,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

#### 3. heart_rate_zones テーブル
```sql
CREATE TABLE IF NOT EXISTS heart_rate_zones (
    activity_id BIGINT NOT NULL,
    zone_number INTEGER NOT NULL,
    zone_low_boundary INTEGER,
    time_in_zone_seconds DOUBLE,
    zone_percentage DOUBLE,
    PRIMARY KEY (activity_id, zone_number),
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

#### 4. hr_efficiency テーブル
```sql
CREATE TABLE IF NOT EXISTS hr_efficiency (
    activity_id BIGINT PRIMARY KEY,
    training_type VARCHAR,
    hr_stability VARCHAR,
    zone1_percentage DOUBLE,
    zone2_percentage DOUBLE,
    zone3_percentage DOUBLE,
    zone4_percentage DOUBLE,
    zone5_percentage DOUBLE,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

#### 5. performance_trends テーブル
```sql
CREATE TABLE IF NOT EXISTS performance_trends (
    activity_id BIGINT PRIMARY KEY,
    pace_consistency DOUBLE,
    hr_drift_percentage DOUBLE,
    cadence_consistency VARCHAR,
    fatigue_pattern VARCHAR,
    warmup_avg_pace_seconds_per_km DOUBLE,
    warmup_avg_hr DOUBLE,
    main_avg_pace_seconds_per_km DOUBLE,
    main_avg_hr DOUBLE,
    finish_avg_pace_seconds_per_km DOUBLE,
    finish_avg_hr DOUBLE,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

#### 6. vo2_max テーブル
```sql
CREATE TABLE IF NOT EXISTS vo2_max (
    activity_id BIGINT PRIMARY KEY,
    precise_value DOUBLE,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

#### 7. lactate_threshold テーブル
```sql
CREATE TABLE IF NOT EXISTS lactate_threshold (
    activity_id BIGINT PRIMARY KEY,
    heart_rate INTEGER,
    speed_mps DOUBLE,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

### API/インターフェース設計
**変更するファイル:**

1. **`tools/database/db_writer.py`** (`_ensure_tables()` メソッド)
   - 追加: 上記7テーブルのCREATE TABLE文

2. **`tools/database/inserters/` ディレクトリ**
   - **保持**: 7つの個別inserterファイルはすべて必要
     - `splits.py`
     - `form_efficiency.py`
     - `heart_rate_zones.py`
     - `hr_efficiency.py`
     - `performance_trends.py`
     - `lactate_threshold.py`
     - `vo2_max.py`

3. **`tools/ingest/garmin_worker.py`**
   - **変更なし**: 個別inserter呼び出しは正しい実装

4. **削除対象:**
   - `performance_data`テーブル（JSON格納）の定義を`_ensure_tables()`から削除

---

## 実装フェーズ

### Phase 1: performance_dataテーブルの削除
**実装内容:**
- `db_writer._ensure_tables()` から`performance_data`テーブルの定義を削除
- 古い設計の残骸をクリーンアップ

**テスト内容:**
- `test_performance_data_table_removed()`: `performance_data`テーブルが作成されないことを確認

### Phase 2: 正規化テーブルの追加
**実装内容:**
- `db_writer._ensure_tables()` に7つの正規化テーブルのスキーマを追加
  - `splits`
  - `form_efficiency`
  - `heart_rate_zones`
  - `hr_efficiency`
  - `performance_trends`
  - `vo2_max`
  - `lactate_threshold`

**テスト内容:**
- `test_normalized_tables_created()`: 7つのテーブルが正しく作成されることを確認
- `test_foreign_key_constraints()`: 外部キー制約が正しく設定されていることを確認

### Phase 3: 統合テスト
**実装内容:**
- End-to-endテスト: `process_activity()` の完全な動作確認

**テスト内容:**
- `test_end_to_end_process_activity()`:
  - データ収集 → performance.json生成 → DuckDB挿入が正常に完了
  - 7つの正規化テーブルにデータが正しく挿入されることを確認
  - 外部キー制約エラーが発生しないことを確認

---

## テスト計画

### Unit Tests
- [ ] `test_performance_data_table_removed()`: `performance_data`テーブルが作成されない
- [ ] `test_normalized_tables_created()`: 7つの正規化テーブルが作成される
- [ ] `test_foreign_key_constraints()`: 外部キー制約が正しい

### Integration Tests
- [ ] `test_process_activity_no_fk_error()`: `process_activity()` が外部キー制約エラーなしで完了
- [ ] `test_normalized_tables_insertion()`: 7つのテーブルにデータが正しく挿入される

### Performance Tests
- [ ] `test_process_activity_performance()`: `process_activity()` の実行時間が許容範囲内（< 5秒）

---

## 受け入れ基準

- [ ] `db_writer._ensure_tables()` に7つの正規化テーブルのスキーマが追加されている
- [ ] `performance_data`テーブル（JSON格納）が削除されている
- [ ] 個別inserterファイル（7ファイル）はすべて保持されている
- [ ] `process_activity()` が外部キー制約エラーなしで実行できる
- [ ] 7つの正規化テーブルにデータが正しく挿入される
- [ ] 全テストがパスする
- [ ] カバレッジ80%以上
- [ ] Pre-commit hooksがパスする
- [ ] ドキュメント（CLAUDE.md）が更新されている

---

## 実装進捗

### Phase 1: performance_dataテーブルの削除
**ステータス**: 未着手

### Phase 2: 正規化テーブルの追加
**ステータス**: 未着手

### Phase 3: 統合テスト
**ステータス**: 未着手

---

## 次のステップ

1. **tdd-implementer agent呼び出し**:
   ```bash
   Task: tdd-implementer
   prompt: "docs/project/2025-10-10_duckdb_inserter_cleanup/planning.md に基づいて、TDDサイクルで実装してください。"
   ```

2. **実装完了後**: completion-reporter agentで完了レポート作成
3. **マージ**: Feature branchをmainにマージ
4. **クリーンアップ**: Git worktreeを削除
