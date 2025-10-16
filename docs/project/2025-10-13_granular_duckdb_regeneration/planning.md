# 計画: Granular DuckDB Regeneration

## プロジェクト情報
- **プロジェクト名**: `granular_duckdb_regeneration`
- **作成日**: `2025-10-13`
- **ステータス**: 計画中
- **GitHub Issue**: https://github.com/yamakii/garmin-performance-analysis/issues/23

## 要件定義

### 目的
現在の `regenerate_duckdb.py` はデータベース全体を一括で再生成することしかできない。この制限により、特定のテーブルのみを更新したい場合でも全テーブルの再生成が必要となり、時間がかかる。本プロジェクトでは、テーブル単位での選択的な再生成機能を追加し、開発効率とデータ管理の柔軟性を向上させる。

### 発見された問題点（2025-10-16更新）

#### 設計上の誤認
1. **FK制約は存在しない**: DuckDBスキーマにFOREIGN KEY制約が定義されていない
   - 当初設計では「FK制約によるCASCADE DELETE」を前提としていたが、実際にはFK制約が存在しない
   - FK制約がないため、テーブル削除順序の制約も不要

2. **`delete_activity_records()`の欠陥**: activitiesテーブルをスキップ（line 308-309）
   ```python
   if table == "activities":
       continue  # activitiesをスキップ
   ```
   - このため、`--tables activities --force`が無意味（activitiesは削除されない）
   - 他のテーブルを削除してもactivitiesが残ると論理的不整合が発生する可能性

3. **INSERT OR REPLACEの誤用**: activitiesテーブルのみ実装済みだが、テーブル全体の再作成には不適切
   - INSERT OR REPLACEは個別レコードのUPSERTには有効だが、テーブル全体の再作成では古いデータが残る
   - 例: activity_id=12345のデータを削除した後、別のアクティビティを再生成しても12345は残り続ける

4. **再生成時間の問題**: 全テーブル再生成に約10分かかる
   - テーブル全体の削除+再挿入の効率化が必要

#### 新しい設計方針
**主ユースケース: テーブル全体の再作成**
```bash
python regenerate_duckdb.py --tables splits
```
**動作:**
1. `DELETE FROM splits;` (全レコード削除)
2. 全activityのsplitsを再挿入
3. 目標時間: 3-5分以内

**副ユースケース: ID単位の再作成（整合性修復用）**
```bash
python regenerate_duckdb.py --tables splits --activity-ids 12345
```
**動作:**
1. `DELETE FROM splits WHERE activity_id = 12345;`
2. activity 12345のsplitsのみ再挿入

**activitiesテーブルの扱い:**
- **他のテーブルと同様に削除対象にする**（FK制約がないため安全）
- activitiesを削除しても論理整合性が崩れる可能性はあるが、基本的には再度挿入するので問題ない
- 整合性が崩れたものの検知は別機能で実装（例: `--validate`オプション）

**INSERT OR REPLACEの扱い:**
- **使用しない** - テーブル全体の再作成には不適切（古いスキーマのデータが残る）
- activitiesも含め、全テーブルを通常のINSERTに戻す
- 重複エラーは事前のDELETEで回避

### 解決する問題

#### 現在の課題

#### UC1: 単一テーブルのスキーマ変更後の再生成
**アクター**: 開発者
**前提条件**: `splits` テーブルのスキーマを変更
**操作**:
```bash
python tools/scripts/regenerate_duckdb.py --tables splits --start-date 2025-01-01 --end-date 2025-01-31
```
**期待結果**: `splits` テーブルのみが指定期間で再生成され、他のテーブルは影響を受けない

#### UC2: 複数テーブルの計算ロジック修正後の再生成
**アクター**: 開発者
**前提条件**: `form_efficiency` と `hr_efficiency` の計算ロジックを修正
**操作**:
```bash
python tools/scripts/regenerate_duckdb.py --tables form_efficiency hr_efficiency --activity-ids 12345 67890
```
**期待結果**: 指定した2つのテーブルのみが指定アクティビティで再生成される

#### UC3: テーブル全体の再作成（スキーマ変更後の完全な再生成）
**アクター**: 開発者
**前提条件**: `splits` テーブルのスキーマを変更し、全データを再挿入する必要がある
**操作**:
```bash
python tools/scripts/regenerate_duckdb.py --tables splits
```
**期待結果**:
- `DELETE FROM splits;` で全レコード削除
- 全アクティビティの `splits` データを再挿入
- 目標時間: 3-5分以内

#### UC3b: ID単位の再作成（整合性修復用）
**アクター**: 開発者
**前提条件**: 特定アクティビティのデータに不整合があり、部分的な再生成が必要
**操作**:
```bash
python tools/scripts/regenerate_duckdb.py --tables splits form_efficiency --activity-ids 12345
```
**期待結果**:
- アクティビティ12345の既存データが `splits` と `form_efficiency` テーブルから削除される（`WHERE activity_id = 12345`）
- 新しいデータが再挿入される

#### UC4: 誤った `--delete-db` 使用の防止
**アクター**: Claude Code（自動化エージェント）
**前提条件**: `splits` テーブルのみを再生成したい
**操作**:
```bash
python tools/scripts/regenerate_duckdb.py --tables splits --delete-db
```
**期待結果**: エラーメッセージが表示され、実行が中止される
```
Error: --delete-db cannot be used with --tables.
Database file deletion is only allowed for full regeneration (all tables).
Use --force to delete existing records for specified activities/date range instead.
```

#### UC5: 全テーブル再生成（既存の動作を維持）
**アクター**: 開発者
**前提条件**: データベース全体の再構築が必要
**操作**:
```bash
python tools/scripts/regenerate_duckdb.py --delete-db
```
**期待結果**: データベースファイルが削除され、全テーブルが再生成される（既存の動作）

---

## 設計

### アーキテクチャ

#### システム構成
```
regenerate_duckdb.py (CLI)
    ↓ parse args, validate
DuckDBRegenerator
    ↓ table-level orchestration
TableRegenerator (NEW)
    ↓ selective deletion/insertion
GarminDBWriter
    ↓ table insertion
DuckDB (garmin_performance.duckdb)
```

#### クラス設計
```
DuckDBRegenerator (EXISTING - Enhanced)
  - regenerate_all()           # Enhanced with table filtering
  - regenerate_single_activity() # Enhanced with table filtering
  + filter_tables()            # NEW: Filter and validate table list
  + delete_activity_records()  # NEW: Delete specific activity records

TableRegenerator (NEW)
  + delete_records(table_name, activity_ids)  # DELETE WHERE activity_id IN (...)
  + regenerate_table(table_name, activity_id, data) # Insert single table
  + get_available_tables()     # Return list of valid table names
  + validate_tables(tables)    # Validate table names
  + get_table_dependencies()   # Return table dependency graph
```

### データモデル

#### DuckDB Tables (11 tables)
```sql
-- Metadata table
CREATE TABLE activities (
    activity_id BIGINT PRIMARY KEY,
    date DATE NOT NULL,
    activity_type VARCHAR,
    -- ... other columns
);

-- Performance data tables (can be regenerated independently)
CREATE TABLE splits (...);
CREATE TABLE form_efficiency (...);
CREATE TABLE hr_efficiency (...);
CREATE TABLE heart_rate_zones (...);
CREATE TABLE performance_trends (...);
CREATE TABLE vo2_max (...);
CREATE TABLE lactate_threshold (...);
CREATE TABLE time_series_metrics (...);

-- Analysis tables (can be regenerated independently)
CREATE TABLE section_analyses (...);

-- Body composition (independent table, no activity_id FK)
CREATE TABLE body_composition (...);
```

#### Table Relationships (No FK Constraints)
```
activities (metadata)
    ├── splits (logical relationship via activity_id)
    ├── form_efficiency (logical relationship via activity_id)
    ├── hr_efficiency (logical relationship via activity_id)
    ├── heart_rate_zones (logical relationship via activity_id)
    ├── performance_trends (logical relationship via activity_id)
    ├── vo2_max (logical relationship via activity_id)
    ├── lactate_threshold (logical relationship via activity_id)
    ├── time_series_metrics (logical relationship via activity_id)
    └── section_analyses (logical relationship via activity_id)

body_composition (independent, no activity_id column)
```

**Important Design Decisions (Updated 2025-10-16):**
1. **No FK constraints exist in DuckDB schema** - テーブル削除順序の制約なし
2. `activities` table can be deleted like any other table (no CASCADE needed)
3. `body_composition` has no activity_id column (skip in DELETE WHERE activity_id = ...)
4. All tables (except body_composition) can be regenerated independently via DELETE + INSERT
5. **INSERT OR REPLACE not used** - テーブル全体の再作成には不適切（古いデータが残る）

### API/インターフェース設計

#### CLI Interface (regenerate_duckdb.py)

```python
# NEW OPTIONS
parser.add_argument(
    "--tables",
    type=str,
    nargs="+",
    choices=[
        "activities",
        "splits",
        "form_efficiency",
        "hr_efficiency",
        "heart_rate_zones",
        "performance_trends",
        "vo2_max",
        "lactate_threshold",
        "time_series_metrics",
        "section_analyses",
        "body_composition",
    ],
    help="List of tables to regenerate (default: all tables)"
)

# --force option REMOVED (2025-10-16)
# DELETE strategy now determined by presence of --activity-ids:
# - No --activity-ids: DELETE entire table (DELETE FROM table;)
# - With --activity-ids: DELETE specific IDs (DELETE FROM table WHERE activity_id IN (...);)

# EXISTING OPTIONS (unchanged)
parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
parser.add_argument("--activity-ids", type=int, nargs="+", help="List of activity IDs")
parser.add_argument("--delete-db", action="store_true", help="Delete database file")
parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
```

#### Validation Rules (Updated 2025-10-16)

```python
def validate_arguments(args):
    """Validate CLI arguments."""

    # Rule 1: --delete-db and --tables are mutually exclusive
    if args.delete_db and args.tables:
        raise ValueError(
            "Error: --delete-db cannot be used with --tables. "
            "Database file deletion is only allowed for full regeneration (all tables). "
            "Use --tables without --delete-db to delete and regenerate specific tables."
        )

    # Rule 2: activity_ids and date range are mutually exclusive
    if args.activity_ids and (args.start_date or args.end_date):
        raise ValueError(
            "Error: Cannot specify both --activity-ids and date range. "
            "Use one or the other."
        )

    # Rule 3 (REMOVED): --force no longer needed
    # DELETE strategy is determined by presence of --activity-ids:
    # - No --activity-ids: DELETE entire table (DELETE FROM table;)
    # - With --activity-ids: DELETE specific IDs (DELETE FROM table WHERE activity_id IN (...);)
```

#### Core Methods

```python
class DuckDBRegenerator:
    def __init__(
        self,
        raw_dir: Path | None = None,
        db_path: Path | None = None,
        delete_old_db: bool = False,
        tables: list[str] | None = None,  # NEW
    ):
        """
        Initialize regenerator.

        Args:
            raw_dir: Raw data directory
            db_path: DuckDB path
            delete_old_db: Delete database file (only if tables is None)
            tables: List of tables to regenerate (None = all tables)
        """
        # Validation
        if delete_old_db and tables:
            raise ValueError("Cannot use delete_old_db with tables")

        self.tables = tables
        # ... existing initialization

    def filter_tables(self, tables: list[str] | None) -> list[str]:
        """
        Filter and validate table list.

        Args:
            tables: List of table names (None = all tables)

        Returns:
            Validated list of table names (always includes 'activities')
        """
        available_tables = [
            "activities",
            "splits",
            "form_efficiency",
            "hr_efficiency",
            "heart_rate_zones",
            "performance_trends",
            "vo2_max",
            "lactate_threshold",
            "time_series_metrics",
            "section_analyses",
            "body_composition",
        ]

        if tables is None:
            return available_tables

        # Validate table names
        invalid_tables = set(tables) - set(available_tables)
        if invalid_tables:
            raise ValueError(f"Invalid table names: {invalid_tables}")

        # Always include activities table (except for body_composition only)
        if tables != ["body_composition"] and "activities" not in tables:
            tables = ["activities"] + tables

        return tables

    def delete_activity_records(
        self,
        activity_ids: list[int],
        tables: list[str]
    ) -> None:
        """
        Delete existing records for specified activity IDs.

        UPDATED (2025-10-16): activities テーブルもスキップしない

        Args:
            activity_ids: List of activity IDs to delete
            tables: List of table names to delete from
        """
        with duckdb.connect(str(self.db_path)) as conn:
            for table in tables:
                if table == "body_composition":
                    # body_composition has no activity_id column, skip
                    continue

                placeholders = ",".join(["?"] * len(activity_ids))
                query = f"DELETE FROM {table} WHERE activity_id IN ({placeholders})"
                conn.execute(query, activity_ids)
                logger.info(
                    f"Deleted {len(activity_ids)} records from {table}"
                )

    def delete_table_all_records(self, tables: list[str]) -> None:
        """
        Delete all records from specified tables.

        NEW (2025-10-16): テーブル全体の削除メソッド

        Args:
            tables: List of table names to delete from
        """
        with duckdb.connect(str(self.db_path)) as conn:
            for table in tables:
                if table == "body_composition":
                    # body_composition has no activity_id, skip (not related to activities)
                    continue

                conn.execute(f"DELETE FROM {table}")
                logger.info(f"Deleted all records from {table}")

    def regenerate_single_activity(
        self,
        activity_id: int,
        activity_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Regenerate DuckDB data for a single activity.

        MODIFIED (2025-10-16): Now respects self.tables, deletes before inserting

        Process:
        1. Check if raw data exists
        2. Delete existing records from specified tables (always)
        3. Use GarminIngestWorker.process_activity() to generate data
        4. Insert only specified tables (via table filtering)

        Args:
            activity_id: Activity ID
            activity_date: Activity date (optional)

        Returns:
            Result dict with status and details
        """
        # ... existing checks ...

        # NEW: Delete existing records (always)
        self.delete_activity_records([activity_id], self.tables)

        # NEW: Use TableRegenerator for selective insertion
        worker = GarminIngestWorker()
        performance_data = worker.process_activity(
            activity_id,
            activity_date or "",
            tables_filter=self.tables  # NEW: Pass table filter
        )

        # ... existing return logic ...
```

#### GarminIngestWorker Enhancement

```python
class GarminIngestWorker:
    def process_activity(
        self,
        activity_id: int,
        date: str,
        force_refetch: dict[str, bool] | None = None,
        tables_filter: list[str] | None = None,  # NEW
    ) -> dict[str, Path]:
        """
        Process activity and save to DuckDB.

        MODIFIED: Now supports table filtering

        Args:
            activity_id: Activity ID
            date: Activity date
            force_refetch: API-specific cache control
            tables_filter: List of tables to insert (None = all tables)

        Returns:
            Dict of saved file paths
        """
        # ... existing logic ...

        # NEW: Pass tables_filter to save_data
        self.save_data(activity_id, date, performance_data, tables_filter)

        return {"performance": performance_file}

    def save_data(
        self,
        activity_id: int,
        date: str,
        performance_data: dict,
        tables_filter: list[str] | None = None,  # NEW
    ) -> None:
        """
        Save performance data to DuckDB.

        MODIFIED: Now supports table filtering

        Args:
            activity_id: Activity ID
            date: Activity date
            performance_data: Performance data dict
            tables_filter: List of tables to insert (None = all tables)
        """
        db_writer = GarminDBWriter(tables_filter=tables_filter)  # NEW

        # Insert activity metadata (always)
        if tables_filter is None or "activities" in tables_filter:
            db_writer.insert_activity(activity_id, date, performance_data)

        # Insert performance data (conditionally)
        if tables_filter is None or any(
            t in tables_filter for t in [
                "splits", "form_efficiency", "hr_efficiency",
                "heart_rate_zones", "performance_trends",
                "vo2_max", "lactate_threshold", "time_series_metrics"
            ]
        ):
            db_writer.insert_performance_data(
                activity_id, performance_data, tables_filter
            )
```

#### GarminDBWriter Enhancement

```python
class GarminDBWriter:
    def __init__(
        self,
        db_path: str | None = None,
        tables_filter: list[str] | None = None,  # NEW
    ):
        """
        Initialize DB writer with optional table filtering.

        Args:
            db_path: DuckDB path
            tables_filter: List of tables to insert (None = all tables)
        """
        self.tables_filter = tables_filter
        # ... existing initialization

    def _should_insert_table(self, table_name: str) -> bool:
        """Check if table should be inserted based on filter."""
        if self.tables_filter is None:
            return True
        return table_name in self.tables_filter

    def insert_performance_data(
        self,
        activity_id: int,
        performance_data: dict,
        tables_filter: list[str] | None = None,  # NEW (can override instance filter)
    ) -> None:
        """
        Insert performance data with table filtering.

        MODIFIED: Now checks table filter before insertion
        """
        filter_to_use = tables_filter or self.tables_filter

        # Splits
        if filter_to_use is None or "splits" in filter_to_use:
            self._insert_splits(activity_id, performance_data)

        # Form efficiency
        if filter_to_use is None or "form_efficiency" in filter_to_use:
            self._insert_form_efficiency(activity_id, performance_data)

        # ... similar for other tables ...
```

---

## 実装フェーズ

### Phase 1: Core Infrastructure (Table Filtering & Validation) - 変更なし
**目的**: テーブルフィルタリングの基盤を構築

**実装内容**:
- `DuckDBRegenerator.__init__()` に `tables` パラメータを追加（`force`削除）
- `filter_tables()` メソッドを実装（バリデーション、`activities`自動追加は**削除**）
- CLI引数パーサーに `--tables` を追加（`--force`削除）
- Validation logic を実装（`--delete-db` + `--tables` の排他制御）

**テスト内容**:
- Unit test: `filter_tables()` の各種パターン（None, 単一テーブル, 複数テーブル, 不正なテーブル名）
- Unit test: Validation logic（`--delete-db` + `--tables` でエラー）
- Integration test: CLI引数パースとバリデーション

**受け入れ基準**:
- [ ] `--tables` オプションが正しくパースされる
- [ ] 不正なテーブル名でエラーが発生する
- [ ] `--delete-db` + `--tables` でエラーメッセージが表示される
- [ ] 全Unit testsが合格する

### Phase 2: Deletion Logic Fix - 重要な変更
**目的**: 既存レコードの削除機能を実装・修正

**実装内容**:
- `delete_activity_records()` メソッドを修正（activitiesスキップを削除）
- **NEW**: `delete_table_all_records()` メソッドを追加（テーブル全体削除）
- `regenerate_single_activity()` / `regenerate_all()` に削除ロジックを統合
  - `--activity-ids` なし → `delete_table_all_records()` 呼び出し
  - `--activity-ids` あり → `delete_activity_records()` 呼び出し
- `body_composition` テーブルの特殊処理（activity_id なし）
- トランザクション管理（DELETE → INSERT が原子的）

**テスト内容**:
- Unit test: `delete_table_all_records()` の動作確認
- Unit test: `delete_activity_records()` が activitiesも削除することを確認
- Unit test: `body_composition` テーブルのスキップ
- Integration test: テーブル全体削除 → 全活動再挿入（`--tables splits`）
- Integration test: ID単位削除 → 再挿入（`--tables splits --activity-ids 12345`）
- Integration test: トランザクション整合性（削除中のエラーハンドリング）

**受け入れ基準**:
- [ ] `delete_table_all_records()` がテーブル全体を削除する
- [ ] `delete_activity_records()` が activitiesテーブルも削除する
- [ ] 指定したテーブルのみから削除される
- [ ] `body_composition` テーブルが正しく処理される
- [ ] エラー発生時にロールバックされる
- [ ] 全Integration testsが合格する

### Phase 3: INSERT OR REPLACE Removal - 新規追加
**目的**: INSERT OR REPLACE を通常の INSERT に変更

**実装内容**:
- `tools/database/inserters/activities.py`: `INSERT OR REPLACE` → `INSERT` に変更
- 重複エラーハンドリングの実装（事前DELETEで回避するため基本的に不要）
- 他のinsertersも確認（INSERT OR REPLACE を使用していないか）

**テスト内容**:
- Unit test: `insert_activity()` が通常のINSERTを使用することを確認
- Unit test: 重複挿入時のエラーハンドリング（事前DELETE済みなので発生しない想定）
- Integration test: テーブル全体削除 → 再挿入で重複エラーが発生しない

**受け入れ基準**:
- [ ] activities inserter が `INSERT OR REPLACE` を使用していない
- [ ] 全inserters が通常の `INSERT` を使用している
- [ ] 重複エラーが発生しない（事前DELETEにより）
- [ ] 全Integration testsが合格する

### Phase 4: GarminIngestWorker Integration - 変更
**目的**: データ生成パイプラインにテーブルフィルタリングを統合

**実装内容**:
- `GarminIngestWorker.process_activity()` に `tables_filter` パラメータを追加
- `save_data()` に `tables_filter` パラメータを追加
- `GarminDBWriter.__init__()` に `tables_filter` パラメータを追加
- `GarminDBWriter.insert_performance_data()` にテーブルフィルタリングロジックを実装

**テスト内容**:
- Unit test: `GarminDBWriter._should_insert_table()` メソッド
- Unit test: `insert_performance_data()` のテーブルフィルタリング
- Integration test: エンドツーエンドの選択的挿入（`--tables splits` で `splits` のみ挿入）
- Integration test: 複数テーブルの選択的挿入（`--tables splits form_efficiency`）

**受け入れ基準**:
- [ ] `tables_filter` パラメータが全メソッドチェーンで正しく伝播する
- [ ] 指定したテーブルのみが挿入される
- [ ] 指定していないテーブルは挿入されない
- [ ] 全Integration testsが合格する

### Phase 5: Performance Optimization - 新規追加
**目的**: テーブル全体再生成のパフォーマンス最適化

**実装内容**:
- バッチ処理の最適化（トランザクション管理の改善）
- 並列処理の検討（複数アクティビティの並行処理）
- INSERT処理の高速化（prepare statement、bulk insert）
- 目標: 全テーブル再生成を10分→3分に短縮

**テスト内容**:
- Performance test: 全テーブル再生成の時間測定（100アクティビティ）
- Performance test: 単一テーブル再生成の時間測定（100アクティビティ）
- Performance test: ID単位再生成の時間測定（10アクティビティ）

**受け入れ基準**:
- [ ] 全テーブル再生成が3-5分以内に完了（100アクティビティ）
- [ ] 単一テーブル再生成が1-2分以内に完了（100アクティビティ）
- [ ] ID単位再生成が1activity当たり2秒以内

### Phase 6: End-to-End Testing & Edge Cases - 変更
**目的**: 全機能の統合テストとエッジケース処理

**実装内容**:
- Dry-run モードのテーブルフィルタリング対応
- エラーハンドリングの強化（部分的な失敗の処理）
- ログ出力の改善（どのテーブルを再生成したか明示）
- Summary レポートの拡張（テーブル別の成功/失敗数）

**テスト内容**:
- Integration test: UC1-UC3b の全ユースケースを実行
- Integration test: 大量アクティビティでのテーブル別再生成（パフォーマンス確認）
- Integration test: エラー発生時の部分的な失敗処理
- Performance test: 全テーブル vs 単一テーブル再生成の速度比較

**受け入れ基準**:
- [ ] UC1-UC3b の全ユースケースが正しく動作する
- [ ] Dry-run モードでテーブルフィルタリング情報が表示される
- [ ] エラー発生時も適切にハンドリングされる
- [ ] Summary レポートにテーブル別の統計が表示される
- [ ] 単一テーブル再生成が全テーブル再生成より高速である

### Phase 7: Documentation & Migration Guide - 変更
**目的**: ドキュメント整備とマイグレーションガイド作成

**実装内容**:
- `regenerate_duckdb.py` の docstring 更新
- `CLAUDE.md` の更新（新しいオプションの説明、`--force`削除）
- Migration guide の作成（既存スクリプトからの移行方法）
- Usage examples の追加（各種ユースケースの実例）

**テスト内容**:
- Manual test: ドキュメントの手順に従って各種操作を実行
- Manual test: Claude Code がドキュメントを理解して正しく使用できるか確認

**受け入れ基準**:
- [ ] `--help` 出力が新しいオプションを含む（`--force`は含まない）
- [ ] `CLAUDE.md` が最新のオプションを反映
- [ ] Migration guide が明確で実行可能
- [ ] Usage examples が各種ユースケースをカバー

---

## テスト計画

### Unit Tests

#### Phase 1: Core Infrastructure
- [ ] `test_filter_tables_none_returns_all`
  - Input: `tables=None`
  - Expected: 全11テーブルのリスト

- [ ] `test_filter_tables_single_table`
  - Input: `tables=["splits"]`
  - Expected: `["splits"]`（activities自動追加は**削除**）

- [ ] `test_filter_tables_multiple_tables`
  - Input: `tables=["splits", "form_efficiency"]`
  - Expected: `["splits", "form_efficiency"]`

- [ ] `test_filter_tables_body_composition_only`
  - Input: `tables=["body_composition"]`
  - Expected: `["body_composition"]`

- [ ] `test_filter_tables_invalid_table_name`
  - Input: `tables=["invalid_table"]`
  - Expected: `ValueError` with "Invalid table names: {'invalid_table'}"

- [ ] `test_validate_arguments_delete_db_with_tables`
  - Input: `delete_db=True, tables=["splits"]`
  - Expected: `ValueError` with "--delete-db cannot be used with --tables"

#### Phase 2: Deletion Logic
- [ ] `test_delete_table_all_records` - **NEW**
  - Input: `tables=["splits"]`
  - Expected: `DELETE FROM splits;` が実行され、全レコード削除

- [ ] `test_delete_activity_records_single_table`
  - Input: `activity_ids=[12345], tables=["splits"]`
  - Expected: `splits` テーブルから1レコード削除

- [ ] `test_delete_activity_records_includes_activities` - **NEW**
  - Input: `activity_ids=[12345], tables=["activities", "splits"]`
  - Expected: `activities` テーブルと `splits` テーブルから1レコードずつ削除（activitiesもスキップしない）

- [ ] `test_delete_activity_records_multiple_tables`
  - Input: `activity_ids=[12345], tables=["splits", "form_efficiency"]`
  - Expected: 両テーブルから1レコードずつ削除

- [ ] `test_delete_activity_records_skip_body_composition`
  - Input: `activity_ids=[12345], tables=["body_composition"]`
  - Expected: 削除処理がスキップされる（activity_id column なし）

- [ ] `test_delete_activity_records_multiple_activities`
  - Input: `activity_ids=[12345, 67890], tables=["splits"]`
  - Expected: `splits` テーブルから2レコード削除

#### Phase 3: INSERT OR REPLACE Removal
- [ ] `test_insert_activity_uses_insert_not_replace` - **NEW**
  - Expected: `activities` inserter が `INSERT` を使用（`INSERT OR REPLACE` なし）

- [ ] `test_no_inserters_use_insert_or_replace` - **NEW**
  - Expected: 全inserters が `INSERT OR REPLACE` を使用していない

- [ ] `test_insert_without_or_replace` - **NEW**
  - Input: 通常のINSERT
  - Expected: 正常に挿入される（事前DELETEにより重複なし）

#### Phase 4: GarminIngestWorker Integration
- [ ] `test_should_insert_table_no_filter`
  - Input: `tables_filter=None, table_name="splits"`
  - Expected: `True`

- [ ] `test_should_insert_table_in_filter`
  - Input: `tables_filter=["splits"], table_name="splits"`
  - Expected: `True`

- [ ] `test_should_insert_table_not_in_filter`
  - Input: `tables_filter=["splits"], table_name="form_efficiency"`
  - Expected: `False`

- [ ] `test_insert_performance_data_with_filter`
  - Input: `tables_filter=["splits"]`
  - Expected: `_insert_splits()` のみ呼ばれ、他のメソッドは呼ばれない

### Integration Tests

#### Phase 1 & 2: CLI and Deletion
- [ ] `test_cli_tables_option_parsing`
  - Command: `--tables splits form_efficiency`
  - Expected: `args.tables == ["splits", "form_efficiency"]`

- [ ] `test_cli_validation_delete_db_with_tables`
  - Command: `--tables splits --delete-db`
  - Expected: エラー終了、エラーメッセージ出力

- [ ] `test_regenerate_table_full` - **NEW**
  - Setup: 既存データがDuckDBに存在
  - Command: `--tables splits`（`--activity-ids` なし）
  - Expected: `DELETE FROM splits;` → 全アクティビティのsplits再挿入

- [ ] `test_regenerate_table_partial` - **NEW**
  - Setup: 既存データがDuckDBに存在
  - Command: `--tables splits --activity-ids 12345`
  - Expected: `DELETE FROM splits WHERE activity_id = 12345;` → activity 12345のsplitsのみ再挿入

#### Phase 3 & 4: Table Filtering
- [ ] `test_regenerate_single_table_only_inserts_specified`
  - Command: `--tables splits --activity-ids 12345`
  - Expected: `splits` テーブルのみに新データ、他は変更なし

- [ ] `test_regenerate_multiple_tables_only_inserts_specified`
  - Command: `--tables splits form_efficiency --activity-ids 12345`
  - Expected: `splits`, `form_efficiency` のみ更新

- [ ] `test_regenerate_with_date_range_and_tables`
  - Command: `--tables splits --start-date 2025-01-01 --end-date 2025-01-31`
  - Expected: 期間内の全アクティビティの `splits` テーブルが更新

#### Phase 5 & 6: End-to-End
- [ ] `test_uc1_single_table_schema_change`
  - Scenario: UC1 の完全なフロー
  - Expected: `splits` テーブルのみ再生成、他は影響なし

- [ ] `test_uc2_multiple_tables_logic_fix`
  - Scenario: UC2 の完全なフロー
  - Expected: 2テーブルのみ再生成

- [ ] `test_uc3_table_full_regeneration` - **NEW**
  - Scenario: UC3 の完全なフロー（テーブル全体再作成）
  - Expected: `DELETE FROM splits;` → 全アクティビティのsplits再挿入

- [ ] `test_uc3b_id_unit_regeneration` - **NEW**
  - Scenario: UC3b の完全なフロー（ID単位再作成）
  - Expected: `DELETE FROM splits WHERE activity_id = 12345;` → activity 12345のみ再挿入

- [ ] `test_uc4_error_on_delete_db_with_tables`
  - Scenario: UC4 の完全なフロー
  - Expected: エラーメッセージ、実行中止

- [ ] `test_uc5_full_regeneration_with_delete_db`
  - Scenario: UC5 の完全なフロー
  - Expected: データベースファイル削除 → 全テーブル再生成

### Performance Tests

- [ ] `test_single_table_regeneration_faster_than_full`
  - Setup: 100アクティビティのテストデータ
  - Test: 全テーブル再生成 vs `splits` のみ再生成
  - Expected: 単一テーブル再生成が少なくとも50%高速

- [ ] `test_table_full_regeneration_performance` - **NEW**
  - Setup: 100アクティビティのテストデータ
  - Test: `--tables splits`（全アクティビティ再挿入）
  - Expected: 3-5分以内に完了

- [ ] `test_id_unit_regeneration_performance` - **NEW**
  - Setup: 100アクティビティのテストデータ
  - Test: `--tables splits --activity-ids [10 IDs]`
  - Expected: 1activity当たり2秒以内（合計20秒以内）

- [ ] `test_large_activity_list_performance`
  - Setup: 1000アクティビティ
  - Test: `--tables splits --activity-ids [1000 IDs]`
  - Expected: 30分以内に完了（1アクティビティ平均1.8秒）

---

## 受け入れ基準

### 機能要件（2025-10-16 更新）
- [ ] `--tables` オプションが実装され、指定したテーブルのみが再生成される
- [ ] `--activity-ids` なしで`--tables`を使用すると、テーブル全体が削除→再挿入される
- [ ] `--activity-ids` ありで`--tables`を使用すると、指定IDのみ削除→再挿入される
- [ ] `--delete-db` と `--tables` の同時使用が禁止され、明確なエラーメッセージが表示される
- [ ] `activities` テーブルも他のテーブルと同様に削除対象になる
- [ ] INSERT OR REPLACEが使用されていない（全テーブル）
- [ ] UC1-UC3b, UC4-UC5 の全ユースケースが正しく動作する

### 品質要件
- [ ] 全Unit testsが合格する（最低25個のテストケース）
- [ ] 全Integration testsが合格する（最低12個のテストケース）
- [ ] 全Performance testsが合格する（4個のテストケース）
- [ ] コードカバレッジ80%以上（新規コードに対して）
- [ ] Pre-commit hooks が合格する（Black, Ruff, Mypy）

### パフォーマンス要件（2025-10-16 更新）
- [ ] テーブル全体再生成が3-5分以内に完了（100アクティビティ）
- [ ] 単一テーブル再生成が全テーブル再生成より50%以上高速
- [ ] ID単位再生成が1activity当たり2秒以内
- [ ] 1000アクティビティの処理が30分以内に完了

### ドキュメント要件（2025-10-16 更新）
- [ ] `--help` 出力が新しいオプションを含む（`--force`は含まない）
- [ ] `CLAUDE.md` が更新されている（新しい設計方針を反映）
- [ ] Migration guide が作成されている
- [ ] Usage examples が各種ユースケースをカバーしている

### Claude Code Integration
- [ ] Claude Codeが `--delete-db` と `--tables` を誤って同時使用しない
- [ ] エラーメッセージが Claude Code に理解可能な形式
- [ ] Dry-run 出力が Claude Code のデバッグに有用

---

## リスク管理

### 技術的リスク（2025-10-16 更新）

#### Risk 1: Foreign Key Constraint Violations - **削除**
**理由**: FK制約が存在しないため、このリスクは存在しない

#### Risk 2: Partial Failure Handling
**リスク**: 複数テーブル再生成中に一部が失敗した場合のデータ不整合
**影響度**: 中
**対策**:
- アクティビティ単位でトランザクション管理
- 失敗したアクティビティをログに記録
- リトライメカニズムの実装

#### Risk 3: Performance Degradation
**リスク**: テーブル全体削除時のパフォーマンス低下
**影響度**: 高
**対策**:
- DELETE 操作の最適化（`DELETE FROM table;` は高速）
- バッチ削除の実装（大量アクティビティの場合）
- Performance test で基準値を設定（目標: 3-5分/100アクティビティ）

#### Risk 4: Data Consistency Issues - **NEW**
**リスク**: activitiesテーブル削除により論理的不整合が発生する可能性
**影響度**: 中
**対策**:
- 基本的にはテーブル全体を再生成するため問題ない
- 整合性チェック機能を別途実装（例: `--validate`オプション）
- ドキュメントで注意事項を明記

### 運用リスク

#### Risk 5: Accidental Data Loss
**リスク**: ユーザーが誤ってテーブル全体を削除（`--tables`のみで`--activity-ids`なし）
**影響度**: 高
**対策**:
- テーブル全体削除時に警告メッセージを表示（将来の改善）
- Dry-run モードで削除対象を事前確認可能
- バックアップ推奨のドキュメント化

#### Risk 6: Documentation Misunderstanding
**リスク**: ドキュメント不足で誤った使用法が広まる
**影響度**: 中
**対策**:
- 各種ユースケースの具体例を提供
- エラーメッセージに解決策を含める
- Migration guide で既存スクリプトからの移行方法を明示
- 新しい設計方針（テーブル全体削除 vs ID単位削除）を明確に説明

---

## 実装ガイドライン

### コーディング規約
- Type hints を全メソッドに付与
- Docstring は Google スタイル
- エラーメッセージは具体的で実行可能な解決策を含む
- ログレベルを適切に使い分け（DEBUG/INFO/WARNING/ERROR）

### テスト戦略
- Unit test: 各メソッドの単体動作を検証
- Integration test: 複数コンポーネントの連携を検証
- Performance test: 速度要件を検証
- Manual test: CLI UX を検証

### Git Workflow
1. Planning: Main branch で `planning.md` 作成・コミット
2. Implementation: `git worktree` で feature branch 作成
3. TDD: Red → Green → Refactor サイクル
4. Completion: Main にマージ、`completion_report.md` 作成

---

## 成功指標（2025-10-16 更新）

### 開発効率の向上
- **指標**: スキーマ変更後のテストサイクル時間
- **目標**: 全テーブル再生成（10分）→ 単一テーブル再生成（3-5分）に短縮

### パフォーマンス改善
- **指標**: テーブル全体再生成の時間（100アクティビティ）
- **目標**: 3-5分以内に完了

### データ保護の強化
- **指標**: 誤ったデータベースファイル削除の発生件数
- **目標**: ゼロ（`--delete-db` + `--tables` の排他制御により）

### 柔軟性の向上
- **指標**: テーブル単位での再生成要求への対応率
- **目標**: 100%（全11テーブルが個別に再生成可能）

### コード品質
- **指標**: テストカバレッジ
- **目標**: 新規コードに対して80%以上

---

## 参考資料

### 関連ファイル
- `tools/scripts/regenerate_duckdb.py` (EXISTING)
- `tools/ingest/garmin_worker.py` (EXISTING)
- `tools/database/db_writer.py` (EXISTING)
- `tools/database/db_reader.py` (EXISTING)

### 関連プロジェクト
- `docs/project/2025-10-09_duckdb_section_analysis/` - Section analysis storage
- `docs/project/2024-12-30_time_series_optimization/` - Time series table design

### DuckDB Documentation
- DuckDB DELETE syntax: https://duckdb.org/docs/sql/statements/delete.html
- DuckDB Transaction management: https://duckdb.org/docs/sql/statements/transactions.html
- DuckDB Foreign Keys: https://duckdb.org/docs/sql/constraints.html

---

## Next Steps

### Immediate Actions (Phase 0)
1. ✅ Create project directory: `docs/project/2025-10-13_granular_duckdb_regeneration/`
2. ✅ Create `planning.md` (this document)
3. ⏳ Commit `planning.md` to main branch
4. ⏳ Create GitHub Issue for this project
5. ⏳ Update `planning.md` with GitHub Issue link

### Handoff to Implementation
- **Agent**: `tdd-implementer`
- **Worktree**: Create from main branch
- **Start with**: Phase 1 (Core Infrastructure)
- **Reference**: This planning document for requirements and test cases
