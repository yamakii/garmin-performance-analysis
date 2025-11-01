# 計画: DuckDB × MCP × LLM 分析アーキテクチャ要件書

**GitHub Issue:** [#25](https://github.com/yamakii/garmin-performance-analysis/issues/25)

## プロジェクト情報

- **プロジェクト名**: `duckdb_mcp_llm_architecture`
- **作成日**: `2025-10-16`
- **ステータス**: 完了（Phase 0-5完了）
- **優先度**: 高（基盤アーキテクチャ）
- **推定期間**: 5週間 → 実績: 10日（Phase 0-3）+ 1日（Phase 4-5）
- **スコープ**: 新規実装（4 MCP関数）+ 既存リファクタリング（23 MCP関数）+ クラス分割（GarminDBReader）+ エージェント更新（2エージェント）

## 要件定義

### 目的

LLMがDuckDBの高解像度データを利用して分析を行う際に、コンテキスト膨張を防ぎ、安全かつ効率的にデータ処理を行うための基本方針・実装フロー・セーフティガードを確立する。

**核心的な課題:**
- LLMコンテキストは限られている（秒単位データを1000行展開すると即座に枯渇）
- 生データの解釈はLLMではなく、コード実行環境（Python/DuckDB）が行うべき
- データ抽出→処理→要約→解釈のフローを標準化し、安全性を担保する必要がある

### 解決する問題

**現状の課題:**

1. **コンテキスト膨張問題**
   - LLMが直接生データ（秒単位メトリクス1000-2000行）を読み取ろうとする
   - JSON出力が数十KB〜数百KBに膨張し、トークンを消費
   - 結果として複雑な分析が不可能

2. **データ処理の責任分離不明確**
   - LLMが「データ読み取り」「データ処理」「結果解釈」を混在して実行
   - MCP Serverが生データを直接返却するか、要約を返すかが不明確
   - Python実行環境での処理パターンが標準化されていない

3. **安全性の欠如**
   - 出力サイズ制限がなく、意図せず大量データが返却される
   - LLMが誤って全データ展開を試みた際のガードレールがない
   - ベストプラクティスが文書化されていない

### ユースケース

1. **秒単位インターバル分析**
   - ユーザー: 「5:00-10:00のペース変動を秒単位で分析して」
   - LLM: `export(time_range)` で明細をParquetに抽出
   - Python: 秒単位リサンプリング→ローリング平均→差分計算→グラフ生成
   - LLM: 要約JSON（10行）＋グラフを受け取り、自然言語で解釈

2. **フォーム異常の深堀り分析**
   - ユーザー: 「GCTが急上昇した箇所の前後30秒を詳しく見たい」
   - LLM: `export(anomaly_id, context_window=30)` で該当区間をParquetに抽出
   - Python: 30秒窓データをロード→ペース/HR/標高との相関分析→散布図生成
   - LLM: 統計サマリー＋グラフを受け取り、原因仮説を提示

3. **複数アクティビティ比較**
   - ユーザー: 「過去5回の10kmランの心拍ゾーン推移を比較」
   - LLM: `profile(activity_ids)` で各アクティビティの要約統計を取得
   - LLM: `export(activity_ids, metrics=['heart_rate'])` で心拍データをParquetに抽出
   - Python: 5アクティビティの心拍データをロード→正規化時間軸に整列→重ね合わせグラフ生成
   - LLM: 比較グラフ＋差異サマリーを受け取り、パフォーマンス変化を解説

4. **ペース分布のヒストグラム分析**
   - ユーザー: 「今月のランニングペース分布を見たい」
   - LLM: `histogram(table='splits', column='pace', date_range)` で分布集計を取得（生データなし）
   - LLM: ヒストグラム統計（ビン数10〜20）のみ受け取り、分布特性を解説

---

## 設計

### アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                        User / LLM Prompt                         │
│  "5:00-10:00のペース変動を秒単位で分析して"                      │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                          LLM (Claude)                            │
│  - データ要求の計画 (PLAN)                                       │
│  - MCP呼び出し指示                                               │
│  - 結果の解釈・報告 (INTERPRET)                                  │
│  ❌ 生データ直接読み取り禁止                                     │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                       MCP Server (Garmin DB)                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ export(query, format="parquet")                           │  │
│  │   - DuckDB → Parquet出力                                  │  │
│  │   - 返却: {"handle": "path/to/export_xxx.parquet"}       │  │
│  │   - コンテキスト: ハンドルのみ（数十バイト）             │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ profile(table_or_query)                                   │  │
│  │   - 要約統計: 行数/期間/カラム情報/NULL率                │  │
│  │   - 返却: JSON ~500バイト                                 │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ histogram(table_or_query, column, bins=20)                │  │
│  │   - 分布集計: ビン境界＋カウント                          │  │
│  │   - 返却: JSON ~1KB                                       │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ materialize(name, query)                                  │  │
│  │   - 一時ビュー作成（再利用高速化）                        │  │
│  │   - 返却: {"view": "temp_view_xxx", "rows": 1234}        │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│              Python Code Executor (Claude Code)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ safe_load_export(handle, max_rows=10000)                  │  │
│  │   - Parquetから部分読み込み                               │  │
│  │   - サイズ超過時はエラー                                  │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ safe_summary_table(df, max_rows=10)                       │  │
│  │   - DataFrameの要約出力（10行制限）                       │  │
│  │   - JSON出力は1KB制限                                     │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ DuckDB/Polars/Pandasで分析                                │  │
│  │   - リサンプリング・集計・差分・ローリング平均            │  │
│  │   - グラフ生成（Matplotlib/Plotly）                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                        Output Validation                         │
│  - JSON出力: 1KB以内チェック                                     │
│  - テーブル出力: 10行以内チェック                                │
│  - 違反時: 自動トリム＋警告                                      │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                     LLM Result Interpretation                    │
│  - 要約JSON（10行）を受け取り                                    │
│  - グラフパスを受け取り                                          │
│  - 自然言語で解釈・報告                                          │
│  - 必要なら再ドリルダウン指示                                    │
└─────────────────────────────────────────────────────────────────┘
```

**設計原則:**

1. **責任分離の明確化**
   - LLM: データ要求計画＋結果解釈（データ読み取りは行わない）
   - MCP Server: データ抽出＋要約統計（生データ返却はしない）
   - Python: データ処理＋可視化（全データ展開はしない）

2. **コンテキスト保護**
   - MCP Serverはハンドル（パス文字列）のみ返却
   - Python実行結果は要約＋グラフパスのみ
   - 生データはメモリ内で処理し、LLMには渡さない

3. **セーフティガード**
   - 出力サイズ検証（JSON: 1KB、テーブル: 10行）
   - 入力サイズ制限（Parquetロード: 10,000行）
   - 超過時の自動トリム＋警告

### データフロー詳細

```
STEP 1: PLAN (LLM)
  ↓
  "5:00-10:00のペース変動を秒単位で分析"
  → query = "SELECT * FROM time_series_metrics
              WHERE activity_id = 12345
              AND timestamp BETWEEN 300 AND 600"

STEP 2: EXPORT (MCP)
  ↓
  mcp__garmin-db__export(query, format="parquet")
  → {"handle": "/tmp/export_abc123.parquet", "rows": 300, "size_mb": 0.5}

STEP 3: CODE (Python)
  ↓
  df = safe_load_export("/tmp/export_abc123.parquet")
  df_resampled = df.resample('1S').mean()
  rolling_avg = df_resampled['pace'].rolling(10).mean()
  fig = plot_pace_variation(df_resampled, rolling_avg)
  summary = {
      "avg_pace": df['pace'].mean(),
      "std_pace": df['pace'].std(),
      "max_deviation": (df['pace'] - rolling_avg).abs().max()
  }
  → {"summary": summary, "plot_path": "/tmp/plot_xyz.png"}

STEP 4: RESULT (Validation)
  ↓
  JSON size: 320 bytes ✓
  No raw table output ✓

STEP 5: INTERPRET (LLM)
  ↓
  "5:00-10:00の区間では平均ペース4:30/km、標準偏差5秒でした。
   7:30付近でペースが20秒/km急落しており、給水の影響と推測されます。"
```

### API/インターフェース設計

#### MCP Server Functions

```python
# tools/mcp_server/garmin_db_server.py

@mcp.tool()
def export(
    query: str,
    format: Literal["parquet", "csv"] = "parquet",
    max_rows: int = 100000
) -> dict:
    """
    Export query results to file (returns handle only, not data).

    Args:
        query: DuckDB SQL query
        format: Output format (parquet recommended)
        max_rows: Safety limit for export size

    Returns:
        {
            "handle": "/tmp/export_abc123.parquet",
            "rows": 1234,
            "size_mb": 2.5,
            "columns": ["timestamp", "pace", "heart_rate"]
        }

    Context Cost: ~100 tokens (no data content)
    """
    pass


@mcp.tool()
def profile(
    table_or_query: str,
    date_range: Optional[tuple[str, str]] = None
) -> dict:
    """
    Get summary statistics without raw data.

    Args:
        table_or_query: Table name or SQL query
        date_range: Optional date filter (start, end)

    Returns:
        {
            "row_count": 12345,
            "date_range": ["2025-01-01", "2025-12-31"],
            "columns": {
                "pace": {"min": 240, "max": 360, "mean": 270, "null_rate": 0.01},
                "heart_rate": {"min": 120, "max": 180, "mean": 150, "null_rate": 0.0}
            }
        }

    Context Cost: ~500 bytes
    """
    pass


@mcp.tool()
def histogram(
    table_or_query: str,
    column: str,
    bins: int = 20,
    date_range: Optional[tuple[str, str]] = None
) -> dict:
    """
    Get histogram distribution (aggregated, not raw data).

    Args:
        table_or_query: Table name or SQL query
        column: Column to analyze
        bins: Number of histogram bins
        date_range: Optional date filter

    Returns:
        {
            "column": "pace",
            "bins": [
                {"min": 240, "max": 250, "count": 123},
                {"min": 250, "max": 260, "count": 456},
                ...
            ],
            "total_count": 12345
        }

    Context Cost: ~1KB (20 bins × 50 bytes)
    """
    pass


@mcp.tool()
def materialize(
    name: str,
    query: str,
    ttl_seconds: int = 3600
) -> dict:
    """
    Create temporary view for reuse (faster subsequent queries).

    Args:
        name: View name (must be unique)
        query: SQL query to materialize
        ttl_seconds: Time to live (auto cleanup)

    Returns:
        {
            "view": "temp_view_abc123",
            "rows": 1234,
            "expires_at": "2025-10-16T12:00:00Z"
        }

    Context Cost: ~100 bytes
    """
    pass
```

#### Python Helper Functions

```python
# tools/utils/llm_safe_data.py

import polars as pl
import json
from pathlib import Path

MAX_JSON_SIZE = 1024  # 1KB
MAX_TABLE_ROWS = 10
MAX_LOAD_ROWS = 10000


def safe_load_export(handle: str, max_rows: int = MAX_LOAD_ROWS) -> pl.DataFrame:
    """
    Load exported Parquet with size limit.

    Args:
        handle: Path to Parquet file
        max_rows: Maximum rows to load

    Returns:
        Polars DataFrame

    Raises:
        ValueError: If file exceeds max_rows
    """
    df = pl.scan_parquet(handle)
    row_count = df.select(pl.count()).collect().item()

    if row_count > max_rows:
        raise ValueError(
            f"Export exceeds max_rows: {row_count} > {max_rows}. "
            f"Use aggregation or filtering."
        )

    return df.collect()


def safe_summary_table(
    df: pl.DataFrame,
    max_rows: int = MAX_TABLE_ROWS,
    columns: Optional[list[str]] = None
) -> str:
    """
    Generate summary table with row limit.

    Args:
        df: Input DataFrame
        max_rows: Maximum rows to display
        columns: Optional column subset

    Returns:
        Formatted table string (max 10 rows)
    """
    if columns:
        df = df.select(columns)

    if len(df) > max_rows:
        df_head = df.head(max_rows // 2)
        df_tail = df.tail(max_rows // 2)
        df_display = pl.concat([df_head, df_tail])
        table_str = df_display.to_pandas().to_string(index=False)
        table_str += f"\n... ({len(df) - max_rows} rows omitted) ..."
    else:
        table_str = df.to_pandas().to_string(index=False)

    return table_str


def safe_json_output(data: dict, max_size: int = MAX_JSON_SIZE) -> str:
    """
    Generate JSON output with size limit.

    Args:
        data: Dictionary to serialize
        max_size: Maximum JSON size in bytes

    Returns:
        JSON string

    Raises:
        ValueError: If JSON exceeds max_size
    """
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    if len(json_str.encode('utf-8')) > max_size:
        raise ValueError(
            f"JSON output exceeds max_size: {len(json_str)} > {max_size}. "
            f"Reduce output data."
        )

    return json_str


def validate_output(output: str) -> tuple[bool, Optional[str]]:
    """
    Validate output against size limits.

    Args:
        output: Output string to validate

    Returns:
        (is_valid, error_message)
    """
    # Check JSON size
    try:
        data = json.loads(output)
        if len(output.encode('utf-8')) > MAX_JSON_SIZE:
            return False, f"JSON exceeds {MAX_JSON_SIZE} bytes"
    except json.JSONDecodeError:
        pass  # Not JSON, check table format

    # Check table row count
    lines = output.strip().split('\n')
    if len(lines) > MAX_TABLE_ROWS + 5:  # +5 for header/footer
        return False, f"Table exceeds {MAX_TABLE_ROWS} rows"

    return True, None
```

---

## 実装フェーズ

### Phase 0: 既存MCP関数のリファクタリング・統合・改廃 (Week 1)

**目標:** 既存の23個のMCP関数を新アーキテクチャに準拠させ、統合・改廃により最適化

**現状分析:**

**既存MCP関数（23個）の分類:**

1. **要約統計系（そのまま維持 - 7個）**
   - `get_form_efficiency_summary` - フォーム効率要約（~500バイト）
   - `get_hr_efficiency_analysis` - HR効率分析（~800バイト）
   - `get_heart_rate_zones_detail` - HR ゾーン詳細（~1KB）
   - `get_vo2_max_data` - VO2 max データ（~200バイト）
   - `get_lactate_threshold_data` - 乳酸閾値データ（~300バイト）
   - `get_performance_trends` - パフォーマンストレンド（~1KB）
   - `get_weather_data` - 天候データ（~400バイト）
   - **判定:** ✅ すでにアーキテクチャ準拠（要約データのみ返却）

2. **軽量splits系（statistics_onlyモード追加 - 3個）**
   - `get_splits_pace_hr` - ペース・HR（~3フィールド/split）
   - `get_splits_form_metrics` - フォームメトリクス（~4フィールド/split）
   - `get_splits_elevation` - 標高データ（~5フィールド/split）
   - **判定:** ⚠️ 10-20 splitsで500-1000バイト → `statistics_only=True`オプション追加

3. **大量データ系（export()へ移行推奨 - 2個）**
   - `get_splits_all` - 全splitsデータ（22フィールド/split）
   - `get_section_analysis` - セクション分析（数KB〜数十KB）
   - **判定:** 🔴 大量データ返却 → `export()`推奨、または`summary_only`モード追加

4. **時系列詳細系（すでに最適化済み - 2個）**
   - `get_split_time_series_detail` - split詳細（`statistics_only`対応済み、98.8%削減）
   - `get_time_range_detail` - 時間範囲詳細（`statistics_only`対応済み）
   - **判定:** ✅ すでに最適化済み（statistics_onlyモード実装済み）

5. **異常検出系（すでに最適化済み - 2個）**
   - `detect_form_anomalies_summary` - 異常サマリー（~700トークン、95%削減）
   - `get_form_anomaly_details` - 異常詳細（フィルタ対応、可変サイズ）
   - **判定:** ✅ すでに最適化済み（summary-firstアプローチ実装済み）

6. **RAG分析系（そのまま維持 - 4個）**
   - `get_interval_analysis` - インターバル分析（DuckDB集計済み）
   - `analyze_performance_trends` - トレンド分析（複数アクティビティ集計）
   - `extract_insights` - インサイト抽出（キーワード検索）
   - `compare_similar_workouts` - 類似ワークアウト比較
   - **判定:** ✅ すでに集計済みデータのみ返却

7. **メタデータ系（そのまま維持 - 2個）**
   - `get_activity_by_date` - 日付からアクティビティ検索
   - `get_date_by_activity_id` - アクティビティIDから日付取得
   - **判定:** ✅ メタデータのみ返却（軽量）

8. **書き込み系（そのまま維持 - 1個）**
   - `insert_section_analysis_dict` - セクション分析挿入
   - **判定:** ✅ 書き込み専用（返却データなし）

**リファクタリング方針:**

| カテゴリ | 関数数 | 対策 | 優先度 |
|---------|--------|------|--------|
| そのまま維持 | 14個 | なし（すでに準拠） | - |
| オプション追加 | 3個 | `statistics_only`パラメータ追加 | 中 |
| 非推奨化 | 2個 | `export()`への移行推奨、警告追加 | 高 |
| 新規実装 | 4個 | `export()`/`profile()`/`histogram()`/`materialize()` | 高 |

**Tasks:**

1. **大量データ系の非推奨化（Week 1, Day 1-2）**
   - `get_splits_all()` → 警告追加: "Large data export. Consider using `export()` with `statistics_only=True`"
   - `get_section_analysis()` → 警告追加: "Consider using `extract_insights()` for summary"
   - 両関数に`max_output_size`パラメータ追加（デフォルト10KB）
   - 超過時はエラー + `export()`使用推奨メッセージ

2. **軽量splits系のオプション追加（Week 1, Day 3-4）**
   - `get_splits_pace_hr(activity_id, statistics_only=False)` 追加
   - `get_splits_form_metrics(activity_id, statistics_only=False)` 追加
   - `get_splits_elevation(activity_id, statistics_only=False)` 追加
   - `statistics_only=True` 時: 平均・中央値・標準偏差のみ返却（~200バイト）

3. **CLAUDE.mdの更新（Week 1, Day 5）**
   - 新アーキテクチャガイド追加
   - MCP関数選択マトリックス更新
   - 非推奨関数の代替案明記
   - エージェント向けガイドライン追加

4. **依存エージェントの更新（Week 1, Day 5-7）**
   - **split-section-analyst**: `get_splits_*`呼び出し → `statistics_only=True`使用
   - **summary-section-analyst**: `get_splits_all`呼び出し → `export()` + Python集計に変更
   - **efficiency-section-analyst**: すでに最適化済み（変更不要）
   - **environment-section-analyst**: すでに最適化済み（変更不要）
   - **phase-section-analyst**: `get_performance_trends`使用（変更不要）

**受け入れ基準:**
- [ ] 非推奨関数に警告メッセージ追加
- [ ] 軽量splits系に`statistics_only`オプション追加
- [ ] CLAUDE.mdに新アーキテクチャガイド追加
- [ ] 依存エージェント更新完了
- [ ] 後方互換性維持（既存コードが動作）
- [ ] Unit tests カバレッジ90%以上

### Phase 1: 新規MCP Server Functions実装 (Week 2)

**目標:** MCPサーバーに4つの新規関数を実装し、ハンドルベースの安全なデータ抽出を実現

**Tasks:**

1. **`export()` 関数実装（Week 2, Day 1-3）**
   - DuckDB query → Parquet/CSV出力（`/tmp/garmin_exports/` ディレクトリ）
   - 一時ファイル管理（TTL 1時間、自動クリーンアップ）
   - 返却: ハンドル＋メタデータ（行数、サイズ、カラム情報）
   - エクスポートID: `export_<timestamp>_<uuid>.parquet`
   - テスト: 1000行、10,000行、100,000行の出力

2. **`profile()` 関数実装（Week 2, Day 3-4）**
   - テーブル/クエリの要約統計算出
   - カラム別の min/max/mean/median/null_rate/distinct_count
   - 期間情報（date_range: 最初/最後のタイムスタンプ）
   - 返却サイズ: ~500-1000バイト
   - テスト: splits, time_series_metrics, form_efficiency テーブル

3. **`histogram()` 関数実装（Week 2, Day 4-5）**
   - カラムの分布集計（ビン数可変、デフォルト20）
   - DuckDB `histogram()` 関数活用
   - 返却: ビン境界＋カウント（生データなし）
   - 返却サイズ: ~1KB（20ビン × 50バイト）
   - テスト: pace, heart_rate, cadence の分布

4. **`materialize()` 関数実装（Week 2, Day 5-7）**
   - 一時ビュー作成（`CREATE TEMP VIEW`）
   - TTLベースの自動削除（デフォルト1時間）
   - ビュー名衝突回避（UUID生成: `temp_view_<uuid>`）
   - ビュー数制限（最大10個、超過時は古いものから削除）
   - テスト: 複雑なJOINクエリの物質化、性能改善検証

**受け入れ基準:**
- [ ] 各関数が500バイト以内のレスポンス（`export()`はハンドルのみ）
- [ ] エラーハンドリング（不正SQL、サイズ超過）
- [ ] 一時ファイル/ビューの自動クリーンアップ
- [ ] Unit tests カバレッジ90%以上
- [ ] 既存関数との統合テスト完了

### Phase 1.5: GarminDBReaderリファクタリング (Week 2)

**目標:** 肥大化したGarminDBReaderクラス（1639行、21メソッド）を責務別に分割・整理

**現状の問題:**
- **単一クラスの肥大化**: GarminDBReaderが1639行、21メソッド
- **責務の混在**: 要約統計、splits取得、時系列処理、異常検出、エクスポートが同一クラス
- **メンテナンス性の低下**: メソッド追加時の影響範囲が不明確
- **テストの複雑化**: 巨大クラスのモック作成が困難

**リファクタリング方針:**

責務別に5つのReaderクラスに分割:

1. **BaseDBReader** (基底クラス)
   - DuckDB接続管理
   - 共通ユーティリティメソッド
   - `__init__`, `db_path`, 基本クエリメソッド

2. **MetadataReader** (メタデータ取得)
   - `get_activity_date()`
   - `query_activity_by_date()`
   - アクティビティメタ情報取得

3. **SplitsReader** (Splits データ取得)
   - `get_splits_pace_hr(statistics_only=False)`
   - `get_splits_form_metrics(statistics_only=False)`
   - `get_splits_elevation(statistics_only=False)`
   - `get_splits_all(max_output_size=10240)` ← 非推奨
   - `get_split_time_ranges()`

4. **AggregateReader** (集計・要約統計)
   - `get_form_efficiency_summary()`
   - `get_hr_efficiency_analysis()`
   - `get_heart_rate_zones_detail()`
   - `get_vo2_max_data()`
   - `get_lactate_threshold_data()`
   - `get_performance_trends()`
   - `get_weather_data()`
   - `get_section_analysis(max_output_size=10240)` ← 非推奨

5. **TimeSeriesReader** (時系列データ処理)
   - `get_time_series_statistics()`
   - `get_time_series_raw()`
   - `detect_anomalies_sql()`

6. **ExportReader** (データエクスポート)
   - `export_query_result()` (Phase 1で実装済み)

**統合アクセスクラス:**

```python
# tools/database/db_reader.py (新設計)

class GarminDBReader:
    """統合アクセスクラス（後方互換性維持）"""

    def __init__(self, db_path: Optional[Path] = None):
        self.metadata = MetadataReader(db_path)
        self.splits = SplitsReader(db_path)
        self.aggregate = AggregateReader(db_path)
        self.time_series = TimeSeriesReader(db_path)
        self.export = ExportReader(db_path)

    # 既存メソッドは各Readerに委譲（後方互換性）
    def get_activity_date(self, activity_id: int) -> str:
        return self.metadata.get_activity_date(activity_id)

    def get_splits_pace_hr(self, activity_id: int, statistics_only: bool = False):
        return self.splits.get_splits_pace_hr(activity_id, statistics_only)

    # ... 他のメソッドも同様に委譲
```

**Tasks:**

1. **基底クラス設計（Day 1）**
   - BaseDBReader実装
   - DuckDB接続管理の共通化
   - 共通ユーティリティメソッド抽出

2. **Readerクラス分割（Day 2-3）**
   - MetadataReader実装（2メソッド）
   - SplitsReader実装（5メソッド）
   - AggregateReader実装（8メソッド）
   - TimeSeriesReader実装（3メソッド）
   - ExportReader実装（1メソッド、Phase 1から移動）

3. **統合クラス実装（Day 4）**
   - GarminDBReader（委譲パターン）
   - 後方互換性テスト
   - 既存コードの動作確認

4. **テスト更新（Day 5）**
   - 各Readerクラスの単体テスト
   - 統合クラスの結合テスト
   - 既存テストの回帰テスト（470件全て）

5. **ドキュメント更新（Day 5）**
   - アーキテクチャ図更新
   - 各Readerクラスの責務明記
   - 使用例追加

**受け入れ基準:**
- [ ] 6つのクラスに分割完了（BaseDBReader + 5 Readers）
- [ ] 各クラスが単一責務原則に準拠（平均300行以下）
- [ ] 既存テスト470件が全てパス（後方互換性維持）
- [ ] 新規テスト追加（各Readerクラス単体テスト）
- [ ] Unit testsカバレッジ90%以上維持
- [ ] Type hints完全（mypy strict mode）

**期待される効果:**
- コード可読性向上（1639行 → 平均300行/クラス）
- メンテナンス性向上（変更影響範囲の明確化）
- テスト容易性向上（小規模クラスのモック作成）
- 新機能追加の容易化（適切なReaderクラスに追加）

### Phase 2: Python Helper Functions (Week 2-3)

**目標:** Python実行環境で安全にデータをロード・処理・出力するヘルパー関数群

**Tasks:**

1. **`safe_load_export()` 実装**
   - Parquet/CSVからの部分読み込み
   - サイズ制限チェック（10,000行）
   - Polars/Pandas対応
   - テスト: 正常ケース、サイズ超過ケース

2. **`safe_summary_table()` 実装**
   - DataFrameの10行制限出力
   - 省略表示（先頭5行＋末尾5行）
   - カラムサブセット指定
   - テスト: 10行以下、100行、1000行のDataFrame

3. **`safe_json_output()` 実装**
   - JSON出力の1KB制限
   - サイズ超過時のエラー
   - 日本語対応（ensure_ascii=False）
   - テスト: 小JSON、1KB境界、超過ケース

4. **`validate_output()` 実装**
   - JSON/テーブル出力の自動検証
   - サイズ超過検出
   - 警告メッセージ生成
   - テスト: JSON、テーブル、混在出力

**受け入れ基準:**
- [ ] 全関数が制限値を厳守
- [ ] サイズ超過時に適切なエラーメッセージ
- [ ] Polars/Pandas両対応
- [ ] Unit tests カバレッジ90%以上

### Phase 3: Output Validation & Guard (Week 3)

**目標:** LLM実行環境に出力ガードレールを統合し、意図しない大量出力を防止

**Tasks:**

1. **Output Interceptor実装**
   - Python実行結果の自動検証
   - サイズ超過時の自動トリム
   - 警告ログ出力
   - テスト: 正常出力、超過出力、混在出力

2. **Display Settings強制適用**
   - Pandas: `display.max_rows = 10`
   - Polars: `Config.set_tbl_rows(10)`
   - 実行環境の初期化スクリプト
   - テスト: DataFrame表示時の行数制限

3. **LLM Behavior Rules文書化**
   - 禁止事項リスト（生データ直接読み取り、全データ展開）
   - 推奨フロー（PLAN→EXPORT→CODE→RESULT→INTERPRET）
   - エラーパターンと対処法
   - CLAUDE.mdへの統合

4. **Error Handling統一**
   - サイズ超過エラーの標準フォーマット
   - リトライ可能な指示文生成
   - ログ出力標準化
   - テスト: 各種エラーケース

**受け入れ基準:**
- [ ] 100KB超の出力が自動トリムされる
- [ ] 警告メッセージが明確
- [ ] LLM Behavior Rulesが文書化
- [ ] Integration tests カバレッジ80%以上

### Phase 4: Example Analysis Flow (Week 3-4)

**目標:** 実際のユースケースを実装し、アーキテクチャの実用性を検証

**Tasks:**

1. **秒単位インターバル分析実装**
   - LLMプロンプト例作成
   - MCP `export()` 呼び出し
   - Python: リサンプリング＋ローリング平均＋グラフ生成
   - 結果解釈の自然言語生成
   - テスト: 5分区間、10分区間、全アクティビティ

2. **フォーム異常深堀り分析実装**
   - 異常検出後のドリルダウンフロー
   - 前後30秒窓の詳細データ抽出
   - 相関分析（ペース/HR/標高 vs GCT）
   - 散布図＋統計サマリー生成
   - テスト: GCT異常、VO異常、VR異常

3. **複数アクティビティ比較実装**
   - `profile()` で各アクティビティの要約取得
   - `export()` で複数アクティビティデータ取得
   - 正規化時間軸への整列
   - 重ね合わせグラフ生成
   - テスト: 2アクティビティ、5アクティビティ、10アクティビティ

4. **Jupyter Notebook Example作成**
   - 3つのユースケースをNotebook化
   - セルごとのトークンコスト計測
   - ビフォー/アフター比較（生データ vs アーキテクチャ適用）
   - docs/examples/ に配置

**受け入れ基準:**
- [ ] 3つのユースケースが完全動作
- [ ] トークンコスト70%以上削減
- [ ] Jupyter Notebook実行可能
- [ ] End-to-end tests カバレッジ80%以上

### Phase 5: Documentation & Testing (Week 4)

**目標:** ドキュメント整備とテスト完全性確保

**Tasks:**

1. **CLAUDE.md更新**
   - MCP Server Functions追加
   - Python Helper Functions追加
   - LLM Behavior Rules追加
   - Usage Examplesセクション追加

2. **API Documentation生成**
   - MCP関数のAPI仕様書
   - Python関数のdocstring完備
   - 使用例コード
   - エラーケース説明

3. **Performance Testing**
   - 10,000行、100,000行、1,000,000行のエクスポート性能
   - Parquet vs CSV速度比較
   - メモリ使用量測定
   - ベンチマーク結果文書化

4. **Integration Testing完全化**
   - MCP Server ↔ Python連携テスト
   - 実際のDuckDBデータでのE2Eテスト
   - エラーケース網羅テスト
   - CI/CD統合

**受け入れ基準:**
- [ ] CLAUDE.mdに全機能が文書化
- [ ] API documentationが完全
- [ ] Performance benchmarksが文書化
- [ ] テストカバレッジ90%以上（全体）

---

## テスト計画

### Unit Tests

**MCP Server Functions (`tests/test_mcp_export.py`):**
- [ ] `export()` - Parquet出力成功
- [ ] `export()` - CSV出力成功
- [ ] `export()` - max_rows超過エラー
- [ ] `export()` - 不正SQL構文エラー
- [ ] `profile()` - splits テーブル要約
- [ ] `profile()` - time_series_metrics テーブル要約
- [ ] `profile()` - date_range フィルタ
- [ ] `profile()` - 空テーブルケース
- [ ] `histogram()` - pace 分布（20 bins）
- [ ] `histogram()` - heart_rate 分布（10 bins）
- [ ] `histogram()` - NULL値含むカラム
- [ ] `materialize()` - ビュー作成成功
- [ ] `materialize()` - ビュー名衝突回避
- [ ] `materialize()` - TTL自動削除

**Python Helper Functions (`tests/test_llm_safe_data.py`):**
- [ ] `safe_load_export()` - 正常ロード（1000行）
- [ ] `safe_load_export()` - サイズ超過エラー（100,000行）
- [ ] `safe_load_export()` - Parquet/CSV両対応
- [ ] `safe_summary_table()` - 10行以下のDataFrame
- [ ] `safe_summary_table()` - 100行のDataFrame（省略表示）
- [ ] `safe_summary_table()` - カラムサブセット指定
- [ ] `safe_json_output()` - 正常JSON（500バイト）
- [ ] `safe_json_output()` - サイズ超過エラー（2KB）
- [ ] `safe_json_output()` - 日本語文字列
- [ ] `validate_output()` - 正常JSON
- [ ] `validate_output()` - 正常テーブル
- [ ] `validate_output()` - JSON超過検出
- [ ] `validate_output()` - テーブル超過検出

### Integration Tests

**MCP ↔ Python連携 (`tests/integration/test_mcp_python_flow.py`):**
- [ ] export() → safe_load_export() → 分析 → safe_json_output() フロー
- [ ] profile() → 条件判断 → export() 分岐フロー
- [ ] histogram() → グラフ生成 → ファイル保存フロー
- [ ] materialize() → 複数回クエリ → 性能改善検証
- [ ] エラーケース: サイズ超過 → リトライ → 集計クエリに変更

**実データテスト (`tests/integration/test_real_data.py`):**
- [ ] 実際のアクティビティデータで秒単位インターバル分析
- [ ] 実際のフォーム異常データで深堀り分析
- [ ] 実際の複数アクティビティで比較分析
- [ ] トークンコスト測定（ビフォー/アフター）

### Performance Tests

**Export Performance (`tests/performance/test_export_performance.py`):**
- [ ] 10,000行エクスポート: <1秒
- [ ] 100,000行エクスポート: <5秒
- [ ] 1,000,000行エクスポート: <30秒
- [ ] Parquet vs CSV速度比較: Parquet 3x faster
- [ ] メモリ使用量: 100,000行 < 100MB

**Query Performance (`tests/performance/test_query_performance.py`):**
- [ ] profile() 実行時間: <500ms
- [ ] histogram() 実行時間: <1秒
- [ ] materialize() による性能改善: 2-5x faster

**Output Validation Performance (`tests/performance/test_validation_performance.py`):**
- [ ] validate_output() オーバーヘッド: <10ms
- [ ] safe_json_output() シリアライズ: <50ms
- [ ] safe_summary_table() フォーマット: <100ms

---

## 受け入れ基準

### 機能要件

- [ ] MCP Server Functions (4関数) が実装され、ハンドルベースで動作
- [ ] Python Helper Functions (4関数) が実装され、サイズ制限を厳守
- [ ] Output Validation が統合され、自動トリム機能が動作
- [ ] 3つのExample Analysis Flowが完全動作
- [ ] トークンコスト70%以上削減（秒単位分析ユースケース）

### 品質要件

- [ ] Unit testsカバレッジ90%以上
- [ ] Integration testsカバレッジ80%以上
- [ ] Performance testsが全てパス
- [ ] Pre-commit hooks (Black, Ruff, Mypy) が全てパス
- [ ] 型ヒントが完全（mypy strict mode）

### ドキュメント要件

- [ ] CLAUDE.mdに新機能が統合
- [ ] API documentationが完全
- [ ] LLM Behavior Rulesが文書化
- [ ] Jupyter Notebook Examplesが実行可能
- [ ] Performance benchmarksが文書化

### セキュリティ要件

- [ ] 一時ファイルが自動クリーンアップ
- [ ] SQLインジェクション対策（パラメータ化クエリ）
- [ ] ファイルパストラバーサル対策
- [ ] メモリリーク検証

---

## リスク評価

### 高リスク

**R1: 既存エージェントのリファクタリング影響範囲**
- 影響度: 高（5エージェント中2エージェントが影響）
- 発生確率: 高
- 対策:
  - Phase 0で既存関数に後方互換性を維持
  - `statistics_only`はオプションパラメータ（デフォルト`False`）
  - 段階的移行: 警告 → 推奨 → 非推奨
  - エージェント更新前に既存動作の回帰テスト
- 軽減策: Phase 0でまず既存関数を更新、Phase 1で新規関数追加、Phase 4でエージェント更新

**R2: LLMが生データ読み取りを試行し続ける**
- 影響度: 高（アーキテクチャの根幹）
- 発生確率: 中
- 対策:
  - LLM Behavior Rulesを明示的に文書化
  - プロンプトテンプレートを提供
  - 出力検証で自動リジェクト
  - エラーメッセージで正しいフローを指示
- 軽減策: Phase 3で警告システム実装、Phase 4で正しい使用例を多数提供

**R3: 出力サイズ制限が厳しすぎて実用性が低下**
- 影響度: 中
- 発生確率: 中
- 対策:
  - Phase 2で制限値を実データでチューニング
  - JSON: 1KB → 2KB、テーブル: 10行 → 20行など調整可能
  - 大量出力が必要な場合はファイル保存を推奨
- 軽減策: Phase 4で実ユースケースを検証し、必要なら制限値を緩和

### 中リスク

**R4: Parquetエクスポートがディスク容量を圧迫**
- 影響度: 中
- 発生確率: 低
- 対策:
  - TTLベースの自動削除（デフォルト1時間）
  - ディスク使用量監視
  - 古いエクスポートの定期クリーンアップ
- 軽減策: Phase 1で自動クリーンアップを実装

**R5: 既存のMCPツール（get_split_time_series_detail等）との統合**
- 影響度: 中
- 発生確率: 中
- 対策:
  - 既存ツールは維持（後方互換性）
  - Phase 0で既存ツールを新アーキテクチャに適合
  - 新アーキテクチャは追加機能として提供
  - ユースケース別の推奨ツール選択ガイド作成
- 軽減策: Phase 0で既存関数を段階的に更新、Phase 5でツール選択ガイドをCLAUDE.mdに追加

**R8: GarminDBReaderリファクタリングの影響範囲**
- 影響度: 中
- 発生確率: 中
- 対策:
  - Phase 1.5で委譲パターン採用（後方互換性維持）
  - 既存テスト470件を全て回帰テスト
  - 段階的移行（統合クラス → 個別Readerへの直接アクセス推奨）
  - 既存コードは統合クラス経由で動作継続
- 軽減策: Phase 1.5で後方互換性を最優先、段階的な移行パス提供

### 低リスク

**R6: DuckDBのメモリ使用量増加（materialize利用時）**
- 影響度: 低
- 発生確率: 低
- 対策:
  - TTLベースのビュー削除
  - ビュー数制限（最大10個など）
  - メモリ使用量監視
- 軽減策: Phase 1でTTL実装、Phase 3でメモリ監視追加

**R7: Polars/Pandasの互換性問題**
- 影響度: 低
- 発生確率: 低
- 対策:
  - 両ライブラリ対応のヘルパー関数
  - 型ヒントで明示的に指定
  - Unit testsで両方をテスト
- 軽減策: Phase 2で両対応を実装

---

## 次のステップ

1. **GitHub Issue #25の更新**
   - planning.md URLを Issue descriptionに追加（完了）

2. **Git worktree作成 (tdd-implementer phase)**
   ```bash
   git worktree add -b feature/duckdb_mcp_llm_architecture ../duckdb_mcp_llm_arch main
   cd ../duckdb_mcp_llm_arch
   uv sync
   mcp__serena__activate_project("/absolute/path/to/duckdb_mcp_llm_arch")
   ```

3. **Phase 0開始（Week 1）**
   - 既存MCP関数のリファクタリング・統合・改廃
   - 後方互換性を維持しつつ段階的に更新
   - 依存エージェントの更新

4. **Phase 1開始（Week 2）**
   - 新規MCP Server Functions実装
   - TDDサイクルで進行

5. **定期レビュー**
   - 各Phase完了時にユーザーレビュー
   - 必要に応じて計画調整

---

**計画作成日**: 2025-10-16
**最終更新日**: 2025-10-16
**ステータス**: 実装中（Phase 0完了、Phase 1進行中）
**推定期間**: 4-5週間
**変更履歴**:
- 2025-10-16: 初版作成
- 2025-10-16: Phase 0追加（既存MCP関数リファクタリング）、依存エージェント更新追加、リスク評価更新
- 2025-10-16: Phase 1.5追加（GarminDBReaderクラス分割・整理）、スコープ更新、リスク評価追加（R8）
