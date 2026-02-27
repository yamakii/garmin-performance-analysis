# Development Process Agents Workflow

このドキュメントは、DEVELOPMENT_PROCESS.md の3フェーズ（Planning → Implementation → Completion Report）を支援する専門エージェントの使用方法を説明します。

## エージェント概要

3つの専門エージェントが開発プロセスの各フェーズを支援します：

1. **project-planner**: Phase 1（計画フェーズ）
2. **tdd-implementer**: Phase 2（実装フェーズ）
3. **completion-reporter**: Phase 3（完了レポートフェーズ）

---

## Phase 1: 計画フェーズ（project-planner）

### 役割
- プロジェクトディレクトリ作成
- planning.md 生成
- 要件定義・設計・テスト計画の構造化

### 使用方法

```bash
# Claude Code でエージェント呼び出し
Task: project-planner
prompt: "DuckDBにセクション分析結果を保存する機能を追加したい。プロジェクト名は 'duckdb_section_analysis' で計画を立ててください。"
```

### エージェントの動作

1. **プロジェクトディレクトリ作成**
   ```
   docs/project/2025-10-09_duckdb_section_analysis/
   ```

2. **planning.md 生成**
   - `docs/templates/planning.md` をベースに作成
   - プロジェクト固有情報で置換

3. **対話的な計画立案**
   - 要件定義のヒアリング
   - 設計提案
   - テストケース計画
   - 受け入れ基準定義

### 成果物

- `docs/project/{YYYY-MM-DD}_{project_name}/planning.md`

### 完了基準

- [ ] プロジェクトディレクトリが作成されている
- [ ] planning.md が完全に記述されている
- [ ] 要件定義が SMART（Specific, Measurable, Achievable, Relevant, Time-bound）
- [ ] テストケースが実装可能な粒度で記述されている
- [ ] 受け入れ基準が明確に定義されている

---

## Phase 2: 実装フェーズ（tdd-implementer）

### 役割
- TDD サイクル（Red → Green → Refactor）実行
- コード品質チェック
- Git コミット管理

### 使用方法

```bash
# Claude Code でエージェント呼び出し
Task: tdd-implementer
prompt: "docs/project/2025-10-09_duckdb_section_analysis/planning.md に基づいて、TDDサイクルで実装してください。"
```

### エージェントの動作

#### Step 1: Red（失敗するテストを書く）

1. planning.md からテストケース抽出
2. テストファイル作成 (`tests/database/test_section_analysis.py`)
3. テスト実行（失敗確認）

```bash
uv run pytest tests/database/test_section_analysis.py::test_insert -v
# FAILED ❌ が期待される結果
```

#### Step 2: Green（テストを通す最小限の実装）

1. 最小実装 (`tools/database/db_writer.py`)
2. テスト再実行（成功確認）

```bash
uv run pytest tests/database/test_section_analysis.py::test_insert -v
# PASSED ✅
```

#### Step 3: Refactor（リファクタリング）

1. コード改善
2. テスト再実行（維持確認）
3. コード品質チェック

```bash
# フォーマット
uv run black .

# Lint
uv run ruff check .

# 型チェック
uv run mypy .

# 全テスト実行
uv run pytest

# カバレッジ確認
uv run pytest --cov=tools --cov=servers --cov-report=term-missing
```

#### Step 4: Commit

Conventional Commits 形式でコミット:

```bash
git add .
git commit -m "feat(db): add section analysis insert/read methods

Implemented DuckDB integration for section analyses:
- insert_section_analysis() for storing agent results
- get_section_analysis() for report generation
- UNIQUE constraint on (activity_id, section_type)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### 成果物

- 実装済みコード（`tools/`, `servers/`）
- テストコード（`tests/`）
- Git コミット

### 完了基準

- [ ] 全テストケースが実装されている
- [ ] TDD サイクル（Red → Green → Refactor）が守られている
- [ ] コード品質チェックが全てパス（Black, Ruff, Mypy）
- [ ] カバレッジ 80% 以上
- [ ] Conventional Commits 形式でコミット済み
- [ ] Pre-commit hooks が全てパス

---

## Phase 3: 完了レポートフェーズ（completion-reporter）

### 役割
- completion_report.md 生成
- テスト結果集計
- カバレッジ確認
- コミット情報収集

### 使用方法

```bash
# Claude Code でエージェント呼び出し
Task: completion-reporter
prompt: "docs/project/2025-10-09_duckdb_section_analysis/ の完了レポートを作成してください。"
```

### エージェントの動作

#### Phase 1: 情報収集

1. **プロジェクト情報取得**
   - planning.md 読み込み
   - git log で関連コミット取得

2. **テスト実行・結果収集**
   ```bash
   uv run pytest tests/ -m unit -v
   uv run pytest tests/ -m integration -v
   uv run pytest tests/ -m performance -v
   uv run pytest --cov=tools --cov=servers --cov-report=term-missing
   ```

3. **コード品質チェック**
   ```bash
   uv run black . --check
   uv run ruff check .
   uv run mypy .
   ```

#### Phase 2: レポート生成

1. `docs/templates/completion_report.md` を読み込み
2. 収集した情報でテンプレート置換
3. `{PROJECT_DIR}/completion_report.md` に保存

#### Phase 3: 検証

1. planning.md の受け入れ基準と照合
2. 未達成項目の特定
3. 今後の課題として記載

### 成果物

- `docs/project/{YYYY-MM-DD}_{project_name}/completion_report.md`

### 完了基準

- [ ] completion_report.md が生成されている
- [ ] 全テスト結果が記載されている
- [ ] カバレッジレポートが含まれている
- [ ] コード品質チェック結果が記載されている
- [ ] コミット情報が記載されている
- [ ] 受け入れ基準との照合が完了している
- [ ] 今後の課題が明確に記述されている

---

## フルワークフロー例

### シナリオ: DuckDB Section Analysis 機能追加

#### Step 1: 計画フェーズ

```bash
Task: project-planner
prompt: "DuckDBにセクション分析結果を保存する機能を追加したい。プロジェクト名は 'duckdb_section_analysis' で計画を立ててください。"
```

**エージェントの出力:**
- ✅ `docs/project/2025-10-09_duckdb_section_analysis/` ディレクトリ作成
- ✅ `planning.md` 生成（要件定義、設計、テスト計画）

#### Step 2: 実装フェーズ

```bash
Task: tdd-implementer
prompt: "docs/project/2025-10-09_duckdb_section_analysis/planning.md に基づいて、TDDサイクルで実装してください。"
```

**エージェントの動作:**
1. ❌ テスト作成 → pytest 実行（失敗）
2. ✅ 実装 → pytest 実行（成功）
3. ♻️  リファクタリング → pytest 実行（成功維持）
4. 📝 コミット（Conventional Commits 形式）

**成果物:**
- `tools/database/db_writer.py`: insert_section_analysis()
- `tools/database/db_reader.py`: get_section_analysis()
- `tests/database/test_section_analysis.py`
- Git commits

#### Step 3: 完了レポートフェーズ

```bash
Task: completion-reporter
prompt: "docs/project/2025-10-09_duckdb_section_analysis/ の完了レポートを作成してください。"
```

**エージェントの動作:**
1. テスト結果収集（Unit: 8 passed, Integration: 12 passed, Coverage: 91%）
2. コード品質確認（Black ✅, Ruff ✅, Mypy ✅）
3. `completion_report.md` 生成

**成果物:**
- `docs/project/2025-10-09_duckdb_section_analysis/completion_report.md`

---

## エージェント間の連携

### ハンドオフ情報

各エージェントは次のフェーズに必要な情報を引き継ぎます：

#### project-planner → tdd-implementer
- planning.md パス
- プロジェクトディレクトリパス
- 実装優先順位

#### tdd-implementer → completion-reporter
- 実装済みファイルリスト
- テスト結果サマリー
- カバレッジレポート
- コミットハッシュ

### エージェント呼び出しのベストプラクティス

1. **フェーズを飛ばさない**
   - 必ず Phase 1 → Phase 2 → Phase 3 の順で実行

2. **planning.md を完成させてから実装開始**
   - 不完全な計画での実装は避ける

3. **TDD サイクルを守る**
   - Red → Green → Refactor を厳守

4. **完了レポートは必ず作成**
   - プロジェクトの成果を文書化

---

## トラブルシューティング

### エージェントが期待通りに動作しない場合

#### project-planner

**問題**: planning.md が不完全
**解決策**:
```bash
Task: project-planner
prompt: "planning.md の設計セクションが不足しています。DuckDBスキーマ設計を追加してください。"
```

#### tdd-implementer

**問題**: テストが失敗し続ける
**解決策**:
```bash
# 手動でテスト実行して原因特定
uv run pytest tests/database/test_section_analysis.py -vv --tb=long

# エージェントに修正依頼
Task: tdd-implementer
prompt: "test_insert が 'table not found' エラーで失敗しています。テーブル作成を追加してください。"
```

**問題**: Pre-commit hooks が失敗
**解決策**:
```bash
# 個別実行で原因特定
uv run black .
uv run ruff check --fix .
uv run mypy .

Task: tdd-implementer
prompt: "Ruff が F401（未使用import）エラーを出しています。修正してください。"
```

#### completion-reporter

**問題**: テスト結果が不完全
**解決策**:
```bash
Task: completion-reporter
prompt: "Performance tests の結果が欠けています。再実行して completion_report.md を更新してください。"
```

---

## まとめ

### 開発の3原則（再確認）

1. **計画なしに実装しない** - 必ず project-planner で設計とテスト計画を立てる
2. **テストなしにコミットしない** - tdd-implementer で TDD サイクルを守る
3. **完了レポートなしに完了しない** - completion-reporter で実装内容を文書化する

### 品質基準（再確認）

- テストカバレッジ: 最低80%以上
- Pre-commit hooks: 全てパス
- ドキュメント: 全API/関数にdocstring

### エージェント使用のメリット

- ✅ **一貫性**: DEVELOPMENT_PROCESS.md の標準プロセスを自動的に守る
- ✅ **品質**: TDD サイクル、コード品質チェックが自動実行
- ✅ **文書化**: 計画・実装・完了が全て記録される
- ✅ **効率**: 定型作業の自動化により実装に集中できる

これらのエージェントを活用することで、高品質で保守性の高いコードベースを維持できます。
