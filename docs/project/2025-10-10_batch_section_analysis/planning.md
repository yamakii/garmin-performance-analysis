# 計画: batch_section_analysis

## Git Worktree情報
- **Worktree Path**: `../garmin-batch_section_analysis/`
- **Branch**: `feature/batch_section_analysis`
- **Base Branch**: `main`

---

## 要件定義

### 目的
5つのセクション分析エージェント（split, phase, summary, efficiency, environment）を並列実行するバッチ処理システムを実装し、複数アクティビティの分析を効率的に処理する。パフォーマンスデータは既にDuckDBに格納されており、レポート生成は別プロセスで行う。

### 解決する問題

**現状の課題:**
- 現在は手動で各アクティビティに対して5つのエージェントを逐次的に呼び出す必要がある
- 50アクティビティの場合、50 × 5 = 250回のエージェント呼び出しが必要
- 逐次処理では1アクティビティあたり約5分 × 50 = 250分（4.2時間）かかる
- 進捗の追跡やエラー処理が手動管理で非効率
- 処理が中断した場合、どこから再開すべきか不明

**影響:**
- 大量のアクティビティ分析に時間がかかりすぎる
- 処理中断時のリカバリーが困難
- エラーの一元管理ができない
- リソースの非効率的な利用（並列化できるのに逐次処理）

### ユースケース

1. **データアナリスト（一括分析）**
   - 全アクティビティのセクション分析を一括実行
   - 進捗状況をリアルタイムで確認
   - 完了後にサマリーレポートを確認

2. **システム運用者（差分更新）**
   - 新規追加されたアクティビティのみを分析
   - DuckDBを検索して未分析アクティビティを特定
   - バッチサイズを調整してリソース利用を最適化

3. **開発者（デバッグ・検証）**
   - Dry runで実行計画を確認
   - 特定期間のアクティビティのみを対象に実行
   - エラー発生時の詳細ログを確認

---

## 設計

### アーキテクチャ

**設計方針:**
1. **並列化**: 複数アクティビティ × 5エージェント = 10-15並列タスク
2. **進捗管理**: JSON形式で進捗を記録し、中断時に再開可能
3. **エラーハンドリング**: 個別タスクのエラーでバッチ全体が停止しない
4. **DuckDB統合**: activities テーブルと section_analyses テーブルを活用
5. **Claude Code Task API**: エージェント呼び出しには Task API を使用（想定）

**コンポーネント構成:**
```
BatchSectionAnalyzer (メインクラス)
  ├─ ActivityQuery
  │   ├─ query_all_activities(): 全アクティビティ取得
  │   ├─ query_missing_analyses(): 未分析アクティビティ取得
  │   └─ filter_by_date_range(): 日付範囲フィルター
  │
  ├─ ProgressTracker
  │   ├─ load_progress(): 進捗JSONを読み込み
  │   ├─ save_progress(): 進捗を保存
  │   ├─ mark_completed(): タスク完了マーク
  │   └─ get_pending_tasks(): 未完了タスクを取得
  │
  ├─ BatchExecutor
  │   ├─ launch_agents_parallel(): 並列エージェント起動
  │   ├─ wait_for_completion(): 完了待機
  │   └─ collect_results(): 結果収集
  │
  └─ ResultVerifier
      ├─ verify_completion(): DuckDBで完了確認
      ├─ check_section_analyses(): 5セクション全て存在確認
      └─ generate_summary(): サマリーレポート生成
```

**処理フロー:**
```
1. ActivityQuery: DuckDBから対象アクティビティ取得
   ↓
2. ProgressTracker: 既存進捗を読み込み（再開時）
   ↓
3. BatchExecutor: バッチ実行
   For each batch (2-3 activities):
     For each activity:
       Launch 5 agents in parallel:
         - split-section-analyst
         - phase-section-analyst
         - summary-section-analyst
         - efficiency-section-analyst
         - environment-section-analyst
     Wait for batch completion
     Save progress
   ↓
4. ResultVerifier: DuckDBで完了確認
   ↓
5. Summary: 実行結果サマリー表示
```

**並列化戦略:**
```
Sequential (現状):
Activity 1 → Agent 1,2,3,4,5 (5分)
Activity 2 → Agent 1,2,3,4,5 (5分)
...
Total: 50 activities × 5min = 250min (4.2h)

Parallel (提案):
Batch 1: Activity 1-3 × 5 agents = 15 parallel tasks (5分)
Batch 2: Activity 4-6 × 5 agents = 15 parallel tasks (5分)
...
Total: 17 batches × 5min = 85min (1.4h)
```

**並列度の制限:**
- バッチサイズ: 2-3 activities（デフォルト: 3）
- 並列タスク数: 10-15（Claude Code Task API制限を考慮）
- リトライ: エラー発生時に最大3回リトライ

### データモデル

**Input:**
```sql
-- DuckDB activities table
SELECT activity_id, date
FROM activities
WHERE date >= '2025-01-01'
ORDER BY date DESC;
```

**Progress JSON:**
```json
{
  "version": "1.0",
  "start_time": "2025-10-10T10:00:00Z",
  "last_update": "2025-10-10T10:15:00Z",
  "total_activities": 50,
  "completed_activities": 15,
  "failed_activities": 2,
  "tasks": [
    {
      "activity_id": 20615445009,
      "date": "2025-10-07",
      "status": "completed",
      "sections": {
        "split": {"status": "success", "completed_at": "2025-10-10T10:05:00Z"},
        "phase": {"status": "success", "completed_at": "2025-10-10T10:05:30Z"},
        "summary": {"status": "success", "completed_at": "2025-10-10T10:06:00Z"},
        "efficiency": {"status": "success", "completed_at": "2025-10-10T10:06:30Z"},
        "environment": {"status": "success", "completed_at": "2025-10-10T10:07:00Z"}
      }
    },
    {
      "activity_id": 20612340123,
      "date": "2025-10-06",
      "status": "failed",
      "sections": {
        "split": {"status": "success", "completed_at": "2025-10-10T10:08:00Z"},
        "phase": {"status": "error", "error": "Timeout", "retry_count": 3}
      }
    }
  ]
}
```

**Output (DuckDB section_analyses table):**
```sql
-- 各アクティビティで5レコード挿入される
SELECT activity_id, section_type, created_at
FROM section_analyses
WHERE activity_id = 20615445009;

-- Expected result:
-- 20615445009 | split      | 2025-10-10 10:05:00
-- 20615445009 | phase      | 2025-10-10 10:05:30
-- 20615445009 | summary    | 2025-10-10 10:06:00
-- 20615445009 | efficiency | 2025-10-10 10:06:30
-- 20615445009 | environment| 2025-10-10 10:07:00
```

### API/インターフェース設計

```python
# tools/batch_section_analysis.py

from pathlib import Path
from typing import Literal
import duckdb

SectionType = Literal["split", "phase", "summary", "efficiency", "environment"]

class BatchSectionAnalyzer:
    """Batch processing system for section analysis agents."""

    def __init__(
        self,
        db_path: Path | None = None,
        progress_file: Path | None = None,
        batch_size: int = 3,
        max_retries: int = 3,
    ):
        """
        Initialize batch analyzer.

        Args:
            db_path: DuckDB database path (default: data/database/garmin.db)
            progress_file: Progress tracking JSON file (default: data/progress/batch_analysis.json)
            batch_size: Number of activities per batch (default: 3)
            max_retries: Maximum retry count for failed tasks (default: 3)
        """

    def query_target_activities(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        missing_only: bool = True,
    ) -> list[tuple[int, str]]:
        """
        Query target activities from DuckDB.

        Args:
            start_date: Start date filter (YYYY-MM-DD)
            end_date: End date filter (YYYY-MM-DD)
            missing_only: Only return activities without complete section analyses

        Returns:
            List of (activity_id, date) tuples
        """

    def execute_batch(
        self,
        activities: list[tuple[int, str]],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Execute batch analysis.

        Args:
            activities: List of (activity_id, date) tuples
            dry_run: If True, only show execution plan without actual execution

        Returns:
            Execution summary with success/failure counts
        """

    def launch_agent(
        self,
        agent_name: str,
        activity_id: int,
        date: str,
    ) -> AgentTask:
        """
        Launch a single agent task.

        Args:
            agent_name: Agent name (e.g., "split-section-analyst")
            activity_id: Activity ID
            date: Activity date (YYYY-MM-DD)

        Returns:
            AgentTask object for tracking
        """

    def wait_for_batch_completion(
        self,
        tasks: list[AgentTask],
        timeout: int = 600,
    ) -> dict[str, int]:
        """
        Wait for all tasks in a batch to complete.

        Args:
            tasks: List of AgentTask objects
            timeout: Timeout in seconds (default: 10 minutes)

        Returns:
            Summary with success/failure/timeout counts
        """

    def verify_completion(
        self,
        activity_id: int,
    ) -> dict[SectionType, bool]:
        """
        Verify that all 5 sections are completed in DuckDB.

        Args:
            activity_id: Activity ID to verify

        Returns:
            Dict mapping section_type to completion status
        """

    def generate_summary_report(self) -> str:
        """
        Generate execution summary report.

        Returns:
            Formatted summary string
        """


# CLI Interface
def main():
    """
    CLI entry point.

    Usage:
        # Analyze all activities missing section analysis
        python tools/batch_section_analysis.py --all

        # Analyze specific date range
        python tools/batch_section_analysis.py --start 2025-01-01 --end 2025-12-31

        # Dry run (show execution plan)
        python tools/batch_section_analysis.py --all --dry-run

        # Configure batch size
        python tools/batch_section_analysis.py --all --batch-size 3

        # Resume from previous progress
        python tools/batch_section_analysis.py --resume

    Options:
        --all: Analyze all activities with missing section analyses
        --start: Start date (YYYY-MM-DD)
        --end: End date (YYYY-MM-DD)
        --batch-size: Number of activities per batch (default: 3)
        --dry-run: Show execution plan without running
        --resume: Resume from previous progress file
        --force: Force re-analysis even if sections exist
    """
```

**実行例:**
```bash
# 全アクティビティ分析（未分析のみ）
uv run python tools/batch_section_analysis.py --all

# 特定期間のみ
uv run python tools/batch_section_analysis.py --start 2025-10-01 --end 2025-10-31

# Dry run（実行計画確認）
uv run python tools/batch_section_analysis.py --all --dry-run

# バッチサイズ調整
uv run python tools/batch_section_analysis.py --all --batch-size 2

# 中断から再開
uv run python tools/batch_section_analysis.py --resume
```

**出力例:**
```
=== Batch Section Analysis ===

Target Activities: 50
Batch Size: 3 activities/batch
Expected Batches: 17
Estimated Time: 85 minutes (1.4 hours)

Progress: [###########···············] 40% (20/50)
Current Batch: 7/17
Completed: 20 activities
Failed: 2 activities
Remaining: 28 activities

=== Summary ===
Total Activities: 50
Successful: 48 (96%)
Failed: 2 (4%)
Total Time: 92 minutes

Failed Activities:
- 20612340123 (2025-10-06): phase section timeout
- 20609870456 (2025-10-03): environment section API error
```

---

## テスト計画

### Unit Tests

- [ ] **test_query_target_activities**: DuckDB クエリが正しく動作
  - 全アクティビティ取得
  - 日付範囲フィルター
  - 未分析アクティビティのみフィルター
  - 空の結果を適切に処理

- [ ] **test_progress_tracker_save_load**: 進捗管理が正しく動作
  - 新規進捗ファイル作成
  - 既存進捗ファイル読み込み
  - タスク完了マーク
  - 進捗保存

- [ ] **test_verify_completion**: 完了確認が正しく動作
  - 5セクション全て存在する場合
  - 一部セクションが欠落している場合
  - DuckDBへのクエリが正確

- [ ] **test_generate_summary_report**: サマリー生成が正しく動作
  - 成功率計算
  - 失敗アクティビティリスト
  - 実行時間計測

### Integration Tests

- [ ] **test_batch_execution_with_mock_agents**: モックエージェントでバッチ実行
  - 複数バッチの並列処理
  - 進捗ファイル更新
  - DuckDB挿入確認（モック）

- [ ] **test_error_handling_and_retry**: エラーハンドリングとリトライ
  - 個別タスク失敗時にバッチ継続
  - 最大リトライ回数到達
  - エラーログ記録

- [ ] **test_resume_from_progress**: 中断からの再開
  - 既存進捗ファイルを読み込み
  - 未完了タスクのみ実行
  - 完了タスクはスキップ

- [ ] **test_dry_run_mode**: Dry runモードが正しく動作
  - エージェント起動なし
  - 実行計画のみ表示
  - DuckDBへの書き込みなし

### Performance Tests

- [ ] **test_performance_50_activities**: 50アクティビティの処理時間
  - 目標: 逐次処理の50-66%の時間（2.1-2.8時間以内）
  - バッチサイズ3の場合: 17バッチ × 5分 = 85分 ≈ 1.4時間
  - バッチサイズ2の場合: 25バッチ × 5分 = 125分 ≈ 2.1時間

- [ ] **test_memory_usage**: メモリ使用量が適切
  - 大量のアクティビティ処理中もメモリリークなし
  - ピークメモリ使用量 < 1GB

- [ ] **test_parallel_efficiency**: 並列化の効率
  - バッチ内の5エージェントが真に並列実行されている
  - 待機時間が最小化されている
  - CPU使用率が適切

---

## 実装フェーズ

### Phase 1: Core Classes（優先度: 高）
1. `ActivityQuery` クラス実装
   - DuckDB接続と基本クエリ
   - 日付範囲フィルター
   - 未分析アクティビティ検出

2. `ProgressTracker` クラス実装
   - JSON形式の進捗管理
   - load/save/mark_completed メソッド
   - ファイルロック機構（並列実行時の競合回避）

3. `ResultVerifier` クラス実装
   - DuckDBでの完了確認
   - 5セクション全存在チェック
   - サマリーレポート生成

### Phase 2: Agent Integration（優先度: 高）
1. `AgentTask` クラス実装
   - エージェント起動インターフェース
   - タスクステータス管理
   - タイムアウト処理

2. `BatchExecutor` クラス実装
   - 並列エージェント起動
   - バッチ完了待機
   - エラーハンドリングとリトライ

3. Claude Code Task API 統合
   - エージェント呼び出し実装
   - 非同期実行管理
   - 結果収集

### Phase 3: CLI Interface（優先度: 中）
1. argparse設定
   - --all, --start, --end, --batch-size オプション
   - --dry-run, --resume, --force オプション

2. main() 関数実装
   - エントリーポイント
   - 進捗表示（tqdm使用）
   - サマリー出力

3. ヘルプメッセージとドキュメント

### Phase 4: Testing（優先度: 高）
1. Unit tests実装（pytest）
   - ActivityQuery tests
   - ProgressTracker tests
   - ResultVerifier tests

2. Integration tests実装（モックAPI使用）
   - Batch execution tests
   - Error handling tests
   - Resume tests

3. Performance tests実装
   - 50 activities benchmark
   - Memory usage monitoring

### Phase 5: Documentation & Deployment（優先度: 中）
1. README更新（Usage section追記）
2. CLAUDE.md更新（Common Development Commands）
3. 実環境でのテスト実行（10アクティビティ程度）
4. completion_report.md作成

---

## 受け入れ基準

### 機能要件
- [ ] DuckDBから未分析アクティビティを自動検出できる
- [ ] 複数アクティビティ × 5エージェントを並列実行できる
- [ ] 進捗をJSON形式で記録し、中断時に再開できる
- [ ] エラーが発生しても処理が継続し、最後にサマリーが表示される
- [ ] Dry runモードで実行計画を事前確認できる
- [ ] 日付範囲を指定して対象アクティビティをフィルターできる

### 非機能要件
- [ ] 50アクティビティの処理時間が逐次処理の50-66%（2.1-2.8時間以内）
- [ ] メモリ使用量が1GB以下
- [ ] 並列化効率が70%以上（理想的な並列化時間の1.4倍以内）

### コード品質
- [ ] 全Unit testsがパスする（カバレッジ80%以上）
- [ ] 全Integration testsがパスする
- [ ] Performance testsがパスする
- [ ] Black, Ruff, Mypyのチェックがパスする
- [ ] Pre-commit hooksがパスする

### ドキュメント
- [ ] planning.mdが完成している
- [ ] completion_report.mdが作成されている
- [ ] CLAUDE.mdに使用方法が追記されている
- [ ] コード内にdocstringが適切に記述されている

---

## リスク管理

### 想定されるリスク

1. **Claude Code Task API の制限**
   - 影響: 並列タスク数に制限がある可能性
   - 対策: バッチサイズを調整可能にする（--batch-sizeオプション）
   - 緩和策: エラー時に自動的にバッチサイズを減少

2. **エージェント実行時間の変動**
   - 影響: 一部のエージェントが想定より長時間かかる可能性
   - 対策: タイムアウト設定（デフォルト10分/バッチ）
   - 緩和策: タイムアウト時にリトライ、それでも失敗なら次へ進む

3. **DuckDB ロック競合**
   - 影響: 並列書き込みでロック待機が発生
   - 対策: エージェント側で insert_section_analysis_dict を使用（DuckDB側で排他制御）
   - 緩和策: リトライロジック実装

4. **進捗ファイルの破損**
   - 影響: 中断時に進捗ファイルが不完全な状態になる可能性
   - 対策: アトミックな書き込み（一時ファイル→rename）
   - 緩和策: 破損時は既存進捗を無視して最初から実行

5. **メモリ不足**
   - 影響: 大量の並列タスクでメモリ使用量が増加
   - 対策: バッチサイズを制限（デフォルト3 activities）
   - 緩和策: メモリ監視とバッチサイズの動的調整

---

## 実装ノート

### Claude Code Task API 想定仕様

**注**: 実際のAPI仕様は実装時に確認が必要。以下は想定仕様。

```python
# Hypothetical API (to be confirmed)
from claude_code import Task

task = Task.create(
    agent="split-section-analyst",
    prompt=f"Activity ID {activity_id} ({date}) の全スプリットを詳細分析してください。",
)

# Wait for completion
result = task.wait(timeout=600)

# Or poll status
while task.status == "running":
    time.sleep(5)

if task.status == "completed":
    # Success
elif task.status == "failed":
    # Handle error
```

### 5つのエージェント名

**エージェント定義ファイル（`.claude/agents/`）:**
1. `split-section-analyst.md` - スプリット詳細分析
2. `phase-section-analyst.md` - フェーズ評価（warmup/main/cooldown）
3. `summary-section-analyst.md` - アクティビティタイプ判定と総合評価
4. `efficiency-section-analyst.md` - フォーム効率と心拍効率
5. `environment-section-analyst.md` - 環境要因分析

### エージェントプロンプトテンプレート

```python
AGENT_PROMPTS = {
    "split": "Activity ID {activity_id} ({date}) の全スプリットを詳細分析してください。",
    "phase": "Activity ID {activity_id} ({date}) のフェーズ評価を実行してください。",
    "summary": "Activity ID {activity_id} ({date}) のアクティビティタイプ判定と総合評価を生成してください。",
    "efficiency": "Activity ID {activity_id} ({date}) のフォーム効率と心拍効率を分析してください。",
    "environment": "Activity ID {activity_id} ({date}) の環境要因（気温、風速、地形）の影響を分析してください。",
}
```

### ベストプラクティス

1. **進捗ファイルのアトミック書き込み**
   ```python
   import tempfile
   import os

   with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
       json.dump(progress_data, tmp)
       tmp_path = tmp.name

   os.replace(tmp_path, progress_file)  # Atomic on Unix
   ```

2. **DuckDB接続管理**
   ```python
   # Read-only connection for queries
   conn_ro = duckdb.connect(db_path, read_only=True)

   # Write connection (managed by agents via MCP)
   # エージェントが insert_section_analysis_dict を使用
   ```

3. **タイムアウトと Graceful Shutdown**
   ```python
   import signal

   def signal_handler(sig, frame):
       print("Interrupted! Saving progress...")
       save_progress()
       sys.exit(0)

   signal.signal(signal.SIGINT, signal_handler)
   ```

4. **ログ記録**
   ```python
   import logging

   logging.basicConfig(
       level=logging.INFO,
       format='%(asctime)s [%(levelname)s] %(message)s',
       handlers=[
           logging.FileHandler('data/logs/batch_analysis.log'),
           logging.StreamHandler(),
       ]
   )
   ```

---

## 実装進捗

- [ ] Phase 1: Core Classes
- [ ] Phase 2: Agent Integration
- [ ] Phase 3: CLI Interface
- [ ] Phase 4: Testing
- [ ] Phase 5: Documentation & Deployment
