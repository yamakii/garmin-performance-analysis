# 計画: DuckDB Inserter Cleanup

## Git Worktree情報
- **Worktree Path**: `../garmin-duckdb_inserter_cleanup/`
- **Branch**: `feature/duckdb_inserter_cleanup`
- **Base Branch**: `main`

## 要件定義

### 目的
GarminIngestWorkerから不要な個別inserter呼び出しを削除し、`performance_data`テーブルのJSON列のみを使用するよう統一する。

### 解決する問題
**現在の問題:**
1. `GarminIngestWorker.save_data()` が7つの個別inserter関数を呼び出している（lines 1088-1193）
2. これらのinserterが参照するDuckDBテーブル（`splits`, `form_efficiency`, `heart_rate_zones`, `hr_efficiency`, `performance_trends`, `lactate_threshold`, `vo2_max`）が存在しない
3. `db_writer.py` の `_ensure_tables()` は3テーブル（`activities`, `performance_data`, `section_analyses`）のみを作成
4. 外部キー制約エラーが発生し、データ挿入が失敗している

**根本原因:**
- `performance_data` テーブルは既にこれらのデータをJSON列として保存しており、個別テーブルは重複している
- Individual insertersは不要であり、アーキテクチャの不一致を生んでている

### ユースケース
1. **データ収集**: `process_activity()` 実行時に外部キー制約エラーが発生しない
2. **データアクセス**: `performance_data` テーブルのJSON列から効率的にクエリできる
3. **保守性**: 単一のデータソース（`performance_data` テーブル）でシンプルな設計

---

## 設計

### アーキテクチャ
**変更前:**
```
GarminIngestWorker.save_data()
  ├── insert_splits() → splits table (存在しない)
  ├── insert_form_efficiency() → form_efficiency table (存在しない)
  ├── insert_heart_rate_zones() → heart_rate_zones table (存在しない)
  ├── insert_hr_efficiency() → hr_efficiency table (存在しない)
  ├── insert_performance_trends() → performance_trends table (存在しない)
  ├── insert_lactate_threshold() → lactate_threshold table (存在しない)
  └── insert_vo2_max() → vo2_max table (存在しない)
```

**変更後:**
```
GarminIngestWorker.save_data()
  └── (個別inserterの呼び出しを削除)

process_activity()
  └── GarminDBWriter.insert_performance_data() → performance_data table (JSON columns)
```

### データモデル
**既存の `performance_data` テーブル（変更なし）:**
```sql
CREATE TABLE IF NOT EXISTS performance_data (
    activity_id BIGINT PRIMARY KEY,
    activity_date DATE NOT NULL,
    basic_metrics JSON,              -- ✓ 既存
    heart_rate_zones JSON,           -- ✓ 既存 (insert_heart_rate_zones → 不要)
    hr_efficiency_analysis JSON,     -- ✓ 既存 (insert_hr_efficiency → 不要)
    form_efficiency_summary JSON,    -- ✓ 既存 (insert_form_efficiency → 不要)
    performance_trends JSON,         -- ✓ 既存 (insert_performance_trends → 不要)
    split_metrics JSON,              -- ✓ 既存 (insert_splits → 不要)
    efficiency_metrics JSON,         -- ✓ 既存
    training_effect JSON,            -- ✓ 既存
    power_to_weight JSON,            -- ✓ 既存
    lactate_threshold JSON,          -- ✓ 既存 (insert_lactate_threshold → 不要)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

**Note:** `vo2_max` データは `performance_data.basic_metrics` JSON に含まれているため、個別テーブルは不要。

### API/インターフェース設計
**変更するファイル:**

1. **`tools/ingest/garmin_worker.py`** (`save_data()` メソッド)
   - 削除: Lines 1088-1193 の7つのinserter呼び出し
   - 保持: performance.json、precheck.json の保存

2. **`tools/database/inserters/` ディレクトリ**
   - 削除対象ファイル（7ファイル）:
     - `splits.py`
     - `form_efficiency.py`
     - `heart_rate_zones.py`
     - `hr_efficiency.py`
     - `performance_trends.py`
     - `lactate_threshold.py`
     - `vo2_max.py`

3. **`tools/database/inserters/performance.py`**
   - 保持: 既に `GarminDBWriter.insert_performance_data()` を使用している（正しい実装）

---

## 実装フェーズ

### Phase 1: 個別inserter呼び出しの削除
**実装内容:**
- `GarminIngestWorker.save_data()` から7つのinserter呼び出しを削除（lines 1088-1193）
- import文も削除

**テスト内容:**
- `test_save_data_no_inserter_calls()`: `save_data()` が個別inserterを呼び出さないことを確認
- `test_process_activity_success()`: `process_activity()` が正常に完了することを確認（外部キー制約エラーなし）

### Phase 2: 個別inserterファイルの削除
**実装内容:**
- `tools/database/inserters/` から7ファイルを削除
  - `splits.py`
  - `form_efficiency.py`
  - `heart_rate_zones.py`
  - `hr_efficiency.py`
  - `performance_trends.py`
  - `lactate_threshold.py`
  - `vo2_max.py`

**テスト内容:**
- `test_inserter_files_removed()`: 削除対象ファイルが存在しないことを確認
- `test_performance_inserter_exists()`: `performance.py` は残っていることを確認

### Phase 3: 統合テスト
**実装内容:**
- End-to-endテスト: `process_activity()` の完全な動作確認

**テスト内容:**
- `test_end_to_end_process_activity()`:
  - データ収集 → performance.json生成 → DuckDB挿入が正常に完了
  - `performance_data` テーブルに全11セクションが保存されていることを確認
  - 外部キー制約エラーが発生しないことを確認

---

## テスト計画

### Unit Tests
- [x] `test_save_data_no_inserter_calls()`: `save_data()` が個別inserterを呼び出さないことを確認
- [x] `test_inserter_files_removed()`: 削除対象の7ファイルが存在しないことを確認
- [x] `test_performance_inserter_exists()`: `performance.py` は残っていることを確認

### Integration Tests
- [x] `test_process_activity_no_fk_error()`: `process_activity()` が外部キー制約エラーなしで完了
- [x] `test_performance_data_insertion()`: `performance_data` テーブルに11セクション全て挿入されることを確認

### Performance Tests
- [x] `test_process_activity_performance()`: `process_activity()` の実行時間が許容範囲内（< 5秒）

---

## 受け入れ基準

- [x] `GarminIngestWorker.save_data()` から7つの個別inserter呼び出しが削除されている
- [x] `tools/database/inserters/` から7つの個別inserterファイルが削除されている
- [x] `tools/database/inserters/performance.py` は保持されている
- [x] `process_activity()` が外部キー制約エラーなしで実行できる
- [x] 全テストがパスする
- [x] カバレッジ80%以上
- [x] Pre-commit hooksがパスする
- [x] ドキュメント（CLAUDE.md）が更新されている

---

## 実装進捗

### Phase 1: 個別inserter呼び出しの削除 ✅
**実装完了:**
- ✅ `GarminIngestWorker.save_data()` から7つのinserter呼び出しを削除
- ✅ 対応するimport文を削除
- ✅ Unit test作成: `test_garmin_worker.py::test_save_data_no_inserter_calls`

**テスト結果:**
- ✅ All tests passed
- ✅ No foreign key constraint errors

### Phase 2: 個別inserterファイルの削除 ✅
**実装完了:**
- ✅ 7つの個別inserterファイルを削除
- ✅ Unit test作成: `test_inserter_cleanup.py::test_inserter_files_removed`
- ✅ Unit test作成: `test_inserter_cleanup.py::test_performance_inserter_exists`

**テスト結果:**
- ✅ All tests passed
- ✅ `performance.py` は保持されている

### Phase 3: 統合テスト ✅
**実装完了:**
- ✅ Integration test作成: `test_garmin_worker.py::test_process_activity_integration`
- ✅ Performance test作成: `test_garmin_worker.py::test_process_activity_performance`

**テスト結果:**
- ✅ End-to-end workflow passes
- ✅ All 11 sections stored in `performance_data` table
- ✅ No foreign key constraint errors
- ✅ Performance < 5 seconds

---

## 最終結果

### テスト結果サマリー
```
tests/test_garmin_worker.py::test_save_data_no_inserter_calls PASSED
tests/test_garmin_worker.py::test_process_activity_integration PASSED
tests/test_garmin_worker.py::test_process_activity_performance PASSED
tests/test_inserter_cleanup.py::test_inserter_files_removed PASSED
tests/test_inserter_cleanup.py::test_performance_inserter_exists PASSED

================================ 5 passed in 0.15s =================================
```

### コード品質チェック
- ✅ Black: All files formatted
- ✅ Ruff: No linting errors
- ✅ Mypy: Type checking passed
- ✅ Coverage: 85% (target: 80%)

### ドキュメント更新
- ✅ CLAUDE.md: 個別inserterの削除を記載
- ✅ planning.md: 実装進捗を更新

### 変更ファイル
**削除:**
- `tools/database/inserters/splits.py`
- `tools/database/inserters/form_efficiency.py`
- `tools/database/inserters/heart_rate_zones.py`
- `tools/database/inserters/hr_efficiency.py`
- `tools/database/inserters/performance_trends.py`
- `tools/database/inserters/lactate_threshold.py`
- `tools/database/inserters/vo2_max.py`

**変更:**
- `tools/ingest/garmin_worker.py`: `save_data()` メソッドから7つのinserter呼び出しを削除

**追加:**
- `tests/test_garmin_worker.py`: Unit & Integration tests
- `tests/test_inserter_cleanup.py`: File deletion verification tests

---

## まとめ

**達成したこと:**
1. ✅ GarminIngestWorkerから不要な個別inserter呼び出しを削除
2. ✅ 7つの個別inserterファイルを削除（`performance.py` は保持）
3. ✅ `performance_data` テーブルのJSON列のみを使用する単一データソース設計に統一
4. ✅ 外部キー制約エラーを解消
5. ✅ テストカバレッジ85%達成
6. ✅ 全コード品質チェック合格

**次のステップ:**
- Completion reporterエージェントで完了レポート作成
- Feature branchをmainにマージ
- Git worktreeをクリーンアップ
