# 計画: Remove Backward Compatibility Code (DuckDB-First Architecture Cleanup)

## プロジェクト情報
- **プロジェクト名**: `remove_backward_compatibility`
- **作成日**: `2025-10-16`
- **ステータス**: 計画中
- **GitHub Issue**: TBD (create after planning approval)

## 要件定義

### 目的
Project #24 (remove_performance_json) で実装されたDual-mode (legacy + raw data) の後方互換性コードを完全削除し、Raw data → DuckDB 単一パイプラインに統一する。コードベースの簡略化、保守性向上、~200-300行のコード削減を実現する。

### 解決する問題

**現状の課題:**
1. **コードの二重管理**: 全8 insertersがdual-modeをサポート（`performance_file` パラメータ有無で分岐）
2. **不要な複雑性**: performance.json生成は削除されたが、読み込みコードは残存
3. **保守負担**: legacy code pathのテスト・メンテナンスコスト
4. **死んだコード**: `create_parquet_dataset()` は呼び出されないが、codebaseに残存
5. **混乱の原因**: precheck.json生成が `create_parquet_dataset()` に依存（実行されない）

**根本原因:**
- Project #24 の段階的移行戦略: Dual-mode実装で安全性を確保したが、cleanup未完了
- Backward compatibility の過剰保守: performance.json生成削除後もlegacy読み込みパスを維持
- precheck.json の役割不明: 現在は保存されるが、validation用途が不明確

### ユースケース

1. **単一コードパスでの開発**
   - Inserter実装時にraw data mode のみ考慮
   - Legacy mode の分岐削除による可読性向上
   - 新規開発者のオンボーディング容易化

2. **簡略化されたテスト**
   - Raw dataベースのテストのみ維持
   - Backward compatibility tests 削除
   - テスト実行時間短縮

3. **明確なvalidation戦略**
   - precheck.json の廃止 or DuckDBベース再設計
   - Validation logicの一元化

---

## 設計

### アーキテクチャ変更

#### Before (Current - Project #24 完了後):
```
Raw Data (API) → DuckDB → Analysis
                    ↑
            (Dual-mode inserters)
            ├─ Raw data mode (active)
            └─ Legacy mode (dead code, performance.json読み込み)

create_parquet_dataset() → [NOT CALLED] → precheck.json生成に依存
precheck.json → 保存されるが用途不明
```

**Issues:**
- 全insertersが2つのcode pathを持つ（raw + legacy）
- `performance_file` parameter は常に `None` で呼び出される
- `create_parquet_dataset()` は呼び出されないが存在
- precheck.json は生成されるが、`create_parquet_dataset()` が呼ばれないため不完全

#### After (Target):
```
Raw Data (API) → DuckDB → Analysis
                    ↑
            (Single-mode inserters)
            └─ Raw data mode only

Validation:
  Option A: DuckDB-based validation (推奨)
  Option B: precheck.json削除（validation削除）
```

**Improvements:**
- Single code path per inserter
- `performance_file` parameter 完全削除
- `create_parquet_dataset()` 完全削除
- Validation戦略の明確化

### 影響分析

#### 削除対象ファイル

1. **tests/ingest/test_backward_compatibility.py** (完全削除)
   - Backward compatibility tests (3 test methods)
   - `create_parquet_dataset()` を使用

#### 変更が必要なファイル

**Core Processing:**
2. `tools/ingest/garmin_worker.py` (Lines 681-746, 1755-1760)
   - `create_parquet_dataset()` メソッド削除
   - precheck.json生成ロジック削除 or 再設計
   - Lines 1758: `df = self.create_parquet_dataset(raw_data)` 削除済み (already done in #24)

**Database Inserters (8 files):**
3. `tools/database/inserters/activities.py`
   - `performance_file` parameter削除
   - Legacy mode code path削除 (Lines 57-80 の `if performance_file:` 分岐)
4. `tools/database/inserters/vo2_max.py`
   - 同上
5. `tools/database/inserters/lactate_threshold.py`
   - 同上
6. `tools/database/inserters/heart_rate_zones.py`
   - 同上
7. `tools/database/inserters/hr_efficiency.py`
   - 同上
8. `tools/database/inserters/form_efficiency.py`
   - 同上
9. `tools/database/inserters/splits.py`
   - 同上
10. `tools/database/inserters/performance_trends.py`
    - 同上

**Tests (2 files + backward compatibility):**
11. `tests/ingest/test_garmin_worker.py`
    - `test_create_parquet_dataset()` 削除 (Lines 184-192)
    - Lines 216-220: `create_parquet_dataset()` 呼び出し削除
    - Lines 262, 872: `mock_parquet` 関連削除
12. `tests/ingest/test_garmin_worker_time_series.py`
    - precheck関連の確認削除 (if any)
13. **tests/ingest/test_backward_compatibility.py** (完全削除)

**Documentation:**
14. `CLAUDE.md`
    - Line 267: "create_parquet_dataset()" 言及削除
    - Dual-mode言及削除
    - Architecture説明簡略化

#### 影響を受けるコンポーネント

**Direct Impact (要修正):**
- 8 inserters: signature変更、legacy code削除
- 3 test files: test method削除、mock削除
- GarminIngestWorker: create_parquet_dataset() 削除、precheck再設計

**Indirect Impact (確認のみ):**
- MCP Server: 変更なし (DuckDB経由でデータ取得)
- Analysis agents: 変更なし (DuckDB経由)
- Report generation: 変更なし (DuckDB経由)

### データモデル

#### precheck.json Analysis

**Current Implementation (Lines 1229-1242):**
```python
precheck_data = {
    "activity_id": activity_id,
    "total_splits": len(df),  # ← df は create_parquet_dataset() の戻り値
    "has_hr_data": bool(df["avg_heart_rate"].notna().all()),
    "has_power_data": bool(df["avg_power"].notna().all()),
    "has_form_data": bool(df["ground_contact_time_ms"].notna().all()),
}
```

**Problem:**
- `df` は `create_parquet_dataset()` の戻り値
- #24 で `create_parquet_dataset()` 呼び出しが削除されたため、`df` が存在しない
- precheck.json生成が実質的に壊れている

**Options:**

**Option A: DuckDB-based Validation (推奨)**
```python
# Query DuckDB after insertion
precheck_data = {
    "activity_id": activity_id,
    "total_splits": conn.execute(
        "SELECT COUNT(*) FROM splits WHERE activity_id = ?", [activity_id]
    ).fetchone()[0],
    "has_hr_data": conn.execute(
        "SELECT COUNT(*) FROM splits WHERE activity_id = ? AND avg_hr IS NOT NULL", [activity_id]
    ).fetchone()[0] > 0,
    "has_power_data": conn.execute(
        "SELECT COUNT(*) FROM splits WHERE activity_id = ? AND avg_power IS NOT NULL", [activity_id]
    ).fetchone()[0] > 0,
    "has_form_data": conn.execute(
        "SELECT COUNT(*) FROM form_efficiency WHERE activity_id = ?", [activity_id]
    ).fetchone()[0] > 0,
}
```

**Pros:**
- Single source of truth (DuckDB)
- Validation正確性向上（実際に挿入されたデータを確認）
- precheck.json保持（既存の利用コードがあれば動作継続）

**Cons:**
- DuckDBクエリオーバーヘッド（軽微）
- コード量増加（validation queries追加）

**Option B: Remove precheck.json (最もシンプル)**
```python
# Delete Lines 1229-1242 entirely
# No precheck.json generation
```

**Pros:**
- 最もシンプル（コード削減）
- validation重複削除（DuckDBが唯一の真実）

**Cons:**
- precheck.json利用コードが壊れる（要調査）
- Validation機能の喪失（リスク不明）

**Decision Required:** precheck.jsonの現在の利用状況を調査して決定

### API/インターフェース設計

#### Inserters - Before (Current):

```python
def insert_activity(
    performance_file: str | None,  # Dual-mode parameter
    activity_id: int,
    date: str,
    raw_activity_details_file: str | None = None,
    raw_weather_file: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> bool:
    """Insert activity with dual-mode support."""

    use_raw_data = performance_file is None

    if use_raw_data:
        # Raw data mode (active)
        raw_data = load_from_raw_files()
    else:
        # Legacy mode (dead code)
        raw_data = load_from_performance_json(performance_file)

    # ... insertion logic
```

#### Inserters - After (Target):

```python
def insert_activity(
    activity_id: int,
    date: str,
    raw_activity_details_file: str | None = None,
    raw_weather_file: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> bool:
    """Insert activity from raw data files."""

    # Single code path - raw data only
    raw_data = load_from_raw_files()

    # ... insertion logic
```

**Key Changes:**
1. `performance_file` parameter削除
2. Legacy mode code削除 (`if performance_file:` 分岐削除)
3. `use_raw_data` フラグ削除（常にTrue）
4. Docstring更新（dual-mode言及削除）

#### GarminIngestWorker - Before (Current):

```python
class GarminIngestWorker:
    def create_parquet_dataset(self, raw_data: dict) -> pd.DataFrame:
        """Create DataFrame from lapDTOs (NOT CALLED)."""
        # 65 lines of code
        pass

    def process_activity(self, activity_id: int, date: str):
        # ... fetch raw data

        # precheck.json generation (BROKEN - df not defined)
        df = ???  # create_parquet_dataset() not called
        precheck_data = {
            "total_splits": len(df),  # ← BROKEN
            # ...
        }
```

#### GarminIngestWorker - After (Target):

```python
class GarminIngestWorker:
    # create_parquet_dataset() DELETED

    def process_activity(self, activity_id: int, date: str):
        # ... fetch raw data
        # ... insert to DuckDB

        # Option A: DuckDB-based precheck
        precheck_data = self._validate_from_duckdb(activity_id)

        # Option B: No precheck
        # (delete precheck generation entirely)
```

---

## 実装フェーズ

### Phase 1: Investigation & Decision (~2 hours)
**Goal:** precheck.json利用状況を調査し、削除 or 再設計を決定

**Tasks:**
1. **precheck.json利用箇所調査** (~1 hour)
   - Grep search: "precheck" in entire codebase
   - Identify all read locations (file load, JSON parse)
   - Identify all dependencies (MCP tools, analysis agents, report generation)
   - Document findings

2. **Validation戦略決定** (~0.5 hour)
   - Option A: DuckDB-based validation (if precheck.json is used)
   - Option B: Remove precheck.json (if unused)
   - Document decision rationale

3. **Implementation plan finalization** (~0.5 hour)
   - Update planning.md with decision
   - Define detailed test plan
   - Identify edge cases

**Acceptance Criteria:**
- precheck.json利用状況が完全に把握されている
- Validation戦略が決定されている
- Implementation planが詳細化されている

**Related Files:**
- All files mentioning "precheck"
- `tools/planner/workflow_planner.py` (Line 76)
- `.claude/commands/analyze-activity.md` (Line 31)

### Phase 2: Remove create_parquet_dataset() (~1 hour)
**Goal:** `create_parquet_dataset()` メソッドと関連テストを完全削除

**Tasks:**
1. **GarminIngestWorker refactoring** (~0.5 hour)
   - Delete `create_parquet_dataset()` method (Lines 681-746)
   - Update docstrings
   - Remove unused imports (if any)

2. **Test cleanup** (~0.5 hour)
   - Delete `test_create_parquet_dataset()` (test_garmin_worker.py Lines 184-192)
   - Delete Lines 216-220 (create_parquet_dataset call)
   - Remove mock_parquet (Lines 262, 872)
   - Delete `tests/ingest/test_backward_compatibility.py` entirely

**Acceptance Criteria:**
- `create_parquet_dataset()` メソッドが存在しない
- 関連テストが削除されている
- 全既存テストが合格（backward compatibility tests除く）

**Related Files:**
- `tools/ingest/garmin_worker.py`
- `tests/ingest/test_garmin_worker.py`
- `tests/ingest/test_backward_compatibility.py` (DELETE)

### Phase 3: Implement precheck Strategy (~2 hours)
**Goal:** Phase 1の決定に基づき、precheck.json生成を再設計 or 削除

**Scenario A: DuckDB-based Validation** (~2 hours if selected)
1. **Validation helper実装** (~1 hour)
   - `_validate_from_duckdb(activity_id, conn)` メソッド実装
   - DuckDBクエリでhas_hr_data等を取得
   - Unit test作成

2. **GarminIngestWorker統合** (~0.5 hour)
   - `process_activity()` でvalidation helper呼び出し
   - precheck.json保存
   - Integration test更新

3. **Error handling** (~0.5 hour)
   - DuckDB query失敗時の処理
   - Empty result処理
   - Test coverage

**Scenario B: Remove precheck.json** (~1 hour if selected)
1. **Deletion** (~0.5 hour)
   - Delete Lines 1229-1242 (precheck generation)
   - Remove precheck imports
   - Update docstrings

2. **Dependent code update** (~0.5 hour)
   - Update/delete precheck読み込みコード (if any)
   - Update workflow_planner.py (Line 76)
   - Update .claude/commands/analyze-activity.md (Line 31)

**Acceptance Criteria:**
- precheck戦略が実装されている（DuckDB-based or 削除）
- 全関連テストが合格
- precheck.json生成が正常動作 or 完全削除

**Related Files:**
- `tools/ingest/garmin_worker.py` (Lines 1229-1242)
- `tools/planner/workflow_planner.py`
- `.claude/commands/analyze-activity.md`

### Phase 4: Remove performance_file from Inserters (~4 hours)
**Goal:** 全8 insertersから`performance_file` parameterとlegacy code pathを削除

**Tasks:**

**Per Inserter (~0.5 hour each × 8 = 4 hours):**
1. ActivityInserter
2. Vo2MaxInserter
3. LactateThresholdInserter
4. HeartRateZonesInserter
5. HrEfficiencyInserter
6. FormEfficiencyInserter
7. SplitsInserter
8. PerformanceTrendsInserter

**Common Steps (per inserter):**
1. **Signature変更** (~5 min)
   - `performance_file: str | None,` parameter削除
   - Docstring更新（dual-mode言及削除）

2. **Legacy code削除** (~10 min)
   - `use_raw_data = performance_file is None` 削除
   - `if performance_file:` / `else:` 分岐削除
   - Legacy mode code block完全削除
   - Indentation修正

3. **Caller更新** (~5 min)
   - `garmin_worker.py` のinserter呼び出しから`performance_file=None` 削除
   - 位置引数に変更（必要に応じて）

4. **Test更新** (~10 min)
   - Test functionからperformance_file引数削除
   - Legacy mode testケース削除（if any）
   - 全testケースが動作確認

5. **Code quality** (~5 min)
   - Black, Ruff, Mypy実行
   - Import最適化

**Acceptance Criteria:**
- 全inserterから`performance_file` parameter削除
- Legacy code path完全削除
- 全inserter testsが合格
- Code quality checks合格

**Related Files:**
- `tools/database/inserters/*.py` (8 files)
- `tests/database/inserters/test_*.py` (8 files)
- `tools/ingest/garmin_worker.py` (caller updates)

### Phase 5: Documentation & Final Cleanup (~1.5 hours)
**Goal:** ドキュメント更新とfinal validation

**Tasks:**
1. **CLAUDE.md更新** (~0.5 hour)
   - Line 267: "create_parquet_dataset()" 言及削除
   - Dual-mode説明削除
   - Architecture説明簡略化
   - "Single-mode inserters" セクション追加

2. **Docstring cleanup** (~0.5 hour)
   - 全inserterのdocstringレビュー
   - Legacy/dual-mode言及削除確認
   - Example更新（if any）

3. **Final validation** (~0.5 hour)
   - 全テスト実行（unit + integration）
   - Code quality checks（Black, Ruff, Mypy）
   - Coverage確認（80%以上維持）
   - Manual smoke test（1 activity処理）

**Acceptance Criteria:**
- CLAUDE.md更新完了
- 全docstrings最新化
- 全テスト合格
- Code quality checks合格

**Related Files:**
- `CLAUDE.md`
- All modified inserters
- All test files

---

## テスト計画

### Unit Tests

#### Phase 2: create_parquet_dataset() Removal
- [x] Existing tests pass without `test_create_parquet_dataset()`
- [x] No references to `mock_parquet` remain
- [x] `test_backward_compatibility.py` deleted

#### Phase 3: precheck Strategy
**Scenario A: DuckDB-based Validation**
- [ ] `test_validate_from_duckdb_success` - DuckDBから正常取得
- [ ] `test_validate_from_duckdb_missing_data` - データなし時の処理
- [ ] `test_validate_from_duckdb_partial_data` - 一部データなし時の処理
- [ ] `test_precheck_json_generation_from_duckdb` - precheck.json生成確認

**Scenario B: Remove precheck.json**
- [ ] `test_process_activity_without_precheck` - precheck.jsonなしで処理成功
- [ ] No precheck.json files generated

#### Phase 4: Inserter Refactoring (per inserter)
- [ ] `test_insert_activity_without_performance_file` - performance_file引数なし
- [ ] `test_insert_activity_raw_data_only` - Raw dataから正常挿入
- [ ] `test_insert_activity_data_integrity` - データ整合性（変更前と同一）
- [ ] All existing test cases pass with updated signature

### Integration Tests

#### End-to-End Processing
- [ ] `test_process_activity_single_code_path` - Raw data → DuckDB完全フロー
- [ ] `test_process_activity_no_legacy_code` - Legacy code pathが実行されない
- [ ] `test_all_inserters_raw_data_mode` - 全inserterがraw data modeで動作

#### DuckDB Validation (if Scenario A)
- [ ] `test_precheck_validation_accuracy` - DuckDBベースvalidationの正確性
- [ ] `test_precheck_matches_duckdb_state` - precheck.jsonとDuckDB状態が一致

### Regression Tests

- [ ] `test_existing_duckdb_data_unchanged` - 既存DuckDBデータに影響なし
- [ ] `test_mcp_tools_still_work` - MCP Server tools動作確認
- [ ] `test_analysis_workflow_unchanged` - Analysis workflow動作確認

### Performance Tests

- [ ] `test_insertion_speed_no_regression` - 挿入速度が変更前と同等
- [ ] `test_validation_overhead_minimal` - DuckDB validation overhead < 5% (if Scenario A)

### Code Quality

- [ ] Black formatting passes
- [ ] Ruff linting passes (no warnings)
- [ ] Mypy type checking passes (no errors)
- [ ] Code coverage ≥ 80% (maintained from baseline)

---

## 受け入れ基準

### Functionality
- [ ] `create_parquet_dataset()` メソッド完全削除
- [ ] `test_backward_compatibility.py` 完全削除
- [ ] 全8 insertersから`performance_file` parameter削除
- [ ] Legacy code path完全削除（dual-mode分岐なし）
- [ ] precheck.json戦略実装完了（DuckDB-based or 削除）
- [ ] 全inserterが単一code pathで動作
- [ ] DuckDBに挿入されるデータが変更前と同一

### Code Quality
- [ ] 全テストがパスする (unit, integration, performance)
- [ ] Backward compatibility tests削除
- [ ] カバレッジ80%以上維持（既存と同等）
- [ ] Black formatting passes
- [ ] Ruff linting passes
- [ ] Mypy type checking passes
- [ ] ~200-300行のコード削減達成

### Documentation
- [ ] CLAUDE.md更新（dual-mode言及削除、single-path説明追加）
- [ ] 全Inserterの docstrings 更新
- [ ] precheck.json戦略文書化（if DuckDB-based）
- [ ] Migration noteドキュメント作成（breaking changes記録）

### Performance
- [ ] 挿入速度: 変更前と同等 or 改善
- [ ] Validation overhead: < 5% (if DuckDB-based precheck)
- [ ] DuckDBクエリ性能: 変更前と同等

### Breaking Changes (Expected)
- [ ] Legacy mode呼び出しコード（external）が壊れることを確認・文書化
- [ ] precheck.json format変更（if DuckDB-based）を文書化

---

## リスク管理

### High Priority Risks

1. **precheck.json依存コードの破壊**
   - **Risk:** precheck.json削除/変更により、未知の依存コードが壊れる
   - **Mitigation:** Phase 1で完全な利用状況調査（Grep search, code review）
   - **Fallback:** DuckDB-based validationを選択（precheck.json維持）

2. **Test coverage低下**
   - **Risk:** Backward compatibility tests削除により、カバレッジが低下
   - **Mitigation:** Phase 4で各inserterのtest coverage確認、必要に応じて追加test
   - **Fallback:** カバレッジ80%未満なら追加test作成

3. **データ整合性リスク**
   - **Risk:** Legacy code削除時のバグにより、DuckDBデータが不正確
   - **Mitigation:** 各PhaseでデータIntegrity test実施
   - **Fallback:** 変更前後でDuckDBダンプ比較、不一致あれば修正

### Medium Priority Risks

4. **DuckDB validation overhead**
   - **Risk:** DuckDB-based precheck選択時、クエリオーバーヘッドが発生
   - **Mitigation:** Performance test実施、< 5% overhead確認
   - **Fallback:** Lazy validation（必要時のみクエリ）実装

5. **Signature変更による外部コード破壊**
   - **Risk:** Inserter signatureが変わり、外部呼び出しコードが壊れる
   - **Mitigation:** 外部呼び出し箇所の完全調査（garmin_worker.py以外）
   - **Fallback:** Deprecation warning追加（optional parameter化）

### Low Priority Risks

6. **ドキュメント更新漏れ**
   - **Risk:** Dual-mode言及が一部ドキュメントに残る
   - **Mitigation:** Phase 5でGrep search、"performance_file" / "dual-mode" 全検索
   - **Fallback:** 発見次第修正

7. **Migration confusion**
   - **Risk:** 開発者がlegacy modeを期待してコード書く
   - **Mitigation:** CLAUDE.mdにMigration note追加、breaking changes明記
   - **Fallback:** PR review時に指摘

---

## 関連プロジェクト

### 直接関連
- **#24 Remove performance.json Generation** (Completed 2025-10-16)
  - **関係**: 本プロジェクトの前提（dual-mode実装完了）
  - **理由**: #24でdual-mode実装、本projectでlegacy mode削除

### 間接関連
- **#23 Granular DuckDB Regeneration** (Active)
  - **関係**: 本プロジェクト完了後、regeneration logicが簡略化
  - **理由**: Single code pathのみサポート
- **#12 DuckDB Storage** (Completed)
  - **関係**: DuckDB-first architectureの基盤
- **#7 Multi-Agent Analysis** (Completed)
  - **関係**: MCP Server経由でDuckDB利用（変更なし）

---

## マイルストーン

### Milestone 1: Investigation Complete (Phase 1 完了)
- **期限**: Phase 1完了後
- **成果物**:
  - precheck.json利用状況レポート
  - Validation戦略決定
  - Detailed implementation plan

### Milestone 2: Dead Code Removed (Phase 2-3 完了)
- **期限**: Phase 3完了後
- **成果物**:
  - `create_parquet_dataset()` 削除
  - `test_backward_compatibility.py` 削除
  - precheck戦略実装完了

### Milestone 3: Single Code Path (Phase 4 完了)
- **期限**: Phase 4完了後
- **成果物**:
  - 全inserterから`performance_file` 削除
  - Legacy code path完全削除
  - 全テスト合格

### Milestone 4: Documentation Complete (Phase 5 完了)
- **期限**: Phase 5完了後
- **成果物**:
  - CLAUDE.md更新
  - 全docstrings最新化
  - Completion report作成

---

## 完成基準

### Definition of Done
- [ ] 全フェーズ完了 (Phase 1-5)
- [ ] 全受け入れ基準達成
- [ ] 全テスト合格 (unit, integration, performance)
- [ ] コード品質チェック合格 (Black, Ruff, Mypy)
- [ ] ドキュメント更新 (CLAUDE.md, docstrings)
- [ ] `create_parquet_dataset()` 完全削除
- [ ] `test_backward_compatibility.py` 完全削除
- [ ] 全inserterがsingle code path
- [ ] ~200-300行のコード削減
- [ ] Planning document更新（完了ノート）
- [ ] Completion report生成
- [ ] GitHub Issue作成・クローズ

### Success Metrics
- **Primary Metric:** コード削減 (~200-300 lines)
  - `create_parquet_dataset()`: ~65 lines
  - Legacy code paths (8 inserters × ~15 lines): ~120 lines
  - `test_backward_compatibility.py`: ~80 lines
  - Test cleanup: ~20 lines
- **Secondary Metric:** Single code path達成（全inserters）
- **Tertiary Metric:** 保守性向上（code complexity reduction）

### Post-Launch Activities
- [ ] Monitor for external code breakage (if any)
- [ ] Archive planning.md to docs/project/_archived/ (when project closed)
- [ ] Share migration learnings with team
- [ ] Update onboarding documentation (if exists)

---

## 技術的詳細

### Code Removal Estimate

**Files to Delete:**
1. `tests/ingest/test_backward_compatibility.py` - **80 lines**

**Code to Remove:**

2. `tools/ingest/garmin_worker.py`:
   - `create_parquet_dataset()` method: **65 lines** (Lines 681-746)
   - precheck.json generation: **15 lines** (Lines 1229-1242) - if Option B
   - Total: **80 lines**

3. `tools/database/inserters/*.py` (8 files):
   - Per inserter (average):
     - `performance_file` parameter: **1 line**
     - Legacy mode code: **10-15 lines**
     - Docstring updates: **2-3 lines**
   - Total per inserter: **~15 lines**
   - Total all inserters: **~120 lines**

4. `tests/ingest/test_garmin_worker.py`:
   - `test_create_parquet_dataset()`: **8 lines**
   - create_parquet_dataset() calls: **5 lines**
   - mock_parquet references: **4 lines**
   - Total: **~20 lines**

**Grand Total: ~300 lines removed**

### Performance Impact

**Expected Improvements:**
- Code complexity: -15% (dual-mode → single-mode)
- Test execution: -5% (backward compatibility tests削除)
- Maintenance cost: -20% (legacy code削除)

**No Regression Expected:**
- Insertion speed: 同等（code path簡略化で微改善の可能性）
- DuckDB query: 同等
- Memory usage: 同等

### Breaking Changes

**For External Code (if any):**
1. Inserter signature changes:
   ```python
   # Before
   insert_activity(performance_file=None, activity_id=123, ...)

   # After
   insert_activity(activity_id=123, ...)  # performance_file removed
   ```

2. precheck.json format (if DuckDB-based):
   ```json
   // May have slight differences in validation logic
   // Recommend re-testing dependent code
   ```

**Migration Guide:**
- Remove all `performance_file` arguments from inserter calls
- Ensure raw data files are available (no longer support performance.json fallback)
- Re-test precheck.json dependent code (if DuckDB-based validation selected)

---

## 参考資料

### Related Documents
- Project #24 Planning: `docs/project/2025-10-14_remove_performance_json/planning.md`
- Project #24 Completion: `docs/project/2025-10-14_remove_performance_json/completion_report.md`
- CLAUDE.md: Architecture overview

### Code References
- Inserters: `tools/database/inserters/*.py`
- GarminIngestWorker: `tools/ingest/garmin_worker.py`
- Tests: `tests/database/inserters/`, `tests/ingest/`

### Decision Log
- **2025-10-16**: Project planning initiated
- **TBD**: precheck.json strategy decision (Phase 1)
- **TBD**: Implementation start date

---

## 注意事項

### Critical Considerations

1. **Phase 1 Blocker**: precheck.json利用状況調査が完了するまで実装開始しない
2. **Incremental Commits**: 各inserter変更を個別commit（rollback容易化）
3. **Test First**: 各Phase完了時に全テストを実行（regression早期発見）
4. **Documentation Sync**: コード変更とdocstring更新を同一commit

### Known Limitations

1. Performance.json読み込みサポート完全削除（legacy dataアクセス不可）
2. Backward compatibility維持不可（breaking change）
3. External code破壊リスク（要調査）

### Future Work

1. **Validation Framework**: DuckDB-based validationを汎用化（他のテーブルにも適用）
2. **Type Safety**: Inserter return typeをより厳密に（Success/Failure型導入）
3. **Performance Monitoring**: Insertion速度の継続的モニタリング
