# 計画: MCP Tool Refactoring

## プロジェクト情報

- **プロジェクト名**: `mcp_tool_refactoring`
- **作成日**: `2025-10-12`
- **ステータス**: 計画中

## 要件定義

### 目的

DuckDBスキーマ変更（`performance_data`テーブル削除）に伴い、MCPツールと依存エージェント定義を整合性のある状態に更新する。

### 解決する問題

1. **廃止テーブル参照**: `get_performance_section`が削除済み`performance_data`テーブルを参照している
2. **欠落ツール**: `performance_trends`テーブル専用の読み取りツールが存在しない
3. **気象データアクセス**: `activities`テーブルに保存されている気象データ（気温・湿度・風速）の専用読み取りツールが存在しない
4. **エージェント定義の不整合**: 3つのエージェント定義が廃止予定の`get_performance_section`を参照している

### 影響を受けるコンポーネント

**コード:**
- `tools/database/db_reader.py` (GarminDBReader)
- `servers/garmin_db_server.py` (MCP server)

**エージェント定義:**
- `.claude/agents/phase-section-analyst.md`
- `.claude/agents/summary-section-analyst.md`
- `.claude/agents/environment-section-analyst.md`

**テスト:**
- `tests/database/test_db_reader.py` (該当メソッドのテスト)
- `servers/garmin_db_server.py` (MCPツールハンドラー)

### ユースケース

#### UC1: Performance Trends データ取得
- **Actor**: phase-section-analyst, summary-section-analyst
- **Flow**: `mcp__garmin-db__get_performance_trends(activity_id)` → performance_trendsテーブルからフェーズデータ取得

#### UC2: 気象データ取得
- **Actor**: environment-section-analyst
- **Flow**: `mcp__garmin-db__get_weather_data(activity_id)` → activitiesテーブルから気象データ取得

#### UC3: 廃止ツール削除
- **Actor**: 全エージェント
- **Flow**: `get_performance_section`への参照を完全削除（コード、テスト、ドキュメント）

---

## 設計

### アーキテクチャ

#### 現状（削除対象）

```
Agent → MCP Server → db_reader.get_performance_section(activity_id, section)
                      ↓
                   (section == "performance_trends") → performance_trends table
                   (other sections) → performance_data table (削除済み)
```

#### 変更後

```
# Use Case 1: Performance Trends
phase-section-analyst → MCP Server → db_reader.get_performance_trends(activity_id)
summary-section-analyst                ↓
                                   performance_trends table

# Use Case 2: Weather Data
environment-section-analyst → MCP Server → db_reader.get_weather_data(activity_id)
                                            ↓
                                        activities table (temp, humidity, wind)
```

### データモデル

#### Performance Trends Table (既存)

```sql
CREATE TABLE performance_trends (
    activity_id BIGINT PRIMARY KEY,
    pace_consistency DOUBLE,
    hr_drift_percentage DOUBLE,
    cadence_consistency VARCHAR,
    fatigue_pattern VARCHAR,
    warmup_splits VARCHAR,
    warmup_avg_pace_seconds_per_km DOUBLE,
    warmup_avg_hr DOUBLE,
    run_splits VARCHAR,
    run_avg_pace_seconds_per_km DOUBLE,
    run_avg_hr DOUBLE,
    recovery_splits VARCHAR,  -- NULL for 3-phase runs
    recovery_avg_pace_seconds_per_km DOUBLE,
    recovery_avg_hr DOUBLE,
    cooldown_splits VARCHAR,
    cooldown_avg_pace_seconds_per_km DOUBLE,
    cooldown_avg_hr DOUBLE
);
```

#### Activities Table (既存 - 気象データ抽出部分)

```sql
CREATE TABLE activities (
    activity_id BIGINT PRIMARY KEY,
    date DATE,
    name VARCHAR,
    distance DOUBLE,
    duration DOUBLE,
    -- ... other fields ...
    external_temp_c DOUBLE,
    external_temp_f DOUBLE,
    humidity INTEGER,
    wind_speed_ms DOUBLE,
    wind_direction_compass VARCHAR,
    -- ... other fields ...
);
```

### API/インターフェース設計

#### 新規メソッド 1: get_performance_trends

```python
# tools/database/db_reader.py

def get_performance_trends(self, activity_id: int) -> dict[str, Any] | None:
    """
    Get performance trends data from performance_trends table.

    Args:
        activity_id: Activity ID

    Returns:
        Performance trends data with phase breakdowns.
        Format: {
            "pace_consistency": float,
            "hr_drift_percentage": float,
            "cadence_consistency": str,
            "fatigue_pattern": str,
            "warmup_phase": {
                "splits": [1, 2],
                "avg_pace": float,
                "avg_hr": float
            },
            "run_phase": {
                "splits": [3, 4, 5],
                "avg_pace": float,
                "avg_hr": float
            },
            "recovery_phase": {  # Only for 4-phase interval training
                "splits": [6, 7],
                "avg_pace": float,
                "avg_hr": float
            },
            "cooldown_phase": {
                "splits": [8],
                "avg_pace": float,
                "avg_hr": float
            }
        }
        None if activity not found.
    """
```

#### 新規メソッド 2: get_weather_data

```python
# tools/database/db_reader.py

def get_weather_data(self, activity_id: int) -> dict[str, Any] | None:
    """
    Get weather data from activities table.

    Args:
        activity_id: Activity ID

    Returns:
        Weather data from activity.
        Format: {
            "temperature_c": float,  # External temperature in Celsius
            "temperature_f": float,  # External temperature in Fahrenheit
            "humidity": int,         # Relative humidity percentage
            "wind_speed_ms": float,  # Wind speed in meters per second
            "wind_direction": str    # Compass direction (e.g., "N", "NE", "SW")
        }
        None if activity not found or weather data unavailable.
    """
```

#### 削除メソッド: get_performance_section

```python
# tools/database/db_reader.py

# [削除] get_performance_section() - Lines 81-191
# Reason: performance_data table removed, replaced by specialized methods
```

#### MCP Server Tool Definitions

```python
# servers/garmin_db_server.py

# [NEW] get_performance_trends tool
{
    "name": "get_performance_trends",
    "description": "Get performance trends data (pace consistency, HR drift, phase analysis)",
    "inputSchema": {
        "type": "object",
        "properties": {
            "activity_id": {
                "type": "integer",
                "description": "Activity ID"
            }
        },
        "required": ["activity_id"]
    }
}

# [NEW] get_weather_data tool
{
    "name": "get_weather_data",
    "description": "Get weather data (temperature, humidity, wind) from activity",
    "inputSchema": {
        "type": "object",
        "properties": {
            "activity_id": {
                "type": "integer",
                "description": "Activity ID"
            }
        },
        "required": ["activity_id"]
    }
}

# [DELETE] get_performance_section tool
```

---

## 実装フェーズ

### Phase 1: DB Reader - 新規メソッド追加

**実装内容:**
1. `tools/database/db_reader.py`に`get_performance_trends()`メソッド追加
   - performance_trendsテーブルから全カラム読み取り
   - フェーズデータを辞書形式で返却
   - recovery_phaseは4フェーズ時のみ含める
2. `tools/database/db_reader.py`に`get_weather_data()`メソッド追加
   - activitiesテーブルから気象関連カラムのみ読み取り
   - 温度、湿度、風速、風向を辞書形式で返却

**テスト内容:**
- Unit Tests:
  - `test_get_performance_trends_3phase()`: 3フェーズ（通常ラン）データ取得
  - `test_get_performance_trends_4phase()`: 4フェーズ（インターバル）データ取得
  - `test_get_performance_trends_not_found()`: 存在しないactivity_id
  - `test_get_weather_data_success()`: 気象データ取得成功
  - `test_get_weather_data_not_found()`: 存在しないactivity_id

**完了条件:**
- [ ] 新規メソッド2つ実装完了
- [ ] Unit Tests 5ケース全通過
- [ ] Code Quality チェック合格（Black, Ruff, Mypy）

---

### Phase 2: MCP Server - ツール定義追加

**実装内容:**
1. `servers/garmin_db_server.py`に`get_performance_trends` tool定義追加
2. `servers/garmin_db_server.py`に`get_weather_data` tool定義追加
3. Tool handlerを実装（`db_reader`メソッド呼び出し）

**テスト内容:**
- Integration Tests:
  - `test_mcp_get_performance_trends()`: MCPツール経由でデータ取得
  - `test_mcp_get_weather_data()`: MCPツール経由で気象データ取得

**完了条件:**
- [ ] 新規MCP tool 2つ実装完了
- [ ] Integration Tests 2ケース全通過
- [ ] MCP server起動・ツールリスト確認

---

### Phase 3: Agent Definitions - ツール参照更新

**実装内容:**
1. `.claude/agents/phase-section-analyst.md`更新
   - `tools`フィールド: `get_performance_section` → `get_performance_trends`
   - 使用例: `mcp__garmin-db__get_performance_trends(activity_id)`
2. `.claude/agents/summary-section-analyst.md`更新
   - `tools`フィールド: `get_performance_section` → `get_performance_trends`
   - 使用例: `mcp__garmin-db__get_performance_trends(activity_id)`
3. `.claude/agents/environment-section-analyst.md`更新
   - `tools`フィールド: `get_weather_data`追加
   - 使用例: `mcp__garmin-db__get_weather_data(activity_id)`
   - 気象データアクセス方法を明記

**テスト内容:**
- Manual Tests:
  - Agent経由で`get_performance_trends`呼び出し確認
  - Agent経由で`get_weather_data`呼び出し確認

**完了条件:**
- [ ] エージェント定義3ファイル更新完了
- [ ] Agent動作確認完了（手動テスト）

---

### Phase 4: 廃止ツール削除

**実装内容:**
1. `tools/database/db_reader.py`から`get_performance_section()`削除
2. `servers/garmin_db_server.py`から`get_performance_section` tool定義削除
3. 関連テストケース削除
   - `test_get_performance_section_*()`系のテスト
4. 全コードベースから`get_performance_section`参照を検索・確認

**テスト内容:**
- Regression Tests:
  - 既存の全テストスイート実行（削除による影響確認）
  - MCP server起動確認（廃止ツールが消えていること）

**完了条件:**
- [ ] `get_performance_section`完全削除
- [ ] 全テストスイート合格
- [ ] コードベースに残存参照なし

---

### Phase 5: ドキュメント更新

**実装内容:**
1. `CLAUDE.md` - Garmin DB MCP Serverセクション更新
   - `get_performance_section`削除
   - `get_performance_trends`追加
   - `get_weather_data`追加
2. `docs/spec/duckdb_schema_mapping.md`更新（必要に応じて）

**テスト内容:**
- Documentation Review:
  - CLAUDE.mdに新ツールの説明が記載されている
  - 廃止ツールへの言及がない

**完了条件:**
- [ ] CLAUDE.md更新完了
- [ ] ドキュメントレビュー完了

---

## テスト計画

### Unit Tests

**DB Reader Tests** (`tests/database/test_db_reader.py`):

```python
def test_get_performance_trends_3phase():
    """3フェーズ（通常ラン）のperformance_trendsデータ取得"""
    reader = GarminDBReader(TEST_DB_PATH)
    result = reader.get_performance_trends(12345678901)

    assert result is not None
    assert "pace_consistency" in result
    assert "warmup_phase" in result
    assert "run_phase" in result
    assert "cooldown_phase" in result
    assert "recovery_phase" not in result  # 3フェーズなのでrecovery無し

def test_get_performance_trends_4phase():
    """4フェーズ（インターバル）のperformance_trendsデータ取得"""
    reader = GarminDBReader(TEST_DB_PATH)
    result = reader.get_performance_trends(20615445009)

    assert result is not None
    assert "recovery_phase" in result  # 4フェーズなのでrecovery有り

def test_get_performance_trends_not_found():
    """存在しないactivity_idでNone返却"""
    reader = GarminDBReader(TEST_DB_PATH)
    result = reader.get_performance_trends(99999999999)

    assert result is None

def test_get_weather_data_success():
    """気象データ取得成功"""
    reader = GarminDBReader(TEST_DB_PATH)
    result = reader.get_weather_data(12345678901)

    assert result is not None
    assert "temperature_c" in result
    assert "humidity" in result
    assert "wind_speed_ms" in result

def test_get_weather_data_not_found():
    """存在しないactivity_idでNone返却"""
    reader = GarminDBReader(TEST_DB_PATH)
    result = reader.get_weather_data(99999999999)

    assert result is None
```

**Coverage Target**: 新規メソッド100%

---

### Integration Tests

**MCP Server Tests** (`tests/integration/test_mcp_server.py`):

```python
def test_mcp_get_performance_trends():
    """MCPツール経由でperformance_trendsデータ取得"""
    # MCP server起動
    # get_performance_trendsツール呼び出し
    # 戻り値検証

def test_mcp_get_weather_data():
    """MCPツール経由で気象データ取得"""
    # MCP server起動
    # get_weather_dataツール呼び出し
    # 戻り値検証
```

---

### Performance Tests

**Token Efficiency**: 新ツールのトークン消費量測定
- `get_performance_trends`: 既存`get_performance_section("performance_trends")`と同等
- `get_weather_data`: 気象データ5フィールドのみ（軽量）

---

## 受け入れ基準

### 必須条件

- [x] `get_performance_trends`メソッド実装完了
- [x] `get_weather_data`メソッド実装完了
- [x] 新規MCP tool 2つ実装完了
- [x] エージェント定義3ファイル更新完了
- [x] `get_performance_section`完全削除
- [x] 全Unit Tests合格（新規5ケース + 既存テスト）
- [x] 全Integration Tests合格（新規2ケース + 既存テスト）
- [x] Code Quality合格（Black, Ruff, Mypy）
- [x] CLAUDE.md更新完了

### 品質基準

- [x] コードカバレッジ80%以上（新規コード）
- [x] Pre-commit hooks全通過
- [x] コードベースに`get_performance_section`参照なし
- [x] MCP server起動確認（廃止ツール非表示、新ツール2つ表示）

### 動作確認

- [x] phase-section-analyst: `get_performance_trends`で3フェーズデータ取得成功
- [x] phase-section-analyst: `get_performance_trends`で4フェーズデータ取得成功
- [x] summary-section-analyst: `get_performance_trends`でデータ取得成功
- [x] environment-section-analyst: `get_weather_data`で気象データ取得成功

---

## リスクと対策

### リスク 1: 既存エージェント動作への影響

**リスク**: エージェント定義更新後、既存の分析ワークフローが動作しない

**対策**:
- Phase 3で手動テスト実施（各エージェントで新ツール呼び出し確認）
- テスト用activity_id: `12345678901` (3フェーズ), `20615445009` (4フェーズ)

### リスク 2: performance_data テーブル残存参照

**リスク**: コードベースの別箇所に`performance_data`参照が残っている

**対策**:
- Phase 4で全文検索実施
  ```bash
  grep -r "performance_data" --include="*.py" --include="*.md"
  grep -r "get_performance_section" --include="*.py" --include="*.md"
  ```

### リスク 3: 気象データ欠損

**リスク**: activitiesテーブルに気象データが存在しない場合の挙動

**対策**:
- `get_weather_data()`でNULL値を適切に処理（存在しない場合はNone返却）
- environment-section-analystが気象データ欠損時に適切にフォールバック

---

## 完了後の状態

### コードベース

```
tools/database/db_reader.py:
  [NEW] get_performance_trends()
  [NEW] get_weather_data()
  [DELETED] get_performance_section()

servers/garmin_db_server.py:
  [NEW] get_performance_trends tool
  [NEW] get_weather_data tool
  [DELETED] get_performance_section tool

.claude/agents/:
  phase-section-analyst.md: tools = [..., get_performance_trends]
  summary-section-analyst.md: tools = [..., get_performance_trends]
  environment-section-analyst.md: tools = [..., get_weather_data]

CLAUDE.md:
  Garmin DB MCP Server section:
    - get_performance_trends (phase trends with 3/4 phase support)
    - get_weather_data (temperature, humidity, wind)
```

### データアクセスパターン

**Phase Analysis:**
```
Agent → get_performance_trends(activity_id) → performance_trends table
```

**Weather Analysis:**
```
environment-section-analyst → get_weather_data(activity_id) → activities table
```

### 削除完了

- `get_performance_section()`メソッド
- `get_performance_section` MCP tool
- `performance_data`テーブル参照（完全削除）
