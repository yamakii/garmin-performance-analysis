# 計画: Form Anomaly API Refactoring

## プロジェクト情報
- **プロジェクト名**: `form_anomaly_api_refactoring`
- **作成日**: `2025-10-13`
- **ステータス**: 計画中
- **GitHub Issue**: [#22](https://github.com/yamakii/garmin-performance-analysis/issues/22)

## 要件定義

### 目的
現在の `detect_form_anomalies()` MCP ツールの極端なトークン消費問題（~14.3k tokens/call）を解決し、マルチアクティビティ分析を実用可能にする。サマリーAPIで95%のトークン削減（~700 tokens）、詳細APIで柔軟なフィルタリングを実現する。

### 解決する問題

**現状の課題:**
1. **トークン消費が極端に大きい**: 1回の呼び出しで14.3k tokens消費
2. **マルチアクティビティ分析が不可能**: 複数のアクティビティを分析すると即座にコンテキストウィンドウを使い果たす
3. **柔軟性の欠如**: すべての詳細情報を返すため、サマリーだけ欲しい場合も全データを取得
4. **詳細分析のフィルタリング不可**: 特定の異常やメトリック、時間範囲だけを取得できない

**根本原因:**
- 全異常の詳細（context windows, cause analysis, full metrics）を単一レスポンスで返却
- ユーザーがサマリーだけ必要な場合も全データを取得

### ユースケース

1. **マルチアクティビティ概要取得** (Primary Use Case)
   - 複数のアクティビティで異常発生頻度を比較
   - トークン消費: 700 tokens/activity × 10 activities = 7,000 tokens
   - 現状比: 143k tokens → 7k tokens (95% reduction)

2. **特定異常の深掘り分析**
   - サマリーAPIで異常を特定
   - 詳細APIで特定のanomaly IDsまたは時間範囲のみ取得
   - トークン消費: 700 (summary) + 2,000 (filtered details) = 2,700 tokens

3. **メトリック別異常分析**
   - GCT、VO、VRの異常を個別に分析
   - 詳細APIでメトリックフィルタリング
   - トークン消費: 700 (summary) + 1,500 (metric-filtered) = 2,200 tokens

4. **原因別異常分析**
   - Elevation、Pace、Fatigueによる異常を分類
   - 詳細APIで原因フィルタリング
   - トークン消費: 700 (summary) + 1,800 (cause-filtered) = 2,500 tokens

---

## 設計

### アーキテクチャ

**API分割戦略:**

```
FormAnomalyDetector
├── detect_form_anomalies_summary()    # NEW: Lightweight summary
│   ├── _extract_time_series()         # REFACTOR: Shared helper
│   ├── _detect_all_anomalies()        # REFACTOR: Shared helper
│   ├── _generate_severity_distribution()  # NEW
│   ├── _generate_temporal_clusters()  # NEW
│   └── _generate_recommendations()    # EXISTING (reuse)
│
├── get_form_anomaly_details()         # NEW: Filtered details
│   ├── _extract_time_series()         # REFACTOR: Shared helper
│   ├── _detect_all_anomalies()        # REFACTOR: Shared helper
│   └── _apply_anomaly_filters()       # NEW
│
└── detect_form_anomalies()            # REMOVE: Legacy API
```

**Token Optimization Strategy:**

| API | Token Count | Content | Use Case |
|-----|-------------|---------|----------|
| `detect_form_anomalies_summary()` | ~700 | Activity ID, total count, summary stats, temporal clusters, top 5 anomalies, recommendations | Multi-activity overview |
| `get_form_anomaly_details()` | Variable | Filtered anomaly details (context, causes, full metrics) | Detailed analysis |
| `detect_form_anomalies()` (REMOVE) | ~14,300 | All anomaly details | ❌ Deprecated |

### API設計

#### 1. `detect_form_anomalies_summary()` - Lightweight Summary API

**Purpose:** Provide high-level overview of anomalies for an activity (~700 tokens, 95% reduction)

**Signature:**
```python
def detect_form_anomalies_summary(
    self,
    activity_id: int,
    metrics: list[str] | None = None,
    z_threshold: float = 2.0,
) -> dict[str, Any]:
    """Detect form anomalies and return lightweight summary only.

    Args:
        activity_id: Activity ID.
        metrics: List of metric names to analyze
                (default: ["directGroundContactTime",
                           "directVerticalOscillation",
                           "directVerticalRatio"]).
        z_threshold: Z-score threshold for anomaly detection (default: 2.0).

    Returns:
        Dictionary with lightweight summary:
        {
            "activity_id": int,
            "total_anomalies": int,
            "summary_by_metric": {
                "gct_anomalies": int,
                "vo_anomalies": int,
                "vr_anomalies": int
            },
            "summary_by_cause": {
                "elevation_related": int,
                "pace_related": int,
                "fatigue_related": int
            },
            "severity_distribution": {
                "high": int,      # z_score > 3.0
                "medium": int,    # 2.5 < z_score <= 3.0
                "low": int        # 2.0 < z_score <= 2.5
            },
            "temporal_clusters": [
                {
                    "time_window": "00:05:00-00:10:00",  # 5-minute windows
                    "anomaly_count": int,
                    "dominant_cause": str,
                    "dominant_metric": str
                },
                ...
            ],
            "top_severe_anomalies": [
                {
                    "anomaly_id": int,
                    "timestamp": int,
                    "metric": str,
                    "z_score": float,
                    "probable_cause": str
                },
                ...  # Top 5 only
            ],
            "recommendations": [str, ...]
        }
    """
```

**Token Estimate:**
- Activity metadata: 50 tokens
- Summary statistics: 150 tokens
- Severity distribution: 50 tokens
- Temporal clusters: 200 tokens (avg 5 clusters × 40 tokens)
- Top 5 anomalies: 200 tokens (5 × 40 tokens)
- Recommendations: 50 tokens
- **Total: ~700 tokens** (95% reduction from 14,300)

#### 2. `get_form_anomaly_details()` - Filtered Details API

**Purpose:** Retrieve detailed anomaly information with flexible filtering

**Signature:**
```python
def get_form_anomaly_details(
    self,
    activity_id: int,
    anomaly_ids: list[int] | None = None,
    time_range: tuple[int, int] | None = None,
    metrics: list[str] | None = None,
    z_threshold: float | None = None,
    causes: list[str] | None = None,
    limit: int = 50,
    sort_by: str = "z_score",  # "z_score" or "timestamp"
) -> dict[str, Any]:
    """Get detailed anomaly information with filtering options.

    Args:
        activity_id: Activity ID.
        anomaly_ids: Optional list of specific anomaly IDs to retrieve.
        time_range: Optional (start_sec, end_sec) to filter by time.
        metrics: Optional list of metric names to filter.
        z_threshold: Optional minimum z-score threshold (filters anomalies >= threshold).
        causes: Optional list of causes to filter
               (e.g., ["elevation_change", "pace_change"]).
        limit: Maximum number of anomalies to return (default: 50).
        sort_by: Sort order - "z_score" (desc) or "timestamp" (asc).

    Returns:
        Dictionary with filtered anomaly details:
        {
            "activity_id": int,
            "filters_applied": {
                "anomaly_ids": list[int] | None,
                "time_range": tuple[int, int] | None,
                "metrics": list[str] | None,
                "z_threshold": float | None,
                "causes": list[str] | None,
                "limit": int
            },
            "total_matching": int,
            "returned_count": int,
            "anomalies": [
                {
                    "anomaly_id": int,
                    "timestamp": int,
                    "metric": str,
                    "value": float,
                    "baseline": float,
                    "z_score": float,
                    "probable_cause": str,
                    "cause_details": {
                        "elevation_change_5s": float,
                        "pace_change_10s": float,
                        "hr_drift_percent": float,
                        "{cause}_correlation": float
                    },
                    "context": {
                        "before_30s": {
                            "metric_avg": float,
                            "elevation": float
                        },
                        "after_30s": {
                            "metric_avg": float,
                            "elevation": float
                        }
                    }
                },
                ...
            ]
        }
    """
```

**Token Estimate (variable based on filters):**
- No filter: ~14,000 tokens (same as current API)
- Filter by 5 anomaly IDs: ~1,500 tokens (5 × 300 tokens/anomaly)
- Filter by time range (5 min): ~2,000 tokens
- Filter by metric (GCT only): ~4,500 tokens (33% of anomalies)
- Filter by cause (elevation only): ~5,000 tokens (35% of anomalies)

#### 3. `detect_form_anomalies()` - REMOVE

**Action:** Complete removal of existing API
- **Reason:** Replaced by two specialized APIs
- **Migration:** Users must switch to `detect_form_anomalies_summary()` for overview
- **Breaking Change:** Yes (intentional for token optimization)

### 共通ヘルパーメソッド設計

**1. `_extract_time_series()` - Time Series Extraction**
```python
def _extract_time_series(
    self,
    activity_id: int,
    metrics: list[str],
) -> dict[str, list[float | None]]:
    """Extract time series for form metrics and contextual metrics.

    Args:
        activity_id: Activity ID.
        metrics: List of metric names to extract.

    Returns:
        Dictionary mapping metric names to time series:
        {
            "directGroundContactTime": [float, ...],
            "directVerticalOscillation": [float, ...],
            "directVerticalRatio": [float, ...],
            "directElevation": [float, ...],
            "directSpeed": [float, ...],  # Converted to pace
            "directHeartRate": [float, ...]
        }
    """
```

**2. `_detect_all_anomalies()` - Full Anomaly Detection**
```python
def _detect_all_anomalies(
    self,
    time_series_data: dict[str, list[float | None]],
    metrics: list[str],
    z_threshold: float,
) -> list[dict[str, Any]]:
    """Detect anomalies for all requested metrics with cause analysis.

    Args:
        time_series_data: Dictionary of metric time series.
        metrics: List of form metrics to analyze.
        z_threshold: Z-score threshold for anomaly detection.

    Returns:
        List of anomaly dictionaries with full details
        (anomaly_id, timestamp, metric, value, baseline, z_score,
         probable_cause, cause_details, context).
    """
```

**3. `_generate_severity_distribution()` - Severity Classification**
```python
def _generate_severity_distribution(
    self,
    anomalies: list[dict[str, Any]],
) -> dict[str, int]:
    """Classify anomalies by severity based on z-score.

    Args:
        anomalies: List of anomaly dictionaries.

    Returns:
        Dictionary with severity counts:
        {
            "high": int,      # z_score > 3.0
            "medium": int,    # 2.5 < z_score <= 3.0
            "low": int        # 2.0 < z_score <= 2.5
        }
    """
```

**4. `_generate_temporal_clusters()` - Temporal Clustering**
```python
def _generate_temporal_clusters(
    self,
    anomalies: list[dict[str, Any]],
    window_size: int = 300,  # 5 minutes
) -> list[dict[str, Any]]:
    """Group anomalies into temporal clusters (5-minute windows).

    Args:
        anomalies: List of anomaly dictionaries.
        window_size: Cluster window size in seconds (default: 300).

    Returns:
        List of temporal cluster dictionaries:
        [
            {
                "time_window": "00:05:00-00:10:00",
                "anomaly_count": int,
                "dominant_cause": str,
                "dominant_metric": str
            },
            ...
        ]
    """
```

**5. `_apply_anomaly_filters()` - Filter Anomalies**
```python
def _apply_anomaly_filters(
    self,
    anomalies: list[dict[str, Any]],
    anomaly_ids: list[int] | None = None,
    time_range: tuple[int, int] | None = None,
    metrics: list[str] | None = None,
    z_threshold: float | None = None,
    causes: list[str] | None = None,
    limit: int = 50,
    sort_by: str = "z_score",
) -> list[dict[str, Any]]:
    """Apply filtering criteria to anomaly list.

    Args:
        anomalies: List of anomaly dictionaries.
        anomaly_ids: Optional list of specific anomaly IDs.
        time_range: Optional (start_sec, end_sec) range.
        metrics: Optional list of metric names.
        z_threshold: Optional minimum z-score.
        causes: Optional list of probable causes.
        limit: Maximum number of results.
        sort_by: Sort order ("z_score" or "timestamp").

    Returns:
        Filtered and sorted list of anomaly dictionaries.
    """
```

### MCP Server Tool Definitions

**Update `servers/garmin_db_server.py`:**

```python
# REMOVE existing tool definition
Tool(
    name="detect_form_anomalies",
    description="Detect form metric anomalies and identify causes (elevation/pace/fatigue)",
    inputSchema={...},
)

# ADD new tool definitions
Tool(
    name="detect_form_anomalies_summary",
    description="Detect form anomalies and return lightweight summary (~700 tokens, 95% reduction)",
    inputSchema={
        "type": "object",
        "properties": {
            "activity_id": {"type": "integer"},
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Metrics to analyze (default: GCT, VO, VR)",
            },
            "z_threshold": {
                "type": "number",
                "description": "Z-score threshold for anomaly detection (default: 2.0)",
            },
        },
        "required": ["activity_id"],
    },
)

Tool(
    name="get_form_anomaly_details",
    description="Get detailed anomaly information with flexible filtering (variable token size)",
    inputSchema={
        "type": "object",
        "properties": {
            "activity_id": {"type": "integer"},
            "anomaly_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional specific anomaly IDs to retrieve",
            },
            "time_range": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Optional [start_sec, end_sec] time range",
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional metric names to filter",
            },
            "z_threshold": {
                "type": "number",
                "description": "Optional minimum z-score threshold",
            },
            "causes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional causes to filter (elevation_change, pace_change, fatigue)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 50)",
                "default": 50,
            },
            "sort_by": {
                "type": "string",
                "description": "Sort order: z_score (desc) or timestamp (asc)",
                "enum": ["z_score", "timestamp"],
                "default": "z_score",
            },
        },
        "required": ["activity_id"],
    },
)
```

**Update tool handler:**
```python
@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    import json

    # REMOVE existing handler
    # elif name == "detect_form_anomalies":
    #     ...

    # ADD new handlers
    elif name == "detect_form_anomalies_summary":
        from tools.rag.queries.form_anomaly_detector import FormAnomalyDetector

        detector = FormAnomalyDetector()
        result = detector.detect_form_anomalies_summary(
            activity_id=arguments["activity_id"],
            metrics=arguments.get("metrics"),
            z_threshold=arguments.get("z_threshold", 2.0),
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_form_anomaly_details":
        from tools.rag.queries.form_anomaly_detector import FormAnomalyDetector

        detector = FormAnomalyDetector()

        # Convert time_range from list to tuple if provided
        time_range = arguments.get("time_range")
        if time_range is not None:
            time_range = tuple(time_range)

        result = detector.get_form_anomaly_details(
            activity_id=arguments["activity_id"],
            anomaly_ids=arguments.get("anomaly_ids"),
            time_range=time_range,
            metrics=arguments.get("metrics"),
            z_threshold=arguments.get("z_threshold"),
            causes=arguments.get("causes"),
            limit=arguments.get("limit", 50),
            sort_by=arguments.get("sort_by", "z_score"),
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]
```

---

## 実装フェーズ

### Phase 1: Helper Methods Extraction (~2 hours)
**Goal:** Extract reusable logic from existing `detect_form_anomalies()` method

**Tasks:**
1. Implement `_extract_time_series()` helper
   - Extract time series loading logic
   - Handle metric descriptors parsing
   - Include contextual metrics (elevation, pace, HR)
2. Implement `_detect_all_anomalies()` helper
   - Extract anomaly detection pipeline
   - Include rolling stats calculation
   - Include cause analysis and context extraction
3. Refactor existing `detect_form_anomalies()` to use helpers
   - Replace inline logic with helper calls
   - Verify behavior unchanged (regression testing)

**Acceptance Criteria:**
- All existing tests pass without modification
- No behavior change in `detect_form_anomalies()` output
- Code duplication eliminated

### Phase 2: New Helper Methods (~1.5 hours)
**Goal:** Implement new helper methods for summary API

**Tasks:**
1. Implement `_generate_severity_distribution()`
   - Classify anomalies by z-score thresholds
   - Return high/medium/low counts
2. Implement `_generate_temporal_clusters()`
   - Group anomalies into 5-minute windows
   - Calculate dominant cause and metric per cluster
   - Format time windows as "HH:MM:SS-HH:MM:SS"
3. Implement `_apply_anomaly_filters()`
   - Implement filtering logic for all criteria
   - Implement sorting (by z_score desc or timestamp asc)
   - Apply limit

**Acceptance Criteria:**
- Unit tests pass for each helper method
- Edge cases handled (empty input, single anomaly, etc.)

### Phase 3: Summary API Implementation (~2 hours)
**Goal:** Implement `detect_form_anomalies_summary()` API

**Tasks:**
1. Implement `detect_form_anomalies_summary()` method
   - Call `_extract_time_series()`
   - Call `_detect_all_anomalies()`
   - Generate summary statistics
   - Call `_generate_severity_distribution()`
   - Call `_generate_temporal_clusters()`
   - Extract top 5 anomalies by z-score
   - Call `_generate_recommendations()`
2. Add comprehensive tests
   - Test summary structure
   - Test token count (~700 tokens)
   - Test severity distribution accuracy
   - Test temporal clustering logic
   - Test top 5 extraction

**Acceptance Criteria:**
- Summary API returns all required fields
- Token count < 1,000 (target: ~700)
- All tests pass

### Phase 4: Details API Implementation (~2.5 hours)
**Goal:** Implement `get_form_anomaly_details()` API with filtering

**Tasks:**
1. Implement `get_form_anomaly_details()` method
   - Call `_extract_time_series()`
   - Call `_detect_all_anomalies()`
   - Call `_apply_anomaly_filters()` with all parameters
   - Return filtered results with metadata
2. Add comprehensive tests
   - Test each filter type independently
   - Test filter combinations
   - Test sorting options
   - Test limit behavior
   - Test token counts for various filters

**Acceptance Criteria:**
- Details API returns filtered results correctly
- All filter types work (anomaly IDs, time range, metrics, z-threshold, causes)
- Sorting works correctly
- All tests pass

### Phase 5: MCP Server Integration (~1.5 hours)
**Goal:** Update MCP server tool definitions and handlers

**Tasks:**
1. Update tool definitions in `servers/garmin_db_server.py`
   - Remove `detect_form_anomalies` tool
   - Add `detect_form_anomalies_summary` tool
   - Add `get_form_anomaly_details` tool
2. Update tool handler
   - Remove `detect_form_anomalies` handler
   - Add `detect_form_anomalies_summary` handler
   - Add `get_form_anomaly_details` handler (with tuple conversion)
3. Test MCP server integration
   - Start MCP server
   - Test summary API via MCP
   - Test details API via MCP with various filters

**Acceptance Criteria:**
- MCP server starts without errors
- Tools appear in MCP tool list
- Tool calls work correctly
- JSON serialization works

### Phase 6: Legacy API Removal (~1 hour)
**Goal:** Remove deprecated `detect_form_anomalies()` method

**Tasks:**
1. Remove `detect_form_anomalies()` method from `FormAnomalyDetector`
2. Update tests
   - Remove tests specifically for old API
   - Update integration tests to use new APIs
3. Add migration notes to docstring
   - Document breaking change
   - Provide migration examples

**Acceptance Criteria:**
- Old API completely removed
- All tests updated and passing
- No references to old API in codebase

### Phase 7: Documentation Update (~1 hour)
**Goal:** Update CLAUDE.md and inline documentation

**Tasks:**
1. Update `CLAUDE.md`
   - Update "Garmin DB MCP Server" section
   - Document new APIs with token estimates
   - Add usage examples
   - Remove old API references
2. Update docstrings
   - Ensure all new methods have comprehensive docstrings
   - Add usage examples in class docstring
3. Add migration guide
   - Document breaking change
   - Provide before/after examples

**Acceptance Criteria:**
- CLAUDE.md updated with new APIs
- All docstrings complete
- Migration guide provided

---

## テスト計画

### Unit Tests

**FormAnomalyDetector Helper Methods:**
- [ ] `test_extract_time_series_success` - Verify time series extraction
- [ ] `test_extract_time_series_missing_metrics` - Handle missing metrics gracefully
- [ ] `test_detect_all_anomalies_basic` - Verify anomaly detection pipeline
- [ ] `test_detect_all_anomalies_with_causes` - Verify cause analysis integration
- [ ] `test_generate_severity_distribution_all_levels` - Test all severity levels
- [ ] `test_generate_severity_distribution_single_level` - Test single severity level
- [ ] `test_generate_severity_distribution_empty` - Handle empty input
- [ ] `test_generate_temporal_clusters_basic` - Verify clustering logic
- [ ] `test_generate_temporal_clusters_single_window` - Test single window
- [ ] `test_generate_temporal_clusters_empty` - Handle empty input
- [ ] `test_apply_anomaly_filters_by_ids` - Test anomaly ID filtering
- [ ] `test_apply_anomaly_filters_by_time_range` - Test time range filtering
- [ ] `test_apply_anomaly_filters_by_metrics` - Test metric filtering
- [ ] `test_apply_anomaly_filters_by_z_threshold` - Test z-score filtering
- [ ] `test_apply_anomaly_filters_by_causes` - Test cause filtering
- [ ] `test_apply_anomaly_filters_combined` - Test multiple filters
- [ ] `test_apply_anomaly_filters_sorting_z_score` - Test z-score sorting
- [ ] `test_apply_anomaly_filters_sorting_timestamp` - Test timestamp sorting
- [ ] `test_apply_anomaly_filters_limit` - Test limit enforcement

**Summary API Tests:**
- [ ] `test_detect_form_anomalies_summary_structure` - Verify response structure
- [ ] `test_detect_form_anomalies_summary_token_count` - Verify token count < 1000
- [ ] `test_detect_form_anomalies_summary_severity_distribution` - Verify severity accuracy
- [ ] `test_detect_form_anomalies_summary_temporal_clusters` - Verify clustering accuracy
- [ ] `test_detect_form_anomalies_summary_top_5_anomalies` - Verify top 5 extraction
- [ ] `test_detect_form_anomalies_summary_no_anomalies` - Handle no anomalies case
- [ ] `test_detect_form_anomalies_summary_recommendations` - Verify recommendations

**Details API Tests:**
- [ ] `test_get_form_anomaly_details_no_filter` - Verify unfiltered results
- [ ] `test_get_form_anomaly_details_filter_by_ids` - Verify ID filtering
- [ ] `test_get_form_anomaly_details_filter_by_time_range` - Verify time filtering
- [ ] `test_get_form_anomaly_details_filter_by_metrics` - Verify metric filtering
- [ ] `test_get_form_anomaly_details_filter_by_z_threshold` - Verify z-score filtering
- [ ] `test_get_form_anomaly_details_filter_by_causes` - Verify cause filtering
- [ ] `test_get_form_anomaly_details_combined_filters` - Verify filter combinations
- [ ] `test_get_form_anomaly_details_sort_by_z_score` - Verify z-score sorting
- [ ] `test_get_form_anomaly_details_sort_by_timestamp` - Verify timestamp sorting
- [ ] `test_get_form_anomaly_details_limit_enforcement` - Verify limit behavior
- [ ] `test_get_form_anomaly_details_empty_results` - Handle empty results

**Regression Tests (Existing Tests):**
- [ ] All existing tests in `test_form_anomaly_detector.py` pass after Phase 1 refactoring
- [ ] Behavior unchanged for `detect_form_anomalies()` during Phase 1-2

### Integration Tests

- [ ] `test_mcp_server_summary_api_integration` - Test summary API via MCP server
- [ ] `test_mcp_server_details_api_integration` - Test details API via MCP server
- [ ] `test_mcp_server_details_api_filtering` - Test filtering via MCP server
- [ ] `test_mcp_server_tool_list_updated` - Verify old tool removed, new tools added
- [ ] `test_mcp_server_json_serialization` - Verify JSON serialization works
- [ ] `test_summary_to_details_workflow` - Test typical workflow (summary → details)

### Performance Tests

- [ ] `test_summary_api_token_count_multiple_activities` - Verify token reduction for 10 activities
  - **Target:** 10 activities × 700 tokens = 7,000 tokens
  - **Current:** 10 activities × 14,300 tokens = 143,000 tokens
  - **Reduction:** 95%
- [ ] `test_details_api_token_count_with_filters` - Verify filtering reduces tokens
  - **Target:** Filter by 5 IDs = ~1,500 tokens (vs 14,300 unfiltered)
  - **Reduction:** 89%
- [ ] `test_summary_api_response_time` - Verify acceptable response time (<2s for typical activity)
- [ ] `test_details_api_response_time` - Verify acceptable response time (<2s with filters)

---

## 受け入れ基準

### Functionality
- [ ] `detect_form_anomalies_summary()` returns all required fields
- [ ] Summary API token count < 1,000 (target: ~700)
- [ ] `get_form_anomaly_details()` supports all filter types
- [ ] Details API filtering works correctly
- [ ] Old `detect_form_anomalies()` API completely removed
- [ ] MCP server tools updated and working

### Code Quality
- [ ] 全テストがパスする (unit, integration, performance)
- [ ] カバレッジ90%以上 (target: match existing coverage)
- [ ] Black formatting passes
- [ ] Ruff linting passes
- [ ] Mypy type checking passes

### Performance
- [ ] Summary API: ~700 tokens/call (95% reduction from 14,300)
- [ ] Details API with filters: Variable (50-90% reduction depending on filters)
- [ ] Multi-activity analysis: 10 activities in 7,000 tokens vs 143,000 (95% reduction)

### Documentation
- [ ] CLAUDE.md updated with new APIs
- [ ] MCP tool descriptions updated
- [ ] Migration guide provided
- [ ] All new methods have comprehensive docstrings

### Breaking Changes
- [ ] Old API removed (intentional breaking change)
- [ ] Migration path documented
- [ ] No backward compatibility (by design)

---

## リスク管理

### High Priority Risks

1. **Token Count Estimation Inaccuracy**
   - **Risk:** Summary API exceeds 1,000 tokens
   - **Mitigation:** Implement token counting test early (Phase 3)
   - **Fallback:** Remove temporal clusters or reduce top anomalies to 3

2. **Filter Combinations Complexity**
   - **Risk:** Complex filter logic introduces bugs
   - **Mitigation:** Comprehensive unit tests for each filter + combinations
   - **Fallback:** Disable filter combinations if issues arise

3. **Breaking Change Impact**
   - **Risk:** Users rely on old API
   - **Mitigation:** Document breaking change clearly, provide migration guide
   - **Fallback:** N/A (breaking change is intentional)

### Medium Priority Risks

4. **MCP Server Integration Issues**
   - **Risk:** JSON serialization or tool registration fails
   - **Mitigation:** Test MCP integration early (Phase 5)
   - **Fallback:** Revert to old API temporarily

5. **Performance Regression**
   - **Risk:** New APIs slower than old API
   - **Mitigation:** Performance tests in Phase 3-4
   - **Fallback:** Optimize helper methods

### Low Priority Risks

6. **Test Fixture Compatibility**
   - **Risk:** Existing test fixtures don't work with new APIs
   - **Mitigation:** Reuse existing fixtures where possible
   - **Fallback:** Create new fixtures if needed

---

## 完成基準

### Definition of Done
- [ ] All phases completed
- [ ] All acceptance criteria met
- [ ] All tests passing (unit, integration, performance)
- [ ] Code quality checks passing (Black, Ruff, Mypy)
- [ ] Documentation updated (CLAUDE.md, docstrings)
- [ ] Old API removed
- [ ] MCP server updated and tested
- [ ] Migration guide provided
- [ ] Token reduction verified (95% for summary API)
- [ ] Planning document updated with completion notes
- [ ] Completion report generated

### Success Metrics
- **Primary Metric:** Token reduction for multi-activity analysis (target: 95%)
- **Secondary Metric:** API usability (flexible filtering, clear structure)
- **Tertiary Metric:** Code maintainability (reduced duplication, clear separation of concerns)
