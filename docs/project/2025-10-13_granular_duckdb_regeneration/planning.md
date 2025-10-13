# 計画: Granular DuckDB Regeneration

## プロジェクト情報
- **プロジェクト名**: `granular_duckdb_regeneration`
- **作成日**: `2025-10-13`
- **ステータス**: 計画中
- **GitHub Issue**: https://github.com/yamakii/garmin-performance-analysis/issues/23

## 要件定義

### 目的
現在の `regenerate_duckdb.py` はデータベース全体を一括で再生成することしかできない。この制限により、特定のテーブルのみを更新したい場合でも全テーブルの再生成が必要となり、時間がかかる。本プロジェクトでは、テーブル単位での選択的な再生成機能を追加し、開発効率とデータ管理の柔軟性を向上させる。

### 解決する問題

#### 現在の課題
1. **全テーブル再生成の非効率性**: スキーマ変更が1テーブルのみの場合も全テーブル再生成が必要
2. **データベースファイル削除のリスク**: `--delete-db` オプションが常に使用可能で、部分的な再生成時に誤って全データを削除する可能性
3. **柔軟性の欠如**: 特定のテーブルのみを更新したいユースケースに対応できない
4. **開発効率の低下**: スキーマ変更後のテストサイクルが長い（全テーブル再生成待ち）

#### 具体的なユースケースの問題点
- `splits` テーブルのスキーマを変更 → 10個のテーブル全てを再生成
- `form_efficiency` の計算ロジックを修正 → 関係のない `hr_efficiency` なども再生成
- Claude Codeが部分的な再生成時に誤って `--delete-db` を使用 → 全データ消失

### ユースケース

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

#### UC3: 強制的なデータ削除と再生成（デバッグ用）
**アクター**: 開発者
**前提条件**: 特定アクティビティのデータに不整合があり、完全な再生成が必要
**操作**:
```bash
python tools/scripts/regenerate_duckdb.py --tables splits form_efficiency --activity-ids 12345 --force
```
**期待結果**:
- アクティビティ12345の既存データが `splits` と `form_efficiency` テーブルから削除される
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
-- Parent table (metadata, always included)
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

#### Table Dependency Graph
```
activities (parent)
    ├── splits
    ├── form_efficiency
    ├── hr_efficiency
    ├── heart_rate_zones
    ├── performance_trends
    ├── vo2_max
    ├── lactate_threshold
    ├── time_series_metrics
    └── section_analyses

body_composition (independent, no FK)
```

**Important Design Decisions:**
1. `activities` table is ALWAYS included when regenerating any table (maintains FK integrity)
2. `body_composition` can be regenerated independently (no FK to activities)
3. All other tables have FK to `activities.activity_id`

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

parser.add_argument(
    "--force",
    action="store_true",
    help=(
        "Delete existing records for specified activity_ids/date range "
        "BEFORE re-insertion (use with caution)"
    )
)

# EXISTING OPTIONS (unchanged)
parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
parser.add_argument("--activity-ids", type=int, nargs="+", help="List of activity IDs")
parser.add_argument("--delete-db", action="store_true", help="Delete database file")
parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
```

#### Validation Rules

```python
def validate_arguments(args):
    """Validate CLI arguments."""

    # Rule 1: --delete-db and --tables are mutually exclusive
    if args.delete_db and args.tables:
        raise ValueError(
            "Error: --delete-db cannot be used with --tables. "
            "Database file deletion is only allowed for full regeneration (all tables). "
            "Use --force to delete existing records for specified activities instead."
        )

    # Rule 2: --force requires --tables (force is meaningless for full regeneration)
    if args.force and not args.tables:
        raise ValueError(
            "Error: --force requires --tables. "
            "Use --force with --tables to delete existing records before re-insertion."
        )

    # Rule 3: activity_ids and date range are mutually exclusive
    if args.activity_ids and (args.start_date or args.end_date):
        raise ValueError(
            "Error: Cannot specify both --activity-ids and date range. "
            "Use one or the other."
        )
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
        force: bool = False,              # NEW
    ):
        """
        Initialize regenerator.

        Args:
            raw_dir: Raw data directory
            db_path: DuckDB path
            delete_old_db: Delete database file (only if tables is None)
            tables: List of tables to regenerate (None = all tables)
            force: Delete existing records before re-insertion
        """
        # Validation
        if delete_old_db and tables:
            raise ValueError("Cannot use delete_old_db with tables")

        self.tables = tables
        self.force = force
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

        Args:
            activity_ids: List of activity IDs to delete
            tables: List of table names to delete from
        """
        with duckdb.connect(str(self.db_path)) as conn:
            for table in tables:
                if table == "body_composition":
                    # body_composition has no activity_id, skip
                    continue

                placeholders = ",".join(["?"] * len(activity_ids))
                query = f"DELETE FROM {table} WHERE activity_id IN ({placeholders})"
                conn.execute(query, activity_ids)
                logger.info(
                    f"Deleted {len(activity_ids)} records from {table}"
                )

    def regenerate_single_activity(
        self,
        activity_id: int,
        activity_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Regenerate DuckDB data for a single activity.

        MODIFIED: Now respects self.tables and self.force

        Process:
        1. Check if raw data exists
        2. If force=True, delete existing records from specified tables
        3. Use GarminIngestWorker.process_activity() to generate data
        4. Insert only specified tables (via table filtering)

        Args:
            activity_id: Activity ID
            activity_date: Activity date (optional)

        Returns:
            Result dict with status and details
        """
        # ... existing checks ...

        # NEW: Delete existing records if force=True
        if self.force:
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

### Phase 1: Core Infrastructure (Table Filtering & Validation)
**目的**: テーブルフィルタリングの基盤を構築

**実装内容**:
- `DuckDBRegenerator.__init__()` に `tables` と `force` パラメータを追加
- `filter_tables()` メソッドを実装（バリデーション + `activities` 自動追加）
- CLI引数パーサーに `--tables` と `--force` を追加
- Validation logic を実装（`--delete-db` + `--tables` の排他制御）

**テスト内容**:
- Unit test: `filter_tables()` の各種パターン（None, 単一テーブル, 複数テーブル, 不正なテーブル名）
- Unit test: `activities` テーブルの自動追加ロジック（`body_composition` のみの場合は追加しない）
- Unit test: Validation logic（`--delete-db` + `--tables` でエラー）
- Integration test: CLI引数パースとバリデーション

**受け入れ基準**:
- [ ] `--tables` オプションが正しくパースされる
- [ ] 不正なテーブル名でエラーが発生する
- [ ] `activities` テーブルが自動的に追加される（`body_composition` 単独を除く）
- [ ] `--delete-db` + `--tables` でエラーメッセージが表示される
- [ ] 全Unit testsが合格する

### Phase 2: Selective Deletion (--force option)
**目的**: 既存レコードの選択的削除機能を実装

**実装内容**:
- `delete_activity_records()` メソッドを実装
- `regenerate_single_activity()` に削除ロジックを統合
- `body_composition` テーブルの特殊処理（activity_id なし）
- トランザクション管理（DELETE → INSERT が原子的）

**テスト内容**:
- Unit test: `delete_activity_records()` の各種パターン
- Unit test: `body_composition` テーブルのスキップ
- Integration test: `--force` オプションの動作確認（DELETE → INSERT）
- Integration test: トランザクション整合性（削除中のエラーハンドリング）

**受け入れ基準**:
- [ ] `--force` オプションが正しく動作する（既存データ削除 → 再挿入）
- [ ] 指定したテーブルのみから削除される
- [ ] `body_composition` テーブルが正しく処理される
- [ ] エラー発生時にロールバックされる
- [ ] 全Integration testsが合格する

### Phase 3: GarminIngestWorker Integration
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
- [ ] `activities` テーブルは常に挿入される（フィルタに含まれる場合）
- [ ] 全Integration testsが合格する

### Phase 4: End-to-End Testing & Edge Cases
**目的**: 全機能の統合テストとエッジケース処理

**実装内容**:
- Dry-run モードのテーブルフィルタリング対応
- エラーハンドリングの強化（部分的な失敗の処理）
- ログ出力の改善（どのテーブルを再生成したか明示）
- Summary レポートの拡張（テーブル別の成功/失敗数）

**テスト内容**:
- Integration test: UC1-UC5 の全ユースケースを実行
- Integration test: 大量アクティビティでのテーブル別再生成（パフォーマンス確認）
- Integration test: エラー発生時の部分的な失敗処理
- Performance test: 全テーブル vs 単一テーブル再生成の速度比較

**受け入れ基準**:
- [ ] UC1-UC5 の全ユースケースが正しく動作する
- [ ] Dry-run モードでテーブルフィルタリング情報が表示される
- [ ] エラー発生時も適切にハンドリングされる
- [ ] Summary レポートにテーブル別の統計が表示される
- [ ] 単一テーブル再生成が全テーブル再生成より高速である

### Phase 5: Documentation & Migration Guide
**目的**: ドキュメント整備とマイグレーションガイド作成

**実装内容**:
- `regenerate_duckdb.py` の docstring 更新
- `CLAUDE.md` の更新（新しいオプションの説明）
- Migration guide の作成（既存スクリプトからの移行方法）
- Usage examples の追加（各種ユースケースの実例）

**テスト内容**:
- Manual test: ドキュメントの手順に従って各種操作を実行
- Manual test: Claude Code がドキュメントを理解して正しく使用できるか確認

**受け入れ基準**:
- [ ] `--help` 出力が新しいオプションを含む
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
  - Expected: `["activities", "splits"]`（`activities` 自動追加）

- [ ] `test_filter_tables_multiple_tables`
  - Input: `tables=["splits", "form_efficiency"]`
  - Expected: `["activities", "splits", "form_efficiency"]`

- [ ] `test_filter_tables_body_composition_only`
  - Input: `tables=["body_composition"]`
  - Expected: `["body_composition"]`（`activities` 追加なし）

- [ ] `test_filter_tables_invalid_table_name`
  - Input: `tables=["invalid_table"]`
  - Expected: `ValueError` with "Invalid table names: {'invalid_table'}"

- [ ] `test_validate_arguments_delete_db_with_tables`
  - Input: `delete_db=True, tables=["splits"]`
  - Expected: `ValueError` with "--delete-db cannot be used with --tables"

- [ ] `test_validate_arguments_force_without_tables`
  - Input: `force=True, tables=None`
  - Expected: `ValueError` with "--force requires --tables"

#### Phase 2: Selective Deletion
- [ ] `test_delete_activity_records_single_table`
  - Input: `activity_ids=[12345], tables=["splits"]`
  - Expected: `splits` テーブルから1レコード削除

- [ ] `test_delete_activity_records_multiple_tables`
  - Input: `activity_ids=[12345], tables=["splits", "form_efficiency"]`
  - Expected: 両テーブルから1レコードずつ削除

- [ ] `test_delete_activity_records_skip_body_composition`
  - Input: `activity_ids=[12345], tables=["body_composition"]`
  - Expected: 削除処理がスキップされる（activity_id なし）

- [ ] `test_delete_activity_records_multiple_activities`
  - Input: `activity_ids=[12345, 67890], tables=["splits"]`
  - Expected: `splits` テーブルから2レコード削除

#### Phase 3: GarminIngestWorker Integration
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

- [ ] `test_force_option_deletes_and_reinserts`
  - Setup: 既存データがDuckDBに存在
  - Command: `--tables splits --activity-ids 12345 --force`
  - Expected: 既存データ削除 → 新データ挿入

- [ ] `test_force_option_without_force_skips_existing`
  - Setup: 既存データがDuckDBに存在
  - Command: `--tables splits --activity-ids 12345`（`--force` なし）
  - Expected: 既存データをスキップ（再挿入なし）

#### Phase 3: Table Filtering
- [ ] `test_regenerate_single_table_only_inserts_specified`
  - Command: `--tables splits --activity-ids 12345`
  - Expected: `splits` と `activities` テーブルのみに新データ、他は変更なし

- [ ] `test_regenerate_multiple_tables_only_inserts_specified`
  - Command: `--tables splits form_efficiency --activity-ids 12345`
  - Expected: `splits`, `form_efficiency`, `activities` のみ更新

- [ ] `test_regenerate_with_date_range_and_tables`
  - Command: `--tables splits --start-date 2025-01-01 --end-date 2025-01-31`
  - Expected: 期間内の全アクティビティの `splits` テーブルが更新

#### Phase 4: End-to-End
- [ ] `test_uc1_single_table_schema_change`
  - Scenario: UC1 の完全なフロー
  - Expected: `splits` テーブルのみ再生成、他は影響なし

- [ ] `test_uc2_multiple_tables_logic_fix`
  - Scenario: UC2 の完全なフロー
  - Expected: 2テーブルのみ再生成

- [ ] `test_uc3_force_delete_and_regenerate`
  - Scenario: UC3 の完全なフロー
  - Expected: データ削除 → 再挿入

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

- [ ] `test_force_option_performance_overhead`
  - Setup: 100アクティビティのテストデータ
  - Test: `--force` あり vs なし
  - Expected: `--force` のオーバーヘッドが10%以下

- [ ] `test_large_activity_list_performance`
  - Setup: 1000アクティビティ
  - Test: `--tables splits --activity-ids [1000 IDs]`
  - Expected: 30分以内に完了（1アクティビティ平均1.8秒）

---

## 受け入れ基準

### 機能要件
- [ ] `--tables` オプションが実装され、指定したテーブルのみが再生成される
- [ ] `--force` オプションが実装され、既存レコードの削除 → 再挿入が可能
- [ ] `--delete-db` と `--tables` の同時使用が禁止され、明確なエラーメッセージが表示される
- [ ] `activities` テーブルが自動的に含まれる（`body_composition` 単独を除く）
- [ ] UC1-UC5 の全ユースケースが正しく動作する

### 品質要件
- [ ] 全Unit testsが合格する（最低20個のテストケース）
- [ ] 全Integration testsが合格する（最低10個のテストケース）
- [ ] 全Performance testsが合格する（3個のテストケース）
- [ ] コードカバレッジ80%以上（新規コードに対して）
- [ ] Pre-commit hooks が合格する（Black, Ruff, Mypy）

### パフォーマンス要件
- [ ] 単一テーブル再生成が全テーブル再生成より50%以上高速
- [ ] `--force` オプションのオーバーヘッドが10%以下
- [ ] 1000アクティビティの処理が30分以内に完了

### ドキュメント要件
- [ ] `--help` 出力が新しいオプションを含む
- [ ] `CLAUDE.md` が更新されている
- [ ] Migration guide が作成されている
- [ ] Usage examples が各種ユースケースをカバーしている

### Claude Code Integration
- [ ] Claude Codeが `--delete-db` と `--tables` を誤って同時使用しない
- [ ] エラーメッセージが Claude Code に理解可能な形式
- [ ] Dry-run 出力が Claude Code のデバッグに有用

---

## リスク管理

### 技術的リスク

#### Risk 1: Foreign Key Constraint Violations
**リスク**: テーブル削除順序の誤りで FK 制約違反が発生
**影響度**: 高
**対策**:
- `activities` テーブルを常に最後に削除
- 削除前に FK 制約をチェック
- トランザクション内で実行し、エラー時はロールバック

#### Risk 2: Partial Failure Handling
**リスク**: 複数テーブル再生成中に一部が失敗した場合のデータ不整合
**影響度**: 中
**対策**:
- アクティビティ単位でトランザクション管理
- 失敗したアクティビティをログに記録
- リトライメカニズムの実装

#### Risk 3: Performance Degradation
**リスク**: `--force` オプション使用時に DELETE 操作が遅い
**影響度**: 中
**対策**:
- DELETE クエリに適切なインデックスを使用
- バッチ削除の実装（大量アクティビティの場合）
- Performance test で基準値を設定

### 運用リスク

#### Risk 4: Accidental Data Loss
**リスク**: ユーザーが誤って `--force` を使用してデータを削除
**影響度**: 高
**対策**:
- `--force` 使用時に警告メッセージを表示
- Dry-run モードで削除対象を事前確認可能
- バックアップ推奨のドキュメント化

#### Risk 5: Documentation Misunderstanding
**リスク**: ドキュメント不足で誤った使用法が広まる
**影響度**: 中
**対策**:
- 各種ユースケースの具体例を提供
- エラーメッセージに解決策を含める
- Migration guide で既存スクリプトからの移行方法を明示

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

## 成功指標

### 開発効率の向上
- **指標**: スキーマ変更後のテストサイクル時間
- **目標**: 全テーブル再生成（20分）→ 単一テーブル再生成（5分）に短縮

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
