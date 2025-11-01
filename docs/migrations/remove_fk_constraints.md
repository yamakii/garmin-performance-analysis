# Database Migration Guide: Foreign Key Constraint Removal

**Migration Date**: 2025-11-01
**GitHub Issue**: #44
**Status**: Completed

---

## Overview

This migration removes foreign key (FK) constraints from 9 child tables in the DuckDB schema. The change simplifies data management while maintaining data integrity at the application layer.

### Affected Tables

| Table               | FK Constraint (Before)                          | Status (After) |
| ------------------- | ----------------------------------------------- | -------------- |
| `splits`            | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `form_efficiency`   | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `heart_rate_zones`  | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `hr_efficiency`     | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `performance_trends`| FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `vo2_max`           | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `lactate_threshold` | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `form_evaluations`  | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |
| `section_analyses`  | FOREIGN KEY (activity_id) REFERENCES activities | **Removed**    |

### Unchanged Tables

- `activities` (parent table, no FK constraints)
- `body_composition` (independent table)
- `form_baseline_history` (independent table)

---

## Rationale

### Why Remove FK Constraints?

**System Characteristics:**
1. **Single Data Source**: All data comes from Garmin API (no multi-source conflicts)
2. **Bulk Write Pattern**: Activities and child records inserted together (no partial writes)
3. **LEFT JOIN Usage**: All queries use LEFT JOIN (orphaned records tolerated by design)
4. **Application-Layer Integrity**: `activity_id` consistency enforced by GarminIngestWorker

**Benefits:**
- ✅ **Simplified Deletion Logic**: No FK ordering required in `regenerate_duckdb.py`
- ✅ **Easier Schema Evolution**: New tables don't need FK considerations
- ✅ **Reduced Error Handling**: No FK violation exceptions to handle
- ✅ **Faster Deletion**: No FK constraint checks during DELETE operations

---

## Migration Process

### For Existing Databases

**⚠️ IMPORTANT: Backup your database before migration**

#### Step 1: Backup Database

```bash
# Create backup copy
cp data/database/garmin_performance.duckdb data/database/garmin_performance.duckdb.backup
```

#### Step 2: Dry Run (Recommended)

```bash
# Test migration without making changes
uv run python -c "
from tools.database.migrations.remove_fk_constraints import migrate_remove_fk_constraints
result = migrate_remove_fk_constraints('data/database/garmin_performance.duckdb', dry_run=True)
print(result)
"
```

**Expected Output:**
```
DRY RUN MODE - No changes will be made

Tables to migrate: ['splits', 'form_efficiency', ...]

Steps:
1. BEGIN TRANSACTION
2. CREATE TABLE splits_backup_fk AS SELECT * FROM splits
3. DROP TABLE splits
4. CREATE TABLE splits (...) -- without FK
...
8. COMMIT
```

#### Step 3: Execute Migration

```bash
# Run actual migration
uv run python -c "
from tools.database.migrations.remove_fk_constraints import migrate_remove_fk_constraints
result = migrate_remove_fk_constraints('data/database/garmin_performance.duckdb')
print(f'Migration status: {result[\"status\"]}')
print(f'Tables migrated: {len(result[\"tables\"])}')
"
```

**Expected Output:**
```
Migration status: success
Tables migrated: 9
```

#### Step 4: Verify Migration

```bash
# Verify no FK constraints exist
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb')

# Test orphaned record insertion (should succeed with no FK)
conn.execute('INSERT INTO splits (activity_id, split_index) VALUES (999999, 1)')
count = conn.execute('SELECT COUNT(*) FROM splits WHERE activity_id = 999999').fetchone()[0]

print(f'Orphaned record count: {count}')
print('✅ FK constraints successfully removed' if count == 1 else '❌ FK constraints still exist')

# Cleanup test record
conn.execute('DELETE FROM splits WHERE activity_id = 999999')
conn.close()
"
```

#### Step 5: Verify Data Integrity

```bash
# Check for orphaned records (should be zero)
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb')

orphaned = conn.execute('''
    SELECT s.activity_id
    FROM splits s
    LEFT JOIN activities a ON s.activity_id = a.activity_id
    WHERE a.activity_id IS NULL
''').fetchall()

print(f'Orphaned records: {len(orphaned)}')
print('✅ Data integrity maintained' if len(orphaned) == 0 else f'⚠️  Found {len(orphaned)} orphaned records')

conn.close()
"
```

---

## For New Databases

**No migration needed.** New databases created after 2025-11-01 automatically use the FK-free schema.

```bash
# GarminDBWriter._ensure_tables() now creates tables without FK constraints
from tools.database.db_writer import GarminDBWriter

writer = GarminDBWriter(db_path="new_database.duckdb")
writer._ensure_tables()  # Creates tables WITHOUT FK constraints
```

---

## Migration Script Details

### Internal Strategy

The migration script uses a safe **CTAS (CREATE TABLE AS SELECT)** strategy:

```sql
BEGIN TRANSACTION;

-- 1. Backup
CREATE TABLE splits_backup_fk AS SELECT * FROM splits;

-- 2. Drop old table
DROP TABLE splits;

-- 3. Create new table (without FK)
CREATE TABLE splits (
    activity_id BIGINT,
    split_index INTEGER,
    -- ... other columns ...
    PRIMARY KEY (activity_id, split_index)
    -- Note: NO FOREIGN KEY constraint
);

-- 4. Restore data
INSERT INTO splits SELECT * FROM splits_backup_fk;

-- 5. Verify data integrity
-- Assert: COUNT(*) from splits == COUNT(*) from splits_backup_fk

-- 6. Cleanup
DROP TABLE splits_backup_fk;

COMMIT;  -- Or ROLLBACK on error
```

### Safety Features

- ✅ **Transaction Safety**: All operations in BEGIN...COMMIT block
- ✅ **Automatic Rollback**: On any error, database returns to pre-migration state
- ✅ **Data Verification**: Row counts checked before cleanup
- ✅ **Backup Tables**: Created before DROP (recoverable within transaction)
- ✅ **Column-Aware Restore**: Handles schema differences between test and production

---

## Rollback Procedure

### If Migration Fails

The migration script automatically rolls back on error. Database remains unchanged.

```bash
# Verify rollback succeeded
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb')

# Check if backup tables exist (should be 0 after rollback)
backups = conn.execute('''
    SELECT table_name FROM information_schema.tables
    WHERE table_name LIKE '%_backup_fk'
''').fetchall()

print(f'Backup tables: {len(backups)}')
print('✅ Rollback successful' if len(backups) == 0 else '⚠️  Backup tables still exist')

conn.close()
"
```

### If Migration Succeeded But You Want to Revert

**Option 1: Restore from Backup**

```bash
# Restore backup database
mv data/database/garmin_performance.duckdb data/database/garmin_performance_no_fk.duckdb
cp data/database/garmin_performance.duckdb.backup data/database/garmin_performance.duckdb
```

**Option 2: Recreate Database** (⚠️ Requires full data re-ingestion)

```bash
# Delete database
rm data/database/garmin_performance.duckdb

# Re-ingest all data (with OLD db_writer.py that has FK constraints)
git checkout main  # Before FK removal
uv run python tools/scripts/bulk_ingest.py --start-date 2025-01-01 --end-date 2025-12-31
```

---

## Testing

### Unit Tests (7 tests)

```bash
# Run unit tests
uv run pytest tests/unit/test_remove_fk_migration.py -v
```

Tests cover:
- Backup table creation
- Drop old tables
- Create new tables without FK
- Restore data from backup
- Verify data integrity
- Cleanup backup tables
- Transaction rollback on error

### Integration Tests (7 tests)

```bash
# Run integration tests
uv run pytest tests/integration/test_remove_fk_migration_integration.py -v
```

Tests cover:
- End-to-end migration on production-like database
- Data integrity preservation
- LEFT JOIN queries after migration
- No FK constraints after migration
- Dry run mode
- Regenerate script compatibility
- Orphaned record detection

---

## Impact on Existing Code

### ✅ No Breaking Changes

All existing code continues to work:

- ✅ **Data Ingestion**: No changes required
- ✅ **Queries**: LEFT JOINs work identically
- ✅ **Reports**: No changes needed
- ✅ **Regeneration**: Works with simplified logic

### ✅ Updated Components

- ✅ **db_writer.py**: Schema definitions updated (FK removed)
- ✅ **regenerate_duckdb.py**: Comment added (FK ordering no longer required)
- ✅ **Tests**: 2 tests updated to verify NO FK constraints

---

## FAQ

### Q: Will this break existing queries?

**A:** No. All queries use LEFT JOIN, which works identically with or without FK constraints.

### Q: What happens to orphaned records?

**A:** LEFT JOINs tolerate orphaned records. The application layer ensures `activity_id` consistency via GarminIngestWorker.

### Q: Can I still use regenerate_duckdb.py?

**A:** Yes. Deletion logic is simplified (no FK ordering required).

### Q: How long does migration take?

**A:** ~10 seconds for 100 activities. Time scales linearly with row count.

### Q: What if I have custom FK constraints?

**A:** This migration only affects the 9 standard tables. Custom tables are unaffected.

### Q: Can I add new tables with FK constraints?

**A:** Not recommended. Follow the FK-free pattern for consistency.

---

## Troubleshooting

### Issue: Migration fails with "table does not exist"

**Cause**: Database missing some tables (e.g., fresh database)

**Solution**: Migration script automatically skips missing tables. No action needed.

### Issue: Data integrity check fails

**Cause**: Row count mismatch between new table and backup

**Solution**: Migration automatically rolls back. Investigate why counts differ:

```bash
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb')

# Check for duplicate rows or NULL primary keys
duplicates = conn.execute('''
    SELECT activity_id, split_index, COUNT(*)
    FROM splits
    GROUP BY activity_id, split_index
    HAVING COUNT(*) > 1
''').fetchall()

print(f'Duplicate rows: {len(duplicates)}')
conn.close()
"
```

### Issue: Orphaned records detected after migration

**Cause**: Data inconsistency existed before migration

**Solution**: Clean up orphaned records:

```bash
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb')

# Delete orphaned splits
conn.execute('''
    DELETE FROM splits
    WHERE activity_id NOT IN (SELECT activity_id FROM activities)
''')

conn.close()
"
```

---

## References

- **GitHub Issue**: #44
- **Planning Document**: `docs/project/2025-11-01_remove_fk_constraints/planning.md`
- **Migration Script**: `tools/database/migrations/remove_fk_constraints.py`
- **DuckDB FK Documentation**: https://duckdb.org/docs/sql/constraints

---

## Contact

For questions or issues, please open a GitHub Issue referencing #44.
