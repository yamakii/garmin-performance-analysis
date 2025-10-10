# 計画: Section Analyst Normalized Table Access

## Git Worktree情報
- **Worktree Path**: `../garmin-section_analyst_normalized_access/`
- **Branch**: `feature/section_analyst_normalized_access`
- **Base Branch**: `main`

## 要件定義

### 目的

セクション分析エージェントが削除された`performance_data`テーブルに依存せず、正規化テーブル（splits, form_efficiency, hr_efficiency, heart_rate_zones, vo2_max, lactate_threshold, performance_trends）に直接アクセスできるようにする。

### 解決する問題

**現状の問題:**
- `get_performance_section`ツールは削除された`performance_data`テーブルの`JSON`列に依存している（`performance_trends`以外）
- 正規化テーブル（splits, form_efficiency, hr_efficiency, heart_rate_zones, vo2_max, lactate_threshold）には既にデータが格納されているが、エージェントがアクセスできない
- エージェントが必要なデータを取得できず、分析が実行できない状態

**影響を受けるエージェント:**
- **efficiency-section-analyst**: form_efficiency, hr_efficiency, heart_rate_zones が必要
- **environment-section-analyst**: splits (terrain, elevation, environmental_conditions) が必要
- **phase-section-analyst**: performance_trends が必要（既に対応済み）
- **split-section-analyst**: splits (全フィールド) が必要
- **summary-section-analyst**: 複数テーブル（splits, form_efficiency, performance_trends）が必要

### ユースケース

1. **efficiency-section-analyst**: フォーム効率データを取得
   - `get_form_efficiency_summary(activity_id)` → form_efficiency テーブルから取得
   - `get_hr_efficiency_analysis(activity_id)` → hr_efficiency テーブルから取得
   - `get_heart_rate_zones_detail(activity_id)` → heart_rate_zones テーブルから取得

2. **environment-section-analyst**: 環境・地形データを取得
   - 既存の`get_splits_elevation(activity_id)`を使用（terrain_type, elevation_gain/loss）
   - `get_splits_all(activity_id)` → splits テーブルから全データ取得（environmental_conditions, wind_impact, temp_impact含む）

3. **split-section-analyst**: 全スプリットデータを取得
   - `get_splits_all(activity_id)` → splits テーブルから全22フィールド取得

4. **summary-section-analyst**: 複合データを取得
   - 複数の既存ツールと新規ツールを組み合わせて使用

---

## 設計

### アーキテクチャ

```
Section Analysis Agents
    ↓ (MCP call)
Garmin DB MCP Server (servers/garmin_db_server.py)
    ↓ (Python method call)
GarminDBReader (tools/database/db_reader.py)
    ↓ (SQL query)
DuckDB Normalized Tables
    - form_efficiency (20 columns)
    - hr_efficiency (13 columns)
    - heart_rate_zones (6 columns, 5 rows/activity)
    - vo2_max (6 columns)
    - lactate_threshold (8 columns)
    - splits (22 columns)
    - performance_trends (26 columns) [既存対応済み]
```

**データフロー:**
1. エージェントが新しいMCPツールを呼び出す
2. MCPサーバーがGarminDBReaderのメソッドを実行
3. GarminDBReaderが正規化テーブルをクエリ
4. 結果をJSON形式でエージェントに返却

### データモデル

**既存の正規化テーブル（DuckDB）:**

```sql
-- form_efficiency テーブル (20 columns)
CREATE TABLE form_efficiency (
    activity_id BIGINT PRIMARY KEY,
    gct_average DOUBLE,
    gct_min DOUBLE,
    gct_max DOUBLE,
    gct_std DOUBLE,
    gct_variability DOUBLE,
    gct_rating VARCHAR,
    gct_evaluation VARCHAR,
    vo_average DOUBLE,
    vo_min DOUBLE,
    vo_max DOUBLE,
    vo_std DOUBLE,
    vo_trend VARCHAR,
    vo_rating VARCHAR,
    vo_evaluation VARCHAR,
    vr_average DOUBLE,
    vr_min DOUBLE,
    vr_max DOUBLE,
    vr_std DOUBLE,
    vr_rating VARCHAR,
    vr_evaluation VARCHAR,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

-- hr_efficiency テーブル (13 columns)
CREATE TABLE hr_efficiency (
    activity_id BIGINT PRIMARY KEY,
    primary_zone VARCHAR,
    zone_distribution_rating VARCHAR,
    hr_stability VARCHAR,
    aerobic_efficiency VARCHAR,
    training_quality VARCHAR,
    zone2_focus BOOLEAN,
    zone4_threshold_work BOOLEAN,
    training_type VARCHAR,
    zone1_percentage DOUBLE,
    zone2_percentage DOUBLE,
    zone3_percentage DOUBLE,
    zone4_percentage DOUBLE,
    zone5_percentage DOUBLE,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

-- heart_rate_zones テーブル (6 columns, 5 rows per activity)
CREATE TABLE heart_rate_zones (
    activity_id BIGINT,
    zone_number INTEGER,
    zone_low_boundary INTEGER,
    zone_high_boundary INTEGER,
    time_in_zone_seconds DOUBLE,
    zone_percentage DOUBLE,
    PRIMARY KEY (activity_id, zone_number),
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

-- vo2_max テーブル (6 columns)
CREATE TABLE vo2_max (
    activity_id BIGINT PRIMARY KEY,
    precise_value DOUBLE,
    value DOUBLE,
    date DATE,
    fitness_age INTEGER,
    category INTEGER,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

-- lactate_threshold テーブル (8 columns)
CREATE TABLE lactate_threshold (
    activity_id BIGINT PRIMARY KEY,
    heart_rate INTEGER,
    speed_mps DOUBLE,
    date_hr TIMESTAMP,
    functional_threshold_power INTEGER,
    power_to_weight DOUBLE,
    weight DOUBLE,
    date_power TIMESTAMP,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

-- splits テーブル (22 columns)
CREATE TABLE splits (
    activity_id BIGINT,
    split_index INTEGER,
    distance DOUBLE,
    role_phase VARCHAR,
    pace_str VARCHAR,
    pace_seconds_per_km DOUBLE,
    heart_rate INTEGER,
    hr_zone VARCHAR,
    cadence DOUBLE,
    cadence_rating VARCHAR,
    power DOUBLE,
    power_efficiency VARCHAR,
    stride_length DOUBLE,
    ground_contact_time DOUBLE,
    vertical_oscillation DOUBLE,
    vertical_ratio DOUBLE,
    elevation_gain DOUBLE,
    elevation_loss DOUBLE,
    terrain_type VARCHAR,
    environmental_conditions VARCHAR,
    wind_impact VARCHAR,
    temp_impact VARCHAR,
    environmental_impact VARCHAR,
    PRIMARY KEY (activity_id, split_index),
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);
```

### API/インターフェース設計

#### GarminDBReader 新規メソッド

```python
class GarminDBReader:
    """Read-only DuckDB access for Garmin performance data."""

    # 新規メソッド #1: Form Efficiency Summary
    def get_form_efficiency_summary(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get form efficiency summary from form_efficiency table.

        Args:
            activity_id: Activity ID

        Returns:
            Form efficiency data with GCT, VO, VR metrics and ratings
            Format: {
                "gct": {"average": float, "min": float, "max": float, "std": float,
                        "variability": float, "rating": str, "evaluation": str},
                "vo": {"average": float, "min": float, "max": float, "std": float,
                       "trend": str, "rating": str, "evaluation": str},
                "vr": {"average": float, "min": float, "max": float, "std": float,
                       "rating": str, "evaluation": str}
            }
        """

    # 新規メソッド #2: HR Efficiency Analysis
    def get_hr_efficiency_analysis(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get HR efficiency analysis from hr_efficiency table.

        Args:
            activity_id: Activity ID

        Returns:
            HR efficiency data with zone distribution and training type
            Format: {
                "primary_zone": str,
                "zone_distribution_rating": str,
                "hr_stability": str,
                "aerobic_efficiency": str,
                "training_quality": str,
                "zone2_focus": bool,
                "zone4_threshold_work": bool,
                "training_type": str,
                "zone_percentages": {
                    "zone1": float,
                    "zone2": float,
                    "zone3": float,
                    "zone4": float,
                    "zone5": float
                }
            }
        """

    # 新規メソッド #3: Heart Rate Zones Detail
    def get_heart_rate_zones_detail(self, activity_id: int) -> dict[str, list[dict]] | None:
        """
        Get heart rate zones detail from heart_rate_zones table.

        Args:
            activity_id: Activity ID

        Returns:
            Heart rate zones data with boundaries and time distribution
            Format: {
                "zones": [
                    {
                        "zone_number": int,
                        "low_boundary": int,
                        "high_boundary": int,
                        "time_in_zone_seconds": float,
                        "zone_percentage": float
                    },
                    ...
                ]
            }
        """

    # 新規メソッド #4: VO2 Max Data
    def get_vo2_max_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get VO2 max data from vo2_max table.

        Args:
            activity_id: Activity ID

        Returns:
            VO2 max data with precise value, fitness age, and category
            Format: {
                "precise_value": float,
                "value": float,
                "date": str,
                "fitness_age": int,
                "category": int
            }
        """

    # 新規メソッド #5: Lactate Threshold Data
    def get_lactate_threshold_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get lactate threshold data from lactate_threshold table.

        Args:
            activity_id: Activity ID

        Returns:
            Lactate threshold data with HR, speed, and power metrics
            Format: {
                "heart_rate": int,
                "speed_mps": float,
                "date_hr": str,
                "functional_threshold_power": int,
                "power_to_weight": float,
                "weight": float,
                "date_power": str
            }
        """

    # 新規メソッド #6: All Splits Data (既存の軽量版を補完)
    def get_splits_all(self, activity_id: int) -> dict[str, list[dict]] | None:
        """
        Get all split data from splits table (全22フィールド).

        Args:
            activity_id: Activity ID

        Returns:
            Complete split data with all metrics
            Format: {
                "splits": [
                    {
                        "split_number": int,
                        "distance_km": float,
                        "role_phase": str,
                        "pace_str": str,
                        "avg_pace_seconds_per_km": float,
                        "avg_heart_rate": int,
                        "hr_zone": str,
                        "cadence": float,
                        "cadence_rating": str,
                        "power": float,
                        "power_efficiency": str,
                        "stride_length": float,
                        "ground_contact_time_ms": float,
                        "vertical_oscillation_cm": float,
                        "vertical_ratio_percent": float,
                        "elevation_gain_m": float,
                        "elevation_loss_m": float,
                        "terrain_type": str,
                        "environmental_conditions": str,
                        "wind_impact": str,
                        "temp_impact": str,
                        "environmental_impact": str
                    },
                    ...
                ]
            }
        """
```

#### Garmin DB MCP Server 新規ツール

```python
@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ... 既存ツール ...

        # 新規ツール #1
        Tool(
            name="get_form_efficiency_summary",
            description="Get form efficiency summary (GCT, VO, VR metrics) from form_efficiency table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),

        # 新規ツール #2
        Tool(
            name="get_hr_efficiency_analysis",
            description="Get HR efficiency analysis (zone distribution, training type) from hr_efficiency table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),

        # 新規ツール #3
        Tool(
            name="get_heart_rate_zones_detail",
            description="Get heart rate zones detail (boundaries, time distribution) from heart_rate_zones table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),

        # 新規ツール #4
        Tool(
            name="get_vo2_max_data",
            description="Get VO2 max data (precise value, fitness age, category) from vo2_max table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),

        # 新規ツール #5
        Tool(
            name="get_lactate_threshold_data",
            description="Get lactate threshold data (HR, speed, power) from lactate_threshold table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),

        # 新規ツール #6
        Tool(
            name="get_splits_all",
            description="Get all split data (22 fields) from splits table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
    ]
```

---

## 実装フェーズ

### Phase 1: GarminDBReader メソッド実装 (6メソッド)

**実装順序: TDD cycle (Red → Green → Refactor)**

#### 1.1 get_form_efficiency_summary
- **Test**: `test_get_form_efficiency_summary()` - form_efficiency テーブルから取得
- **Implementation**: SQLクエリでGCT, VO, VR全20列を取得、構造化辞書に変換
- **Refactor**: エラーハンドリング、ロギング追加

#### 1.2 get_hr_efficiency_analysis
- **Test**: `test_get_hr_efficiency_analysis()` - hr_efficiency テーブルから取得
- **Implementation**: SQLクエリで全13列を取得、zone_percentagesを構造化
- **Refactor**: Boolean値の型安全性確保

#### 1.3 get_heart_rate_zones_detail
- **Test**: `test_get_heart_rate_zones_detail()` - heart_rate_zones テーブルから5行取得
- **Implementation**: SQLクエリでzone_number順にソート、zones配列を構築
- **Refactor**: 空データケースの処理

#### 1.4 get_vo2_max_data
- **Test**: `test_get_vo2_max_data()` - vo2_max テーブルから取得
- **Implementation**: SQLクエリで6列を取得
- **Refactor**: データ欠損時のNone返却

#### 1.5 get_lactate_threshold_data
- **Test**: `test_get_lactate_threshold_data()` - lactate_threshold テーブルから取得
- **Implementation**: SQLクエリで8列を取得
- **Refactor**: TIMESTAMP型の文字列変換

#### 1.6 get_splits_all
- **Test**: `test_get_splits_all()` - splits テーブルから全22列取得
- **Implementation**: SQLクエリでsplit_index順にソート、全フィールドをマッピング
- **Refactor**: 既存の軽量版（get_splits_pace_hr, get_splits_form_metrics, get_splits_elevation）との一貫性確保

### Phase 2: Garmin DB MCP Server ツール追加 (6ツール)

**実装順序: TDD cycle (Red → Green → Refactor)**

#### 2.1 get_form_efficiency_summary ツール
- **Test**: MCPツール呼び出しテスト
- **Implementation**: `call_tool()`にget_form_efficiency_summaryケース追加
- **Refactor**: JSON serialization確認

#### 2.2 get_hr_efficiency_analysis ツール
- **Test**: MCPツール呼び出しテスト
- **Implementation**: `call_tool()`にget_hr_efficiency_analysisケース追加
- **Refactor**: Boolean値のJSON変換確認

#### 2.3 get_heart_rate_zones_detail ツール
- **Test**: MCPツール呼び出しテスト
- **Implementation**: `call_tool()`にget_heart_rate_zones_detailケース追加
- **Refactor**: 配列形式のJSON出力確認

#### 2.4 get_vo2_max_data ツール
- **Test**: MCPツール呼び出しテスト
- **Implementation**: `call_tool()`にget_vo2_max_dataケース追加
- **Refactor**: None値のJSON処理

#### 2.5 get_lactate_threshold_data ツール
- **Test**: MCPツール呼び出しテスト
- **Implementation**: `call_tool()`にget_lactate_threshold_dataケース追加
- **Refactor**: TIMESTAMP文字列化確認

#### 2.6 get_splits_all ツール
- **Test**: MCPツール呼び出しテスト
- **Implementation**: `call_tool()`にget_splits_allケース追加
- **Refactor**: 大容量データのトークン効率確認

### Phase 3: エージェント定義更新 (5エージェント)

**更新対象:**

#### 3.1 efficiency-section-analyst
- **Before**: `mcp__garmin-db__get_performance_section(activity_id, "form_efficiency_summary")`
- **After**:
  - `mcp__garmin-db__get_form_efficiency_summary(activity_id)`
  - `mcp__garmin-db__get_hr_efficiency_analysis(activity_id)`
  - `mcp__garmin-db__get_heart_rate_zones_detail(activity_id)`
- **Update**: `.claude/agents/efficiency-section-analyst.md` の tools リスト

#### 3.2 environment-section-analyst
- **Before**: `get_performance_section` (使えない状態)
- **After**:
  - `mcp__garmin-db__get_splits_all(activity_id)` （environmental_conditions, wind_impact, temp_impact取得）
  - `mcp__garmin-db__get_splits_elevation(activity_id)` （既存、terrain/elevation取得）
- **Update**: `.claude/agents/environment-section-analyst.md` の tools リスト

#### 3.3 phase-section-analyst
- **Before**: `mcp__garmin-db__get_performance_section(activity_id, "performance_trends")` （既に対応済み）
- **After**: 変更なし（既存ツールで正しく動作）
- **Update**: なし

#### 3.4 split-section-analyst
- **Before**: `get_performance_section` (使えない状態)
- **After**:
  - `mcp__garmin-db__get_splits_all(activity_id)` （全22フィールド取得）
- **Update**: `.claude/agents/split-section-analyst.md` の tools リスト

#### 3.5 summary-section-analyst
- **Before**: 複数の`get_performance_section`呼び出し
- **After**:
  - `mcp__garmin-db__get_splits_all(activity_id)`
  - `mcp__garmin-db__get_form_efficiency_summary(activity_id)`
  - `mcp__garmin-db__get_performance_section(activity_id, "performance_trends")`
  - `mcp__garmin-db__get_vo2_max_data(activity_id)` （新規）
  - `mcp__garmin-db__get_lactate_threshold_data(activity_id)` （新規）
- **Update**: `.claude/agents/summary-section-analyst.md` の tools リスト

### Phase 4: 統合テスト & 検証

#### 4.1 実データでの動作確認
- テストアクティビティ（例: 20464005432）で全エージェント実行
- DuckDBからの取得データが正しいか検証
- section_analysesテーブルへの保存確認

#### 4.2 トークン効率測定
- 新旧アプローチのトークン消費量比較
- 軽量版ツール（get_splits_pace_hr, get_splits_form_metrics, get_splits_elevation）との比較

#### 4.3 エラーケース検証
- データが存在しないactivity_idでの動作確認
- 部分的にデータが欠損している場合の処理確認

---

## テスト計画

### Unit Tests

#### GarminDBReader メソッドテスト (6メソッド × 3ケース = 18テスト)

**テストファイル**: `tests/database/test_db_reader_normalized.py`

1. **get_form_efficiency_summary**
   - [ ] `test_get_form_efficiency_summary_valid_data()` - 正常データ取得
   - [ ] `test_get_form_efficiency_summary_no_data()` - データなし時にNone返却
   - [ ] `test_get_form_efficiency_summary_data_structure()` - 返却構造が正しい (gct/vo/vr keys)

2. **get_hr_efficiency_analysis**
   - [ ] `test_get_hr_efficiency_analysis_valid_data()` - 正常データ取得
   - [ ] `test_get_hr_efficiency_analysis_no_data()` - データなし時にNone返却
   - [ ] `test_get_hr_efficiency_analysis_zone_percentages()` - zone_percentages構造が正しい

3. **get_heart_rate_zones_detail**
   - [ ] `test_get_heart_rate_zones_detail_valid_data()` - 5ゾーン取得
   - [ ] `test_get_heart_rate_zones_detail_no_data()` - データなし時に空配列返却
   - [ ] `test_get_heart_rate_zones_detail_sort_order()` - zone_number順にソート

4. **get_vo2_max_data**
   - [ ] `test_get_vo2_max_data_valid_data()` - 正常データ取得
   - [ ] `test_get_vo2_max_data_no_data()` - データなし時にNone返却
   - [ ] `test_get_vo2_max_data_data_structure()` - 6フィールド全て存在

5. **get_lactate_threshold_data**
   - [ ] `test_get_lactate_threshold_data_valid_data()` - 正常データ取得
   - [ ] `test_get_lactate_threshold_data_no_data()` - データなし時にNone返却
   - [ ] `test_get_lactate_threshold_data_timestamp_conversion()` - TIMESTAMP → 文字列変換

6. **get_splits_all**
   - [ ] `test_get_splits_all_valid_data()` - 全22フィールド取得
   - [ ] `test_get_splits_all_no_data()` - データなし時に空配列返却
   - [ ] `test_get_splits_all_field_completeness()` - 全フィールドが存在

### Integration Tests

**テストファイル**: `tests/integration/test_section_analysts_normalized.py`

1. **efficiency-section-analyst 統合テスト**
   - [ ] `test_efficiency_analyst_with_normalized_tables()` - 正規化テーブルから分析実行
   - [ ] `test_efficiency_analyst_data_completeness()` - form_efficiency + hr_efficiency + heart_rate_zones 全て取得

2. **environment-section-analyst 統合テスト**
   - [ ] `test_environment_analyst_with_splits_all()` - splits_all から環境データ取得
   - [ ] `test_environment_analyst_environmental_conditions()` - environmental_conditions, wind_impact, temp_impact 取得

3. **split-section-analyst 統合テスト**
   - [ ] `test_split_analyst_with_splits_all()` - splits_all から全データ取得
   - [ ] `test_split_analyst_field_completeness()` - 22フィールド全て利用可能

4. **summary-section-analyst 統合テスト**
   - [ ] `test_summary_analyst_with_multiple_tools()` - 複数ツールを組み合わせて分析
   - [ ] `test_summary_analyst_vo2_lactate_threshold()` - vo2_max, lactate_threshold データ取得

5. **MCP Server 統合テスト**
   - [ ] `test_mcp_server_tool_availability()` - 6つの新規ツールが利用可能
   - [ ] `test_mcp_server_tool_invocation()` - 各ツールが正しく呼び出せる

### Performance Tests

**テストファイル**: `tests/performance/test_normalized_access_performance.py`

1. **トークン効率測定**
   - [ ] `test_token_efficiency_splits_all_vs_lightweight()` - splits_all と軽量版のトークン比較
   - [ ] `test_token_efficiency_form_efficiency_vs_performance_data()` - 正規化テーブル vs performance_data JSON比較
   - [ ] 目標: 正規化テーブルアクセスでトークン削減（performance_dataテーブルが存在しないため比較不可の可能性あり）

2. **クエリパフォーマンス**
   - [ ] `test_query_performance_splits_all()` - 100アクティビティで平均クエリ時間 < 100ms
   - [ ] `test_query_performance_form_efficiency()` - 100アクティビティで平均クエリ時間 < 50ms
   - [ ] `test_query_performance_heart_rate_zones()` - 100アクティビティで平均クエリ時間 < 50ms

3. **並列アクセステスト**
   - [ ] `test_concurrent_agent_access()` - 5エージェント並列実行時のデータ整合性
   - [ ] 目標: 並列実行時もデータ競合なし

---

## 受け入れ基準

### 機能要件
- [ ] GarminDBReaderに6つの新規メソッドが実装されている
- [ ] Garmin DB MCP Serverに6つの新規ツールが登録されている
- [ ] 5つのセクション分析エージェント定義が更新されている
- [ ] efficiency-section-analystが正規化テーブルから分析実行できる
- [ ] environment-section-analystがsplitsテーブルから環境データ取得できる
- [ ] split-section-analystがsplitsテーブルから全データ取得できる
- [ ] summary-section-analystが複数のツールを組み合わせて分析実行できる

### テスト要件
- [ ] 全Unit Testsがパスする（18テスト）
- [ ] 全Integration Testsがパスする（9テスト）
- [ ] 全Performance Testsがパスする（6テスト）
- [ ] テストカバレッジ80%以上

### コード品質要件
- [ ] Black フォーマット済み
- [ ] Ruff lintエラーなし
- [ ] Mypy型チェックエラーなし
- [ ] Pre-commit hooks全てパス

### ドキュメント要件
- [ ] CLAUDE.md の "Garmin DB MCP Server" セクションに新規ツール追加
- [ ] 各エージェント定義ファイル (.claude/agents/*.md) に利用可能ツール更新
- [ ] completion_report.md 作成（実装完了後）

### 検証要件
- [ ] 実データ（activity_id: 20464005432）で5エージェント全て実行成功
- [ ] section_analysesテーブルに分析結果が正しく保存されている
- [ ] エラーログにデータアクセス失敗メッセージがない
- [ ] トークン効率が改善している（軽量版ツールと比較）

---

## リスク & 対策

### リスク1: performance_data テーブル削除の影響範囲不明
- **対策**: `get_performance_section` の使用箇所を全検索し、影響を事前確認
- **Mitigation**: performance_trends以外のsectionで`get_performance_section`を使用しているコードは既に機能していない前提

### リスク2: splits_all のトークン消費量が大きい
- **対策**: 既存の軽量版ツール（get_splits_pace_hr, get_splits_form_metrics, get_splits_elevation）を優先使用
- **Mitigation**: split-section-analyst のみ splits_all を使用し、他のエージェントは軽量版を推奨

### リスク3: エージェント定義の更新漏れ
- **対策**: 全5エージェントの定義ファイルをチェックリスト化
- **Mitigation**: 統合テストで各エージェントのツール使用を検証

---

## 実装後のメンテナンス

### 定期的な確認事項
1. 正規化テーブルスキーマ変更時の影響確認（db_writer.py との同期）
2. 新規エージェント追加時のツール選定ガイドライン更新
3. トークン効率の定期的な測定

### 今後の改善案
1. `get_performance_section` の完全削除（performance_trendsも正規化テーブルから直接取得）
2. キャッシュ機構の追加（頻繁にアクセスされるform_efficiency, hr_efficiencyデータ）
3. バッチ取得API（複数activity_idを一括取得）
