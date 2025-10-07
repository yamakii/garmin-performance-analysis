# 計画: Planner Date Resolution

## 要件定義

### 目的
WorkflowPlannerを拡張し、日付またはActivity IDのどちらでも受け取れるようにする。日付からActivity IDを解決する機能を追加し、様々な場面で活用できるようMCP serverで公開する。

### 問題
現在のWorkflowPlannerは`execute_full_workflow(activity_id, date)`でactivity_idが必須。日付のみを指定してアクティビティを処理したい場合（例: `/analyze-activity 2025-10-07`）に対応できない。

### ユースケース

**UC1: 日付からActivity ID解決**
```python
planner = WorkflowPlanner()
activity_id = planner.resolve_activity_id(date="2025-10-07")
# → 20594901208
```

**UC2: 日付でワークフロー実行**
```python
planner = WorkflowPlanner()
result = planner.execute_full_workflow(date="2025-10-07")
# activity_idは内部で自動解決
```

**UC3: MCP経由でActivity ID取得**
```python
# MCP tool: mcp__garmin-db__get_activity_id_by_date
activity_data = mcp__garmin-db__get_activity_id_by_date(date="2025-10-07")
# → {"activity_id": 20594901208, "activity_name": "戸田市 - Base", ...}
```

**UC4: 複数アクティビティの日付**
```python
# 同じ日に複数アクティビティがある場合
activities = planner.get_activities_by_date("2025-10-07")
# → [{"activity_id": 123, "start_time": "06:00"}, {"activity_id": 456, "start_time": "18:00"}]
```

## 設計

### 1. WorkflowPlanner拡張

#### 既存メソッドの変更
```python
def execute_full_workflow(
    self,
    activity_id: int | None = None,  # Optional化
    date: str | None = None,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """
    Execute the full analysis workflow.

    Args:
        activity_id: Activity ID (optional if date is provided)
        date: Activity date YYYY-MM-DD (optional if activity_id is provided)
        force_regenerate: Force regeneration

    Raises:
        ValueError: If neither activity_id nor date is provided
        ValueError: If date has multiple activities and activity_id not specified
    """
    # Validate inputs
    if not activity_id and not date:
        raise ValueError("Either activity_id or date must be provided")

    # Resolve activity_id from date if needed
    if not activity_id:
        activity_id = self.resolve_activity_id(date)

    # Resolve date from activity_id if needed
    if not date:
        date = self._get_activity_date(activity_id)

    # Continue with workflow...
```

#### 新規メソッド: resolve_activity_id()
```python
def resolve_activity_id(self, date: str) -> int:
    """
    Resolve Activity ID from date.

    Priority:
    1. DuckDB activities.start_time_local
    2. Garmin API (via GarminIngestWorker)

    Args:
        date: Activity date (YYYY-MM-DD)

    Returns:
        Activity ID

    Raises:
        ValueError: If no activity found for date
        ValueError: If multiple activities found (user must specify activity_id)
    """
    # Try DuckDB first
    activities = self._get_activities_from_duckdb(date)

    if len(activities) == 1:
        return activities[0]["activity_id"]
    elif len(activities) > 1:
        raise ValueError(
            f"Multiple activities found for {date}. "
            f"Please specify activity_id. Found: {activities}"
        )

    # Try Garmin API
    activities = self._get_activities_from_api(date)

    if len(activities) == 0:
        raise ValueError(f"No activities found for {date}")
    elif len(activities) == 1:
        return activities[0]["activity_id"]
    else:
        raise ValueError(
            f"Multiple activities found for {date} in Garmin API. "
            f"Please specify activity_id. Found: {activities}"
        )
```

#### 新規メソッド: _get_activities_from_duckdb()
```python
def _get_activities_from_duckdb(self, date: str) -> list[dict[str, Any]]:
    """
    Get activities from DuckDB by date (start_time_local).

    Args:
        date: YYYY-MM-DD format

    Returns:
        List of activity dicts with activity_id, activity_name, start_time
    """
    import duckdb

    try:
        conn = duckdb.connect(str(self.db_path), read_only=True)
        result = conn.execute(
            """
            SELECT
                activity_id,
                activity_name,
                start_time_local,
                total_distance_km,
                total_time_seconds
            FROM activities
            WHERE DATE(start_time_local) = ?
            ORDER BY start_time_local
            """,
            [date]
        ).fetchall()
        conn.close()

        activities = []
        for row in result:
            activities.append({
                "activity_id": row[0],
                "activity_name": row[1],
                "start_time": str(row[2]),
                "distance_km": row[3],
                "duration_seconds": row[4],
            })

        return activities

    except Exception as e:
        logger.warning(f"DuckDB query failed: {e}")
        return []
```

#### 新規メソッド: _get_activities_from_api()
```python
def _get_activities_from_api(self, date: str) -> list[dict[str, Any]]:
    """
    Get activities from Garmin API by date.

    Args:
        date: YYYY-MM-DD format

    Returns:
        List of activity dicts with activity_id, activity_name
    """
    from tools.ingest.garmin_worker import GarminIngestWorker

    try:
        worker = GarminIngestWorker()
        client = worker.get_garmin_client()

        # Get activities for date
        activities_data = client.get_activities_fordate(date)

        activities = []
        for activity in activities_data:
            activities.append({
                "activity_id": activity.get("activityId"),
                "activity_name": activity.get("activityName"),
                "start_time": activity.get("startTimeLocal"),
                "distance_km": activity.get("distance", 0) / 1000,
                "duration_seconds": activity.get("duration"),
            })

        return activities

    except Exception as e:
        logger.error(f"Garmin API query failed: {e}")
        return []
```

### 2. MCP Server拡張 (garmin-db server)

#### 新規MCP Tool: get_activity_id_by_date
```python
# servers/garmin_db_server.py

@server.call_tool()
async def get_activity_id_by_date(date: str) -> dict[str, Any]:
    """
    Get activity ID and metadata by date.

    Args:
        date: Activity date (YYYY-MM-DD)

    Returns:
        Activity metadata dict or error if multiple/no activities
    """
    from tools.planner.workflow_planner import WorkflowPlanner

    planner = WorkflowPlanner()

    try:
        # Get all activities for date
        activities = planner._get_activities_from_duckdb(date)

        if len(activities) == 0:
            # Try API
            activities = planner._get_activities_from_api(date)

        if len(activities) == 0:
            return {
                "success": False,
                "error": f"No activities found for {date}",
                "activities": []
            }
        elif len(activities) == 1:
            return {
                "success": True,
                "activity_id": activities[0]["activity_id"],
                "activity_name": activities[0]["activity_name"],
                "start_time": activities[0]["start_time"],
                "distance_km": activities[0]["distance_km"],
                "duration_seconds": activities[0]["duration_seconds"],
            }
        else:
            return {
                "success": False,
                "error": f"Multiple activities found for {date}. Please specify activity_id.",
                "activities": activities
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "activities": []
        }
```

### 3. DuckDBスキーマ確認

**activities.start_time_localカラムの存在確認:**
- 現在の36カラムスキーマに`start_time_local TIMESTAMP`が含まれているか確認
- 含まれていない場合はスキーマ拡張が必要

## テスト計画

### Unit Tests

#### Test 1: test_resolve_activity_id_from_duckdb
- DuckDBに存在する日付でActivity ID解決
- 期待: 正しいactivity_idが返される

#### Test 2: test_resolve_activity_id_multiple_activities
- 同日に複数アクティビティがある場合
- 期待: ValueErrorが発生し、全アクティビティ情報が含まれる

#### Test 3: test_resolve_activity_id_not_found_duckdb
- DuckDBに存在しない日付でGarmin API使用
- 期待: APIから取得してactivity_idが返される

#### Test 4: test_resolve_activity_id_not_found_anywhere
- DuckDBにもAPIにも存在しない日付
- 期待: ValueErrorが発生

#### Test 5: test_execute_full_workflow_with_date_only
- dateのみ指定してワークフロー実行
- 期待: activity_idが自動解決され、ワークフロー実行

#### Test 6: test_execute_full_workflow_with_activity_id_only
- activity_idのみ指定してワークフロー実行（既存動作）
- 期待: dateが自動解決され、ワークフロー実行

#### Test 7: test_execute_full_workflow_no_args
- activity_idもdateも指定しない
- 期待: ValueError発生

### Integration Tests

#### Test 8: test_mcp_get_activity_id_by_date_single
- MCP toolで単一アクティビティの日付を指定
- 期待: success=True, activity_id返却

#### Test 9: test_mcp_get_activity_id_by_date_multiple
- MCP toolで複数アクティビティの日付を指定
- 期待: success=False, 全アクティビティリスト返却

#### Test 10: test_mcp_get_activity_id_by_date_not_found
- MCP toolで存在しない日付を指定
- 期待: success=False, error message返却

## 受け入れ基準

✅ `WorkflowPlanner.execute_full_workflow()`がdateのみで呼び出せる
✅ `WorkflowPlanner.execute_full_workflow()`がactivity_idのみで呼び出せる（後方互換性）
✅ 日付から単一アクティビティのIDを正しく解決できる
✅ 日付に複数アクティビティがある場合、適切なエラーメッセージを返す
✅ DuckDBにない場合、Garmin APIフォールバック動作
✅ MCP tool `get_activity_id_by_date`が正常動作
✅ 全Unit Tests、Integration Testsがパス
✅ Pre-commit hooks（black, ruff, mypy）が全てパス

## 実装の優先順位

**Phase 1 (必須):**
- [ ] `WorkflowPlanner.resolve_activity_id()`実装
- [ ] `WorkflowPlanner._get_activities_from_duckdb()`実装
- [ ] `WorkflowPlanner._get_activities_from_api()`実装
- [ ] `WorkflowPlanner.execute_full_workflow()`のシグネチャ変更
- [ ] Unit tests作成（7テスト）

**Phase 2 (必須):**
- [ ] MCP tool `get_activity_id_by_date`実装
- [ ] Integration tests作成（3テスト）

**Phase 3 (オプション):**
- [ ] `/analyze-activity`コマンド更新（日付対応）
- [ ] `start_time_local`カラムがない場合のスキーマ拡張

## 参考資料

- 既存実装: `tools/planner/workflow_planner.py`
- DuckDBスキーマ: `docs/spec/duckdb_schema_mapping.md`
- MCP server: `servers/garmin_db_server.py`
- Garmin API wrapper: `tools/ingest/garmin_worker.py`
