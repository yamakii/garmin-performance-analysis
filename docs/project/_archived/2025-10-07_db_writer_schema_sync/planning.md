# 計画: db_writer Schema Sync

## 要件定義

### 目的
`tools/database/db_writer.py`の`_ensure_tables()`メソッドが作成するテーブルスキーマを、本番DuckDBスキーマと同期させる。

### 問題
現在の`db_writer.py`は古いスキーマ（10カラムのみ）でテーブルを作成しているが、本番DuckDBは36カラムのactivitiesテーブルを持つ。このため、`insert_activity()`メソッドが受け取る`weight_kg`, `weight_source`, `weight_method`パラメータを実際にINSERTできない。

### ユースケース
1. `GarminIngestWorker.process_activity()`が`insert_activity()`を呼び出す
2. `insert_activity()`に`weight_kg`, `weight_source`, `weight_method`が渡される
3. これらのパラメータがDuckDBに正しくINSERTされる
4. レポート生成時に体重情報が正しく取得できる

## 設計

### 現在のdb_writer.pyスキーマ（10カラム）
```sql
CREATE TABLE IF NOT EXISTS activities (
    activity_id BIGINT PRIMARY KEY,
    activity_date DATE,
    activity_name VARCHAR,
    location_name VARCHAR,
    activity_type VARCHAR,
    distance_km DOUBLE,
    duration_seconds INTEGER,
    avg_pace_seconds_per_km DOUBLE,
    avg_heart_rate INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 本番DuckDBスキーマ（36カラム）
```sql
CREATE TABLE IF NOT EXISTS activities (
    activity_id BIGINT PRIMARY KEY,
    date DATE,                                    -- ⚠️ activity_date → date
    activity_name VARCHAR,
    start_time_local TIMESTAMP,
    start_time_gmt TIMESTAMP,
    total_time_seconds INTEGER,                   -- ⚠️ duration_seconds → total_time_seconds
    total_distance_km DOUBLE,                     -- ⚠️ distance_km → total_distance_km
    avg_pace_seconds_per_km DOUBLE,
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    avg_cadence INTEGER,
    avg_power INTEGER,
    normalized_power INTEGER,
    cadence_stability DOUBLE,
    power_efficiency DOUBLE,
    pace_variability DOUBLE,
    aerobic_te DOUBLE,
    anaerobic_te DOUBLE,
    training_effect_source VARCHAR,
    power_to_weight DOUBLE,
    weight_kg DOUBLE,                             -- ⚠️ 新規追加
    weight_source VARCHAR,                        -- ⚠️ 新規追加
    weight_method VARCHAR,                        -- ⚠️ 新規追加
    stability_score DOUBLE,
    external_temp_c DOUBLE,
    external_temp_f DOUBLE,
    humidity INTEGER,
    wind_speed_ms DOUBLE,
    wind_direction_compass VARCHAR,
    gear_name VARCHAR,
    gear_type VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_elevation_gain DOUBLE,
    total_elevation_loss DOUBLE,
    location_name VARCHAR
)
```

### 修正対象

#### 1. `_ensure_tables()`メソッド（行23-84）
- activitiesテーブルのCREATE TABLE文を36カラムスキーマに更新
- カラム名の統一: `activity_date` → `date`, `distance_km` → `total_distance_km`, `duration_seconds` → `total_time_seconds`

#### 2. `insert_activity()`メソッド（行86-146）
- INSERT文に`weight_kg`, `weight_source`, `weight_method`を追加
- カラム名をスキーマに合わせる: `date`, `total_distance_km`, `total_time_seconds`
- VALUES部分に3つの新しいパラメータを追加

#### 3. 正規化テーブルの追加（オプション）
本番DBには以下の正規化テーブルも存在するが、今回は**必須ではない**（既にinsert_splits, insert_form_efficiencyなどの個別メソッドが存在するため）:
- splits
- form_efficiency
- hr_efficiency
- performance_trends
- heart_rate_zones
- vo2_max
- lactate_threshold
- body_composition

## テスト計画

### Unit Tests

#### Test 1: `test_ensure_tables_creates_correct_schema`
- `_ensure_tables()`実行後、activitiesテーブルが36カラムで作成されることを確認
- DuckDBの`DESCRIBE activities`でカラム名とデータ型を検証

#### Test 2: `test_insert_activity_with_weight_parameters`
- `insert_activity()`に`weight_kg`, `weight_source`, `weight_method`を渡す
- INSERT後、SELECTで3つの値が正しく保存されていることを確認

#### Test 3: `test_insert_activity_without_weight_parameters`
- `insert_activity()`に`weight_kg`なしで呼び出す（後方互換性）
- 他のカラムが正常にINSERTされることを確認

#### Test 4: `test_column_name_consistency`
- 本番DBと同じカラム名でINSERT/SELECT可能であることを確認
- `date`, `total_distance_km`, `total_time_seconds`でクエリ実行

### Integration Tests

#### Test 5: `test_garmin_worker_inserts_weight_data`
- `GarminIngestWorker.process_activity()`が体重データを含むactivityをINSERTする
- DuckDBからSELECTして体重データが保存されていることを確認

#### Test 6: `test_backward_compatibility_with_existing_data`
- 既存の10カラムデータが新36カラムスキーマで読み取れることを確認
- 欠損カラムがNULLとして扱われることを確認

### Performance Tests

#### Test 7: `test_insert_performance_with_36_columns`
- 100件のINSERTが1秒以内に完了することを確認
- スキーマ拡大によるパフォーマンス劣化がないことを確認

## 受け入れ基準

✅ `_ensure_tables()`が本番DBと同じ36カラムのactivitiesテーブルを作成する
✅ `insert_activity()`が`weight_kg`, `weight_source`, `weight_method`を正しくINSERTする
✅ カラム名が本番DBと一致する（date, total_distance_km, total_time_seconds）
✅ 既存の10カラムデータとの後方互換性が保たれる
✅ 全Unit Tests、Integration Testsがパスする
✅ Pre-commit hooks（black, ruff, mypy）が全てパスする

## 実装の優先順位

**Phase 1 (必須):**
- [x] `_ensure_tables()`のactivitiesテーブルスキーマ更新（36カラム）
- [x] `insert_activity()`のINSERT文にweight_kg, weight_source, weight_method追加
- [x] カラム名の統一（date, total_distance_km, total_time_seconds）

**Phase 2 (オプション):**
- [ ] 正規化テーブルのCREATE TABLE文追加（splits, form_efficiency等）
- [ ] 既存データのマイグレーションスクリプト作成

## 参考資料

- 本番スキーマ定義: `docs/spec/duckdb_schema_mapping.md`
- 実装ファイル: `tools/database/db_writer.py`
- Serenaメモ: `db_writer_schema_mismatch`
- 関連Issue: Body composition data specification fix (Phase 1完了)
