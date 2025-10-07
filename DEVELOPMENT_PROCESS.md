# Development Process

このドキュメントはGarmin Performance Analysis Systemの開発プロセスを定義します。

## 開発フロー概要

本プロジェクトは **Test-Driven Development (TDD)** をベースとした3段階の開発フローを採用しています：

```
1. 計画フェーズ（Planning）
   ↓
2. 実装フェーズ（Implementation with TDD）
   ↓
3. 完了レポートフェーズ（Completion Report）
```

---

## Phase 1: 計画フェーズ（Planning）

新機能開発やバグ修正を開始する前に、必ず計画を立てます。

### 1.1 要件定義

**成果物:**
- 実装する機能の明確な説明
- 解決する問題の特定
- ユースケースの記述

**例:**
```markdown
## 要件: DuckDB Section Analysis統合

### 目的
エージェント分析結果をDuckDBに保存し、レポート生成時に効率的に取得する。

### ユースケース
1. 5つのエージェント（efficiency, environment, phase, split, summary）が分析結果を生成
2. 各分析結果をDuckDB section_analysesテーブルに保存
3. report-generatorがDuckDBから全分析結果を取得
4. Jinja2テンプレートで最終レポートを生成
```

### 1.2 設計

**成果物:**
- アーキテクチャ設計
- データモデル設計
- API/インターフェース設計

**例:**
```markdown
## 設計: DuckDB Section Analysis Schema

### テーブル定義
CREATE TABLE section_analyses (
    id INTEGER PRIMARY KEY,
    activity_id BIGINT NOT NULL,
    activity_date DATE NOT NULL,
    section_type VARCHAR NOT NULL,  -- efficiency, environment, phase, split, summary
    analysis_data JSON NOT NULL,
    analyst VARCHAR,
    version VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (activity_id, section_type)
)

### 実装クラス
- GarminDBWriter.insert_section_analysis()
- GarminDBReader.get_section_analysis()
```

### 1.3 テスト計画

**成果物:**
- テストケースリスト
- テストデータ準備
- 受け入れ基準

**テストレベル:**
- **Unit Tests** (`pytest -m unit`): 個別関数・メソッドのテスト
- **Integration Tests** (`pytest -m integration`): DuckDB統合、MCP統合テスト
- **Performance Tests** (`pytest -m performance`): パフォーマンス検証

**例:**
```markdown
## テストケース: Section Analysis Insert/Read

### Unit Tests
- ✅ insert_section_analysis()が正しくJSONをINSERTする
- ✅ get_section_analysis()が正しくJSONをパースする
- ✅ UNIQUE制約違反時にエラーハンドリングする

### Integration Tests
- ✅ 5セクション分析を連続でINSERTできる
- ✅ activity_id + section_typeで一意に取得できる
- ✅ 存在しないactivity_idでNoneを返す

### Performance Tests
- ✅ 100件のINSERTが1秒以内に完了する
- ✅ 並列読み取り（5セクション同時）が0.5秒以内
```

---

## Phase 2: 実装フェーズ（TDD Implementation）

### 2.1 TDDサイクル

**Red → Green → Refactor** を繰り返します。

#### Step 1: Red（失敗するテストを書く）

```bash
# tests/database/test_section_analysis.py
def test_insert_section_analysis():
    writer = GarminDBWriter(":memory:")

    analysis_data = {
        "metadata": {"analyst": "efficiency-section-analyst", "version": "1.0"},
        "efficiency": "フォーム効率が優秀"
    }

    result = writer.insert_section_analysis(
        activity_id=20464005432,
        activity_date="2025-09-22",
        section_type="efficiency",
        analysis_data=analysis_data
    )

    assert result is True  # ❌ まだ実装されていないので失敗
```

実行:
```bash
uv run pytest tests/database/test_section_analysis.py::test_insert_section_analysis -v
# FAILED - AttributeError: 'GarminDBWriter' object has no attribute 'insert_section_analysis'
```

#### Step 2: Green（テストを通す最小限の実装）

```python
# tools/database/db_writer.py
def insert_section_analysis(
    self, activity_id: int, activity_date: str,
    section_type: str, analysis_data: dict
) -> bool:
    try:
        conn = duckdb.connect(str(self.db_path))

        metadata = analysis_data.get("metadata", {})
        analyst = metadata.get("analyst")
        version = metadata.get("version")

        conn.execute(
            """
            INSERT OR REPLACE INTO section_analyses
            (activity_id, activity_date, section_type, analysis_data, analyst, version)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [activity_id, activity_date, section_type,
             json.dumps(analysis_data), analyst, version]
        )

        conn.close()
        logger.info(f"Inserted {section_type} analysis for activity {activity_id}")
        return True
    except Exception as e:
        logger.error(f"Error inserting section analysis: {e}")
        return False
```

実行:
```bash
uv run pytest tests/database/test_section_analysis.py::test_insert_section_analysis -v
# PASSED ✅
```

#### Step 3: Refactor（リファクタリング）

- コードの重複を削除
- 可読性向上
- パフォーマンス最適化

**リファクタリング後もテストが通ることを確認:**
```bash
uv run pytest tests/database/ -v
# All tests PASSED ✅
```

### 2.2 コード品質チェック

実装後、必ず以下のツールでコード品質を確認します：

```bash
# 1. フォーマット
uv run black .

# 2. Lint
uv run ruff check .

# 3. 型チェック
uv run mypy .

# 4. 全テスト実行
uv run pytest

# 5. カバレッジ確認
uv run pytest --cov=tools --cov=servers --cov-report=term-missing
```

### 2.3 Pre-commit Hooks

コミット前に自動的にチェックが実行されます（`.pre-commit-config.yaml`）：

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-json
      - id: check-merge-conflict

  - repo: https://github.com/psf/black
    hooks:
      - id: black

  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff

  - repo: https://github.com/pre-commit/mirrors-mypy
    hooks:
      - id: mypy
```

**Pre-commit hooksをスキップする場合:**
```bash
SKIP=mypy git commit -m "fix: update main.py output"
```

### 2.4 コミットメッセージ規約

**Conventional Commits形式**を採用：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type:**
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント変更
- `style`: コードフォーマット（機能変更なし）
- `refactor`: リファクタリング
- `perf`: パフォーマンス改善
- `test`: テスト追加・修正
- `chore`: ビルド・ツール設定変更

**例:**
```bash
git commit -m "feat(db): add section analysis insert/read methods

Implemented DuckDB integration for section analyses:
- insert_section_analysis() for storing agent results
- get_section_analysis() for report generation
- UNIQUE constraint on (activity_id, section_type)

Closes #42

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 3: 完了レポートフェーズ（Completion Report）

実装完了後、以下の内容を含む完了レポートを作成します。

### 3.1 完了レポートテンプレート

```markdown
# 実装完了レポート: [機能名]

## 1. 実装概要

- **目的**: [何を解決したか]
- **影響範囲**: [変更されたファイル・モジュール]
- **実装期間**: [開始日 - 完了日]

## 2. 実装内容

### 2.1 新規追加ファイル
- `tools/database/db_writer.py`: Section analysis insert機能
- `tests/database/test_section_analysis.py`: Integration tests

### 2.2 変更ファイル
- `servers/garmin_db_server.py`: get_section_analysis MCP tool追加

### 2.3 主要な実装ポイント
1. DuckDB section_analysesテーブル作成
2. JSON形式でanalysis_dataを保存
3. UNIQUE制約で重複防止

## 3. テスト結果

### 3.1 Unit Tests
```
pytest tests/database/test_section_analysis.py -m unit -v
========================== 8 passed in 0.42s ==========================
```

### 3.2 Integration Tests
```
pytest tests/database/test_section_analysis.py -m integration -v
========================== 12 passed in 2.15s ==========================
```

### 3.3 Performance Tests
```
pytest tests/database/test_section_analysis.py -m performance -v
========================== 3 passed in 5.03s ==========================

Performance Results:
- 100 inserts: 0.85s (117 ops/sec) ✅
- 5 parallel reads: 0.32s ✅
```

### 3.4 カバレッジ
```
tools/database/db_writer.py    95%
tools/database/db_reader.py    92%
servers/garmin_db_server.py    88%
------------------------------------------
TOTAL                          91%
```

## 4. コード品質

- ✅ Black: Passed
- ✅ Ruff: Passed
- ✅ Mypy: Passed
- ✅ Pre-commit hooks: All passed

## 5. ドキュメント更新

- ✅ CLAUDE.md: MCP tools使用例追加
- ✅ README.md: データベーススキーマ更新
- ✅ Docstrings: 全関数に追加

## 6. 今後の課題

- [ ] Section analysesのバージョン管理機能
- [ ] 古い分析データの自動削除（retention policy）
- [ ] 分析結果の差分検出機能

## 7. リファレンス

- Commit: `abc1234`
- PR: #42 (if applicable)
- Related Issues: #38, #40
```

### 3.2 完了レポート保存場所

```
docs/
└── completion_reports/
    ├── 2025-09-30_duckdb_section_analysis.md
    ├── 2025-10-02_report_generator_jinja2.md
    └── ...
```

---

## 開発環境セットアップ

### 初回セットアップ

```bash
# 1. 依存関係インストール
uv sync --extra dev

# 2. Pre-commit hooks設定
uv run pre-commit install

# 3. テスト実行確認
uv run pytest

# 4. DuckDB初期化
mkdir -p data/database
```

### 日常的な開発フロー

```bash
# 1. ブランチ作成（必要に応じて）
git checkout -b feat/new-feature

# 2. テスト作成（TDD Red）
vim tests/test_new_feature.py
uv run pytest tests/test_new_feature.py  # ❌ Failed

# 3. 実装（TDD Green）
vim tools/new_feature.py
uv run pytest tests/test_new_feature.py  # ✅ Passed

# 4. リファクタリング（TDD Refactor）
uv run pytest  # ✅ All Passed

# 5. コミット
git add .
git commit -m "feat: implement new feature"  # Pre-commit hooks自動実行

# 6. 完了レポート作成
vim docs/completion_reports/YYYY-MM-DD_new_feature.md
```

---

## トラブルシューティング

### Pre-commit hooksが失敗する場合

```bash
# 個別に実行して確認
uv run black .
uv run ruff check --fix .
uv run mypy .

# 修正後に再コミット
git add .
git commit -m "style: fix linting errors"
```

### テストが失敗する場合

```bash
# 詳細ログ表示
uv run pytest -vv --tb=long

# 特定のテストのみ実行
uv run pytest tests/path/to/test.py::test_function_name -v

# デバッグモード
uv run pytest --pdb
```

### DuckDBエラーが発生する場合

```bash
# データベース再作成
rm data/database/garmin_performance.duckdb
uv run python tools/database/db_writer.py  # 再初期化
```

---

## まとめ

**開発の3原則:**
1. **計画なしに実装しない** - 必ず設計とテスト計画を立てる
2. **テストなしにコミットしない** - TDDサイクルを守る
3. **完了レポートなしに完了しない** - 実装内容を文書化する

**品質基準:**
- テストカバレッジ: 最低80%以上
- Pre-commit hooks: 全てパス
- ドキュメント: 全API/関数にdocstring

この開発プロセスに従うことで、高品質で保守性の高いコードベースを維持します。
