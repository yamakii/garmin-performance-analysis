# 計画: Weight Data Migration

## 要件定義

### 目的
体重測定データのディレクトリ構造をアクティビティデータと統一し、将来的な拡張性とメンテナンス性を向上させる。現在 `data/weight_cache/` に保存されている体重データを `data/raw/weight/` に移行し、システム全体のデータ管理の一貫性を保つ。

### 解決する問題
**現在の課題:**
1. **ディレクトリ構造の不統一**: アクティビティデータは `data/raw/activity/` に保存されているが、体重データは `data/weight_cache/` という別の場所に保存されている
2. **命名規則の不統一**: 体重データは `weight_YYYY-MM-DD_raw.json` という日付ベースの命名規則を使用しているが、アクティビティデータは `activity_id` ベースのディレクトリ構造を使用している
3. **将来の拡張性の制限**: 現在の構造では、複数の体重測定ソース（スマート体重計以外）を追加する際に柔軟性が不足する
4. **コードの冗長性**: 異なるディレクトリ構造のため、データアクセスコードが複雑化している

**移行対象データ:**
- 総データ量: 約111ファイル（日付ごと、1ファイル=1日の複数測定値）
- 保存場所: `data/weight_cache/raw/weight_YYYY-MM-DD_raw.json`
- データ構造:
  - `startDate`, `endDate`: 日付範囲
  - `dateWeightList`: 1日の複数測定値配列（weight, bmi, bodyFat, bodyWater, boneMass, muscleMass など）
  - `totalAverage`: 日平均値

### ユースケース
1. **体重データの統一的な管理**: 全ての raw data を `data/raw/` 配下に統一し、データソース別にサブディレクトリで管理する
2. **完全な構造移行**: 旧構造（`data/weight_cache/`）を完全に削除し、新構造のみを使用する
3. **既存コードの直接更新**: `GarminIngestWorker`, `BodyCompositionInserter` などを新しいパス構造に直接更新する
4. **データ検証**: 移行前後でデータの整合性を確認し、データ損失がないことを保証する

---

## 設計

### アーキテクチャ

**移行後のディレクトリ構造:**

```
data/
├── raw/
│   ├── activity/          # 既存: アクティビティデータ
│   │   └── {activity_id}/
│   │       ├── activity.json
│   │       ├── splits.json
│   │       ├── weather.json
│   │       └── ...
│   └── weight/            # 新規: 体重データ（フラット構造）
│       ├── 2025-05-15.json
│       ├── 2025-05-16.json
│       └── ...            # 111ファイル（旧: weight_YYYY-MM-DD_raw.json）
├── weight/                # 新規: weight関連の派生データ
│   └── index.json         # 改名: weight_index.json から（パス更新）
├── performance/           # 既存: 変更なし
└── database/              # 既存: 変更なし

# 削除: data/weight_cache/ ディレクトリ全体
# 注: parquetファイルは削除済み（commit 3e4e783）
```

**設計方針:**
1. **日付ベースのフラットファイル構造**: 体重データは1日1ファイルで完結するため、`data/raw/weight/{YYYY-MM-DD}.json` のシンプルな構造を採用
2. **完全な構造統一**: `data/raw/` 配下に全てのrawデータを統一し、旧構造は完全に削除
3. **index.jsonの移動**: `weight_index.json` を `data/weight/index.json` に移動・簡潔化
4. **コードの直接更新**: 全ての既存コードを新しいパス構造に直接更新

### データモデル

**移行対象データ構造:**
```json
{
  "startDate": "2025-09-21",
  "endDate": "2025-09-21",
  "dateWeightList": [
    {
      "samplePk": 1758435532139,
      "date": 1758467906000,
      "calendarDate": "2025-09-21",
      "weight": 76199.0,
      "bmi": 27.299999237060547,
      "bodyFat": 24.6,
      "bodyWater": 55.1,
      "boneMass": 4199,
      "muscleMass": 30799,
      "sourceType": "INDEX_SCALE",
      "timestampGMT": 1758435506000,
      "weightDelta": -200.00000000000284
    }
  ],
  "totalAverage": {
    "from": 1758412800000,
    "until": 1758499199999,
    "weight": 76599.33333333333,
    "bmi": 27.433333079020183,
    "bodyFat": 24.9,
    "bodyWater": 54.8,
    "boneMass": 4199,
    "muscleMass": 30866
  }
}
```

**index.json構造（移行後）:**
```json
{
  "2025-09-21": {
    "date": "2025-09-21",
    "weight": 70.5,
    "bmi": 25.3,
    "raw_file": "data/raw/weight/2025-09-21.json",  // 新パス（フラット構造）
    "cached_at": "2025-09-29T17:53:20.486801",
    "source": "INDEX_SCALE"
  }
}
```

**注**: `parquet_file` フィールドは削除されました（commit 3e4e783でparquet生成が廃止）

### API/インターフェース設計

#### 1. データ移行ツール
```python
class WeightDataMigrator:
    """Migrate weight data from old structure to new structure completely."""

    def __init__(self, project_root: Path, dry_run: bool = False):
        self.project_root = project_root
        self.dry_run = dry_run
        self.old_raw_dir = project_root / "data" / "weight_cache" / "raw"
        self.old_index_file = project_root / "data" / "weight_cache" / "weight_index.json"
        self.new_raw_dir = project_root / "data" / "raw" / "weight"
        self.new_weight_dir = project_root / "data" / "weight"
        self.new_index_file = project_root / "data" / "weight" / "index.json"

    def migrate_all(self) -> dict:
        """
        Migrate all weight data from old to new structure.

        Steps:
        1. Migrate raw weight files to data/raw/weight/{YYYY-MM-DD}.json
        2. Update and move index.json with new paths (remove parquet_file field)
        3. Delete old data/weight_cache/ directory

        Returns:
            Migration report with statistics
        """
        pass

    def migrate_single_date(self, date: str) -> bool:
        """
        Migrate a single date's weight data.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            True if migration successful, False otherwise
        """
        pass

    def update_and_move_index(self) -> None:
        """Update index.json with new paths and move to new location."""
        pass

    def verify_migration(self) -> dict:
        """
        Verify migration integrity by comparing old and new files.

        Returns:
            Verification report with any discrepancies
        """
        pass

    def cleanup_old_structure(self) -> None:
        """Delete old data/weight_cache/ directory after verification."""
        pass
```

#### 2. GarminIngestWorker の更新
```python
class GarminIngestWorker:
    def __init__(self):
        # Update paths to new structure
        self.weight_raw_dir = self.project_root / "data" / "raw" / "weight"
        self.weight_index_file = self.project_root / "data" / "weight" / "index.json"

    def get_body_composition_data(self, date: str, days_back: int = 0) -> dict | None:
        """Get weight data from new structure (flat file)."""
        weight_file = self.weight_raw_dir / f"{date}.json"
        if weight_file.exists():
            return json.loads(weight_file.read_text())

        # If not found, fetch from MCP
        # ...
```

#### 3. BodyCompositionInserter の更新
```python
class BodyCompositionInserter:
    """Update all weight data paths to new structure."""

    def __init__(self):
        self.weight_index_file = Path("data/weight/index.json")  # 新パス
        # その他のパス更新
```

---

## テスト計画

### Unit Tests
- [ ] `WeightDataMigrator.migrate_single_date()` がファイルを正しく新構造 (`data/raw/weight/{date}.json`) にコピーする
- [ ] `WeightDataMigrator.migrate_single_date()` が `data/raw/weight/` ディレクトリを自動作成する
- [ ] `WeightDataMigrator.update_and_move_index()` が全エントリのパスを新構造に更新する
- [ ] `WeightDataMigrator.verify_migration()` がデータ整合性を検証する
- [ ] `WeightDataMigrator.cleanup_old_structure()` が旧ディレクトリを削除する
- [ ] Dry-run モードでファイルが実際にコピーされないことを確認

### Integration Tests
- [ ] 111ファイル全てのマイグレーションが成功する
- [ ] `index.json` が `data/weight/index.json` に移動・更新される（`parquet_file` フィールド削除）
- [ ] マイグレーション後、`GarminIngestWorker.get_body_composition_data()` が新構造からデータを取得できる
- [ ] マイグレーション後、`BodyCompositionInserter` が正常に動作する
- [ ] 旧構造 `data/weight_cache/` が完全に削除される

### Performance Tests
- [ ] 111ファイルのマイグレーションが10秒以内に完了する
- [ ] データ検証が30秒以内に完了する

### Validation Tests
- [ ] マイグレーション前後でJSON構造が完全一致する
- [ ] マイグレーション前後で日付エントリ数が一致する
- [ ] 全ての `dateWeightList` 配列が正しく保存される
- [ ] `totalAverage` が損失なく移行される

---

## 受け入れ基準

- [ ] 全111ファイルが `data/raw/weight/{YYYY-MM-DD}.json` に移行されている（フラット構造）
- [ ] `index.json` が `data/weight/index.json` に移動・更新されている（全エントリのパスが新構造、`parquet_file` フィールド削除）
- [ ] 旧構造 `data/weight_cache/` が完全に削除されている
- [ ] `GarminIngestWorker`, `BodyCompositionInserter` などが新パス構造で動作する
- [ ] データ検証スクリプトがゼロディスクレパンシーを報告する
- [ ] 全テストがパスする（Unit, Integration, Performance, Validation）
- [ ] カバレッジ85%以上（新規コードおよび更新コード）
- [ ] Pre-commit hooksがパスする
- [ ] CLAUDE.md の "Data Files Naming Convention" セクションが更新されている
- [ ] マイグレーションスクリプトのドキュメント（README.md）が作成されている

---

## 実装フェーズ

### Phase 0: 準備（調査・設計完了確認）
- [x] 既存のディレクトリ構造を調査
- [x] データ構造を確認（111ファイル、JSON構造）
- [x] 影響を受けるコードを特定（GarminIngestWorker, BodyCompositionInserter, tests）
- [x] planning.md を作成（完全移行方針）

### Phase 1: マイグレーションツールの実装（TDD）
- [x] `WeightDataMigrator` クラスの実装
  - [x] テスト: `test_migrate_single_date_success`
  - [x] テスト: `test_migrate_single_date_creates_directory`
  - [x] テスト: `test_migrate_all_dry_run`
  - [x] テスト: `test_update_and_move_index`
  - [x] テスト: `test_verify_migration_no_discrepancies`
  - [x] テスト: `test_cleanup_old_structure`
- [x] CLI スクリプト `tools/migrate_weight_data.py` の実装
  - [x] `--dry-run`, `--date`, `--all`, `--verify`, `--cleanup` オプション

### Phase 2: マイグレーション実行とバリデーション
- [x] Dry-run モードで全ファイルをテスト
- [x] 実際のマイグレーションを実行（raw + index）
- [x] データ検証スクリプトを実行
- [x] 旧構造 `data/weight_cache/` を削除

### Phase 3: 既存コードの更新（TDD）
- [x] `GarminIngestWorker` のパス更新
  - [x] `get_body_composition_data()` を新パス構造に対応
  - [x] テスト: `test_get_body_composition_new_structure`
- [x] `BodyCompositionInserter` のパス更新
  - [x] `weight_index_file` パスを更新
  - [x] テスト: 既存テストの実行
- [x] その他の影響を受けるコードの更新
- [x] 既存テストスイートを実行（regression test）

### Phase 4: ドキュメント更新とクリーンアップ
- [x] CLAUDE.md の "Data Files Naming Convention" セクションを更新
- [x] `tools/migrate_weight_data.py` の README.md を作成
- [x] Completion Report を作成

---

## リスク管理

### リスク1: データ損失
**緩和策:**
- Dry-run モードで事前テスト
- マイグレーション前にバックアップ作成（`data/weight_cache/` をコピー）
- データ検証スクリプトで全ファイルをチェック
- 検証完了まで旧構造を保持（cleanup は手動実行）

### リスク2: 既存コードの破壊
**緩和策:**
- マイグレーション実行後、既存コードを順次更新
- 各更新後に既存テストスイートを全実行
- Phase 3（コード更新）で段階的に対応

### リスク3: index.json の移動・更新失敗
**緩和策:**
- 更新前にバックアップ作成
- JSON validation を実装
- ロールバック手順を文書化（バックアップから復元）

### リスク4: 完全移行による復元困難
**緩和策:**
- Git commit を各フェーズごとに作成
- バックアップディレクトリ `data/weight_cache.backup/` を別途保持
- ロールバックスクリプトの準備

---

## 参考情報

- 既存プロジェクト: `docs/project/2025-10-09_garmin_ingest_refactoring/planning.md`
- 関連コード: `tools/ingest/garmin_worker.py`, `tools/database/inserters/body_composition.py`
- テストファイル: `tests/ingest/test_body_composition.py`, `tests/unit/test_garmin_worker_phase0.py`
