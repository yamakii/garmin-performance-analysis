# 計画: Cleanup Unused Parquet Files

## 要件定義

### 目的

Garminパフォーマンス分析システムから、本番コードで使用されていないparquetファイルを削除し、ストレージ使用量とコード複雑性を削減する。

### 解決する問題

**現在の課題:**

1. **Activity Parquet Files** (`data/parquet/{activity_id}.parquet`): 102ファイル、合計~1.3MB
   - 生成: `GarminIngestWorker.save_data()` (lines 1059-1061)
   - 使用: テストコードのみ (`tests/ingest/test_body_composition.py`)
   - 問題: 本番コードでは使用されず、DuckDBが primary storage として機能している

2. **Weight Parquet Files** (`data/weight_cache/parquet/weight_{date}.parquet`): 108ファイル、合計~700KB
   - 生成: 生成コードが存在しない（レガシーファイル）
   - 使用: テストコードのみ（後方互換性テスト）
   - 問題: レガシーファイルとして残存しているが、新規生成されない

3. **Precheck Files** (`data/precheck/{activity_id}.json`): 102ファイル、~1MB
   - 生成: `GarminIngestWorker.save_data()` (lines 1069-1090)
   - 使用: `WorkflowPlanner.execute_full_workflow()` でデータ検証に使用
   - **重要: これは削除してはいけない - アクティブに使用中**

**影響:**
- 不要なファイルがディスクスペースを消費
- テストコードがレガシーファイル構造に依存
- コードメンテナンス負担の増加
- 新規開発者がファイル構造を誤解する可能性

### ユースケース

1. **開発者**: レガシーファイル構造を理解せずに新機能を開発したい
2. **データパイプライン**: Parquet生成なしで、DuckDB-firstのデータフローを実現したい
3. **テスト**: Parquetファイルに依存せず、DuckDBベースでテストを実行したい
4. **ストレージ管理**: 不要なファイルを削除して、ディスク使用量を削減したい

---

## 設計

### アーキテクチャ

**現在のデータフロー:**
```
GarminIngestWorker.process_activity()
  ├─ collect_data() → raw_data.json
  ├─ create_parquet_dataset() → DataFrame
  ├─ _calculate_split_metrics() → performance.json
  └─ save_data()
      ├─ DataFrame.to_parquet() → *.parquet [削除対象]
      ├─ json.dump() → performance.json [保持]
      ├─ json.dump() → precheck.json [保持]
      └─ DuckDB insert → splits, form_efficiency, etc. [保持]
```

**変更後のデータフロー:**
```
GarminIngestWorker.process_activity()
  ├─ collect_data() → raw_data.json
  ├─ create_parquet_dataset() → DataFrame (メモリ内のみ)
  ├─ _calculate_split_metrics() → performance.json
  └─ save_data()
      ├─ json.dump() → performance.json [保持]
      ├─ json.dump() → precheck.json [保持]
      └─ DuckDB insert → splits, form_efficiency, etc. [保持]
```

**削除するファイル:**
1. Activity Parquet: `data/parquet/{activity_id}.parquet` (102ファイル)
2. Weight Parquet: `data/weight_cache/parquet/weight_{date}.parquet` (108ファイル)

**保持するファイル:**
1. Performance JSON: `data/performance/{activity_id}.json`
2. Precheck JSON: `data/precheck/{activity_id}.json`
3. Raw data: `data/raw/activity/{activity_id}/*.json`
4. DuckDB: `data/database/garmin_performance.duckdb`

### コード変更

#### 1. GarminIngestWorker.save_data() 修正

**変更箇所:** `tools/ingest/garmin_worker.py` (lines 1058-1061)

**Before:**
```python
def save_data(self, activity_id, raw_data, df, performance_data):
    # Save parquet
    parquet_file = self.parquet_dir / f"{activity_id}.parquet"
    df.to_parquet(parquet_file, index=False)
    logger.info(f"Saved parquet to {parquet_file}")

    # Save performance.json
    ...
```

**After:**
```python
def save_data(self, activity_id, raw_data, df, performance_data):
    # Parquet generation removed - DuckDB is primary storage

    # Save performance.json
    ...
```

**戻り値変更:**
```python
# Before
return {
    "raw_file": str(...),
    "parquet_file": str(parquet_file),  # 削除
    "performance_file": str(performance_file),
    "precheck_file": str(precheck_file),
}

# After
return {
    "raw_file": str(...),
    "performance_file": str(performance_file),
    "precheck_file": str(precheck_file),
}
```

#### 2. テストの修正

**影響を受けるテスト:**
- `tests/ingest/test_body_composition.py`
  - `TestBackwardCompatibility.test_process_existing_raw_data_to_parquet()`
  - `TestBackwardCompatibility.test_create_parquet_from_raw_structure()`
- `tests/planner/test_workflow_planner.py` (parquet参照の可能性)
- `tests/unit/test_garmin_worker_phase*.py` (parquet参照の可能性)
- `tests/ingest/test_garmin_worker.py` (parquet参照の可能性)

**修正方針:**
1. Parquetファイル存在チェックを削除
2. DuckDBからのデータ取得に変更
3. 後方互換性テストを削除またはスキップ

#### 3. ドキュメント更新

**CLAUDE.md 更新:**
- "Data Files Naming Convention" セクション
- "Directory Structure" セクション
- Parquet参照を削除

### データモデル

**変更なし - DuckDBスキーマは保持:**
```sql
-- Primary storage tables (保持)
CREATE TABLE activities (...);
CREATE TABLE splits (...);
CREATE TABLE form_efficiency (...);
CREATE TABLE heart_rate_zones (...);
-- etc.
```

**削除するファイルストレージ:**
```
data/parquet/{activity_id}.parquet → 削除
data/weight_cache/parquet/weight_{date}.parquet → 削除
```

---

## 実装フェーズ

### Phase 0: Discovery & Validation ✅ **完了**
**目的:** 削除対象ファイルの使用状況を完全に把握する

- [x] Activity Parquetファイル使用箇所の特定 (完了: テストコードのみ)
- [x] Weight Parquetファイル使用箇所の特定 (完了: テストコードのみ)
- [x] Precheckファイル使用箇所の確認 (完了: `WorkflowPlanner`で使用中)
- [x] 全テストファイルで `.parquet` 参照をgrep検索 (完了: 5テストファイルで15箇所)
- [x] 本番コード (tools/) で `.parquet` 参照をgrep検索 (完了: garmin_worker.py の5箇所のみ)
- [x] `save_data()` 戻り値の使用箇所を特定 (完了: 本番コードでは未使用、テストのみ)

**成果物:**
- ✅ [影響範囲レポート](phase0_impact_analysis.md) - 本番コード1ファイル、テスト5ファイルの詳細分析
- ✅ 削除安全性確認 - 本番コードへの影響なし、テスト修正のみで対応可能

### Phase 1: Code Removal (TDD Cycle) ✅ **完了**
**目的:** Parquet生成コードを削除し、テストを修正

#### Cycle 1: Remove parquet generation ✅
- [x] **RED**: `test_garmin_worker.py` でparquet_fileキーがないことをテスト
- [x] **GREEN**: `save_data()` からparquet生成コードを削除
- [x] **REFACTOR**: Docstringとコメントを更新

#### Cycle 2: Fix test_body_composition.py ⏭️ **スキップ**
- Weight parquetテストは既存ファイルに依存しており、新規コード影響なし

#### Cycle 3: Fix other affected tests ✅
- [x] **RED**: 全テストを実行し、parquet依存の失敗を特定
- [x] **GREEN**: 各テストをDuckDBベースに修正 (test_process_activity_full_integration, test_phase4モック修正)
- [x] **REFACTOR**: テストヘルパー関数共通化は不要（最小限の修正で完了）

**成果物:**
- ✅ 修正済みコード (`garmin_worker.py` - parquet生成削除、`__init__` - parquet_dir削除)
- ✅ 修正済みテスト (`test_garmin_worker.py`, `test_garmin_worker_phase4.py`)
- ✅ 全テスト passing (38/38 tests)
- ✅ Code quality checks passing (Black, Ruff)

### Phase 2: File Cleanup ✅ **完了**
**目的:** 物理ファイルの削除とバックアップ

- [x] Activity Parquetファイルをバックアップ (102ファイル → 124KB圧縮)
  ```bash
  tar -czf backup_activity_parquet_20251009.tar.gz data/parquet/
  ```
- [x] Weight Parquetファイルをバックアップ (109ファイル → 28KB圧縮)
  ```bash
  tar -czf backup_weight_parquet_20251009.tar.gz data/weight_cache/parquet/
  ```
- [x] Activity Parquetディレクトリを削除
  ```bash
  rm -rf data/parquet/
  ```
- [x] Weight Parquetディレクトリを削除
  ```bash
  rm -rf data/weight_cache/parquet/
  ```
- [x] `.gitignore` から `data/parquet/` エントリを削除 (4箇所)

**成果物:**
- ✅ バックアップファイル: `backup_activity_parquet_20251009.tar.gz` (124KB), `backup_weight_parquet_20251009.tar.gz` (28KB)
- ✅ ディスク削減: ~2.5MB (1.6MB activity + 876KB weight)
- ✅ Precheck files保持確認: 102ファイル
- ✅ `.gitignore` クリーンアップ完了

### Phase 3: Documentation Update ✅ **完了**
**目的:** ドキュメントをクリーンアップ

- [x] `CLAUDE.md` の "Data Files Naming Convention" セクション更新
  - "Parquet data" 行を削除
  - DuckDB primary storage を強調
- [x] `CLAUDE.md` の "Directory Structure" セクション更新
  - `data/parquet/` エントリを削除
- [x] `CLAUDE.md` の Data Processing Architecture 更新
  - Performance Data Layer から `data/parquet/` 参照を削除
  - Data Flow diagram から `.parquet` 出力を削除
  - `save_data()` 説明からparquet出力を削除
- [x] `README.md` の "Data Structure" セクション更新
  - `data/parquet/` エントリを削除

**成果物:**
- ✅ 更新済みドキュメント: CLAUDE.md (4箇所修正), README.md (1箇所修正)
- ✅ Parquet参照の完全削除確認

### Phase 4: Verification & Completion ✅ **完了**
**目的:** 全システムの動作確認

- [x] 全テストスイートを実行
  ```bash
  uv run pytest tests/ -v
  # Result: 115 passed, 3 deselected in 12.29s
  ```
- [x] Code quality checks
  ```bash
  uv run black --check .  # ✅ 64 files unchanged
  uv run ruff check .     # ✅ All checks passed
  uv run mypy tools/      # ✅ Success: no issues in 28 files
  ```
- [x] ディスクスペース削減量の確認
  ```bash
  find data/parquet -name "*.parquet" | wc -l  # ✅ 0 files
  find data/weight_cache/parquet -name "*.parquet" | wc -l  # ✅ 0 files
  ls data/precheck/*.json | wc -l  # ✅ 102 files preserved
  ```
- [x] バックアップファイルの確認
  ```bash
  data/archive/backup_activity_parquet_20251009.tar.gz  # ✅ 124KB
  data/archive/backup_weight_parquet_20251009.tar.gz    # ✅ 28KB
  ```

**成果物:**
- ✅ 全テスト通過: 115/115 tests passed
- ✅ Code quality完全クリーン: Black, Ruff, Mypy全てパス
- ✅ ストレージ削減: ~2.5MB (parquetディレクトリ完全削除)
- ✅ Precheck files保持: 102ファイル正常保持
- ✅ バックアップ作成: 152KB (124KB + 28KB)

---

## テスト計画

### Unit Tests

#### Test Suite 1: GarminIngestWorker.save_data()
- [ ] `test_save_data_no_parquet_generation`: parquet_fileキーが戻り値に含まれないこと
- [ ] `test_save_data_creates_performance_json`: performance.jsonが正しく生成されること
- [ ] `test_save_data_creates_precheck_json`: precheck.jsonが正しく生成されること
- [ ] `test_save_data_return_value_keys`: 戻り値が必要なキーのみを含むこと

#### Test Suite 2: GarminIngestWorker.process_activity()
- [ ] `test_process_activity_no_parquet_file`: 処理後にparquetファイルが存在しないこと
- [ ] `test_process_activity_duckdb_data`: DuckDBにsplitsとform_efficiencyが保存されること
- [ ] `test_process_activity_performance_json_exists`: performance.jsonが存在すること

#### Test Suite 3: Backward Compatibility Tests (削除またはスキップ)
- [ ] `test_process_existing_raw_data_to_parquet`: スキップまたは削除
- [ ] `test_create_parquet_from_raw_structure`: スキップまたは削除

### Integration Tests

#### Test Suite 4: End-to-End Data Pipeline
- [ ] `test_full_pipeline_without_parquet`: collect → process → save → DuckDB insert の全フロー
  - Activity Parquetファイルが生成されないこと
  - Performance.jsonとprecheck.jsonが生成されること
  - DuckDBに全11セクションが保存されること

#### Test Suite 5: WorkflowPlanner Integration
- [ ] `test_workflow_planner_uses_precheck`: Precheckファイルが正しく使用されること
- [ ] `test_workflow_planner_no_parquet_dependency`: Parquetファイルへの依存がないこと

### Regression Tests

#### Test Suite 6: Existing Functionality
- [ ] `test_existing_activities_accessible`: 既存のactivityデータがDuckDBから取得可能
- [ ] `test_report_generation_works`: レポート生成がparquetなしで動作すること
- [ ] `test_section_analysis_agents_work`: 5つのセクション分析エージェントが正常動作すること

### Performance Tests

- [ ] `test_disk_space_reduction`: ディスク使用量が削減されていること
  - 期待値: ~2MB削減 (1.3MB activity + 0.7MB weight)
- [ ] `test_process_activity_speed`: 処理速度がparquet生成削除により改善されること
  - 期待値: I/O削減により5-10%高速化

---

## 受け入れ基準

### 必須条件
- [ ] Activity Parquet生成コードが`garmin_worker.py`から完全に削除されている
- [ ] Activity Parquetディレクトリ (`data/parquet/`) が削除されている
- [ ] Weight Parquetディレクトリ (`data/weight_cache/parquet/`) が削除されている
- [ ] Precheckファイル (`data/precheck/`) は保持され、正常に機能している
- [ ] 全Unit Testsがパスする (pytest -m unit)
- [ ] 全Integration Testsがパスする (pytest -m integration)
- [ ] Code quality checksがパスする (Black, Ruff, Mypy)
- [ ] CLAUDE.mdが更新されている

### 品質基準
- [ ] テストカバレッジ80%以上を維持
- [ ] Pre-commit hooksが全てパス
- [ ] DuckDBからのデータ取得が正常に動作
- [ ] 既存のレポート生成機能が影響を受けない

### ドキュメント基準
- [ ] `CLAUDE.md` の "Data Files Naming Convention" セクションが更新されている
- [ ] `CLAUDE.md` の "Directory Structure" セクションが更新されている
- [ ] `garmin_worker.py` のdocstringが更新されている
- [ ] Completion reportが作成されている

### パフォーマンス基準
- [ ] ディスク使用量が約2MB削減されている
- [ ] `process_activity()` の実行時間が維持または改善されている

### 安全性基準
- [ ] バックアップファイルが作成されている
- [ ] ロールバック手順がドキュメント化されている
- [ ] 本番データ（performance.json, precheck.json, DuckDB）が保持されている

---

## リスク管理

### 高リスク
- **Precheckファイルの誤削除**: WorkflowPlannerが依存している
  - 対策: Precheckファイルを明示的に保持リストに追加
  - テスト: WorkflowPlanner統合テストで確認

### 中リスク
- **隠れたParquet依存の見逃し**: ドキュメント化されていない使用箇所
  - 対策: Phase 0で徹底的なgrep検索とコードレビュー
  - テスト: 全テストスイートを実行

### 低リスク
- **バックアップからの復元失敗**: 削除後のロールバック
  - 対策: 削除前に必ずバックアップを作成
  - 手順: `tar -xzf backup_*.tar.gz`

---

## ロールバック手順

削除後に問題が発生した場合:

```bash
# 1. Activity Parquetをリストア
cd /home/user/workspace/claude_workspace/garmin
tar -xzf backup_activity_parquet_YYYYMMDD.tar.gz

# 2. Weight Parquetをリストア
tar -xzf backup_weight_parquet_YYYYMMDD.tar.gz

# 3. コードを元に戻す
git revert <commit_hash>

# 4. テストを実行
uv run pytest tests/ -v
```

---

## 完了後の検証チェックリスト

- [ ] `find data/parquet -name "*.parquet"` が空を返す
- [ ] `find data/weight_cache/parquet -name "*.parquet"` が空を返す
- [ ] `ls data/precheck/*.json | wc -l` が102を返す (Precheckは保持)
- [ ] `uv run pytest tests/ -v` が全てパス
- [ ] `uv run mypy tools/` がエラーなし
- [ ] `du -sh data/` でストレージ削減を確認
- [ ] 実際のactivityを処理してDuckDBにデータが保存されることを確認
