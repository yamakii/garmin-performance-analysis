# 計画: Remove Foreign Key Constraints from DuckDB Schema

## プロジェクト情報
- **プロジェクト名**: `remove_fk_constraints`
- **作成日**: `2025-11-01`
- **ステータス**: 計画中
- **GitHub Issue**: (作成予定)

---

## 要件定義

### 目的
DuckDB schema から外部キー制約を削除し、データ再生成ロジックを簡素化する。

### 解決する問題

**現状の課題:**
1. **複雑な削除順序管理**: FK制約により子テーブル→親テーブルの削除順序を管理する必要がある
2. **不要な制約**: 単一データソース（Garmin API）でbulk writeのみのため、FK制約は冗長
3. **保守コストの増加**: 新テーブル追加時にFK制約を考慮する必要がある
4. **エラーハンドリングの複雑化**: FK違反エラーの特別な処理が必要

**システム特性（FK不要の根拠）:**
- 単一データソース（Garmin API）からの bulk write のみ
- JOINは常に LEFT JOIN（孤立レコードを許容）
- データ整合性はアプリケーション層で保証
- 削除は activities.activity_id を基準に WHERE句で制御

### ユースケース

1. **通常の再生成**: `regenerate_duckdb.py` による特定テーブルの再生成が簡素化される
2. **部分削除**: 特定 activity_id のデータ削除が順序を気にせず実行可能
3. **新テーブル追加**: FK制約を考慮せずに新テーブルをスキーマに追加できる
4. **既存DBのマイグレーション**: 本番環境の既存データベースをFK無しに移行

---

## 設計

### アーキテクチャ

**影響範囲:**
```
tools/database/db_writer.py         # Schema定義（FK削除）
tools/scripts/regenerate_duckdb.py  # 削除ロジック簡素化
tools/database/migrations/          # マイグレーションスクリプト（新規）
tests/unit/test_db_writer.py        # スキーマテスト更新
tests/integration/                   # 統合テスト更新
```

**FK制約を持つ9テーブル:**
1. `splits` → activities(activity_id)
2. `form_efficiency` → activities(activity_id)
3. `heart_rate_zones` → activities(activity_id)
4. `hr_efficiency` → activities(activity_id)
5. `performance_trends` → activities(activity_id)
6. `vo2_max` → activities(activity_id)
7. `lactate_threshold` → activities(activity_id)
8. `form_evaluations` → activities(activity_id)
9. `section_analyses` → activities(activity_id)

**FK制約の無いテーブル（変更不要）:**
- `activities` (親テーブル)
- `body_composition` (独立テーブル)
- `form_baseline_history` (独立テーブル)

### データモデル

**Before (現状):**
```sql
CREATE TABLE IF NOT EXISTS splits (
    activity_id BIGINT,
    split_index INTEGER,
    -- ... 他のカラム ...
    PRIMARY KEY (activity_id, split_index),
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)  -- 削除対象
)
```

**After (変更後):**
```sql
CREATE TABLE IF NOT EXISTS splits (
    activity_id BIGINT,
    split_index INTEGER,
    -- ... 他のカラム ...
    PRIMARY KEY (activity_id, split_index)
    -- FOREIGN KEY削除: データ整合性はアプリケーション層で保証
)
```

**マイグレーション戦略:**
```sql
-- Phase 1: Backup (CTAS - CREATE TABLE AS SELECT)
CREATE TABLE splits_backup AS SELECT * FROM splits;

-- Phase 2: Drop old table
DROP TABLE splits;

-- Phase 3: Create new table (without FK)
CREATE TABLE splits (
    activity_id BIGINT,
    split_index INTEGER,
    -- ... (FK無しのスキーマ) ...
);

-- Phase 4: Restore data
INSERT INTO splits SELECT * FROM splits_backup;

-- Phase 5: Drop backup
DROP TABLE splits_backup;
```

### API/インターフェース設計

#### 1. Migration Script
```python
# tools/database/migrations/remove_fk_constraints.py

class ForeignKeyRemovalMigration:
    """Remove FK constraints from 9 child tables."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.tables_with_fk = [
            "splits",
            "form_efficiency",
            "heart_rate_zones",
            "hr_efficiency",
            "performance_trends",
            "vo2_max",
            "lactate_threshold",
            "form_evaluations",
            "section_analyses",
        ]

    def migrate(self, dry_run: bool = False) -> dict[str, str]:
        """
        Execute migration with transaction safety.

        Args:
            dry_run: If True, show SQL only without execution

        Returns:
            Migration result (status, tables migrated, errors)
        """
        pass

    def backup_table(self, conn, table: str) -> None:
        """Create backup table with CTAS."""
        pass

    def drop_old_table(self, conn, table: str) -> None:
        """Drop original table."""
        pass

    def create_new_table(self, conn, table: str) -> None:
        """Create table without FK constraint."""
        pass

    def restore_data(self, conn, table: str) -> None:
        """Restore data from backup."""
        pass

    def cleanup_backup(self, conn, table: str) -> None:
        """Drop backup table."""
        pass
```

**Usage:**
```bash
# Dry run
uv run python tools/database/migrations/remove_fk_constraints.py --dry-run

# Execute migration
uv run python tools/database/migrations/remove_fk_constraints.py

# Force migrate (skip validation)
uv run python tools/database/migrations/remove_fk_constraints.py --force
```

#### 2. Updated db_writer.py
```python
# tools/database/db_writer.py

def _ensure_tables(self):
    """Create tables WITHOUT foreign key constraints.

    Change log:
    - 2025-11-01: Removed FK constraints from 9 child tables
      Reason: Single data source + bulk writes + LEFT JOINs only
    """
    # ... (FK削除後のCREATE TABLE文) ...
```

#### 3. Simplified regenerate_duckdb.py
```python
# tools/scripts/regenerate_duckdb.py

def delete_activity_records(self, activity_ids: list[int]) -> None:
    """Delete records from filtered tables (simplified - no FK ordering).

    Before: FK-aware deletion order required
    After: Simple DELETE FROM WHERE activity_id IN (...) for any order
    """
    # 削除順序不要（FK制約無し）
    for table in self.tables:
        conn.execute(f"DELETE FROM {table} WHERE activity_id IN (?)", activity_ids)
```

---

## 実装フェーズ

### Phase 1: Migration Script Development
**目的**: 既存DBを安全にFK無しスキーマに移行

**実装内容:**
- Migration script作成 (`tools/database/migrations/remove_fk_constraints.py`)
- Dry run モード実装（SQL表示のみ）
- Transaction safety（ROLLBACK on error）
- Backup/Restore/Cleanup自動化
- Progress logging（tqdm）

**テスト内容:**
- Unit test: 各メソッド（backup/drop/create/restore）
- Integration test: テストDBでの完全なマイグレーション
- Error handling: 中断時のROLLBACK検証

**受け入れ基準:**
- Dry run で正しいSQL生成
- Migration成功率100%（テストDB）
- エラー時に完全ロールバック

---

### Phase 2: Schema Update
**目的**: db_writer.py のスキーマ定義からFK削除

**実装内容:**
- `_ensure_tables()` の9テーブルからFOREIGN KEY句削除
- Comments追加（FK削除理由を記載）
- スキーマバージョン管理（変更履歴コメント）

**テスト内容:**
- Unit test: 新規DB作成時にFKが存在しないことを確認
- Schema validation: PRAGMA foreign_key_list で確認

**受け入れ基準:**
- 9テーブルすべてでFK無し
- 新規DB作成が正常動作
- 既存データアクセスに影響なし

---

### Phase 3: Code Simplification
**目的**: regenerate_duckdb.py の削除ロジック簡素化

**実装内容:**
- `delete_activity_records()` 簡素化
  - FK削除順序の除去
  - コメント更新（FK不要を明記）
- `delete_table_all_records()` 簡素化
  - 同様にFK順序除去
- エラーハンドリング簡素化（FK違反チェック不要）

**テスト内容:**
- Integration test: 削除→再挿入の動作確認
- Edge case: 孤立レコードが発生しないことを確認

**受け入れ基準:**
- 削除ロジックが10行以上削減
- 既存の再生成機能が正常動作
- 孤立レコードゼロ（LEFT JOINで検証）

---

### Phase 4: Documentation & Migration Guide
**目的**: 変更内容のドキュメント化とマイグレーション手順書作成

**実装内容:**
- CLAUDE.md 更新（FK削除を明記）
- Migration guide作成 (`docs/database-migration-guide.md`)
- Troubleshooting section追加

**マイグレーションガイド内容:**
```markdown
# Database Migration Guide: FK Removal

## Overview
DuckDB schema から外部キー制約を削除

## Migration Steps
1. Backup current database
2. Run migration script with --dry-run
3. Review SQL output
4. Execute migration
5. Verify data integrity
6. Run tests

## Rollback Procedure
(エラー時の復旧手順)
```

**受け入れ基準:**
- CLAUDE.md にFK削除の記載
- Migration guide完成
- Troubleshooting含む

---

## テスト計画

### Unit Tests

**Migration Script Tests:**
- [ ] `test_backup_table()` - CTAS成功確認
- [ ] `test_drop_old_table()` - DROP成功確認
- [ ] `test_create_new_table()` - FK無しテーブル作成確認
- [ ] `test_restore_data()` - データ完全復元確認
- [ ] `test_cleanup_backup()` - バックアップ削除確認
- [ ] `test_migration_transaction_rollback()` - エラー時ROLLBACK確認
- [ ] `test_dry_run_mode()` - Dry runがSQLのみ出力することを確認

**Schema Tests:**
- [ ] `test_no_foreign_keys_in_new_schema()` - PRAGMA foreign_key_list が空
- [ ] `test_primary_keys_preserved()` - PKは維持されていることを確認
- [ ] `test_all_columns_present()` - カラム数・型が変更前と一致

**Deletion Logic Tests:**
- [ ] `test_delete_activity_records_any_order()` - 任意順序で削除可能
- [ ] `test_delete_table_all_records_simplified()` - FK順序不要を確認

### Integration Tests

**End-to-End Migration:**
- [ ] `test_migrate_production_like_db()` - 本番相当のDBでマイグレーション
- [ ] `test_data_integrity_after_migration()` - データ完全性確認（行数・値一致）
- [ ] `test_queries_work_after_migration()` - LEFT JOINクエリが正常動作
- [ ] `test_regenerate_after_migration()` - regenerate_duckdb.py が正常動作

**Regeneration Logic:**
- [ ] `test_regenerate_specific_tables()` - 特定テーブル再生成
- [ ] `test_regenerate_with_activity_ids()` - 特定activity削除→再挿入
- [ ] `test_regenerate_all_tables()` - 全テーブル再生成
- [ ] `test_no_orphaned_records()` - 孤立レコードゼロ（LEFT JOIN検証）

### Performance Tests

- [ ] `test_migration_performance()` - マイグレーション時間 < 10秒（100 activities）
- [ ] `test_deletion_performance()` - FK無し削除が10%以上高速化
- [ ] `test_insertion_performance()` - 挿入速度に影響なし

---

## 受け入れ基準

### Functional Requirements
- [ ] 全438+テストがパスする
- [ ] Migration scriptが本番相当DBで成功する（dry run検証済み）
- [ ] FK制約が9テーブルすべてから削除されている
- [ ] regenerate_duckdb.py が簡素化されている（コメント含む10行以上削減）
- [ ] 孤立レコードがゼロ（LEFT JOIN検証）

### Code Quality
- [ ] Pre-commit hooks パス（Black, Ruff, Mypy）
- [ ] Unit test coverage 80%以上（新規コード）
- [ ] Integration test coverage 100%（マイグレーションパス）

### Documentation
- [ ] CLAUDE.md にFK削除の変更を記載
- [ ] Migration guide完成（手順・Rollback含む）
- [ ] Code commentsにFK削除理由を明記

### Performance
- [ ] マイグレーション時間 < 10秒（100 activities）
- [ ] 削除処理が10%以上高速化（FK制約チェック不要）
- [ ] 既存機能のパフォーマンス劣化ゼロ

### Safety
- [ ] Migration scriptにROLLBACK機能
- [ ] Dry runモードで事前確認可能
- [ ] Backupテーブル自動作成

---

## リスクと対策

### リスク1: マイグレーション中のデータ消失
**対策:**
- Transaction内で全操作実行（COMMIT前にエラー検出）
- Backupテーブル作成（CTAS）
- Dry runモードで事前検証

### リスク2: 孤立レコードの発生
**対策:**
- LEFT JOIN検証クエリ追加
- Integration testで孤立レコード検出
- アプリケーション層でactivity_id整合性を保証

### リスク3: 既存コードの互換性問題
**対策:**
- Schemaテスト更新（FK存在チェック削除）
- Integration test全実行（438+テスト）
- Rollback手順のドキュメント化

---

## 開発スケジュール（目安）

**Phase 1**: Migration Script (2-3 hours)
- Script実装: 1.5h
- Unit test: 1h
- Integration test: 0.5h

**Phase 2**: Schema Update (1 hour)
- db_writer.py修正: 0.5h
- Schema test: 0.5h

**Phase 3**: Code Simplification (1-2 hours)
- regenerate_duckdb.py簡素化: 0.5h
- Integration test: 1h
- Performance test: 0.5h

**Phase 4**: Documentation (1 hour)
- CLAUDE.md更新: 0.5h
- Migration guide: 0.5h

**Total**: 5-7 hours

---

## 次のステップ

1. **GitHub Issue作成**: このplanning.mdをベースにIssue作成
2. **TDD Implementer起動**: Git worktree作成、Phase 1から実装開始
3. **Migration Script優先**: Phase 1完了後、本番DBでdry run実施
4. **段階的マージ**: Phase毎にPR作成、レビュー後マージ

---

## 参考資料

**DuckDB Documentation:**
- Foreign Keys: https://duckdb.org/docs/sql/constraints
- Transactions: https://duckdb.org/docs/sql/statements/transactions

**既存コード:**
- `tools/database/db_writer.py` - 現在のスキーマ定義
- `tools/scripts/regenerate_duckdb.py` - 削除ロジック
- `tests/unit/test_db_writer.py` - スキーマテスト

**関連プロジェクト:**
- `docs/project/2025-10-*` - 過去の類似プロジェクト参考
