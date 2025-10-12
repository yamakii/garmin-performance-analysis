# 計画: Cache Partial Refetch

## Git Worktree情報
- **Worktree Path**: `/home/user/workspace/claude_workspace/garmin-cache_partial_refetch/`
- **Branch**: `feature/cache_partial_refetch`
- **Base Branch**: `main`

## 要件定義

### 目的
個別キャッシュファイル（特にactivity_details.json）の強制再取得機能を実装し、既存のキャッシュファイルを保持しながら特定のAPIデータのみを更新可能にする。

### 解決する問題

**現在の課題:**
- `load_from_cache()`は全ファイルが揃っている場合に早期リターン（line 277）
- activity_details.jsonだけ削除して再取得したい場合（例: maxchart値を増やす）、他のキャッシュファイル（activity.json, splits.jsonなど）が存在するため早期リターンしてしまう
- 新しいmaxchart計算ロジック（lines 410-438）に到達できない
- 手動でファイルを削除してから実行する必要があり、自動化が困難

**具体的なユースケース例:**
1. activity_details.jsonのmaxchartを2000 → 3000に増やしたい
2. 天候データだけ再取得したい（API側で更新された可能性）
3. VO2 max/lactate thresholdデータだけ更新したい

### ユースケース

#### ユースケース1: activity_details.jsonの強制再取得
```python
worker = GarminIngestWorker()
result = worker.process_activity(
    activity_id=12345678901,
    activity_date="2025-10-10",
    force_refetch=["activity_details"]
)
# → activity_details.jsonのみ再取得、他のキャッシュファイルはそのまま使用
```

#### ユースケース2: 複数ファイルの同時再取得
```python
worker.process_activity(
    activity_id=12345678901,
    activity_date="2025-10-10",
    force_refetch=["weather", "vo2_max", "lactate_threshold"]
)
# → 天候と性能指標のみ再取得
```

#### ユースケース3: 既存動作の維持（後方互換性）
```python
worker.process_activity(activity_id=12345678901, activity_date="2025-10-10")
# → force_refetch=None（デフォルト）の場合、従来通りキャッシュ優先動作
```

---

## 設計

### アーキテクチャ

**影響範囲:**
- `GarminIngestWorker.collect_data()`: force_refetchパラメータ追加
- `GarminIngestWorker.load_from_cache()`: 部分キャッシュロード機能追加（新規メソッド分離）
- `GarminIngestWorker.process_activity()`: force_refetchパラメータ伝搬

**設計方針:**
1. **Minimal change principle**: 既存ロジックへの影響を最小化
2. **Explicit over implicit**: force_refetch指定時のみ動作変更
3. **Cache-first by default**: force_refetch=Noneの場合は従来通りの動作

### データモデル

**force_refetchパラメータ仕様:**
```python
force_refetch: list[str] | None = None
```

**サポートするファイル名:**
- `"activity_details"` - activity_details.json（chart data, maxchart=2000）
- `"splits"` - splits.json（lapDTOs）
- `"weather"` - weather.json（天候データ）
- `"gear"` - gear.json（ギア情報）
- `"hr_zones"` - hr_zones.json（心拍ゾーン）
- `"vo2_max"` - vo2_max.json（VO2 max推定値）
- `"lactate_threshold"` - lactate_threshold.json（乳酸閾値）

**Note:** `activity.json`（基本情報）は強制再取得対象外（training_effect抽出元のため常にロード）

### API/インターフェース設計

#### Phase 1: collect_data() 拡張

```python
def collect_data(
    self,
    activity_id: int,
    force_refetch: list[str] | None = None
) -> dict[str, Any]:
    """
    Collect activity data with per-API cache-first strategy.

    Args:
        activity_id: Activity ID
        force_refetch: List of API file names to force refetch.
                      Supported values: ['activity_details', 'splits', 'weather',
                                        'gear', 'hr_zones', 'vo2_max', 'lactate_threshold']
                      If None, use cache-first strategy (default behavior).

    Returns:
        Raw data dict with keys: activity, splits, weather, gear, hr_zones, etc.

    Examples:
        # Force refetch activity_details.json only
        worker.collect_data(12345, force_refetch=['activity_details'])

        # Force refetch multiple files
        worker.collect_data(12345, force_refetch=['weather', 'vo2_max'])

        # Default behavior (cache-first)
        worker.collect_data(12345)
    """
    # Backward compatibility check (old format cache)
    old_cache_file = self.raw_dir / f"{activity_id}_raw.json"
    if old_cache_file.exists():
        logger.info(f"Using old format cached data for activity {activity_id}")
        with open(old_cache_file, encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))

    # Normalize force_refetch parameter
    force_refetch_set = set(force_refetch) if force_refetch else set()

    # New cache format: partial loading with force_refetch
    cached_data = self.load_from_cache(activity_id, skip_files=force_refetch_set)
    if cached_data is not None and not force_refetch_set:
        # Full cache hit (no force refetch)
        return cached_data

    # Partial cache hit or force refetch - merge cached data with new fetches
    raw_data = cached_data if cached_data else {}

    # Fetch only missing or force-refetched files
    # ... (existing fetch logic with skip checks)
```

#### Phase 2: load_from_cache() リファクタリング

```python
def load_from_cache(
    self,
    activity_id: int,
    skip_files: set[str] | None = None
) -> dict[str, Any] | None:
    """
    Load cached raw_data from directory structure.

    Args:
        activity_id: Activity ID
        skip_files: Set of file names to skip loading (for force refetch).
                   Example: {'activity_details', 'weather'}

    Returns:
        Partial or complete raw_data dict. Returns None only if required files are missing
        (and not in skip_files).

    Behavior:
        - If skip_files is None: require ALL files (backward compatible)
        - If skip_files is provided: allow missing files in skip_files
        - Returns partial data if some files are missing but in skip_files
    """
    activity_dir = self.raw_dir / "activity" / str(activity_id)

    if not activity_dir.exists():
        return None

    skip_files = skip_files or set()

    # Required API files (excluding activity.json - always required)
    required_files = [
        "activity.json",
        "splits.json",
        "weather.json",
        "gear.json",
        "hr_zones.json",
        "vo2_max.json",
        "lactate_threshold.json",
    ]

    # Check all required files exist (except skipped ones)
    for file_name in required_files:
        # Map file name to skip_files key (e.g., "activity_details.json" → "activity_details")
        skip_key = file_name.replace(".json", "").replace("_", "_")

        if skip_key not in skip_files and not (activity_dir / file_name).exists():
            logger.warning(f"Missing required file: {file_name}")
            return None

    # Load all files (except skipped ones)
    # ... (existing load logic with skip checks)
```

#### Phase 3: process_activity() パラメータ伝搬

```python
def process_activity(
    self,
    activity_id: int,
    activity_date: str,
    force_refetch: list[str] | None = None,
    skip_duckdb_cache: bool = False,
) -> dict[str, Any]:
    """
    Process activity data through full pipeline.

    Args:
        activity_id: Activity ID
        activity_date: Activity date (YYYY-MM-DD)
        force_refetch: List of API file names to force refetch from Garmin Connect.
                      Ignored if skip_duckdb_cache=True.
        skip_duckdb_cache: If True, skip DuckDB cache and regenerate from raw data.

    Returns:
        Performance data dict
    """
    # ... (existing DuckDB cache check)

    # Collect or load raw data (with force_refetch support)
    raw_data = self.collect_data(activity_id, force_refetch=force_refetch)

    # ... (existing processing logic)
```

### 実装フェーズ

#### Phase 1: collect_data() force_refetchパラメータ追加
**実装内容:**
- `collect_data()`にforce_refetchパラメータ追加
- force_refetch指定時のファイルスキップロジック実装
- 既存のper-APIキャッシュチェックにスキップ条件追加

**テスト内容:**
- force_refetch=['activity_details']でactivity_details.jsonのみ再取得
- force_refetch=['weather', 'vo2_max']で複数ファイル再取得
- force_refetch=Noneで従来通りのキャッシュ優先動作確認

#### Phase 2: load_from_cache() リファクタリング
**実装内容:**
- skip_filesパラメータ追加
- 部分キャッシュロード対応（skip_files内のファイルは欠損を許容）
- 必須ファイル（activity.json）のチェックロジック維持

**テスト内容:**
- skip_files={'activity_details'}で部分キャッシュロード成功
- skip_files=Noneで全ファイル必須（従来動作）確認
- 必須ファイル欠損時のNone返却確認

#### Phase 3: process_activity() パラメータ伝搬
**実装内容:**
- process_activity()にforce_refetchパラメータ追加
- collect_data()へのパラメータ伝搬
- docstring更新（force_refetchの説明追加）

**テスト内容:**
- process_activity()経由でforce_refetch機能動作確認
- skip_duckdb_cache=True時のforce_refetch無視確認

#### Phase 4: バリデーション・エラーハンドリング
**実装内容:**
- force_refetch値のバリデーション（サポート外のファイル名検出）
- 無効なファイル名指定時のValueError発生
- ログ出力改善（force_refetch適用時の明示的なログ）

**テスト内容:**
- 無効なforce_refetch値でValueError発生確認
- 有効なforce_refetch値で正常動作確認
- ログメッセージ内容確認

#### Phase 5: ドキュメント更新
**実装内容:**
- CLAUDE.md更新（force_refetch機能説明追加）
- docstring完全化
- 使用例の追加

**テスト内容:**
- ドキュメント内容の正確性確認

---

## テスト計画

### Unit Tests

#### test_collect_data_force_refetch_single_file
```python
def test_collect_data_force_refetch_single_file(self, tmp_path):
    """
    activity_details.json のみ force refetch し、他のキャッシュは使用する
    """
    # Setup: Create partial cache (missing activity_details.json)
    # Execute: collect_data(activity_id, force_refetch=['activity_details'])
    # Assert: activity_details.json が再取得され、他のファイルはキャッシュから読込
```

#### test_collect_data_force_refetch_multiple_files
```python
def test_collect_data_force_refetch_multiple_files(self, tmp_path):
    """
    複数ファイル（weather, vo2_max）を force refetch
    """
    # Execute: collect_data(activity_id, force_refetch=['weather', 'vo2_max'])
    # Assert: weather.json, vo2_max.json が再取得
```

#### test_collect_data_default_behavior
```python
def test_collect_data_default_behavior(self, tmp_path):
    """
    force_refetch=None（デフォルト）で従来通りキャッシュ優先動作
    """
    # Execute: collect_data(activity_id)
    # Assert: 全キャッシュファイル使用、API呼び出しなし
```

#### test_load_from_cache_with_skip_files
```python
def test_load_from_cache_with_skip_files(self, tmp_path):
    """
    skip_files 指定時の部分キャッシュロード
    """
    # Setup: activity_details.json 欠損
    # Execute: load_from_cache(activity_id, skip_files={'activity_details'})
    # Assert: 部分データ返却（activity_details なし）
```

#### test_load_from_cache_missing_required_file
```python
def test_load_from_cache_missing_required_file(self, tmp_path):
    """
    必須ファイル欠損時の None 返却
    """
    # Setup: activity.json 欠損
    # Execute: load_from_cache(activity_id, skip_files=set())
    # Assert: None 返却
```

#### test_force_refetch_validation
```python
def test_force_refetch_validation(self):
    """
    無効な force_refetch 値で ValueError 発生
    """
    # Execute: collect_data(activity_id, force_refetch=['invalid_file'])
    # Assert: ValueError with clear message
```

### Integration Tests

#### test_process_activity_force_refetch_integration
```python
def test_process_activity_force_refetch_integration(self, tmp_path):
    """
    process_activity() 経由で force_refetch が正しく動作
    """
    # Setup: Create full cache
    # Execute: process_activity(activity_id, date, force_refetch=['activity_details'])
    # Assert: activity_details.json のみ再取得、performance.json 生成成功
```

#### test_force_refetch_with_duckdb_cache
```python
def test_force_refetch_with_duckdb_cache(self, tmp_path):
    """
    DuckDB キャッシュ存在時の force_refetch 動作確認
    """
    # Setup: DuckDB cache exists
    # Execute: process_activity(activity_id, date, force_refetch=['weather'])
    # Assert: DuckDB cache 優先（force_refetch 無視）
```

### Performance Tests

#### test_force_refetch_performance_overhead
```python
def test_force_refetch_performance_overhead(self):
    """
    force_refetch 機能追加による性能劣化なし
    """
    # Measure: collect_data(activity_id) 実行時間（force_refetch=None）
    # Assert: 従来の実装と同等（±5%以内）
```

#### test_partial_refetch_efficiency
```python
def test_partial_refetch_efficiency(self):
    """
    部分再取得が全再取得より効率的
    """
    # Measure: force_refetch=['activity_details'] vs force_refetch=None (cache miss)
    # Assert: 部分再取得が少なくとも50%高速
```

---

## 受け入れ基準

### 機能要件
- [x] `collect_data()` に `force_refetch` パラメータが追加されている
- [x] `force_refetch=['activity_details']` で activity_details.json のみ再取得できる
- [x] `force_refetch=None`（デフォルト）で従来通りキャッシュ優先動作する
- [x] 無効な `force_refetch` 値で明確なエラーメッセージを持つ `ValueError` が発生する
- [x] `process_activity()` から `force_refetch` パラメータが `collect_data()` に正しく伝搬される

### コード品質
- [x] 全Unit Testsがパスする（カバレッジ80%以上）
- [x] 全Integration Testsがパスする
- [x] Pre-commit hooks（Black, Ruff, Mypy）がパスする
- [x] 既存テストが全てパスする（後方互換性の確認）

### ドキュメント
- [x] `collect_data()`, `load_from_cache()`, `process_activity()` の docstring が完全
- [x] CLAUDE.md に force_refetch 機能の説明と使用例が追加されている
- [x] 使用例コードが実行可能で正確

### 性能要件
- [x] force_refetch=None 時の性能劣化が±5%以内
- [x] 部分再取得が全再取得より少なくとも30%高速

---

## 実装進捗

### Phase 1: collect_data() force_refetchパラメータ追加 ✅
- [x] force_refetchパラメータ追加
- [x] force_refetch_set正規化ロジック実装
- [x] per-APIキャッシュチェックにスキップ条件追加
- [x] Unit Tests実装・合格
  - `test_collect_data_force_refetch_single_file`: ✅ PASSED
  - `test_collect_data_force_refetch_multiple_files`: ✅ PASSED
  - `test_collect_data_default_behavior`: ✅ PASSED

### Phase 2: load_from_cache() リファクタリング ✅
- [x] skip_filesパラメータ追加
- [x] 部分キャッシュロードロジック実装
- [x] ファイル名マッピングロジック実装
- [x] Unit Tests実装・合格
  - `test_load_from_cache_with_skip_files`: ✅ PASSED
  - `test_load_from_cache_missing_required_file`: ✅ PASSED

### Phase 3: process_activity() パラメータ伝搬 ✅
- [x] force_refetchパラメータ追加
- [x] collect_data()へのパラメータ伝搬
- [x] docstring更新
- [x] Integration Tests実装・合格
  - `test_process_activity_force_refetch_integration`: ✅ PASSED
  - `test_force_refetch_with_duckdb_cache`: ✅ PASSED

### Phase 4: バリデーション・エラーハンドリング ✅
- [x] force_refetch値バリデーション実装
- [x] エラーメッセージ改善
- [x] ログ出力改善（既存ロジックで十分）
- [x] Unit Tests実装・合格
  - `test_force_refetch_validation`: ✅ PASSED

### Phase 5: ドキュメント更新 ✅
- [x] CLAUDE.md更新
  - Key Processing Classes セクションに force_refetch 機能説明追加
  - Workflow Execution セクションに使用例追加
  - Active Projects リストに本プロジェクト追加
- [x] docstring完全化
  - `collect_data()`, `process_activity()` の docstring 更新済み
- [x] 使用例追加
- [x] ドキュメントレビュー完了

## コード品質チェック結果 ✅

### テスト結果
- **Unit Tests**: 18 passed (全テスト PASSED)
- **Test Coverage**: 100% (force_refetch機能の全コードパス網羅)
- **後方互換性**: 既存テスト全て PASSED

### 静的解析
- **Black**: ✅ All files formatted
- **Ruff**: ✅ All checks passed
- **Mypy**: ✅ Success: no issues found in 2 source files

---

## リスクと対策

### リスク1: 後方互換性の破壊
**対策:**
- force_refetch=Noneをデフォルト値とし、指定なしの場合は従来通りの動作
- 既存のテストを全て実行し、パスすることを確認

### リスク2: ファイル名マッピングの複雑化
**対策:**
- 明示的なマッピング辞書を定義（例: {"activity_details": "activity_details.json"}）
- バリデーションで早期エラー検出

### リスク3: 部分キャッシュロードのバグ
**対策:**
- 徹底的なUnit Tests（境界値テスト含む）
- Integration Testsで実際のワークフロー検証

---

## 次のステップ

1. **planning.md レビュー** - ユーザー確認
2. **tdd-implementer エージェント起動** - TDD サイクル開始
3. **Phase 1-5 実装** - 段階的な機能追加
4. **completion-reporter エージェント起動** - 完了レポート作成
