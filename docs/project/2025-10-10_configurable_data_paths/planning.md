# 計画: Configurable Data Paths

## Git Worktree情報
- **Worktree Path**: `../garmin-configurable_data_paths/`
- **Branch**: `feature/configurable_data_paths`
- **Base Branch**: `main`

## 要件定義

### 目的
GitHubに安全にコードを公開できるよう、個人の健康データや走行ルートを含むディレクトリ（`data/`, `result/`）をプロジェクト外に配置可能にする。

### 解決する問題
**現在の問題:**
1. `data/` と `result/` はプロジェクトルート直下に配置されている
2. `.gitignore` で除外しているが、誤ってコミット・公開されるリスクがある
3. データディレクトリのパスを変更するには、コードを複数箇所修正する必要がある
4. プライバシー保護のため、データを完全にプロジェクト外に配置したいニーズがある

**リスクシナリオ:**
- `.gitignore` の設定ミス → データが公開される
- リポジトリフォーク時にデータが含まれる
- ログファイルにデータパスが記録され、個人情報が推測される

**解決策:**
- 環境変数でデータディレクトリのパスを設定可能にする
- デフォルトでは既存の動作を維持（後方互換性）
- シンプルな実装（環境変数2つのみ）

### ユースケース

1. **GitHub公開ユーザー**
   - データを `~/garmin_data/` に配置
   - レポジトリには一切のデータファイルを含めない
   - 環境変数で分離されたデータパスを設定

2. **ローカル開発者**
   - デフォルトパス（`./data`, `./result`）を使用
   - 環境変数を設定せずに従来通り動作

3. **複数プロジェクトユーザー**
   - 複数のworktreeで異なるデータセットを使用
   - worktreeごとに異なる `.env` で別々のデータディレクトリを指定

---

## 設計

### アーキテクチャ

**環境変数設計:**
- `GARMIN_DATA_DIR`: データディレクトリのベースパス（default: `./data`）
- `GARMIN_RESULT_DIR`: 結果ディレクトリのパス（default: `./result`）

**パス解決ロジック:**
```python
from pathlib import Path
import os

def get_data_base_dir() -> Path:
    """Get the base data directory from environment or default."""
    env_path = os.getenv("GARMIN_DATA_DIR")
    if env_path:
        return Path(env_path).resolve()
    # Default: project_root/data
    return Path(__file__).parent.parent.parent / "data"

def get_result_dir() -> Path:
    """Get the result directory from environment or default."""
    env_path = os.getenv("GARMIN_RESULT_DIR")
    if env_path:
        return Path(env_path).resolve()
    # Default: project_root/result
    return Path(__file__).parent.parent.parent / "result"
```

**影響を受けるコンポーネント:**
1. **GarminIngestWorker** (`tools/ingest/garmin_worker.py`)
   - `self.raw_dir` → `get_data_base_dir() / "raw"`
   - `self.performance_dir` → `get_data_base_dir() / "performance"`
   - `self.precheck_dir` → `get_data_base_dir() / "precheck"`
   - `self.weight_raw_dir` → `get_data_base_dir() / "raw" / "weight"`

2. **ReportGeneratorWorker** (`tools/reporting/report_generator_worker.py`)
   - `result_dir` → `get_result_dir()`

3. **Database paths** (`tools/database/db_reader.py`, `db_writer.py`)
   - `db_path` → `get_data_base_dir() / "database" / "garmin.db"`

4. **Migration/Bulk scripts**
   - `tools/migrate_raw_data_structure.py`
   - `tools/migrate_weight_data.py`
   - `tools/bulk_fetch_activity_details.py`
   - `tools/scripts/reingest_duckdb_data.py`

### データモデル

**ディレクトリ構造（デフォルト）:**
```
project_root/
├── data/                    # GARMIN_DATA_DIR (default)
│   ├── raw/
│   ├── performance/
│   ├── precheck/
│   └── database/
└── result/                  # GARMIN_RESULT_DIR (default)
    ├── individual/
    ├── monthly/
    └── special/
```

**ディレクトリ構造（カスタム）:**
```
/home/user/garmin_data/      # GARMIN_DATA_DIR=/home/user/garmin_data
├── raw/
├── performance/
├── precheck/
└── database/

/home/user/garmin_results/   # GARMIN_RESULT_DIR=/home/user/garmin_results
├── individual/
├── monthly/
└── special/
```

### API/インターフェース設計

**新規ファイル: `tools/utils/paths.py`**
```python
"""Path configuration utilities for Garmin Performance Analysis.

This module provides centralized path configuration that can be
customized via environment variables for privacy and data separation.
"""

from pathlib import Path
import os


def get_data_base_dir() -> Path:
    """Get the base data directory from environment or default.

    Returns:
        Path: Base data directory (default: project_root/data)

    Environment:
        GARMIN_DATA_DIR: Override default data directory path
    """
    env_path = os.getenv("GARMIN_DATA_DIR")
    if env_path:
        return Path(env_path).resolve()
    # Default: project_root/data
    project_root = Path(__file__).parent.parent.parent
    return project_root / "data"


def get_result_dir() -> Path:
    """Get the result directory from environment or default.

    Returns:
        Path: Result directory (default: project_root/result)

    Environment:
        GARMIN_RESULT_DIR: Override default result directory path
    """
    env_path = os.getenv("GARMIN_RESULT_DIR")
    if env_path:
        return Path(env_path).resolve()
    # Default: project_root/result
    project_root = Path(__file__).parent.parent.parent
    return project_root / "result"


def get_raw_dir() -> Path:
    """Get the raw data directory."""
    return get_data_base_dir() / "raw"


def get_performance_dir() -> Path:
    """Get the performance data directory."""
    return get_data_base_dir() / "performance"


def get_precheck_dir() -> Path:
    """Get the precheck data directory."""
    return get_data_base_dir() / "precheck"


def get_database_dir() -> Path:
    """Get the database directory."""
    return get_data_base_dir() / "database"


def get_weight_raw_dir() -> Path:
    """Get the weight raw data directory."""
    return get_data_base_dir() / "raw" / "weight"
```

**新規ファイル: `.env.example`**
```bash
# Garmin Performance Analysis - Environment Configuration
#
# Data Directory Configuration
# -----------------------------
# Override the default data directory location for privacy and data separation.
# Useful when publishing code to GitHub to keep personal health data separate.
#
# Default: ./data (relative to project root)
# Example: /home/user/garmin_data (absolute path recommended)
#
# GARMIN_DATA_DIR=/home/user/garmin_data

# Result Directory Configuration
# ------------------------------
# Override the default result directory location for analysis reports.
#
# Default: ./result (relative to project root)
# Example: /home/user/garmin_results (absolute path recommended)
#
# GARMIN_RESULT_DIR=/home/user/garmin_results

# Usage
# -----
# 1. Copy this file to .env:
#    cp .env.example .env
#
# 2. Uncomment and set your custom paths in .env
#
# 3. .env is automatically loaded by python-dotenv (already in dependencies)
#
# Note: .env is gitignored to prevent accidental commits of personal paths
```

**修正対象ファイル:**

1. **`tools/ingest/garmin_worker.py`**
   ```python
   from tools.utils.paths import (
       get_raw_dir,
       get_performance_dir,
       get_precheck_dir,
       get_weight_raw_dir,
   )

   def __init__(self, db_path: str | None = None):
       self.project_root = Path(__file__).parent.parent.parent
       self.raw_dir = get_raw_dir()
       self.performance_dir = get_performance_dir()
       self.precheck_dir = get_precheck_dir()
       self.weight_raw_dir = get_weight_raw_dir()
       # ... rest of init
   ```

2. **`tools/reporting/report_generator_worker.py`**
   ```python
   from tools.utils.paths import get_result_dir

   def generate_report(self, ...):
       result_dir = get_result_dir()
       # ... rest of method
   ```

3. **`tools/database/db_reader.py`, `db_writer.py`**
   ```python
   from tools.utils.paths import get_database_dir

   def __init__(self, db_path: str | None = None):
       if db_path is None:
           db_path = str(get_database_dir() / "garmin.db")
       # ... rest of init
   ```

4. **Migration/Bulk scripts**
   - Update default path arguments to use `get_*_dir()` functions

---

## 実装フェーズ

### Phase 1: パスユーティリティモジュール作成
**実装内容:**
- `tools/utils/paths.py` を作成
- `get_data_base_dir()`, `get_result_dir()` 関数実装
- ヘルパー関数（`get_raw_dir()`, `get_performance_dir()`, etc.）実装
- `.env.example` を作成

**テスト内容:**
- `test_get_data_base_dir_default()`: 環境変数未設定時にデフォルトパスを返す
- `test_get_data_base_dir_custom()`: 環境変数設定時にカスタムパスを返す
- `test_get_result_dir_default()`: 環境変数未設定時にデフォルトパスを返す
- `test_get_result_dir_custom()`: 環境変数設定時にカスタムパスを返す
- `test_helper_functions()`: ヘルパー関数が正しいサブディレクトリを返す

### Phase 2: GarminIngestWorker修正
**実装内容:**
- `GarminIngestWorker.__init__()` を修正
- ハードコードされたパスを `get_*_dir()` 呼び出しに置き換え

**テスト内容:**
- `test_garmin_worker_default_paths()`: デフォルトパスで動作確認
- `test_garmin_worker_custom_paths()`: カスタムパスで動作確認
- `test_garmin_worker_backward_compatibility()`: 既存データが読み込める

### Phase 3: ReportGeneratorWorker修正
**実装内容:**
- `ReportGeneratorWorker` のresult_dir参照を `get_result_dir()` に置き換え

**テスト内容:**
- `test_report_generator_default_path()`: デフォルトパスで動作確認
- `test_report_generator_custom_path()`: カスタムパスで動作確認

### Phase 4: Database修正
**実装内容:**
- `GarminDBReader`, `GarminDBWriter` のdb_pathデフォルト値を `get_database_dir()` に変更

**テスト内容:**
- `test_db_reader_default_path()`: デフォルトパスで動作確認
- `test_db_reader_custom_path()`: カスタムパスで動作確認

### Phase 5: Migration/Bulk scripts修正
**実装内容:**
- `tools/migrate_raw_data_structure.py`
- `tools/migrate_weight_data.py`
- `tools/bulk_fetch_activity_details.py`
- `tools/scripts/reingest_duckdb_data.py`
- 各スクリプトのデフォルトパス引数を `get_*_dir()` に置き換え

**テスト内容:**
- `test_migration_scripts_default_paths()`: デフォルトパスで動作確認
- `test_migration_scripts_custom_paths()`: カスタムパスで動作確認

### Phase 6: ドキュメント更新
**実装内容:**
- `CLAUDE.md` にデータパス設定方法を追加
- `.env.example` の使い方を記載
- プライバシー保護のベストプラクティスを追加

**テスト内容:**
- ドキュメントのレビュー

---

## テスト計画

### Unit Tests

**`tests/utils/test_paths.py`:**
- [ ] `test_get_data_base_dir_default()`: デフォルトパスが `project_root/data`
- [ ] `test_get_data_base_dir_custom()`: `GARMIN_DATA_DIR` 環境変数が反映される
- [ ] `test_get_data_base_dir_absolute()`: 絶対パスが正しく解決される
- [ ] `test_get_result_dir_default()`: デフォルトパスが `project_root/result`
- [ ] `test_get_result_dir_custom()`: `GARMIN_RESULT_DIR` 環境変数が反映される
- [ ] `test_get_raw_dir()`: `get_data_base_dir()/raw` を返す
- [ ] `test_get_performance_dir()`: `get_data_base_dir()/performance` を返す
- [ ] `test_get_precheck_dir()`: `get_data_base_dir()/precheck` を返す
- [ ] `test_get_database_dir()`: `get_data_base_dir()/database` を返す
- [ ] `test_get_weight_raw_dir()`: `get_data_base_dir()/raw/weight` を返す

### Integration Tests

**`tests/integration/test_configurable_paths.py`:**
- [ ] `test_garmin_worker_with_custom_data_dir()`: カスタムデータディレクトリでworkerが動作
- [ ] `test_report_generator_with_custom_result_dir()`: カスタム結果ディレクトリでレポート生成
- [ ] `test_database_with_custom_db_path()`: カスタムDBパスでデータベース操作
- [ ] `test_end_to_end_with_custom_paths()`: データ収集→処理→レポート生成が全てカスタムパスで動作

### Backward Compatibility Tests

**`tests/integration/test_backward_compatibility_paths.py`:**
- [ ] `test_default_paths_unchanged()`: 環境変数未設定時に既存のパスが使われる
- [ ] `test_existing_data_accessible()`: 既存のデータファイルが読み込める
- [ ] `test_migration_scripts_default_behavior()`: Migration scriptsがデフォルトパスで動作

---

## 受け入れ基準

- [ ] `tools/utils/paths.py` が作成され、環境変数からパスを取得する関数が実装されている
- [ ] `.env.example` が作成され、設定方法が明記されている
- [ ] `GarminIngestWorker` がパスユーティリティを使用している
- [ ] `ReportGeneratorWorker` がパスユーティリティを使用している
- [ ] Database readers/writers がパスユーティリティを使用している
- [ ] Migration/Bulk scripts がパスユーティリティを使用している
- [ ] 環境変数未設定時にデフォルトパス（`./data`, `./result`）が使用される（後方互換性）
- [ ] 環境変数設定時にカスタムパスが使用される
- [ ] 全テストがパスする（Unit, Integration, Backward Compatibility）
- [ ] カバレッジ80%以上
- [ ] Pre-commit hooksがパスする（Black, Ruff, Mypy）
- [ ] ドキュメント（CLAUDE.md）が更新されている
- [ ] `.gitignore` に `.env` が追加されている（既に追加済みか確認）

---

## セキュリティ考慮事項

### プライバシー保護
1. **`.env` をgitignoreに追加**
   - ユーザー固有のパスが誤ってコミットされないようにする
   - `.env.example` のみをリポジトリに含める

2. **絶対パス推奨**
   - `.env.example` で絶対パスの使用を推奨
   - プロジェクト外にデータを配置することでGit操作からデータを完全分離

3. **ドキュメント記載**
   - CLAUDE.md にプライバシー保護のベストプラクティスを記載
   - GitHub公開時の推奨設定を明記

### データ分離のベストプラクティス
```bash
# Recommended setup for GitHub users
GARMIN_DATA_DIR=/home/user/private/garmin_data
GARMIN_RESULT_DIR=/home/user/private/garmin_results
```

---

## 次のステップ

1. **tdd-implementer agent呼び出し**:
   ```bash
   Task: tdd-implementer
   prompt: "docs/project/2025-10-10_configurable_data_paths/planning.md に基づいて、TDDサイクルで実装してください。"
   ```

2. **実装完了後**: completion-reporter agentで完了レポート作成
3. **マージ**: Feature branchをmainにマージ
4. **クリーンアップ**: Git worktreeを削除

---

## 実装上の注意事項

### python-dotenv の活用
- すでに `pyproject.toml` に `python-dotenv` が依存関係に含まれている
- アプリケーション起動時に `.env` を自動ロードする必要がある場合、エントリーポイントで `load_dotenv()` を呼び出す
- ただし、`os.getenv()` は `.env` がロードされていなくてもシステム環境変数を読み取るため、明示的なロードは必須ではない

### パス解決の一貫性
- すべてのパスは `Path.resolve()` で絶対パスに変換する
- シンボリックリンクやrelativeパスによる曖昧さを排除

### ディレクトリ自動作成
- `get_*_dir()` 関数内ではディレクトリを作成しない（副作用を避ける）
- 各コンポーネント（GarminIngestWorker等）の初期化時に必要なディレクトリを作成

### エラーハンドリング
- カスタムパスが無効な場合（書き込み権限がない等）は明確なエラーメッセージを表示
- ただし、Phase 1では基本的なパス取得のみを実装し、詳細なバリデーションは将来のフェーズで検討
