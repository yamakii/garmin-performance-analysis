# 計画: Regenerate DuckDB Post-FK Removal Enhancement

## プロジェクト情報
- **プロジェクト名**: `regenerate_duckdb_post_fk_removal`
- **作成日**: `2025-11-01`
- **ステータス**: 計画中
- **GitHub Issue**: #45

## 要件定義

### 目的
Foreign key (FK) constraints removal (2025-11-01) により可能になった独立したテーブル再生成機能を、regenerate_duckdb.py のドキュメント、安全性チェック、ログ機能を通じて完全に活用できるようにする。

### 解決する問題
**現状の課題:**
1. **ドキュメント不足**: FK制約削除の利点（独立したテーブル再生成）がmodule docstringで説明されていない
2. **安全性検証なし**: 子テーブルのみ再生成時に親活動の存在確認がない（参照整合性エラーのリスク）
3. **ログの不明瞭性**: 削除戦略（活動単位 vs テーブル全体）がログから判別しづらい
4. **Breaking changeリスク**: `--force`フラグの追加は既存ワークフローに影響（Phase 4は慎重に検討）

**FK削除の背景:**
- 旧システム: 全テーブルが `activities` テーブルに依存（CASCADE削除）
- 新システム: FK制約なし → 独立したテーブル更新が可能
- 実装完了: `--tables` パラメータとフィルタリング機能は実装済み

### ユースケース
1. **メタデータのみ修正**: `--tables activities --activity-ids 12345` で活動情報のみ更新
2. **パフォーマンス指標再計算**: `--tables splits form_efficiency --activity-ids 12345` でパフォーマンステーブルのみ更新
3. **日付範囲での部分更新**: `--tables splits --start-date 2025-10-01 --end-date 2025-10-31` で期間指定
4. **安全性検証**: 親活動が存在しない場合のエラー早期検出
5. **操作履歴追跡**: ログから削除戦略とテーブル一覧を明確に把握

---

## 設計

### アーキテクチャ
```
regenerate_duckdb.py
├── Module docstring (Phase 1: Documentation)
│   ├── FK removal benefits explanation
│   ├── Common use case examples (4+)
│   └── Safety rules documentation
│
├── DuckDBRegenerator class
│   ├── validate_table_dependencies() (Phase 2: NEW)
│   │   ├── Check parent activities exist
│   │   └── Raise ValueError if missing
│   │
│   ├── delete_activity_records() (Phase 3: Enhanced logging)
│   │   └── Log: 🗑️ Deletion strategy: Activity-specific
│   │
│   ├── delete_table_all_records() (Phase 3: Enhanced logging)
│   │   └── Log: ⚠️ Deletion strategy: Table-wide
│   │
│   └── regenerate_all() (Phase 2: Integration)
│       └── Call validate_table_dependencies() before deletion
│
└── main() (Phase 4: Optional --force flag)
    └── Add --force argument (breaking change)
```

### API/インターフェース設計
```python
# Phase 2: Validation method
def validate_table_dependencies(
    self,
    tables: list[str] | None,
    activity_ids: list[int]
) -> None:
    """
    Validate that parent tables exist before regenerating child tables.

    Args:
        tables: List of table names (None = all tables)
        activity_ids: List of activity IDs to regenerate

    Raises:
        ValueError: If child tables specified without activities existing

    Logic:
        - Skip validation if tables is None (full regeneration)
        - Skip validation if "activities" in tables (parent being regenerated)
        - For child-only regeneration: check each activity_id exists in DuckDB
        - Raise ValueError with helpful message listing missing IDs (first 5)
    """
    pass

# Phase 3: Enhanced logging format
# delete_activity_records() logs:
# 🗑️  Deletion strategy: Activity-specific (3 activities)
#    Tables: splits, form_efficiency
#    Reason: --activity-ids specified with --tables

# delete_table_all_records() logs:
# ⚠️  Deletion strategy: Table-wide (all records)
#    Tables: splits, form_efficiency
#    Reason: --tables specified without --activity-ids
```

---

## 実装フェーズ

### Phase 1: Documentation Improvements (HIGH Priority)
**実装内容:**
- Module docstring の更新
- FK制約削除の利点を説明
- 4+ の一般的なユースケース例を追加
- 安全性ルール（子テーブルには親活動が必要）を明記

**テスト内容:**
- Docstring が sphinx でレンダリング可能か確認
- 例コマンドが実際に動作するか検証

**受け入れ基準:**
- [ ] Docstring に FK removal の言及がある
- [ ] 4+ のユースケース例がある（metadata-only, performance-only, date range, etc.）
- [ ] Safety rules が明記されている
- [ ] Key Benefits セクションがある

### Phase 2: Safety Validation (MEDIUM Priority)
**実装内容:**
- `validate_table_dependencies()` メソッド作成
- `regenerate_all()` に検証ロジックを統合（削除前）
- 親活動が存在しない場合の ValueError 発生
- エラーメッセージにmissing activity IDs を含める（先頭5件）

**テスト内容:**
- Unit test: `validate_table_dependencies()` の動作確認
  - 親活動存在時: ValidationError なし
  - 親活動不在時: ValueError with missing IDs
  - tables=None 時: 検証スキップ
  - "activities" in tables 時: 検証スキップ
- Integration test: FK-independent regeneration
  - activities のみ再生成 → 成功
  - 子テーブルのみ再生成（親存在） → 成功
  - 子テーブルのみ再生成（親不在） → ValidationError

**受け入れ基準:**
- [ ] `validate_table_dependencies()` が実装されている
- [ ] 親活動不在時に明確なエラーメッセージが表示される
- [ ] エラーメッセージに missing activity IDs が含まれる（先頭5件）
- [ ] 適切な場合（tables=None, "activities" in tables）に検証がスキップされる
- [ ] Unit tests が 100% パス
- [ ] Integration tests が成功

### Phase 3: Enhanced Logging (HIGH Priority)
**実装内容:**
- `delete_activity_records()` に削除戦略ログを追加
  - 絵文字: 🗑️
  - フォーマット: "Deletion strategy: Activity-specific (N activities)"
  - テーブル一覧と理由を含める
- `delete_table_all_records()` に削除戦略ログを追加
  - 絵文字: ⚠️（警告）
  - フォーマット: "Deletion strategy: Table-wide (all records)"
  - テーブル一覧と理由を含める

**テスト内容:**
- Manual test: ログ出力の確認
  - `--tables splits --activity-ids 12345` → 🗑️ Activity-specific
  - `--tables splits --start-date ... --end-date ...` → ⚠️ Table-wide

**受け入れ基準:**
- [ ] 全削除操作が戦略を明確にログ出力
- [ ] テーブル全体削除時に ⚠️ 絵文字が表示される
- [ ] ログにテーブル名と理由が含まれる
- [ ] ログフォーマットが読みやすい

### Phase 4: --force Flag Enhancement (LOW Priority, Optional)
**実装内容:**
- `argparse` に `--force` 引数を追加
- `__init__()` に `self.force` 属性を追加
- 削除ロジックで `self.force` をチェック
- `--force` なしの場合、既存レコードをスキップ（削除なし）
- Help text 更新

**Breaking Change 警告:**
- 現在: `--tables` 指定時に常に削除が発生
- 変更後: `--force` フラグがないと削除されない
- 影響: 既存スクリプトが `--force` を追加する必要あり

**テスト内容:**
- Unit test: `--force` フラグの動作確認
- Integration test: 既存レコードのスキップ動作

**受け入れ基準:**
- [ ] `--force` フラグが実装されている
- [ ] `--force` なしで既存レコードがスキップされる
- [ ] Help text が `--force` の動作を説明
- [ ] Breaking change が CHANGELOG に記載されている
- [ ] ユーザーへの移行ガイド作成（オプション）

**Note:** このフェーズは breaking change であり、ユーザーとの議論が必要。Phase 1-3 完了後に検討を推奨。

### Phase 5: CLAUDE.md Documentation (MEDIUM Priority)
**実装内容:**
- `garmin-performance-analysis/CLAUDE.md` の "For Tool Development" セクションに追加
- 新セクション: "DuckDB Regeneration (Post-FK-Removal)"
- 新機能の説明（独立したテーブル更新）
- 4+ の実用的なコマンド例
- 安全性ルールの言及

**Content Structure:**
```markdown
### DuckDB Regeneration (Post-FK-Removal)

**New Capabilities (2025-11-01):**
- Independent table regeneration (FK constraints removed)
- Update metadata without touching performance data
- Recalculate specific metrics for targeted activities

**Common Patterns:**

1. **Metadata Fix (activities table only)**
```bash
uv run python tools/scripts/regenerate_duckdb.py \
  --tables activities \
  --activity-ids 12345
```

2. **Performance Recalculation (child tables only)**
```bash
uv run python tools/scripts/regenerate_duckdb.py \
  --tables splits form_efficiency \
  --activity-ids 12345
```

3. **Date Range with Specific Tables**
```bash
uv run python tools/scripts/regenerate_duckdb.py \
  --tables splits \
  --start-date 2025-10-01 \
  --end-date 2025-10-31
```

4. **Full Table Regeneration (all activities)**
```bash
uv run python tools/scripts/regenerate_duckdb.py \
  --tables splits form_efficiency
```

**Safety Rules:**
- Child tables require parent activities to exist
- Validation occurs before deletion (prevents orphaned records)
- Use `--activity-ids` for surgical updates, date range for batch updates
```

**テスト内容:**
- Manual review: CLAUDE.md の可読性確認
- Command verification: 例コマンドの動作確認

**受け入れ基準:**
- [ ] "For Tool Development" セクション内に配置
- [ ] 4+ の動作するコマンド例がある
- [ ] 安全性ルールが記載されている
- [ ] FK removal の日付（2025-11-01）が明記されている

---

## テスト計画

### Unit Tests
- [ ] `validate_table_dependencies()` の動作確認
  - tables=None 時の検証スキップ
  - "activities" in tables 時の検証スキップ
  - 親活動存在時の成功
  - 親活動不在時の ValueError
  - エラーメッセージに missing IDs 含む
- [ ] `--force` フラグの動作（Phase 4）
  - force=True 時の削除
  - force=False 時のスキップ

### Integration Tests
- [ ] FK-independent regeneration シナリオ
  - activities のみ再生成 → 成功
  - 子テーブルのみ再生成（親存在） → 成功
  - 子テーブルのみ再生成（親不在） → ValidationError
- [ ] 削除戦略のログ出力確認
  - Activity-specific deletion (🗑️)
  - Table-wide deletion (⚠️)

### Manual Tests
- [ ] ドキュメント例の実行確認
  - Module docstring の例コマンド
  - CLAUDE.md の例コマンド
- [ ] ログ出力の可読性確認
  - 削除戦略が明確に表示されるか
  - テーブル一覧と理由が含まれるか

---

## 受け入れ基準

**Phase 1 (Documentation):**
- [ ] Module docstring が FK removal benefits を説明
- [ ] 4+ のユースケース例を含む
- [ ] Safety rules が明記されている

**Phase 2 (Safety Validation):**
- [ ] `validate_table_dependencies()` 実装完了
- [ ] 親活動不在時に明確なエラー
- [ ] Missing activity IDs を含むエラーメッセージ
- [ ] Unit tests 100% パス

**Phase 3 (Enhanced Logging):**
- [ ] 削除戦略が絵文字付きでログ出力
- [ ] テーブル一覧と理由が含まれる
- [ ] Table-wide deletion に ⚠️ 表示

**Phase 4 (--force Flag, Optional):**
- [ ] `--force` フラグ実装
- [ ] Breaking change の CHANGELOG 記載
- [ ] ユーザー移行ガイド作成

**Phase 5 (CLAUDE.md):**
- [ ] "For Tool Development" に新セクション追加
- [ ] 4+ の動作するコマンド例
- [ ] 安全性ルールの言及

**共通:**
- [ ] 全テストがパスする
- [ ] Pre-commit hooks がパスする
- [ ] ドキュメントが更新されている
- [ ] コードカバレッジ 80% 以上（新規コードに限る）

---

## 実装戦略

### 推奨アプローチ
1. **Phase 1 (Documentation)** から開始
   - 即座に価値提供（ユーザー理解向上）
   - コード変更なし、リスク最小
2. **Phase 3 (Logging)** を次に実装
   - 小さな変更、高い可視性
   - ユーザーフィードバック収集
3. **Phase 2 (Validation)** を実装
   - 新メソッド追加、エラー防止
   - Unit tests で品質保証
4. **Phase 5 (CLAUDE.md)** を更新
   - 知識の集約とドキュメント統合
5. **Phase 4 (--force Flag)** を検討
   - Breaking change のため慎重に議論
   - ユーザーニーズ確認後に判断

### 依存関係
- Phase 1 → 独立
- Phase 2 → Phase 1 完了後（ドキュメント整合性）
- Phase 3 → 独立
- Phase 4 → Phase 1-3 完了後（Breaking change のため）
- Phase 5 → Phase 1-3 完了後（全機能の統合ドキュメント）

### リスク管理
**低リスク:**
- Phase 1: ドキュメントのみ、コード影響なし
- Phase 3: ログ追加のみ、既存動作に影響なし

**中リスク:**
- Phase 2: 新 ValueError 発生の可能性（既存ワークフローで親活動不在の場合）
  - 軽減策: エラーメッセージに解決方法を含める

**高リスク:**
- Phase 4: Breaking change（`--force` フラグ必須化）
  - 軽減策: ユーザー議論、移行期間設定、CHANGELOG 明記

---

## Success Metrics

1. **Documentation Clarity**: ユーザーが docstring のみで FK removal benefits を理解
2. **Error Prevention**: 検証が親活動不在を削除前に検出（データ整合性向上）
3. **Log Visibility**: 削除戦略がログから明確に判別可能
4. **User Guidance**: CLAUDE.md がコピペ可能な実用例を提供

---

## プロジェクトメタデータ

- **プロジェクト名**: regenerate_duckdb_post_fk_removal
- **推定期間**: 1-2 days
- **依存関係**: なし（現在の Phase 4 実装は完了済み）
- **リスクレベル**: 低（大部分はドキュメント + 検証、Phase 4 のみ Breaking change）
- **影響範囲**: regenerate_duckdb.py, CLAUDE.md, unit/integration tests

---

## Notes

**FK制約削除の背景 (2025-11-01):**
- PR: [Link to be added]
- 削除理由: 独立したテーブル更新の柔軟性向上
- 現在の実装: `--tables` パラメータと `_should_insert_table()` フィルタリング実装済み

**Phase 4 (--force flag) 慎重検討が必要:**
- 現在のデフォルト動作: `--tables` 指定時に削除が発生
- 変更後のデフォルト動作: `--force` なしでは削除なし
- 移行コスト: 既存スクリプトに `--force` 追加必要
- ユーザー議論推奨: Phase 1-3 完了後にニーズ確認

**参考プロジェクト:**
- `docs/project/_archived/2025-10-31_remove_fk_constraints/` (FK制約削除)
- `docs/project/_archived/2025-10-25_regenerate_duckdb_tables_filtering/` (テーブルフィルタリング実装)
