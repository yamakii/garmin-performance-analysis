# 計画: splits_comprehensive_mcp_tool

## プロジェクト情報

- **プロジェクト名**: `splits_comprehensive_mcp_tool`
- **作成日**: `2025-10-20`
- **ステータス**: 計画中
- **GitHub Issue**: [#37](https://github.com/yamakii/garmin-performance-analysis/issues/37)

---

## 要件定義

### 目的

split-section-analystエージェントが、splitsテーブルの全ての重要なフィールド（12フィールド）を1回の呼び出しで取得できる新しいMCPツール `get_splits_comprehensive()` を実装する。

### 解決する問題

**現状の制約:**
- split-section-analystは2つの軽量MCPツールのみ使用可能:
  - `get_splits_pace_hr()`: ペース、心拍のみ（4フィールド）
  - `get_splits_form_metrics()`: GCT、VO、VRのみ（4フィールド）

**問題:**
- splitsテーブルには他にも重要なフィールドが存在:
  - `power`: パワー出力（W）- 運動強度の客観的指標
  - `stride_length`: 歩幅（cm）- フォーム効率の指標
  - `cadence`: ケイデンス（spm）- リズムの指標
  - `elevation_gain/loss`: 標高変化（m）- 地形の影響評価
  - `max_heart_rate`: 最大心拍数（bpm）- 心拍スパイクの検出
  - `max_cadence`: 最大ケイデンス（spm）- リズムの乱れ検出

**影響:**
- これらのフィールドは現在レポートには表示されているが、エージェントは分析に使用できない
- エージェントが総合的なスプリット分析を行えない（データの一部のみしかアクセスできない）
- 2回のMCP呼び出しが必要で、トークン効率が最適でない

**解決策の利点:**
- 1回のMCP呼び出しで全ての重要なフィールドを取得可能
- split-section-analystがより詳細で総合的な分析を実施可能
- `statistics_only` パラメータで80%のトークン削減（既存ツールと同様）
- 既存ツールは維持（後方互換性確保）

### ユースケース

#### 1. split-section-analystによる総合的なスプリット分析
```python
# Before: 2回のMCP呼び出し + 限定的なデータ
pace_hr_data = mcp__garmin_db__get_splits_pace_hr(activity_id, statistics_only=True)
form_data = mcp__garmin_db__get_splits_form_metrics(activity_id, statistics_only=True)
# → elevation, power, stride_length, cadence は取得不可

# After: 1回のMCP呼び出し + 全データ
comprehensive_data = mcp__garmin_db__get_splits_comprehensive(activity_id, statistics_only=True)
# → 12フィールド全てを取得、パワーやケイデンスも分析可能
```

#### 2. 統計モードでのトレンド分析（デフォルト推奨）
```python
# statistics_only=True: 80%トークン削減、平均値・標準偏差・最大最小値のみ取得
data = mcp__garmin_db__get_splits_comprehensive(activity_id, statistics_only=True)

# 出力例:
{
    "activity_id": 12345,
    "statistics_only": true,
    "metrics": {
        "pace": {"mean": 305.5, "median": 303.0, "std": 12.3, "min": 290.0, "max": 325.0},
        "heart_rate": {"mean": 152, "median": 153, "std": 8, "min": 140, "max": 165},
        "power": {"mean": 240.5, "median": 238.0, "std": 18.2, "min": 210.0, "max": 275.0},
        "cadence": {"mean": 182.3, "median": 183.0, "std": 3.2, "min": 176.0, "max": 188.0},
        "stride_length": {"mean": 128.5, "median": 129.0, "std": 4.1, "min": 120.0, "max": 135.0},
        "ground_contact_time": {"mean": 242.0, "median": 241.0, "std": 5.2, "min": 235.0, "max": 250.0},
        "vertical_oscillation": {"mean": 8.5, "median": 8.4, "std": 0.5, "min": 7.8, "max": 9.2},
        "vertical_ratio": {"mean": 6.8, "median": 6.7, "std": 0.3, "min": 6.4, "max": 7.3},
        "elevation_gain": {"mean": 5.2, "median": 4.8, "std": 3.1, "min": 0.0, "max": 12.0},
        "elevation_loss": {"mean": 4.8, "median": 4.5, "std": 2.9, "min": 0.0, "max": 11.0},
        "max_heart_rate": {"mean": 165, "median": 166, "std": 5, "min": 158, "max": 172},
        "max_cadence": {"mean": 195.2, "median": 196.0, "std": 4.1, "min": 188.0, "max": 202.0}
    }
}
```

#### 3. フルモードでのスプリット間比較
```python
# statistics_only=False: スプリット毎の詳細データ取得（個別比較が必要な場合のみ）
data = mcp__garmin_db__get_splits_comprehensive(activity_id, statistics_only=False)

# 出力例:
{
    "splits": [
        {
            "split_number": 1,
            "distance_km": 1.0,
            "avg_pace_seconds_per_km": 310.5,
            "avg_heart_rate": 145,
            "ground_contact_time_ms": 245.0,
            "vertical_oscillation_cm": 8.8,
            "vertical_ratio_percent": 7.1,
            "power_watts": 225.0,
            "stride_length_cm": 125.0,
            "cadence_spm": 180.0,
            "elevation_gain_m": 2.5,
            "elevation_loss_m": 1.2,
            "max_heart_rate_bpm": 158,
            "max_cadence_spm": 192.0
        },
        # ... 残りのスプリット
    ]
}
```

---

## 設計

### アーキテクチャ

**システムコンポーネント:**
```
[split-section-analyst Agent]
        ↓
[MCP: get_splits_comprehensive()]  ← 新規実装
        ↓
[GarminDBReader.get_splits_comprehensive()]  ← 新規実装
        ↓
[SplitsReader.get_splits_comprehensive()]  ← 新規実装
        ↓
[DuckDB: splits table]
```

**実装レイヤー:**
1. **MCP Server Layer** (`servers/garmin_db_server.py`)
   - MCP Tool定義（inputSchema）
   - Tool handler実装（call_tool）

2. **Database Reader Layer** (`tools/database/db_reader.py`)
   - GarminDBReaderクラスにproxy method追加

3. **Splits Reader Layer** (`tools/database/readers/splits.py`)
   - SplitsReaderクラスに実装メソッド追加
   - SQL query実装（statistics mode / full mode）

### データモデル

**DuckDB Schema (splits table):**
取得対象の12フィールド:

| カテゴリ | フィールド名 | データ型 | 説明 | Population |
|---------|------------|---------|------|-----------|
| **ペース・心拍** | pace_seconds_per_km | DOUBLE | ペース（秒/km） | 100% |
| | heart_rate | INTEGER | 平均心拍数（bpm） | 100% |
| | max_heart_rate | INTEGER | 最大心拍数（bpm） | 100% |
| **フォーム指標** | ground_contact_time | DOUBLE | 接地時間（ms） | 100% |
| | vertical_oscillation | DOUBLE | 上下動（cm） | 100% |
| | vertical_ratio | DOUBLE | 上下動比率（%） | 100% |
| **パワー・リズム** | power | DOUBLE | パワー出力（W） | 39.8% |
| | stride_length | DOUBLE | 歩幅（cm） | 99.75% |
| | cadence | DOUBLE | ケイデンス（spm, total） | 100% |
| | max_cadence | DOUBLE | 最大ケイデンス（spm） | 100% |
| **地形** | elevation_gain | DOUBLE | 標高上昇（m） | 100% |
| | elevation_loss | DOUBLE | 標高下降（m） | 100% |

**注意事項:**
- `power` は39.8%のみ利用可能（デバイス依存）
- NULL値は適切にハンドリング（0.0へのfallback）

### API/インターフェース設計

#### 1. SplitsReader.get_splits_comprehensive()

```python
def get_splits_comprehensive(
    self, activity_id: int, statistics_only: bool = False
) -> dict[str, list[dict]] | dict[str, Any]:
    """
    Get comprehensive split data (12 fields) from splits table.

    Args:
        activity_id: Activity ID
        statistics_only: If True, return only aggregated statistics (mean, median, std, min, max)
                       instead of per-split data. Significantly reduces output size (~80% reduction).
                       Default: False (backward compatible)

    Returns:
        Full mode (statistics_only=False):
            Dict with 'splits' key containing list of split data with all 12 fields
        Statistics mode (statistics_only=True):
            Dict with aggregated statistics:
            {
                "activity_id": int,
                "statistics_only": True,
                "metrics": {
                    "pace": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "heart_rate": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "ground_contact_time": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "vertical_oscillation": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "vertical_ratio": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "power": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "stride_length": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "cadence": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "elevation_gain": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "elevation_loss": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "max_heart_rate": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                    "max_cadence": {"mean": float, "median": float, "std": float, "min": float, "max": float}
                }
            }
    """
```

#### 2. MCP Tool Schema

```python
Tool(
    name="get_splits_comprehensive",
    description="Get comprehensive split data (12 fields: pace, HR, form, power, cadence, elevation) from splits table. Supports statistics_only mode for 80% token reduction.",
    inputSchema={
        "type": "object",
        "properties": {
            "activity_id": {"type": "integer"},
            "statistics_only": {
                "type": "boolean",
                "description": "If true, return only aggregated statistics (mean, median, std, min, max) instead of per-split data. Reduces output size by ~80%. Default: false",
                "default": False,
            },
        },
        "required": ["activity_id"],
    },
)
```

#### 3. SQL Query (Statistics Mode)

```sql
-- Statistics mode: 12フィールドの統計量を計算
SELECT
    AVG(pace_seconds_per_km) as pace_mean,
    MEDIAN(pace_seconds_per_km) as pace_median,
    STDDEV(pace_seconds_per_km) as pace_std,
    MIN(pace_seconds_per_km) as pace_min,
    MAX(pace_seconds_per_km) as pace_max,

    AVG(heart_rate) as hr_mean,
    MEDIAN(heart_rate) as hr_median,
    STDDEV(heart_rate) as hr_std,
    MIN(heart_rate) as hr_min,
    MAX(heart_rate) as hr_max,

    AVG(ground_contact_time) as gct_mean,
    MEDIAN(ground_contact_time) as gct_median,
    STDDEV(ground_contact_time) as gct_std,
    MIN(ground_contact_time) as gct_min,
    MAX(ground_contact_time) as gct_max,

    AVG(vertical_oscillation) as vo_mean,
    MEDIAN(vertical_oscillation) as vo_median,
    STDDEV(vertical_oscillation) as vo_std,
    MIN(vertical_oscillation) as vo_min,
    MAX(vertical_oscillation) as vo_max,

    AVG(vertical_ratio) as vr_mean,
    MEDIAN(vertical_ratio) as vr_median,
    STDDEV(vertical_ratio) as vr_std,
    MIN(vertical_ratio) as vr_min,
    MAX(vertical_ratio) as vr_max,

    AVG(power) as power_mean,
    MEDIAN(power) as power_median,
    STDDEV(power) as power_std,
    MIN(power) as power_min,
    MAX(power) as power_max,

    AVG(stride_length) as stride_mean,
    MEDIAN(stride_length) as stride_median,
    STDDEV(stride_length) as stride_std,
    MIN(stride_length) as stride_min,
    MAX(stride_length) as stride_max,

    AVG(cadence) as cadence_mean,
    MEDIAN(cadence) as cadence_median,
    STDDEV(cadence) as cadence_std,
    MIN(cadence) as cadence_min,
    MAX(cadence) as cadence_max,

    AVG(elevation_gain) as gain_mean,
    MEDIAN(elevation_gain) as gain_median,
    STDDEV(elevation_gain) as gain_std,
    MIN(elevation_gain) as gain_min,
    MAX(elevation_gain) as gain_max,

    AVG(elevation_loss) as loss_mean,
    MEDIAN(elevation_loss) as loss_median,
    STDDEV(elevation_loss) as loss_std,
    MIN(elevation_loss) as loss_min,
    MAX(elevation_loss) as loss_max,

    AVG(max_heart_rate) as max_hr_mean,
    MEDIAN(max_heart_rate) as max_hr_median,
    STDDEV(max_heart_rate) as max_hr_std,
    MIN(max_heart_rate) as max_hr_min,
    MAX(max_heart_rate) as max_hr_max,

    AVG(max_cadence) as max_cad_mean,
    MEDIAN(max_cadence) as max_cad_median,
    STDDEV(max_cadence) as max_cad_std,
    MIN(max_cadence) as max_cad_min,
    MAX(max_cadence) as max_cad_max
FROM splits
WHERE activity_id = ?
```

#### 4. SQL Query (Full Mode)

```sql
-- Full mode: 12フィールドのスプリット毎データを取得
SELECT
    split_index,
    distance,
    pace_seconds_per_km,
    heart_rate,
    ground_contact_time,
    vertical_oscillation,
    vertical_ratio,
    power,
    stride_length,
    cadence,
    elevation_gain,
    elevation_loss,
    max_heart_rate,
    max_cadence
FROM splits
WHERE activity_id = ?
ORDER BY split_index
```

---

## 実装フェーズ

### Phase 1: Core Implementation（TDD）

#### 1.1 SplitsReader.get_splits_comprehensive() 実装
**タスク:**
- `tools/database/readers/splits.py` に新メソッド追加
- Statistics mode実装（DuckDB aggregate functions使用）
- Full mode実装（全スプリットデータ取得）
- NULL値ハンドリング（0.0へのfallback）
- エラーハンドリング（空データ、例外処理）

**参考実装:**
- `get_splits_pace_hr()` - 既存の統計モード実装パターン
- `get_splits_form_metrics()` - 既存のフィールドマッピングパターン

**実装方針:**
- 既存ツールと同じアーキテクチャを踏襲
- DuckDBの集約関数（AVG, MEDIAN, STDDEV, MIN, MAX）を活用
- try-exceptブロックで安全に処理

#### 1.2 GarminDBReader.get_splits_comprehensive() proxy 追加
**タスク:**
- `tools/database/db_reader.py` にproxy method追加
- SplitsReaderへの呼び出しを転送

**実装例:**
```python
def get_splits_comprehensive(
    self, activity_id: int, statistics_only: bool = False
) -> dict[str, list[dict]] | dict[str, Any]:
    """Proxy to SplitsReader.get_splits_comprehensive()."""
    return self.splits_reader.get_splits_comprehensive(activity_id, statistics_only)
```

#### 1.3 MCP Server統合
**タスク:**
- `servers/garmin_db_server.py` にMCP Tool定義追加（`list_tools()` 関数）
- `call_tool()` 関数にhandler追加

**実装箇所:**
- `list_tools()`: Tool定義追加（`get_splits_elevation` の後に追加）
- `call_tool()`: handler追加（`get_splits_elevation` の後に追加）

**実装例:**
```python
# In call_tool()
elif name == "get_splits_comprehensive":
    activity_id = arguments["activity_id"]
    statistics_only = arguments.get("statistics_only", False)
    result = db_reader.get_splits_comprehensive(
        activity_id, statistics_only=statistics_only
    )
    return [
        TextContent(
            type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
        )
    ]
```

#### 1.4 Unit Tests実装
**ファイル:** `tests/unit/test_splits_reader.py`

**テストケース:**
- [ ] `test_get_splits_comprehensive_statistics_mode` - 統計モードのテスト
  - 統計量が正しく計算されている（mean, median, std, min, max）
  - 12メトリクス全てが含まれている
  - フォーマットが正しい（activity_id, statistics_only, metrics）

- [ ] `test_get_splits_comprehensive_full_mode` - フルモードのテスト
  - 全スプリットデータが返される
  - 12フィールド全てが含まれている
  - split_indexでソートされている

- [ ] `test_get_splits_comprehensive_null_handling` - NULL値ハンドリング
  - NULL値が0.0にfallbackされる
  - powerがNULLの場合でも正常動作

- [ ] `test_get_splits_comprehensive_no_data` - データなしケース
  - 空の結果が返される（エラーにならない）
  - statistics_only=True: {"activity_id": X, "statistics_only": True, "metrics": {}}
  - statistics_only=False: {"splits": []}

- [ ] `test_get_splits_comprehensive_error_handling` - エラーハンドリング
  - 例外が発生しても安全に処理される
  - 空の結果が返される

**テスト戦略:**
- Mock data使用（実データベース不要）
- `@pytest.fixture` でmock reader作成
- `mocker.Mock()` でDuckDB接続をモック

#### 1.5 Integration Tests実装
**ファイル:** `tests/integration/test_splits_reader_integration.py`

**テストケース:**
- [ ] `test_get_splits_comprehensive_real_data` - 実データテスト
  - 実際のDuckDBデータベースを使用
  - statistics_only=True/Falseの両モードをテスト
  - データの整合性を確認

- [ ] `test_get_splits_comprehensive_completeness` - データ完全性テスト
  - 12フィールド全てが存在する
  - NULLではないフィールドが適切に処理される

**テスト戦略:**
- 実データベースを使用（skip if unavailable）
- 既知のactivity_idでテスト
- データの整合性を検証

### Phase 2: Agent Integration

#### 2.1 split-section-analyst プロンプト更新
**ファイル:** `.claude/agents/split-section-analyst.md`

**更新内容:**
- **ツールリストに追加**: `mcp__garmin-db__get_splits_comprehensive()`
- **使用ガイドライン追加**:
  - デフォルトで `statistics_only=True` を使用（トークン効率化）
  - 個別スプリット比較が必要な場合のみ `statistics_only=False` を使用
  - 既存の2ツール（pace_hr, form_metrics）も引き続き利用可能（後方互換性）

- **分析ガイドライン拡張**:
  - **パワー評価基準**:
    - W/kg比率で評価（体重から計算）
    - Excellent: ≥4.0 W/kg, Good: 3.0-3.9 W/kg, Fair: 2.0-2.9 W/kg, Low: <2.0 W/kg
    - トレンド分析: スプリット間のパワー変動（疲労指標）

  - **歩幅評価基準**:
    - 理想的な歩幅: 身長 × 0.65 程度
    - 疲労指標: スプリット間での歩幅低下（疲労蓄積）
    - ケイデンスとの関係: 歩幅 × ケイデンス ≈ ペース

  - **ケイデンス評価基準**（既存のcadence_ratingを活用）:
    - Excellent: ≥190 spm, Good: 180-189 spm, Fair: 170-179 spm, Low: <170 spm
    - 最大ケイデンス（max_cadence）との比較でリズムの乱れを検出

  - **標高統合評価**（既存のelevation_gain/lossを活用）:
    - 上り区間: ペース低下とパワー上昇は正常
    - 下り区間: ペース上昇とパワー低下は正常
    - 地形適応能力: 標高変化に対するペース調整の適切性

**プロンプト例:**
```markdown
## 使用するMCPツール

**推奨ツール（これらのみ使用可能）:**
- `mcp__garmin-db__get_splits_comprehensive(activity_id, statistics_only=True)` - 全スプリットデータ（12フィールド、統計モード推奨）
  - デフォルトで `statistics_only=True` を使用（80%トークン削減）
  - 個別スプリット比較が必要な場合のみ `statistics_only=False` を使用

**代替ツール（後方互換性のため維持）:**
- `mcp__garmin-db__get_splits_pace_hr(activity_id, statistics_only=False)` - ペース・心拍のみ
- `mcp__garmin-db__get_splits_form_metrics(activity_id, statistics_only=False)` - フォーム指標のみ

## 分析ガイドライン拡張

4. **パワー評価**
   - W/kg比率: >4.0 = Excellent, 3.0-3.9 = Good, 2.0-2.9 = Fair, <2.0 = Low
   - スプリット間のパワー変動: >15%低下 = 疲労蓄積
   - 地形との関係: 上りでパワー上昇は正常

5. **歩幅評価**
   - 理想的な歩幅: 身長 × 0.65程度
   - 疲労指標: スプリット間で5%以上低下 = 疲労蓄積
   - ケイデンスとの関係: stride_length × cadence ≈ speed

6. **ケイデンス評価**
   - 目標範囲: 180-190 spm（エリートランナー基準）
   - max_cadenceとの比較: 10 spm以上の差 = リズムの乱れ
   - スプリット間の安定性: ±5 spm以内が理想
```

#### 2.2 Validation Test（手動実行）
**タスク:**
- 実際のactivity_idで split-section-analyst を実行
- 新しいツールが正しく使用されているか確認
- 分析内容にパワー、歩幅、ケイデンスの評価が含まれているか確認

**検証項目:**
- [ ] `get_splits_comprehensive()` が呼び出されている
- [ ] `statistics_only=True` がデフォルトで使用されている
- [ ] パワー評価が含まれている
- [ ] 歩幅評価が含まれている
- [ ] ケイデンス評価が含まれている
- [ ] 既存の分析品質が維持されている

### Phase 3: Documentation

#### 3.1 CLAUDE.md更新
**ファイル:** `CLAUDE.md`

**更新箇所:**
- **Activity Analysis セクション** → **Essential MCP Tools** に追加
- **Tool Development セクション** → 参照用に記載

**追加内容:**
```markdown
### Essential MCP Tools

**Performance Metrics:**
- `get_performance_trends(activity_id)` - Pace consistency, HR drift, phases
- `get_splits_comprehensive(activity_id, statistics_only=True/False)` - **NEW:** All split data (12 fields: pace, HR, form, power, cadence, elevation)
- `get_splits_pace_hr(activity_id, statistics_only=True/False)` - Pace/HR data (lightweight, backward compatible)
- `get_splits_form_metrics(activity_id, statistics_only=True/False)` - GCT/VO/VR (lightweight, backward compatible)
- `get_splits_elevation(activity_id, statistics_only=True/False)` - Terrain data

**Token Optimization:**
- Use `statistics_only=True` for overview/trends (80% reduction)
- Use `statistics_only=False` only when per-split details needed
- NEW: `get_splits_comprehensive()` provides all 12 fields in one call (recommended for split-section-analyst)
```

#### 3.2 DuckDB Schema Documentation更新
**ファイル:** `docs/spec/duckdb_schema_mapping.md`

**更新箇所:**
- **Section 2 (splits table)** に新MCPツールの情報を追加

**追加内容:**
```markdown
### MCP Tools for Splits Data

**Comprehensive Tool (Recommended):**
- `mcp__garmin-db__get_splits_comprehensive(activity_id, statistics_only=True/False)`
  - **Fields**: 12 fields (pace, HR, GCT, VO, VR, power, stride_length, cadence, elevation_gain/loss, max_HR, max_cadence)
  - **Token Optimization**: 80% reduction with `statistics_only=True`
  - **Use Case**: Complete split analysis in one call

**Lightweight Tools (Backward Compatible):**
- `mcp__garmin-db__get_splits_pace_hr()` - 4 fields (pace, HR, max_HR, distance)
- `mcp__garmin-db__get_splits_form_metrics()` - 4 fields (GCT, VO, VR, split_index)
- `mcp__garmin-db__get_splits_elevation()` - 5 fields (elevation_gain/loss, terrain_type, split_index, distance)
```

---

## テスト計画

### Unit Tests

**ファイル:** `tests/unit/test_splits_reader.py`

- [x] Mock fixtures作成
  - [ ] `mock_duckdb_connection` - DuckDB接続のモック
  - [ ] `mock_splits_comprehensive_stats` - 統計モードのモックデータ
  - [ ] `mock_splits_comprehensive_full` - フルモードのモックデータ

- [x] Statistics Mode Tests
  - [ ] 統計量が正しく計算されている
  - [ ] 12メトリクス全てが含まれている
  - [ ] フォーマットが正しい

- [x] Full Mode Tests
  - [ ] 全スプリットデータが返される
  - [ ] 12フィールド全てが含まれている
  - [ ] split_indexでソートされている

- [x] Edge Cases
  - [ ] NULL値ハンドリング（0.0へのfallback）
  - [ ] データなしケース（空の結果）
  - [ ] エラーハンドリング（例外処理）

**カバレッジ目標:** ≥80%

### Integration Tests

**ファイル:** `tests/integration/test_splits_reader_integration.py`

- [x] Real Database Tests
  - [ ] 実際のDuckDBデータベースを使用
  - [ ] statistics_only=True/Falseの両モードをテスト
  - [ ] データの整合性を確認

- [x] Data Completeness Tests
  - [ ] 12フィールド全てが存在する
  - [ ] NULLではないフィールドが適切に処理される
  - [ ] 既存ツール（pace_hr, form_metrics）との整合性確認

**実行条件:** DuckDBデータベースが存在する場合のみ実行（skip if unavailable）

### Agent Validation Tests

**手動実行:**
- [x] split-section-analystでの実行テスト
  - [ ] activity_idを指定して実行
  - [ ] 新しいツールが使用されているか確認
  - [ ] 分析内容にパワー、歩幅、ケイデンスの評価が含まれているか確認
  - [ ] 既存の分析品質が維持されているか確認

---

## 受け入れ基準

### 機能要件
- [ ] `SplitsReader.get_splits_comprehensive()` が実装されている
- [ ] `statistics_only=True` モードが正しく動作する（80%トークン削減）
- [ ] `statistics_only=False` モードが正しく動作する（全スプリットデータ）
- [ ] 12フィールド全てが正しく取得される
- [ ] NULL値が適切にハンドリングされる（0.0へのfallback）
- [ ] MCP Server統合が完了している（Tool定義 + handler）

### テスト要件
- [ ] 全Unit Testsが合格する
- [ ] 全Integration Testsが合格する（データベースが利用可能な場合）
- [ ] カバレッジ≥80%
- [ ] split-section-analystでの動作確認が完了している

### コード品質要件
- [ ] Pre-commit hooksが全てパスする
  - [ ] Black (formatting)
  - [ ] Ruff (linting)
  - [ ] Mypy (type checking)
- [ ] Type hintsが適切に定義されている
- [ ] Docstringsが完備されている（Google Style）
- [ ] Logging処理が適切に実装されている

### ドキュメント要件
- [ ] CLAUDE.mdが更新されている（Activity Analysis + Tool Development）
- [ ] `duckdb_schema_mapping.md` が更新されている
- [ ] `.claude/agents/split-section-analyst.md` が更新されている
- [ ] completion_report.md が作成されている

### 後方互換性要件
- [ ] 既存ツール（`get_splits_pace_hr`, `get_splits_form_metrics`）は変更なし
- [ ] 既存のテストは全て合格する
- [ ] 既存のエージェントは引き続き動作する

---

## リスクと対策

### リスク1: NULL値の多いフィールド（power: 39.8%）
**影響:** パワーデータがない場合、分析が不完全になる
**対策:**
- NULL値を0.0にfallbackして、"データなし"として扱う
- split-section-analystのプロンプトに「パワーデータがない場合は分析をスキップ」を明記
- 統計モードでは、NULL値を除外して計算（DuckDBのAVGは自動的にNULLを除外）

### リスク2: トークンサイズの増加
**影響:** フルモードで12フィールドを返すと、トークンサイズが増加する
**対策:**
- デフォルトで `statistics_only=True` を推奨（80%削減）
- split-section-analystのプロンプトに「デフォルトで統計モードを使用」を明記
- 個別スプリット比較が必要な場合のみフルモードを使用

### リスク3: 既存ツールとの重複
**影響:** 機能が重複しているため、どのツールを使うべきか混乱する
**対策:**
- 後方互換性のため、既存ツールは削除しない
- CLAUDE.mdに「推奨ツール」として `get_splits_comprehensive()` を明記
- split-section-analystのプロンプトに使用ガイドラインを明記

---

## タイムライン（目安）

- **Phase 1 (Core Implementation)**: 2-3時間
  - SplitsReader実装: 1時間
  - MCP統合: 0.5時間
  - Unit Tests: 1時間
  - Integration Tests: 0.5時間

- **Phase 2 (Agent Integration)**: 1時間
  - split-section-analystプロンプト更新: 0.5時間
  - Validation Test: 0.5時間

- **Phase 3 (Documentation)**: 0.5時間
  - CLAUDE.md更新: 0.25時間
  - Schema documentation更新: 0.25時間

**Total:** 3.5-4.5時間

---

## 参考資料

### 既存実装
- `tools/database/readers/splits.py` - SplitsReaderクラス
  - `get_splits_pace_hr()` - 統計モード実装パターン
  - `get_splits_form_metrics()` - フィールドマッピングパターン
  - `get_splits_elevation()` - エラーハンドリングパターン

- `servers/garmin_db_server.py` - MCP Server
  - `list_tools()` - Tool定義パターン
  - `call_tool()` - Handler実装パターン

### DuckDB Schema
- `docs/spec/duckdb_schema_mapping.md` - Section 2 (splits table)
  - 12フィールドの定義
  - Population率
  - NULL値の扱い

### エージェント
- `.claude/agents/split-section-analyst.md` - Split Section Analystエージェント
  - 現在の分析ガイドライン
  - 使用中のMCPツール
  - 出力形式

---

## 完了後の次のステップ

1. **GitHub Issue作成** - プロジェクト完了後にIssueをCloseする
2. **Completion Report作成** - `completion_report.md` を生成
3. **プロジェクトアーカイブ** - `docs/project/_archived/` に移動
4. **Future Enhancement検討**:
   - 他のエージェントでの活用可能性検討
   - さらなるトークン最適化（フィールド選択機能など）
   - 他のテーブルへの同様のアプローチ展開
