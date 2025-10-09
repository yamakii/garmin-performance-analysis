# Phase 0: Impact Analysis Report

**Generated:** 2025-10-09
**Status:** ✅ Completed

## Executive Summary

Phase 0 の調査により、`.parquet` ファイルと `save_data()` 戻り値の使用箇所を完全に特定しました。

**主な発見:**
- **本番コード**: `tools/ingest/garmin_worker.py` の1箇所のみで parquet ファイルを生成
- **テストコード**: 5ファイルで parquet 参照あり（すべてテストコード）
- **save_data() 戻り値**: 本番コードでは使用されず、テストコードのみで使用
- **削除安全性**: ✅ 本番コードへの影響なし、テスト修正のみで対応可能

---

## 1. 本番コード (tools/) での `.parquet` 参照

### tools/ingest/garmin_worker.py

**参照箇所:** 3箇所

#### 1. __init__() - ディレクトリ定義 (Line 123)
```python
self.parquet_dir = self.project_root / "data" / "parquet"
```
- **影響**: ディレクトリパス定義の削除が必要

#### 2. __init__() - ディレクトリ作成 (Line 131)
```python
for directory in [
    self.raw_dir,
    self.parquet_dir,  # ← 削除対象
    self.performance_dir,
    self.precheck_dir,
]:
```
- **影響**: ディレクトリ作成リストから削除が必要

#### 3. save_data() - Parquet ファイル生成 (Lines 1059-1061)
```python
# Save parquet
parquet_file = self.parquet_dir / f"{activity_id}.parquet"
df.to_parquet(parquet_file, index=False)
logger.info(f"Saved parquet to {parquet_file}")
```
- **影響**: ✅ **削除対象** - これがメインの削除箇所

#### 4. save_data() - 戻り値 (Line 1202)
```python
return {
    "raw_file": str(self.raw_dir / f"{activity_id}_raw.json"),
    "parquet_file": str(parquet_file),  # ← 削除対象
    "performance_file": str(performance_file),
    "precheck_file": str(precheck_file),
}
```
- **影響**: ✅ **削除対象** - 戻り値から `parquet_file` キーを削除

#### 5. Docstring - ファイル作成リスト (Line 1045)
```python
"""
Files created:
- data/raw/{activity_id}_raw.json (already created in collect_data)
- data/parquet/{activity_id}.parquet  # ← 削除対象
- data/performance/{activity_id}.json
- data/precheck/{activity_id}.json
"""
```
- **影響**: Docstring から parquet 行を削除

---

## 2. テストコードでの `.parquet` 参照

### tests/ingest/test_garmin_worker.py

**影響度:** 🔴 **HIGH** - 直接的な parquet 参照あり

#### Line 253: save_data() 戻り値アサーション
```python
assert "parquet_file" in result
```
- **修正必要**: ✅ このアサーションを削除

#### Line 341, 346-347: process_activity() の parquet ファイル確認
```python
assert "parquet_file" in files  # Line 341
parquet_file = worker.parquet_dir / f"{activity_id}.parquet"  # Line 346
assert parquet_file.exists()  # Line 347
```
- **修正必要**: ✅ これらのアサーションを削除
- **代替策**: DuckDB へのデータ保存確認に変更

---

### tests/ingest/test_body_composition.py

**影響度:** 🔴 **HIGH** - Weight parquet 後方互換性テスト

#### Lines 341-356: Weight parquet 存在確認と読み込み
```python
parquet_file = (
    worker.project_root
    / "data"
    / "weight_cache"
    / "parquet"
    / f"weight_{test_date}.parquet"
)
parquet_exists = parquet_file.exists()
if parquet_exists:
    existing_parquet = pd.read_parquet(parquet_file)
```
- **修正必要**: ✅ 後方互換性テストを削除またはスキップ
- **理由**: Weight parquet はレガシーファイルで新規生成されない

---

### tests/unit/test_garmin_worker_phase4.py

**影響度:** 🟡 **MEDIUM** - モックデータのみ

#### Line 166: モックの expected_result
```python
expected_result = {
    "activity_id": activity_id,
    "performance_file": "/path/to/performance.json",
    "parquet_file": "/path/to/data.parquet",  # ← 削除対象
}
```
- **修正必要**: ✅ モックデータから `parquet_file` を削除

---

### tests/unit/test_garmin_worker_phase0.py

**影響度:** 🟢 **LOW** - セットアップコードのみ

#### Lines 20, 28: パッチされた __init__() でのディレクトリ定義
```python
self.parquet_dir = tmp_path / "parquet"  # Line 20
for directory in [
    self.raw_dir,
    self.parquet_dir,  # Line 28
    self.performance_dir,
    self.precheck_dir,
]:
```
- **修正必要**: ✅ テストセットアップから `parquet_dir` を削除

---

### tests/planner/test_workflow_planner.py

**影響度:** 🟡 **MEDIUM** - モックデータのみ

#### Line 99: モックの files dict
```python
"files": {
    "raw_file": "data/raw/20594901208_raw.json",
    "parquet_file": "data/parquet/20594901208.parquet",  # ← 削除対象
    "performance_file": "data/performance/20594901208.json",
    "precheck_file": "data/precheck/20594901208.json",
}
```
- **修正必要**: ✅ モックデータから `parquet_file` を削除

---

## 3. save_data() 戻り値の使用箇所

### 本番コードでの使用

**結果:** ❌ **本番コードでは使用されていない**

- `save_data()` の戻り値を受け取る箇所: `tools/ingest/garmin_worker.py` 内のみ
- 戻り値は `process_activity()` に渡されるが、`process_activity()` 内では戻り値の個別キーは参照されない
- **結論**: `parquet_file` キーの削除は本番コードに影響しない

### テストコードでの使用

**結果:** ✅ **テストコードのみで使用**

1. **tests/ingest/test_garmin_worker.py** (Line 253, 341)
   - `save_data()` と `process_activity()` の戻り値で `parquet_file` キーの存在を確認
   - **修正必要**: アサーションを削除

2. **tests/unit/test_garmin_worker_phase4.py** (Line 166)
   - モックの expected_result に含まれる
   - **修正必要**: モックから削除

3. **tests/planner/test_workflow_planner.py** (Line 99)
   - モックの files dict に含まれる
   - **修正必要**: モックから削除

---

## 4. 影響範囲マップ

### 本番コード影響

| ファイル | 影響箇所 | 修正内容 | 優先度 |
|---------|---------|----------|-------|
| `tools/ingest/garmin_worker.py` | Lines 123, 131, 1059-1061, 1202, 1045 | Parquet 生成コードと戻り値削除 | 🔴 HIGH |

**本番コード変更合計:** 1ファイル、5箇所

### テストコード影響

| ファイル | 影響箇所 | 修正内容 | 優先度 |
|---------|---------|----------|-------|
| `tests/ingest/test_garmin_worker.py` | Lines 253, 341, 346-347 | Parquet アサーション削除 | 🔴 HIGH |
| `tests/ingest/test_body_composition.py` | Lines 341-356 | 後方互換性テスト削除/スキップ | 🔴 HIGH |
| `tests/unit/test_garmin_worker_phase4.py` | Line 166 | モック更新 | 🟡 MEDIUM |
| `tests/unit/test_garmin_worker_phase0.py` | Lines 20, 28 | セットアップ削除 | 🟢 LOW |
| `tests/planner/test_workflow_planner.py` | Line 99 | モック更新 | 🟡 MEDIUM |

**テストコード変更合計:** 5ファイル、合計約15箇所

---

## 5. 削除安全性確認

### ✅ 安全性チェック

- [x] **本番コードでの parquet 使用**: `garmin_worker.py` の生成部分のみ
- [x] **本番コードでの parquet 参照**: なし（生成後は使用されない）
- [x] **テストコードでの parquet 参照**: 5ファイルすべて修正可能
- [x] **save_data() 戻り値の本番使用**: なし（戻り値の個別キーは使用されない）
- [x] **Precheck ファイルへの影響**: なし（完全に独立）
- [x] **DuckDB データへの影響**: なし（parquet とは独立）

### ⚠️ 注意点

1. **Weight Parquet Files**: レガシーファイルのため、後方互換性テストを削除/スキップ
2. **WorkflowPlanner**: Precheck ファイルは保持されるため、影響なし
3. **データ整合性**: DuckDB が primary storage なので、parquet 削除後もデータアクセス可能

---

## 6. Phase 1 への推奨事項

### TDD Cycle 1: Remove parquet generation

**RED (失敗テスト作成):**
```python
def test_save_data_no_parquet_generation():
    """save_data() の戻り値に parquet_file キーが含まれないこと"""
    result = worker.save_data(activity_id, raw_data, df, performance_data)
    assert "parquet_file" not in result
    assert "performance_file" in result
    assert "precheck_file" in result
```

**GREEN (コード修正):**
1. `garmin_worker.py` Lines 1059-1061 削除
2. `garmin_worker.py` Line 1202 削除 (`parquet_file` キー)
3. `garmin_worker.py` Lines 123, 131, 1045 削除（関連コード）

**REFACTOR (リファクタリング):**
- Docstring 更新
- コメント削除

### TDD Cycle 2: Fix test_body_composition.py

**修正方針:**
- Weight parquet テストを削除またはスキップ
- 理由: レガシーファイルで新規生成されない

### TDD Cycle 3: Fix other affected tests

**修正対象:**
1. `tests/ingest/test_garmin_worker.py` - Parquet アサーション削除
2. `tests/unit/test_garmin_worker_phase4.py` - モック更新
3. `tests/unit/test_garmin_worker_phase0.py` - セットアップ更新
4. `tests/planner/test_workflow_planner.py` - モック更新

---

## 7. リスク評価

### 🟢 低リスク

- 本番コードへの影響は `garmin_worker.py` の1箇所のみ
- parquet ファイルは本番コードで使用されていない
- DuckDB が primary storage として機能している
- Precheck ファイルは保持される（WorkflowPlanner への影響なし）

### 🟡 中リスク

- テストコードの修正が5ファイル必要
- 後方互換性テストの削除が必要

### 対策

- TDD サイクルで段階的に修正
- 全テストスイート実行で検証
- バックアップ作成（Phase 2）

---

## 8. Phase 0 完了チェックリスト

- [x] 全テストファイルで `.parquet` 参照をgrep検索
- [x] 本番コード (tools/) で `.parquet` 参照をgrep検索
- [x] `save_data()` 戻り値の使用箇所を特定
- [x] 影響範囲マップ作成
- [x] 削除安全性確認レポート作成

---

## Conclusion

Phase 0 の調査により、parquet ファイル削除の影響範囲が明確になりました。

**次のステップ:**
- Phase 1 (Code Removal) に進む
- TDD サイクルで段階的にコード削除とテスト修正を実行
- 全テストパスを確認して Phase 2 (File Cleanup) へ

**安全性評価:** ✅ **削除安全** - 本番コードへの影響なし、テスト修正のみで対応可能
