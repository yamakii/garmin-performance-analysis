# 計画: コアシステムコンポーネントの復元

## 要件定義

### 目的
git filter-repoで削除された重要なPythonコンポーネントを復元し、analyze-activityコマンドが正常に動作するようにする。

### 解決する問題
現在、以下のコンポーネントが欠落しており、analyze-activityコマンドが実行できない：
1. **GarminIngestWorker**: データ収集・前処理の中核
2. **ValidationWorker**: データ品質検証
3. **Performance Inserters**: DuckDBへのデータ挿入
4. **Section Analysis Inserters**: セクション分析結果のDuckDB挿入
5. **Workflow Planner関連**: エージェント実行・キャッシュ管理

### ユースケース

**UC1: Activity分析実行**
```bash
# ユーザーがactivity分析を実行
/analyze-activity 20464005432 2025-09-22

# 期待される動作:
1. GarminIngestWorkerがGarmin APIからデータ取得
2. raw_data.json, performance.json, .parquet生成
3. ValidationWorkerがデータ検証
4. 5つのエージェントが並列分析実行
5. DuckDBに全結果を保存
6. 最終レポート生成
```

**UC2: バッチ処理**
```bash
# 複数activityを一括処理
python tools/batch/batch_planner.py --start-date 2025-09-01 --end-date 2025-09-30
```

---

## 設計

### アーキテクチャ

```
/analyze-activity {activity_id} {date}
    ↓
【Main Claude Code Agent】

Step 1: データ収集
    GarminIngestWorker.process_activity()
        ├─ collect_data() → Garmin MCP呼び出し
        ├─ create_parquet_dataset() → lapDTOs → DataFrame
        ├─ _calculate_split_metrics() → performance.json生成
        └─ save_data() → 3ファイル出力
    ↓
    ValidationWorker.validate() (オプション)
        └─ データ品質チェック
    ↓
    PerformanceDataInserter.insert()
        └─ performance.json → DuckDB

Step 2: セクション分析（並列実行）
    【Main AgentがTaskツールで5エージェント起動】
    ├─ Task: efficiency-section-analyst
    │   └─ mcp__garmin-db__get_performance_section() → 分析 → DuckDB
    ├─ Task: environment-section-analyst
    │   └─ mcp__garmin-db__get_performance_section() → 分析 → DuckDB
    ├─ Task: phase-section-analyst
    │   └─ mcp__garmin-db__get_performance_section() → 分析 → DuckDB
    ├─ Task: split-section-analyst
    │   └─ mcp__garmin-db__get_splits_complete() → 分析 → DuckDB
    └─ Task: summary-section-analyst
        └─ mcp__garmin-db__get_section_analysis() × 4 → 統合 → DuckDB

Step 3: レポート生成
    【Main AgentがTaskツールでreport-generatorエージェント起動】
    Task: report-generator
        ├─ mcp__report-generator__create_report_structure()
        ├─ mcp__garmin-db__get_section_analysis() × 5
        ├─ 13プレースホルダー置換
        └─ mcp__report-generator__finalize_report()
            → result/individual/{YEAR}/{MONTH}/{DATE}_activity_{ID}.md
```

**重要**:
- エージェント起動はClaude CodeのTaskツールが行う（Pythonコード不要）
- 各エージェントは独立して動作し、結果をDuckDBに保存
- Main Agentはワークフロー全体をオーケストレーション

### 復元優先度

**Phase 1: 最重要（analyze-activity必須コンポーネント）** ✅ 完了
1. ✅ `tools/database/db_reader.py` - 既に復元済み
2. ✅ `tools/database/db_writer.py` - 既に復元済み
3. ✅ `tools/reporting/report_generator_worker.py` - 既に復元済み
4. ✅ `tools/reporting/report_template_renderer.py` - 既に復元済み
5. ✅ `tools/ingest/garmin_worker.py` - データ収集の中核（復元完了、動作確認済み）
6. ✅ `tools/database/inserters/performance.py` - DuckDB挿入（復元完了、動作確認済み）
7. ✅ `tools/database/inserters/section_analyses.py` - DuckDB挿入（復元完了、動作確認済み）
8. ✅ `tools/validation/validation_worker.py` - データ検証（オプション、復元完了）

**注意**: エージェント並列実行はClaude CodeのTaskツールが行うため、AgentExecutorクラスは不要

**Phase 2: バッチ処理・ユーティリティ** ✅ 完了（必須コンポーネント）
9. ✅ `tools/scripts/bulk_fetch_raw_data.py` - Raw data一括取得（API fetching）
10. ✅ `tools/scripts/regenerate_duckdb.py` - DuckDB再生成（raw data → DuckDB）
11. ⏭️ `tools/batch/batch_planner.py` - バッチ処理（オプション、未実装）
12. ⏭️ `tools/database/analysis_helpers.py` - 分析補助関数（オプション、未実装）

**Phase 3: RAG機能** ⏭️ スコープ外（別プロジェクトで実装）
- RAG MCPサーバーは既に実装済み（Garmin DB MCP Phase 2.5/3）
- Pythonラッパーは必要に応じて別プロジェクトで実装
- 理由: MCPサーバー経由で直接利用可能、Pythonラッパーは必須ではない

**オプショナルコンポーネント** ⏭️ スコープ外（必要に応じて別プロジェクトで実装）
- `tools/batch/batch_planner.py` - バッチ処理オーケストレーション
- `tools/database/analysis_helpers.py` - DuckDB分析補助関数
- 理由: 既存スクリプト（bulk_fetch_raw_data.py, regenerate_duckdb.py）で基本機能は完結

**Phase 4: Workflow Planner** ✅ 削除済み（Claude Code Taskツールが代替）
- ~~`tools/planner/agent_executor.py`~~ - 削除（Claude CodeのTaskツールが代替）
- ~~`tools/planner/activity_date_cache.py`~~ - 削除（DuckDBで代替）
- ~~`tools/planner/main.py`~~ - 削除（analyze-activityコマンドで代替）
- ~~`tools/planner/cache_manager.py`~~ - 削除（不要）
- ~~`tools/planner/metrics_collector.py`~~ - 削除（不要）
- ~~`tools/planner/worker_adapters.py`~~ - 削除（不要）

### データフロー

```
Garmin API
    ↓ (GarminIngestWorker.collect_data)
data/raw/{activity_id}_raw.json
    ↓ (GarminIngestWorker.create_parquet_dataset)
data/parquet/{activity_id}.parquet
data/performance/{activity_id}.json
data/precheck/{activity_id}.json
    ↓ (PerformanceDataInserter.insert)
DuckDB: performance_data, activities
    ↓ (5 Agents)
DuckDB: section_analyses (5 rows)
    ↓ (ReportGeneratorWorker)
result/individual/{YEAR}/{MONTH}/{DATE}_activity_{ID}.md
```

---

## コンポーネント詳細仕様

### 1. GarminIngestWorker

**ファイル**: `tools/ingest/garmin_worker.py`

**主要メソッド**:
```python
class GarminIngestWorker:
    def __init__(self):
        """Initialize with Garmin MCP client."""

    def collect_data(self, activity_id: int) -> dict:
        """
        Garmin MCPからデータ収集。

        呼び出すMCPツール:
        - mcp__garmin__get_activity(activity_id)
        - mcp__garmin__get_activity_splits(activity_id)
        - mcp__garmin__get_activity_weather(activity_id)
        - mcp__garmin__get_activity_gear(activity_id)
        - mcp__garmin__get_activity_hr_in_timezones(activity_id)

        Returns:
            {
                "activity": {...},
                "splits": {"lapDTOs": [...]},
                "weather": {...},
                "gear": {...},
                "hr_zones": {...}
            }
        """

    def create_parquet_dataset(self, raw_data: dict) -> pd.DataFrame:
        """
        lapDTOsからParquet用DataFrameを生成。

        抽出フィールド:
        - split_number, distance_km, duration_seconds
        - avg_pace_seconds_per_km, avg_heart_rate, avg_cadence
        - avg_power, ground_contact_time_ms
        - vertical_oscillation_cm, vertical_ratio_percent
        - elevation_gain_m, elevation_loss_m
        - max_elevation_m, min_elevation_m
        - terrain_type (平坦/起伏/丘陵/山岳)

        Returns:
            DataFrame with 22 columns
        """

    def _calculate_split_metrics(self, df: pd.DataFrame) -> dict:
        """
        パフォーマンスメトリクスを計算。

        Phase 1実装（既存）:
        - basic_metrics
        - heart_rate_zones
        - split_metrics
        - efficiency_metrics

        Phase 1追加（2025-09-30）:
        - form_efficiency_summary (GCT/VO/VR統計)
        - hr_efficiency_analysis (zone distribution, training type)

        Phase 2追加（2025-09-30）:
        - performance_trends (warmup/main/finish phase analysis)

        Returns:
            performance.json structure (11 sections)
        """

    def process_activity(
        self, activity_id: int, date: str | None = None
    ) -> dict:
        """
        完全なパイプライン実行。

        1. collect_data()
        2. create_parquet_dataset()
        3. _calculate_split_metrics()
        4. save_data()

        Returns:
            {
                "activity_id": int,
                "date": str,
                "raw_file": str,
                "parquet_file": str,
                "performance_file": str,
                "precheck_file": str
            }
        """

    def save_data(
        self,
        activity_id: int,
        raw_data: dict,
        df: pd.DataFrame,
        performance_data: dict,
    ) -> dict:
        """
        3種類のファイルを保存。

        出力:
        - data/raw/{activity_id}_raw.json
        - data/parquet/{activity_id}.parquet
        - data/performance/{activity_id}.json
        - data/precheck/{activity_id}.json
        """
```

### 2. ValidationWorker

**ファイル**: `tools/validation/validation_worker.py`

**主要メソッド**:
```python
class ValidationWorker:
    def validate(self, performance_file: str) -> dict:
        """
        performance.jsonの品質検証。

        検証項目:
        - 必須フィールド存在確認
        - 数値範囲チェック（HR: 40-220, Cadence: 120-200）
        - スプリット数の妥当性
        - データ完全性（欠損値）

        Returns:
            {
                "valid": bool,
                "errors": list[str],
                "warnings": list[str]
            }
        """
```

### 3. PerformanceDataInserter

**ファイル**: `tools/database/inserters/performance.py`

**主要関数**:
```python
def insert_performance_data(
    performance_file: str,
    activity_id: int,
    activity_date: str
) -> bool:
    """
    performance.jsonをDuckDBに挿入。

    1. db_writer.insert_activity() - activitiesテーブル
    2. db_writer.insert_performance_data() - performance_dataテーブル

    Returns:
        True if successful
    """
```

### 4. SectionAnalysisInserter

**ファイル**: `tools/database/inserters/section_analyses.py`

**主要関数**:
```python
def insert_section_analysis(
    analysis_data: dict,
    activity_id: int,
    activity_date: str,
    section_type: str
) -> bool:
    """
    エージェント分析結果をDuckDBに挿入。

    section_type: efficiency, environment, phase, split, summary

    Uses:
        db_writer.insert_section_analysis()

    Returns:
        True if successful
    """
```

### 5. エージェント実行（Claude Code Taskツール）

**実行方法**: Main AgentがTaskツールを使用

**analyze-activityコマンドの実装**:
```markdown
### Step 2: セクション分析（並列実行）

5つのエージェントを並列で呼び出してください：

Task: efficiency-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) のフォーム効率と心拍効率を分析してください。"

Task: environment-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) の環境要因を分析してください。"

Task: phase-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) の3フェーズを評価してください。"

Task: split-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) の全スプリットを分析してください。"

Task: summary-section-analyst
prompt: "Activity ID {{arg1}} ({{arg2}}) の総合評価を生成してください。"
```

**重要**: Pythonコードではなく、Claude CodeのTaskツールを使用するため、`AgentExecutor`クラスは不要

### 6. bulk_fetch_raw_data.py（Phase 2）

**ファイル**: `tools/scripts/bulk_fetch_raw_data.py`

**目的**: Garmin API から raw data を一括取得（存在しないファイルのみ）

**主要機能**:
```python
def bulk_fetch_raw_data(
    start_date: str | None = None,
    end_date: str | None = None,
    activity_ids: list[int] | None = None,
    api_types: list[str] | None = None,
    force: bool = False,
) -> dict:
    """
    Garmin API から raw data を一括取得。

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        activity_ids: 特定のactivity IDリスト（日付範囲と排他）
        api_types: 取得するAPI種類（デフォルト: 全て）
            ['activity', 'activity_details', 'splits', 'weather',
             'gear', 'hr_zones', 'vo2_max', 'lactate_threshold']
        force: 既存ファイルを強制再取得

    Returns:
        {
            "total": int,
            "fetched": int,
            "skipped": int,
            "failed": int,
            "errors": list[tuple[int, str]]
        }
    """
```

**使用例**:
```bash
# 日付範囲で取得（存在しないファイルのみ）
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31

# 特定のAPI種類のみ取得
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --api-types weather vo2_max

# 特定のactivity IDリストで取得
uv run python tools/scripts/bulk_fetch_raw_data.py --activity-ids 12345 67890 11111

# 既存ファイルを強制再取得
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --force

# Dry run（何が取得されるか確認のみ）
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --dry-run
```

**実装詳細**:
- `data/raw/activity/{activity_id}/{api_type}.json` が存在するか確認
- 存在しない場合のみ API から取得（`force=False` の場合）
- Garminconnect ライブラリを使用（rate limit に注意）
- エラー時は該当 activity をスキップし、最後にサマリー表示

### 7. regenerate_duckdb.py（Phase 2）

**ファイル**: `tools/scripts/regenerate_duckdb.py`

**目的**: raw data から DuckDB を再生成（performance.json は中間生成）

**主要機能**:
```python
def regenerate_duckdb(
    start_date: str | None = None,
    end_date: str | None = None,
    activity_ids: list[int] | None = None,
    delete_old_db: bool = False,
) -> dict:
    """
    raw data から DuckDB を再生成。

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        activity_ids: 特定のactivity IDリスト（日付範囲と排他）
        delete_old_db: 既存DuckDBを削除してから再生成

    Process:
        1. raw data 読み込み（data/raw/activity/{activity_id}/）
        2. performance.json 自動生成（GarminIngestWorker.process_activity）
        3. DuckDB 挿入（normalized tables + section_analyses）

    Returns:
        {
            "total": int,
            "success": int,
            "failed": int,
            "errors": list[tuple[int, str]]
        }
    """
```

**使用例**:
```bash
# 全activityを再生成（既存DuckDBを保持）
uv run python tools/scripts/regenerate_duckdb.py

# 日付範囲で再生成
uv run python tools/scripts/regenerate_duckdb.py --start-date 2025-01-01 --end-date 2025-01-31

# 特定のactivity IDリストで再生成
uv run python tools/scripts/regenerate_duckdb.py --activity-ids 12345 67890

# 既存DuckDBを削除してから再生成（完全リセット）
uv run python tools/scripts/regenerate_duckdb.py --delete-db

# Dry run（何が再生成されるか確認のみ）
uv run python tools/scripts/regenerate_duckdb.py --dry-run
```

**実装詳細**:
- `GarminIngestWorker.process_activity()` を使用
- performance.json は自動生成される（明示的な Phase A は不要）
- DuckDB キャッシュがある場合はスキップ（`--delete-db` で強制再生成）
- raw data が存在しない場合はエラー（API fetch は行わない）

**⚠️ 重要な設計原則**:
1. **API Fetching と Data Regeneration の完全分離**:
   - `bulk_fetch_raw_data.py`: Garmin API → raw data（API呼び出しあり）
   - `regenerate_duckdb.py`: raw data → DuckDB（API呼び出しなし）

2. **performance.json は中間ファイル**:
   - DuckDB 再生成時に自動生成される
   - 明示的な Phase A（performance.json 生成）は不要
   - `GarminIngestWorker.process_activity()` が内部で生成

3. **存在しないファイルのみ取得**:
   - `bulk_fetch_raw_data.py` は既存ファイルをスキップ（`--force` なし）
   - API rate limit を回避

---

## テスト計画

### Unit Tests

**tools/ingest/test_garmin_worker.py**
- [ ] `test_collect_data_success`: MCP呼び出し成功
- [ ] `test_collect_data_api_error`: API エラーハンドリング
- [ ] `test_create_parquet_dataset`: lapDTOs → DataFrame変換
- [ ] `test_calculate_split_metrics`: メトリクス計算の正確性
- [ ] `test_save_data`: ファイル出力

**tools/validation/test_validation_worker.py**
- [ ] `test_validate_valid_data`: 正常データの検証
- [ ] `test_validate_missing_fields`: 必須フィールド欠落検出
- [ ] `test_validate_invalid_ranges`: 数値範囲エラー検出

**tools/database/inserters/test_performance.py**
- [ ] `test_insert_performance_data_success`: DuckDB挿入成功
- [ ] `test_insert_performance_data_duplicate`: 重複時の上書き

### Integration Tests

**tests/integration/test_full_workflow.py**
- [ ] `test_analyze_activity_workflow`: 完全なワークフロー実行
  1. GarminIngestWorker.process_activity()
  2. ValidationWorker.validate()
  3. insert_performance_data()
  4. 5 agents並列実行
  5. insert_section_analysis() × 5
  6. ReportGeneratorWorker.generate_report()

**tests/integration/test_duckdb_integration.py**
- [ ] `test_performance_insert_and_read`: Insert → Read ラウンドトリップ
- [ ] `test_section_analysis_insert_and_read`: 5セクション挿入 → 取得

### Performance Tests

**tests/performance/test_batch_processing.py**
- [ ] `test_10_activities_processing`: 10 activities < 30秒
- [ ] `test_parallel_agent_execution`: 5 agents並列 < 10秒

---

## 実装戦略

### ステップ1: .pycファイルから構造推測
```bash
# 各.pycファイルからstrings抽出
strings tools/ingest/__pycache__/garmin_worker.cpython-312.pyc > garmin_worker_strings.txt

# 関数名、クラス名、import文を特定
grep -E "def |class |import |from " garmin_worker_strings.txt
```

### ステップ2: CLAUDE.mdとコンテキストから仕様補完
- Data Processing Architectureセクションを参照
- analyze-activityコマンドのワークフローを分析
- エージェントファイルから期待される入出力を推測

### ステップ3: TDD実装
1. テスト作成（Red）
2. 最小実装（Green）
3. リファクタリング（Refactor）

### ステップ4: 段階的復元
- Phase 1優先（GarminIngestWorker, Inserters, ValidationWorker）
- 各Phaseごとにcommit
- 全Phase完了後に完了レポート作成

---

## 受け入れ基準

- [x] analyze-activityコマンドが正常に動作する（Phase 1完了、動作確認済み）
- [x] 全Unit Testsがパスする（カバレッジ80%以上）（Phase 1: 17/17テスト通過）
- [x] Integration Testsがパスする（Phase 1: 完全ワークフロー動作確認済み）
- [x] Pre-commit hooksがパスする（black, ruff, mypy）（Phase 1完了）
- [x] CLAUDE.mdが更新されている（Garmin DB MCP Phase 2.5/3追加）
- [ ] completion_report.mdが作成されている（Phase 2完了後に作成）

---

## 推定工数（実績）

- **Phase 1**: 完了（GarminIngestWorker, Inserters, ValidationWorker - 17テスト通過）
- **Phase 2**: 完了（bulk_fetch_raw_data.py, regenerate_duckdb.py）
- **Phase 3**: スコープ外（RAG MCPサーバー既に実装済み）
- **オプショナル**: スコープ外（batch_planner.py, analysis_helpers.py）
- **テスト**: Phase 1完了（17/17通過）、Phase 2は既存インフラで動作確認可能
- **ドキュメント**: planning.md, phase1_completion_report.md, completion_report.md

**実装期間**: 2025-10-07 〜 2025-10-12（5日間）

**削減理由**:
- AgentExecutor等のworkflow plannerコンポーネントは不要（Claude CodeのTaskツールが代替）
- RAG機能はMCPサーバー経由で既に利用可能
- バッチ処理スクリプトで基本的な運用要件は満たされる

---

## リスク

1. **.pycファイルからの情報不足**: 完全な実装詳細が復元できない可能性
   - 対策: CLAUDE.mdとコンテキストから推測、最小限の実装で開始

2. **Garmin MCP仕様変更**: 過去のMCP呼び出しと現在の仕様が異なる可能性
   - 対策: mcp__garmin__* ツールの最新仕様を確認

3. **DuckDBスキーマ不整合**: 既存スキーマとInserterの期待値が異なる
   - 対策: db_writer.pyの_ensure_tables()で検証
