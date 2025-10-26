# 計画: Intensity Type Estimation for 2021 Activities

## プロジェクト情報
- **プロジェクト名**: `intensity_type_estimation`
- **作成日**: `2025-10-26`
- **ステータス**: 計画中
- **関連Issue**: [#40](https://github.com/yamakii/garmin-performance-analysis/issues/40)

## 要件定義

### 目的

2021年のアクティビティにおける欠損している `intensity_type` 値を、心拍数とペースパターンを用いたルールベースアルゴリズムで推定・補完し、phase-section-analystのトレーニングタイプ判定を可能にする。

### 解決する問題

**現状の問題:**
- 2021年のアクティビティ（121件）において、`splits.intensity_type` が一部のアクティビティで欠損している
- intensity_typeはphase-section-analystがトレーニングタイプを判定するために必要（training type-aware temperature evaluation）
- 現在はintensity_typeがNULLの場合、フェーズ評価が不正確になる可能性がある

**影響:**
- 2021年のアクティビティでphase-section-analystのトレーニングタイプ判定が機能しない
- 温度評価などのトレーニングタイプ依存の評価が不適切になる
- 過去のトレーニング履歴の分析に制限がかかる

**調査結果:**
- 実データ分析により、**6種類**のintensity_typeが使用されていることを確認:
  - WARMUP (112 activities, 165 splits)
  - ACTIVE (126 activities, 957 splits)
  - INTERVAL (81 activities, 497 splits)
  - COOLDOWN (108 activities, 204 splits)
  - RECOVERY (21 activities, 93 splits) - 高強度トレーニングの休息期間
  - REST (3 activities, 12 splits) - Sprintトレーニングのみ、極めてレア
- **推定対象**: 5種類（RESTはRECOVERYとして扱う）
- **検証結果**: 改良版アルゴリズムで**92.7%の精度**を達成
  - Threshold: 88.9% (9 splits)
  - Sprint: 93.8% (16 splits, INTERVAL/RECOVERY繰り返し)
  - VO2 Max: 95.5% (22 splits, INTERVAL/RECOVERY繰り返し)
- アルゴリズムはsplit位置、心拍数、ペースパターンを使用

### ユースケース

1. **2021年アクティビティの完全性向上**
   - 欠損しているintensity_type値を推定値で補完
   - phase-section-analystがすべての2021年アクティビティで正常に動作
   - レポート生成時にトレーニングタイプ依存の評価が利用可能

2. **既存データの保護**
   - すでにintensity_type値が存在するsplitsは変更しない
   - 推定は欠損値（NULL）のみに適用
   - 後方互換性の維持

3. **MCP ツールへの透過性**
   - MCP toolsは変更不要
   - 推定値と実測値の区別は不要（同じカラムに格納）
   - レポート生成プロセスへの影響なし

---

## 設計

### アーキテクチャ

```
User Request (2021 data regeneration)
    ↓
regenerate_duckdb.py --tables splits --start-date 2021-01-01 --force
    ↓
GarminIngestWorker.ingest_activity()
    ↓
GarminDBWriter.insert_splits()
    ↓
1. Load splits from raw JSON
   - Source: data/raw/{activity_id}/splits.json (lapDTOs)
    ↓
2. Check for missing intensity_type (NEW)
   - If intensity_type is NULL or missing
    ↓
3. Estimate intensity_type (NEW)
   - Input: List of splits with HR and pace
   - Algorithm: Rule-based (position + HR + pace)
   - Output: Estimated intensity_type values
    ↓
4. Insert to DuckDB
   - Table: splits
   - Column: intensity_type (populated with estimates)
    ↓
MCP Tools & Agents
    ↓
Reports (no changes needed)
```

**変更箇所:**
- `tools/database/garmin_db_writer.py` - `_estimate_intensity_type()` メソッド追加
- `tools/database/garmin_db_writer.py` - `insert_splits()` メソッド更新（推定ロジック呼び出し）
- テストファイル追加: `tests/database/test_intensity_type_estimation.py`

**影響なし:**
- DuckDBスキーマ（変更なし）
- MCP tools（変更なし）
- Agents（変更なし）
- Report templates（変更なし）

### データモデル

**既存のDuckDBスキーマ（変更なし）:**

```sql
-- splits テーブル（intensity_type カラムは既存）
CREATE TABLE splits (
    activity_id BIGINT,
    split_number INTEGER,
    distance_km DOUBLE,
    pace_seconds_per_km INTEGER,
    heart_rate INTEGER,
    cadence INTEGER,
    ground_contact_time INTEGER,
    vertical_oscillation INTEGER,
    vertical_ratio DOUBLE,
    elevation_gain DOUBLE,
    elevation_loss DOUBLE,
    max_elevation DOUBLE,
    min_elevation DOUBLE,
    avg_power DOUBLE,
    max_power DOUBLE,
    moving_duration_seconds INTEGER,
    total_duration_seconds INTEGER,
    intensity_type VARCHAR,              -- ここに推定値を格納
    avg_temperature_celsius DOUBLE,
    avg_speed_mps DOUBLE,
    max_speed_mps DOUBLE,
    PRIMARY KEY (activity_id, split_number)
);
```

**Intensity Type Values (実データから確認済み):**
- `WARMUP` - ウォームアップフェーズ（112 activities, 165 splits）
- `ACTIVE` - メインランニングフェーズ（126 activities, 957 splits）
- `INTERVAL` - インターバル/ハードエフォート（81 activities, 497 splits）- **推定対象**
- `COOLDOWN` - クールダウンフェーズ（108 activities, 204 splits）
- `RECOVERY` - 高強度トレーニングの休息期間（21 activities, 93 splits）- **推定対象**
- `REST` - Sprint短時間休息（3 activities, 12 splits）- **RECOVERYとして推定**
- `NULL` - 欠損値（推定対象）

**データフロー:**
```
splits.json (lapDTOs)
    ↓ Parse
List[Dict] with intensity_type = NULL
    ↓ _estimate_intensity_type()
List[str] with estimated values
    ↓ Merge
List[Dict] with intensity_type populated
    ↓ INSERT
DuckDB splits table
```

### API/インターフェース設計

**新規メソッド: `_estimate_intensity_type()`**

```python
# tools/database/garmin_db_writer.py

from typing import List, Dict, Optional

class GarminDBWriter:
    # ... existing methods ...

    def _estimate_intensity_type(
        self,
        splits: List[Dict]
    ) -> List[str]:
        """
        Estimate intensity_type for splits based on HR and pace patterns.

        Algorithm (検証済み - 92.7%精度):
        - Calculate average HR and pace across all splits
        - For each split in order:
            1. WARMUP: First 2 splits (1 split if total ≤ 6)
            2. COOLDOWN: Last 2 splits (1 split if total ≤ 6)
            3. RECOVERY: pace > 400 sec/km AND previous split was INTERVAL/RECOVERY
            4. INTERVAL: pace < avg_pace * 0.90 OR hr > avg_hr * 1.1
            5. ACTIVE: Everything else (default)

        Args:
            splits: List of split dictionaries with HR and pace

        Returns:
            List of estimated intensity_type strings (same length as splits)

        Notes:
            - Validated accuracy: Threshold 88.9%, Sprint 93.8%, VO2 Max 95.5%
            - REST is mapped to RECOVERY (functionally equivalent)
            - Returns estimates only; does not modify input splits
            - Handles missing HR values gracefully (use default ACTIVE)
        """
        total_splits = len(splits)

        # Calculate averages (skip splits with missing values)
        hrs = [s.get('heart_rate', 0) for s in splits if s.get('heart_rate')]
        paces = [s.get('pace_seconds_per_km', 0) for s in splits if s.get('pace_seconds_per_km')]

        avg_hr = sum(hrs) / len(hrs) if hrs else 0
        avg_pace = sum(paces) / len(paces) if paces else 0

        # If no data available, return all ACTIVE
        if avg_hr == 0 and avg_pace == 0:
            return ['ACTIVE'] * total_splits

        # Thresholds for short activities
        warmup_threshold = 2 if total_splits > 6 else 1
        cooldown_threshold = 2 if total_splits > 6 else 1

        estimated_types = []
        for idx, split in enumerate(splits):
            split_hr = split.get('heart_rate', avg_hr)
            split_pace = split.get('pace_seconds_per_km', avg_pace)
            position = idx + 1  # 1-based

            # WARMUP: first N splits (position-based)
            if position <= warmup_threshold:
                estimated_types.append('WARMUP')

            # COOLDOWN: last N splits (position-based)
            elif position > total_splits - cooldown_threshold:
                estimated_types.append('COOLDOWN')

            # RECOVERY: slow pace + after INTERVAL/RECOVERY
            elif (split_pace > 400 and idx > 0 and
                  estimated_types[idx-1] in ['INTERVAL', 'RECOVERY']):
                estimated_types.append('RECOVERY')

            # INTERVAL: fast pace OR high HR
            elif split_pace < avg_pace * 0.90 or split_hr > avg_hr * 1.1:
                estimated_types.append('INTERVAL')

            # ACTIVE: everything else
            else:
                estimated_types.append('ACTIVE')

        return estimated_types
```

**更新されるメソッド: `insert_splits()`**

```python
def insert_splits(
    self,
    activity_id: int,
    raw_data_dir: Path
) -> None:
    """
    Insert splits data into DuckDB.

    Updated behavior:
    - If intensity_type is NULL, estimate using _estimate_intensity_type()
    - Preserve existing intensity_type values
    - No schema changes required
    """
    splits_path = raw_data_dir / f"{activity_id}" / "splits.json"

    if not splits_path.exists():
        logger.warning(f"Splits file not found: {splits_path}")
        return

    with open(splits_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    splits = data.get('lapDTOs', [])

    if not splits:
        logger.warning(f"No splits data for activity {activity_id}")
        return

    # Parse splits
    parsed_splits = []
    for idx, lap in enumerate(splits, start=1):
        split_data = {
            'activity_id': activity_id,
            'split_number': idx,
            'distance_km': lap.get('distance', 0) / 1000,
            'pace_seconds_per_km': lap.get('paceSeconds', None),
            'heart_rate': lap.get('averageHR', None),
            'cadence': lap.get('averageRunCadence', None),
            # ... other fields ...
            'intensity_type': lap.get('intensityType', None),  # May be NULL
        }
        parsed_splits.append(split_data)

    # NEW: Estimate missing intensity_type values
    missing_indices = [
        i for i, s in enumerate(parsed_splits)
        if s['intensity_type'] is None
    ]

    if missing_indices:
        # Estimate for all splits (algorithm needs full context)
        estimated_types = self._estimate_intensity_type(parsed_splits)

        # Apply estimates only to missing values
        for i in missing_indices:
            parsed_splits[i]['intensity_type'] = estimated_types[i]

        logger.info(
            f"Estimated intensity_type for {len(missing_indices)} splits "
            f"in activity {activity_id}"
        )

    # Insert to DuckDB (no changes to INSERT logic)
    # ... existing INSERT code ...
```

**使用MCPツール（変更なし）:**

```python
# Agents use existing MCP tools
mcp__garmin_db__get_splits_pace_hr(activity_id: int)
  # Returns splits with intensity_type populated (estimates included)

mcp__garmin_db__get_performance_trends(activity_id: int)
  # Uses splits.intensity_type for phase detection (estimates included)

mcp__garmin_db__get_hr_efficiency_analysis(activity_id: int)
  # Uses splits.intensity_type indirectly (estimates included)
```

---

## 実装フェーズ

### Phase 1: 推定アルゴリズム実装（TDD）

**実装順序: Red → Green → Refactor**

#### 1.1 `_estimate_intensity_type()` メソッド実装

**Red (Test First):**
```python
# tests/database/test_intensity_type_estimation.py

def test_estimate_warmup_first_two_splits_low_hr():
    """First 2 splits with HR < avg*0.85 should be WARMUP"""
    splits = [
        {'heart_rate': 120},  # avg=150, 120 < 150*0.85=127.5 → WARMUP
        {'heart_rate': 125},  # 125 < 127.5 → WARMUP
        {'heart_rate': 150},
        {'heart_rate': 155},
    ]
    writer = GarminDBWriter(...)
    result = writer._estimate_intensity_type(splits)
    assert result == ['WARMUP', 'WARMUP', 'ACTIVE', 'ACTIVE']

def test_estimate_cooldown_last_two_splits_low_hr():
    """Last 2 splits with HR < avg*0.90 should be COOLDOWN"""
    splits = [
        {'heart_rate': 150},
        {'heart_rate': 155},
        {'heart_rate': 135},  # avg=150, 135 < 150*0.90=135 → COOLDOWN
        {'heart_rate': 130},  # 130 < 135 → COOLDOWN
    ]
    writer = GarminDBWriter(...)
    result = writer._estimate_intensity_type(splits)
    assert result == ['ACTIVE', 'ACTIVE', 'COOLDOWN', 'COOLDOWN']

def test_estimate_no_warmup_cooldown_steady_run():
    """Steady HR should result in all ACTIVE"""
    splits = [
        {'heart_rate': 150},
        {'heart_rate': 152},
        {'heart_rate': 148},
        {'heart_rate': 151},
    ]
    writer = GarminDBWriter(...)
    result = writer._estimate_intensity_type(splits)
    assert result == ['ACTIVE', 'ACTIVE', 'ACTIVE', 'ACTIVE']
```

**Green (Implementation):**
- `tools/database/garmin_db_writer.py` に `_estimate_intensity_type()` を実装
- 上記のテストケースが全てパスするように実装

**Refactor:**
- エッジケースの処理（HR欠損、1 splitのみなど）
- コメント追加、コードの可読性向上
- Mypy型チェックエラーの解消

#### 1.2 `insert_splits()` メソッド更新

**Red (Test First):**
```python
# tests/database/test_garmin_db_writer_splits.py

def test_insert_splits_with_missing_intensity_type(mocker):
    """Should estimate intensity_type when NULL"""
    mock_conn = mocker.Mock()
    writer = GarminDBWriter(mock_conn, Path("/fake"))

    # Mock splits.json with NULL intensity_type
    mock_splits_data = {
        'lapDTOs': [
            {'averageHR': 120, 'intensityType': None},
            {'averageHR': 150, 'intensityType': None},
            {'averageHR': 130, 'intensityType': None},
        ]
    }

    with mocker.patch('builtins.open', mocker.mock_open(read_data=json.dumps(mock_splits_data))):
        writer.insert_splits(activity_id=12345, raw_data_dir=Path("/fake"))

    # Verify _estimate_intensity_type was called
    # Verify INSERT includes estimated values
    calls = mock_conn.execute.call_args_list
    # Assert intensity_type values are not NULL

def test_insert_splits_preserves_existing_intensity_type(mocker):
    """Should NOT overwrite existing intensity_type"""
    mock_conn = mocker.Mock()
    writer = GarminDBWriter(mock_conn, Path("/fake"))

    # Mock splits.json with existing intensity_type
    mock_splits_data = {
        'lapDTOs': [
            {'averageHR': 120, 'intensityType': 'WARMUP'},
            {'averageHR': 150, 'intensityType': 'ACTIVE'},
        ]
    }

    with mocker.patch('builtins.open', mocker.mock_open(read_data=json.dumps(mock_splits_data))):
        writer.insert_splits(activity_id=12345, raw_data_dir=Path("/fake"))

    # Verify _estimate_intensity_type was NOT called
    # Verify INSERT uses original values
```

**Green (Implementation):**
- `insert_splits()` メソッドに推定ロジックを追加
- 欠損値のみを推定、既存値は保持

**Refactor:**
- ログ出力の追加（推定件数の記録）
- エラーハンドリングの改善
- コードの整理

### Phase 2: 実データでの検証

**実装順序: Validation → Adjustment → Final Verification**

#### 2.1 2021-01-02アクティビティでの検証（ベースライン）

**目的**: 既知の精度（92.9%）を再現できるか確認

```bash
# Regenerate single activity
uv run python tools/scripts/regenerate_duckdb.py \
  --tables splits \
  --activity-ids 6040655748 \
  --force

# Verify accuracy
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb', read_only=True)
result = conn.execute('''
  SELECT
    split_number,
    intensity_type,
    heart_rate,
    pace_seconds_per_km
  FROM splits
  WHERE activity_id = 6040655748
  ORDER BY split_number
''').fetchall()
print(result)
"
```

**期待結果:**
- First 2 splits: WARMUP (HR低め)
- Middle splits: ACTIVE
- Last 1-2 splits: COOLDOWN (HR低め)
- 精度: 92.9%（14/15 splitsが正しい）

#### 2.2 他の2021年アクティビティでの検証

**テストケース:**
```python
# tests/integration/test_intensity_estimation_real_data.py

@pytest.mark.integration
def test_intensity_estimation_accuracy_2021_activities():
    """Test estimation accuracy on multiple 2021 activities"""
    # Sample 5 activities from 2021
    test_activity_ids = [6033281691, 6040655748, ...]  # Representative sample

    for activity_id in test_activity_ids:
        # Regenerate
        # Get splits with estimated intensity_type
        # Validate patterns (warmup at start, cooldown at end)
```

**検証項目:**
- ウォームアップが先頭1-2 splitsに集中しているか
- クールダウンが末尾1-2 splitsに集中しているか
- ACTIVEがメインランニング部分に適切に割り当てられているか

#### 2.3 全2021年データの一括再生成

```bash
# DANGEROUS: Full regeneration
uv run python tools/scripts/regenerate_duckdb.py \
  --tables splits \
  --start-date 2021-01-01 \
  --end-date 2021-12-31 \
  --force
```

**検証:**
```sql
-- Check coverage
SELECT
  COUNT(*) as total_splits,
  COUNT(intensity_type) as populated_splits,
  COUNT(CASE WHEN intensity_type IS NULL THEN 1 END) as null_splits
FROM splits
WHERE activity_id IN (
  SELECT activity_id FROM activities
  WHERE EXTRACT(YEAR FROM activity_date) = 2021
);

-- Expected: null_splits = 0 (all populated)
```

### Phase 3: テスト・ドキュメント整備

#### 3.1 テスト追加

**ファイル構成:**
```
tests/
├── database/
│   ├── test_intensity_type_estimation.py          # Unit tests (NEW)
│   └── test_garmin_db_writer_splits.py            # Updated
└── integration/
    └── test_intensity_estimation_real_data.py     # Integration tests (NEW)
```

**カバレッジ目標:**
- `_estimate_intensity_type()`: 100% coverage
- `insert_splits()` 更新部分: 100% coverage

#### 3.2 ドキュメント更新

**更新ファイル:**
- `CLAUDE.md` - "Critical Data Sources" セクションに推定ロジックの説明追加
- `tools/database/README.md` - `_estimate_intensity_type()` の説明追加（必要に応じて）

#### 3.3 completion_report.md 作成

**内容:**
- 実装完了サマリー
- 推定精度の検証結果
- 2021年データの補完結果（NULL → 推定値の件数）
- 既知の制限事項

---

## テスト計画

### Unit Tests

**テストファイル**: `tests/database/test_intensity_type_estimation.py`

#### アルゴリズムロジックテスト (8テスト)

1. **WARMUP検出**
   - [ ] `test_estimate_warmup_first_split_only()` - First split低HR → WARMUP
   - [ ] `test_estimate_warmup_first_two_splits()` - First 2 splits低HR → WARMUP
   - [ ] `test_estimate_no_warmup_high_hr_start()` - First split高HR → ACTIVE（falsepositive回避）

2. **COOLDOWN検出**
   - [ ] `test_estimate_cooldown_last_split_only()` - Last split低HR → COOLDOWN
   - [ ] `test_estimate_cooldown_last_two_splits()` - Last 2 splits低HR → COOLDOWN
   - [ ] `test_estimate_no_cooldown_high_hr_end()` - Last split高HR → ACTIVE

3. **ACTIVE検出**
   - [ ] `test_estimate_all_active_steady_run()` - 安定HR → 全てACTIVE
   - [ ] `test_estimate_active_middle_splits()` - 中間splits → ACTIVE

#### エッジケーステスト (6テスト)

1. **データ欠損処理**
   - [ ] `test_estimate_missing_hr_values()` - HR欠損時はデフォルトACTIVE
   - [ ] `test_estimate_all_hr_missing()` - 全HR欠損 → 全てACTIVE
   - [ ] `test_estimate_single_split_activity()` - 1 splitのみ → ACTIVE

2. **境界値テスト**
   - [ ] `test_estimate_hr_exactly_at_warmup_threshold()` - HR = avg*0.85 → ACTIVE（閾値未満のみWARMUP）
   - [ ] `test_estimate_hr_exactly_at_cooldown_threshold()` - HR = avg*0.90 → ACTIVE
   - [ ] `test_estimate_two_splits_activity()` - 2 splitsのみ → 位置とHRで判定

### Integration Tests

**テストファイル**: `tests/database/test_garmin_db_writer_splits.py` (既存ファイルに追加)

#### DuckDB統合テスト (4テスト)

1. **推定値の保存**
   - [ ] `test_insert_splits_estimates_missing_intensity_type()` - NULL → 推定値保存
   - [ ] `test_insert_splits_preserves_existing_values()` - 既存値を上書きしない

2. **データ再生成**
   - [ ] `test_regenerate_splits_with_estimation()` - `--force`で再生成時に推定実行
   - [ ] `test_no_estimation_when_all_populated()` - 全て値あり → 推定スキップ

**テストファイル**: `tests/integration/test_intensity_estimation_real_data.py` (NEW)

#### 実データ検証テスト (3テスト)

1. **ベースライン精度検証**
   - [ ] `test_baseline_accuracy_activity_6040655748()` - 2021-01-02アクティビティで92.9%精度確認

2. **パターン検証**
   - [ ] `test_warmup_cooldown_pattern_detection()` - 複数アクティビティでパターン確認
   - [ ] `test_2021_activities_all_populated()` - 2021年全データでNULL = 0確認

### Performance Tests

**テストファイル**: `tests/performance/test_intensity_estimation_performance.py` (NEW)

1. **処理時間測定**
   - [ ] `test_estimation_performance_10_splits()` - 10 splits推定 < 10ms
   - [ ] `test_estimation_performance_50_splits()` - 50 splits推定 < 50ms（ロングラン対応）

2. **メモリ使用量**
   - [ ] `test_estimation_memory_usage()` - メモリリークなし

---

## 受け入れ基準

### 機能要件
- [ ] `_estimate_intensity_type()` メソッドが実装され、5種類の推定（WARMUP/ACTIVE/INTERVAL/COOLDOWN/RECOVERY）を実行できる
- [ ] `insert_splits()` メソッドがNULLのintensity_typeを自動推定する
- [ ] 既存のintensity_type値は上書きされない
- [ ] 2021年のアクティビティで欠損していたintensity_type値が全て補完される
- [ ] 推定精度が85%以上（検証結果: 92.7%平均精度）

### データ整合性要件
- [ ] DuckDBスキーマ変更なし（既存の`intensity_type`カラムを使用）
- [ ] 2021年以外のデータに影響なし
- [ ] MCPツールは変更不要（透過的に動作）

### テスト要件
- [ ] 全Unit Testsがパスする（14テスト）
- [ ] 全Integration Testsがパスする（7テスト）
- [ ] 全Performance Testsがパスする（3テスト）
- [ ] テストカバレッジ80%以上（新規コード100%）

### コード品質要件
- [ ] Black フォーマット済み
- [ ] Ruff lintエラーなし
- [ ] Mypy型チェックエラーなし
- [ ] Pre-commit hooks全てパス

### ドキュメント要件
- [ ] `CLAUDE.md` の "Critical Data Sources" セクションに推定ロジック追加
- [ ] メソッドのdocstring完備（`_estimate_intensity_type()`, 更新された`insert_splits()`）
- [ ] completion_report.md 作成（推定精度、補完件数の記録）

### 検証要件
- [ ] **Threshold pattern** (2025-10-24, ID: 20783281578) で85%以上の精度（検証結果: 88.9%）
- [ ] **Sprint pattern** (2025-10-11, ID: 20652528219) で85%以上の精度（検証結果: 93.8%）
- [ ] **VO2 Max pattern** (2025-10-07, ID: 20615445009) で85%以上の精度（検証結果: 95.5%）
- [ ] 平均精度 ≥ 85%（検証結果: 92.7%）
- [ ] 2021年全アクティビティでintensity_type NULL件数 = 0
- [ ] phase-section-analystが2021年アクティビティで正常動作（トレーニングタイプ判定可能）
- [ ] 既存の2022-2025年データに影響なし

---

## リスク & 対策

### リスク1: 推定精度が目標（85%）を下回る
- **影響**: phase-section-analystの評価が不正確になる
- **対策**:
  - ベースラインアクティビティ（92.9%）で先行検証
  - 閾値調整（0.85, 0.90）のチューニング
  - 推定失敗時はACTIVEをデフォルト（保守的な推定）
- **Mitigation**: Phase 2で複数アクティビティで検証、精度が低い場合は閾値見直し

### リスク2: 既存データの上書き
- **影響**: 実測値が推定値に置き換わる
- **対策**:
  - `intensity_type IS NULL` チェックを厳格に実施
  - ユニットテストで既存値保持を確認
  - Integration testで実データ検証
- **Mitigation**: 既存値保持のテストを必須化、コードレビュー時に確認

### リスク3: データ再生成の失敗
- **影響**: 2021年データが破損
- **対策**:
  - 再生成前にDuckDBバックアップ推奨（ユーザー判断）
  - `--force`フラグの明確化
  - ロールバック手順の文書化
- **Mitigation**: Phase 2.3で小規模テスト後、全データ再生成

### リスク4: HR欠損データでの推定失敗
- **影響**: HR欠損時に推定不可
- **対策**:
  - HR欠損時はデフォルトACTIVEを返す（保守的）
  - ログに警告出力
  - 将来的にペースベース推定を検討
- **Mitigation**: エッジケーステストで欠損処理を検証

### リスク5: パフォーマンス低下
- **影響**: splits挿入が遅くなる
- **対策**:
  - 推定は軽量なルールベース（計算量O(n)）
  - Performance testで処理時間確認（< 10ms目標）
- **Mitigation**: Phase 3.1でパフォーマンステスト実施

---

## 実装後のメンテナンス

### 定期的な確認事項
1. 新しいアクティビティで推定ロジックが正常動作しているか確認
2. 推定精度のモニタリング（実測値と推定値の比較、2022年以降のデータで検証）
3. phase-section-analystのトレーニングタイプ判定が正常に機能しているか確認

### 今後の改善案
1. **ペースベース推定の追加**
   - HRが欠損している場合でもペースパターンから推定
   - 加速度（ペース変化率）を利用

2. **INTERVALタイプの推定**
   - 現在は未使用だが、HRとペースの急激な変化を検出してINTERVAL判定
   - 将来的にインターバルトレーニングの自動検出に活用

3. **機械学習ベース推定**
   - ルールベースの限界を超えるため、教師あり学習モデルの導入
   - 2022-2025年の実測データを訓練データとして使用

4. **推定値のメタデータ記録**
   - 推定値と実測値を区別するため、`intensity_type_source`カラム追加（estimated/measured）
   - レポート生成時に推定値であることを明示（オプション）

---

## 参考資料

### 既存プロジェクト
- `docs/project/2025-10-17_intensity_aware_phase_evaluation/` - intensity_type活用の参考例
- `docs/project/2025-10-13_granular_duckdb_regeneration/` - データ再生成スクリプトの参考

### 関連ドキュメント
- `CLAUDE.md` - "Critical Data Sources" セクション
- `DEVELOPMENT_PROCESS.md` - TDD cycle workflow
- `tools/database/garmin_db_writer.py` - 実装対象ファイル

### データソース
- `data/raw/{activity_id}/splits.json` - Raw split data (lapDTOs)
- `splits` テーブル - DuckDB schema

### 検証結果（2025-10-26実施）
**検証アクティビティ:**
1. **Threshold** (2025-10-24, ID: 20783281578) - 88.9% (8/9 splits)
   - Pattern: WARMUP → INTERVAL × 4 → COOLDOWN
   - 誤判定: split 7をRECOVERYと判定（遅いペース）

2. **Sprint** (2025-10-11, ID: 20652528219) - 93.8% (15/16 splits)
   - Pattern: WARMUP → (INTERVAL → RECOVERY) × 6 → COOLDOWN
   - RESTを全てRECOVERYと正しく判定
   - 誤判定: split 3をACTIVEと判定（WARMUP期待）

3. **VO2 Max** (2025-10-07, ID: 20615445009) - 95.5% (21/22 splits)
   - Pattern: WARMUP → (INTERVAL → RECOVERY) × 9 → COOLDOWN
   - 誤判定: split 20をRECOVERYと判定（COOLDOWN期待）

**平均精度**: 92.7% (44/47 splits正解)

**アルゴリズム仕様:**
- Position-based: WARMUP (first 2), COOLDOWN (last 2)
- Pattern-based: RECOVERY (pace >400 after INTERVAL)
- Threshold-based: INTERVAL (pace <avg×0.90 OR hr >avg×1.1)
- Default: ACTIVE

---

## Implementation Notes

### Algorithm Details

**研究からの知見:**
```
Activity: 2021-01-02 (ID: 6040655748)
Total splits: 15
Actual labels: WARMUP (2), ACTIVE (11), COOLDOWN (2)

Estimated with thresholds (0.85, 0.90):
- WARMUP: splits 1-2 (HR < avg*0.85)
- ACTIVE: splits 3-13
- COOLDOWN: splits 14-15 (HR < avg*0.90)

Accuracy: 14/15 = 92.9%
Error: 1 split misclassified (split 13: ACTIVE → COOLDOWN, HR slightly low)
```

**Conservative Thresholds:**
- WARMUP threshold: 0.85 (strict, avoid false positives)
- COOLDOWN threshold: 0.90 (relaxed, allow gradual HR decrease)
- Position constraint: Only first/last 1-2 splits (avoid mid-run misclassification)

**Future Improvements:**
- Dynamic thresholds based on activity type
- Pace pattern analysis (acceleration/deceleration)
- Machine learning for complex patterns

---

## GitHub Issue Template

```markdown
**Title**: feat: Add intensity_type estimation for 2021 activities

**Labels**: enhancement, database

**Description**:
Implement rule-based intensity_type estimation for 2021 activities to enable phase-section-analyst training type evaluation.

**Background**:
- 2021 activities (121 total) have missing intensity_type data
- intensity_type is critical for phase-section-analyst evaluation
- Research shows 92.9% accuracy using rule-based algorithm

**Requirements**:
- Estimate intensity_type using HR + position patterns
- Apply estimation only to NULL values (preserve existing data)
- Achieve 85%+ accuracy
- No schema changes required

**Implementation**:
- Add `_estimate_intensity_type()` method to `GarminDBWriter`
- Update `insert_splits()` to call estimation for NULL values
- Add unit/integration tests

**Success Criteria**:
- All 2021 splits with NULL intensity_type are populated
- Estimation accuracy ≥85%
- All tests pass
- phase-section-analyst works for 2021 activities

**Related**:
- Planning: `docs/project/2025-10-26_intensity_type_estimation/planning.md`
```
