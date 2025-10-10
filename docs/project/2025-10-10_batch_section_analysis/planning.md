# 計画: batch_section_analysis

## Git Worktree情報
- **Worktree Path**: `../garmin-batch_section_analysis/`
- **Branch**: `feature/batch_section_analysis`
- **Base Branch**: `main`

---

## 要件定義

### 目的
DuckDBに格納された複数アクティビティに対して、5つのセクション分析エージェント（split, phase, summary, efficiency, environment）を効率的に実行するための**プロンプト生成システム**を実装する。

**重要な設計方針:**
- Python workerは**プロンプト生成のみ**を行う（エージェント自動実行はしない）
- 生成されたプロンプトをファイルに出力
- **メインのClaude CodeがファイルからプロンプトをパースしてTaskツールで各エージェントに指示**
- 1エージェント = 10活動処理（エージェント起動オーバーヘッドを90%削減）
- パフォーマンスデータは既にDuckDBに格納済み
- レポート生成は別プロセスで行う

### 解決する問題

**現状の課題:**
- 現在は手動で各アクティビティに対して5つのエージェントを逐次的に呼び出す必要がある
- 50アクティビティの場合、50 × 5 = 250回のエージェント呼び出しが必要
- **エージェント起動オーバーヘッド**が深刻：各起動に5-10秒 = 20-40分のオーバーヘッド
- 逐次処理では1アクティビティあたり約5分 × 50 = 250分（4.2時間）かかる
- どのアクティビティを分析すべきか手動で確認が必要
- プロンプトを毎回手動で作成する必要がある

**影響:**
- 大量のアクティビティ分析に時間がかかりすぎる（4時間以上）
- エージェント起動オーバーヘッドが実分析時間の15-20%を占める
- DuckDBからの対象抽出が手動で非効率
- プロンプト作成の手間とミス

### ユースケース

1. **データアナリスト（一括分析）**
   - ユーザー: "全アクティビティの分析を実行して"
   - メインClaude Code: Python worker実行 → JSON読み込み → 5エージェント並列起動
   - 各エージェントが自動的に10活動ずつ処理
   - 完了後に検証実行で未分析活動をチェック

2. **システム運用者（差分更新）**
   - 定期的に新規追加アクティビティのみを分析
   - Python workerが自動的にDuckDBで未分析活動を特定
   - メインClaude Codeが未分析分のみをエージェント実行
   - 活動数に応じて--activities-per-agentで調整

3. **開発者（デバッグ・検証）**
   - 特定期間のアクティビティのみを対象に実行（--start, --end）
   - 小規模テスト: --activities-per-agent 2で少数の活動で動作確認
   - 完了確認: --verifyで未分析活動を特定
   - エージェントログでエラー箇所を特定

---

## 設計

### アーキテクチャ

**設計方針:**
1. **プロンプト生成**: Pythonで実行プロンプトを自動生成
2. **エージェント最適化**: 1エージェント = 10活動処理（デフォルト）
   - 起動オーバーヘッド90%削減
   - バッチサイズ調整可能: 1-20活動/エージェント（最大20）
   - 推奨: 10活動（バランス型）、5活動（保守的）、20活動（効率重視）
3. **DuckDB統合**: activities テーブルから対象抽出、section_analyses テーブルで完了確認
4. **自動実行**: メインClaude CodeがJSON読み込み→Taskツールで5エージェント並列実行
5. **進捗管理**: 完了状況をDuckDBで管理（別途進捗ファイル不要）

**コンポーネント構成:**
```
BatchPromptGenerator (メインクラス)
  ├─ ActivityQuery
  │   ├─ query_all_activities(): 全アクティビティ取得
  │   ├─ query_missing_analyses(): 未分析アクティビティ取得
  │   └─ filter_by_date_range(): 日付範囲フィルター
  │
  ├─ PromptGenerator
  │   ├─ generate_agent_prompt(): 単一エージェント用プロンプト生成
  │   ├─ generate_batch_prompts(): 全5エージェント用プロンプト生成
  │   └─ format_activity_list(): アクティビティリストのフォーマット
  │
  └─ ResultVerifier
      ├─ verify_completion(): DuckDBで完了確認
      ├─ check_section_analyses(): 5セクション全て存在確認
      └─ generate_summary(): サマリーレポート生成
```

**処理フロー:**
```
[Phase 1: Python Worker - Prompt Generation]
1. ユーザー: "50活動の分析を実行して"
   ↓
2. メインClaude Code: Python worker実行
   uv run python tools/batch_section_analysis.py --all
   ↓
3. Python Worker:
   - ActivityQuery: DuckDBから対象取得
   - Grouping: 10活動ずつグループ化
   - PromptGenerator: 5エージェント用プロンプト生成
   - Output: JSON形式でファイル出力（batch_prompts.json）
   ↓
4. ファイル出力: data/batch/batch_prompts.json
   {
     "split": "以下のアクティビティを順次分析...",
     "phase": "以下のアクティビティのフェーズ評価...",
     ...
   }

[Phase 2: Main Claude Code - Agent Orchestration]
5. メインClaude Code: batch_prompts.jsonを読み取り
   ↓
6. メインClaude Code: Taskツールで5エージェントに並列指示
   Task(split-section-analyst, prompts["split"])
   Task(phase-section-analyst, prompts["phase"])
   Task(summary-section-analyst, prompts["summary"])
   Task(efficiency-section-analyst, prompts["efficiency"])
   Task(environment-section-analyst, prompts["environment"])
   ↓
7. 5エージェント並列実行:
   各エージェントが10活動を順次処理
   insert_section_analysis_dict() でDuckDBに保存
   ↓
8. 完了報告: 各エージェントが完了を報告

[Phase 3: Verification]
9. メインClaude Code: Python worker実行（検証）
   uv run python tools/batch_section_analysis.py --verify
   ↓
10. Python Worker:
    - DuckDBで完了確認
    - 未完了アクティビティがあれば報告
```

**最適化戦略:**

**問題: エージェント起動オーバーヘッド**
```
現状 (1 activity = 5 agents):
50 activities × 5 agents = 250 agent invocations
各起動 5-10秒 = 20-40分のオーバーヘッド（総時間の15-20%）
```

**解決策: 1 agent = 複数 activities**
```
改善案 (1 agent = 10 activities):
50 activities / 10 per agent = 5 groups
5 groups × 5 agents = 25 agent invocations
各起動 5-10秒 = 2-4分のオーバーヘッド（10分の1！）
```

**実行時間の比較（50活動の場合）:**

| バッチサイズ | Agent起動数 | オーバーヘッド | 実行時間/エージェント | 総実行時間 |
|-------------|------------|--------------|---------------------|-----------|
| 現行 (1活動) | 250 | 20-40分 | 1-2分 | 2.5-3時間 |
| 5活動 | 50 | 4-8分 | 5-10分 | 5-10分 |
| **10活動（推奨）** | **25** | **2-4分** | **10-20分** | **10-20分** |
| 20活動（最大） | 15 | 1-2分 | 20-40分 | 20-40分 |

**バッチサイズの選択ガイドライン:**
- **5活動**: 保守的、エラー時の影響最小、デバッグ容易
- **10活動（推奨）**: バランス型、起動回数90%削減
- **20活動（最大）**: 効率重視、起動回数94%削減、エージェント実行時間長め

**期待される効果（バッチサイズ10の場合）:**
- エージェント起動回数: 90%削減（250 → 25）
- オーバーヘッド時間: 90%削減（20-40分 → 2-4分）
- 総実行時間: 85%削減（2.5-3時間 → 10-20分）
- 並列実行: 5エージェント同時実行で効率化

### データモデル

**Input (DuckDB activities table):**
```sql
-- 全アクティビティ取得
SELECT activity_id, date
FROM activities
ORDER BY date DESC;

-- 未分析アクティビティ取得
SELECT a.activity_id, a.date
FROM activities a
LEFT JOIN (
  SELECT activity_id, COUNT(DISTINCT section_type) as section_count
  FROM section_analyses
  GROUP BY activity_id
) s ON a.activity_id = s.activity_id
WHERE s.section_count IS NULL OR s.section_count < 5
ORDER BY a.date DESC;

-- 日付範囲フィルター
SELECT activity_id, date
FROM activities
WHERE date BETWEEN '2025-01-01' AND '2025-12-31'
ORDER BY date DESC;
```

**Output (Generated Prompts - JSON format):**
```json
{
  "metadata": {
    "generated_at": "2025-10-10T10:00:00Z",
    "total_activities": 50,
    "activities_per_agent": 10,
    "num_groups": 5,
    "agent_invocations": 25,
    "old_invocations": 250,
    "reduction_percent": 90,
    "estimated_time_hours": 1.75
  },
  "prompts": {
    "split": "以下のアクティビティを順次分析してください:

1. Activity ID 20615445009 (2025-10-07)
2. Activity ID 20612340123 (2025-10-06)
...
10. Activity ID 20580123789 (2025-09-26)

各アクティビティについて:
- get_splits_pace_hr() でペース・心拍データ取得
- get_splits_form_metrics() でフォームデータ取得
- 全スプリットを分析
- insert_section_analysis_dict() で保存

✅ 各アクティビティ完了時に報告してください",
    "phase": "以下のアクティビティのフェーズ評価を実行してください:

...",
    "summary": "以下のアクティビティのタイプ判定と総合評価を生成してください:

...",
    "efficiency": "以下のアクティビティのフォーム効率と心拍効率を分析してください:

...",
    "environment": "以下のアクティビティの環境要因の影響を分析してください:

..."
  },
  "activities": [
    {"activity_id": 20615445009, "date": "2025-10-07"},
    {"activity_id": 20612340123, "date": "2025-10-06"},
    ...
  ]
}
```

**ファイル出力先:**
- `data/batch/batch_prompts_{timestamp}.json`
- メインClaude CodeがこのファイルをReadして解析
- `prompts`オブジェクトの各キーをTaskツールに渡す

**Verification (DuckDB section_analyses table):**
```sql
-- 完了確認: 各アクティビティで5セクション存在するか
SELECT
  activity_id,
  COUNT(DISTINCT section_type) as completed_sections,
  STRING_AGG(section_type, ', ') as sections
FROM section_analyses
WHERE activity_id IN (20615445009, 20612340123, ...)
GROUP BY activity_id
HAVING COUNT(DISTINCT section_type) < 5;

-- 期待される結果: 空（全て完了している場合）
```

### API/インターフェース設計

```python
# tools/batch_section_analysis.py

from pathlib import Path
from typing import Literal
import duckdb

SectionType = Literal["split", "phase", "summary", "efficiency", "environment"]

class BatchPromptGenerator:
    """Batch prompt generator for section analysis agents."""

    def __init__(
        self,
        db_path: Path | None = None,
        activities_per_agent: int = 10,
    ):
        """
        Initialize prompt generator.

        Args:
            db_path: DuckDB database path (default: data/database/garmin.db)
            activities_per_agent: Number of activities per agent (default: 10, max: 20)

        Raises:
            ValueError: If activities_per_agent is not in range [1, 20]
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

    def generate_agent_prompt(
        self,
        agent_type: SectionType,
        activities: list[tuple[int, str]],
    ) -> str:
        """
        Generate prompt for a single agent type.

        Args:
            agent_type: Agent type (split, phase, summary, efficiency, environment)
            activities: List of (activity_id, date) tuples to process

        Returns:
            Formatted prompt string for Claude Code
        """

    def generate_all_prompts(
        self,
        activities: list[tuple[int, str]],
    ) -> dict[SectionType, str]:
        """
        Generate prompts for all 5 agent types.

        Args:
            activities: List of (activity_id, date) tuples to process

        Returns:
            Dict mapping agent type to prompt string
        """

    def format_output(
        self,
        prompts: dict[SectionType, str],
        activities: list[tuple[int, str]],
        output_file: Path,
    ) -> dict:
        """
        Format prompts as JSON and write to file.

        Args:
            prompts: Dict of agent prompts
            activities: List of (activity_id, date) tuples
            output_file: File path to write JSON prompts

        Returns:
            JSON structure with metadata and prompts
        """

    def verify_completion(
        self,
        activity_ids: list[int],
    ) -> dict[int, list[SectionType]]:
        """
        Verify which sections are completed for given activities.

        Args:
            activity_ids: List of activity IDs to check

        Returns:
            Dict mapping activity_id to list of missing section types
        """


# CLI Interface
def main():
    """
    CLI entry point.

    Usage:
        # Generate prompts for all missing analyses (default output to data/batch/)
        python tools/batch_section_analysis.py --all

        # Generate prompts for specific date range
        python tools/batch_section_analysis.py --start 2025-01-01 --end 2025-12-31

        # Custom output location
        python tools/batch_section_analysis.py --all --output /path/to/prompts.json

        # Verify completion status (after agent execution)
        python tools/batch_section_analysis.py --verify

        # Configure activities per agent
        python tools/batch_section_analysis.py --all --activities-per-agent 10

    Options:
        --all: Generate prompts for all activities with missing analyses
        --start: Start date (YYYY-MM-DD)
        --end: End date (YYYY-MM-DD)
        --activities-per-agent: Activities per agent (default: 10, min: 1, max: 20)
        --output: Output JSON file path (default: data/batch/batch_prompts_{timestamp}.json)
        --verify: Verify completion status only (no prompt generation)
        --force: Include already-analyzed activities

    Batch Size Guidelines:
        1-5:  Conservative (quick execution, easy debugging)
        10:   Recommended (balanced performance and reliability)
        15-20: Aggressive (maximum efficiency, longer execution)
    """
```

**実行例:**

**シナリオ1: 全活動の分析実行（標準的な使い方）**
```bash
# ユーザー: "50活動の分析を実行して"

# Step 1: メインClaude CodeがPython worker実行
uv run python tools/batch_section_analysis.py --all

# Step 2: メインClaude CodeがJSON読み込み
# data/batch/batch_prompts_20251010_100000.json

# Step 3: メインClaude CodeがTaskツールで5エージェントに並列指示
# (自動実行)

# Step 4: 完了後、検証実行
uv run python tools/batch_section_analysis.py --verify
```

**シナリオ2: 特定期間のみ分析**
```bash
uv run python tools/batch_section_analysis.py --start 2025-10-01 --end 2025-10-31
```

**シナリオ3: 活動数を調整（保守的実行）**
```bash
# 1エージェント = 5活動（より短時間で完了）
uv run python tools/batch_section_analysis.py --all --activities-per-agent 5
```

**シナリオ4: 完了状況確認のみ**
```bash
uv run python tools/batch_section_analysis.py --verify
```

**出力例:**

**コンソール出力（Python worker）:**
```
=== Batch Section Analysis Prompt Generator ===

📊 Target Analysis:
  Total Activities: 50
  Activities per Agent: 10
  Number of Groups: 5
  Agents per Group: 5
  Total Agent Invocations: 25

⚡ Performance Optimization:
  Old Method: 250 agent invocations (50 activities × 5 agents)
  New Method: 25 agent invocations (5 groups × 5 agents)
  Overhead Reduction: 90% (20-40min → 2-4min)
  Estimated Time: 1.5-2 hours

📝 Generated Prompts:
  Output: data/batch/batch_prompts_20251010_100000.json

✅ Ready for Main Claude Code to execute agents
```

**生成されたJSONファイル (data/batch/batch_prompts_20251010_100000.json):**
```json
{
  "metadata": {
    "generated_at": "2025-10-10T10:00:00Z",
    "total_activities": 50,
    "activities_per_agent": 10,
    "num_groups": 5,
    "agent_invocations": 25,
    "estimated_time_hours": 1.75
  },
  "prompts": {
    "split": "以下のアクティビティを順次分析してください:

1. Activity ID 20615445009 (2025-10-07)
2. Activity ID 20612340123 (2025-10-06)
...
10. Activity ID 20580123789 (2025-09-26)

各アクティビティについて:
- get_splits_pace_hr() でデータ取得
- get_splits_form_metrics() でフォームデータ取得
- 全スプリットを分析
- insert_section_analysis_dict() で保存

✅ 各アクティビティ完了時に報告してください",
    "phase": "...",
    "summary": "...",
    "efficiency": "...",
    "environment": "..."
  },
  "activities": [
    {"activity_id": 20615445009, "date": "2025-10-07"},
    ...
  ]
}
```

**メインClaude Codeの実行ログ（想定）:**
```
📖 Reading prompts from: data/batch/batch_prompts_20251010_100000.json

🚀 Launching 5 section analysis agents in parallel...

Task: split-section-analyst
Task: phase-section-analyst
Task: summary-section-analyst
Task: efficiency-section-analyst
Task: environment-section-analyst

⏳ Waiting for agents to complete (estimated: 1.5-2 hours)...

✅ All agents completed successfully

🔍 Verifying completion...
  - Completed: 50/50 activities (100%)
  - Missing sections: 0

✨ Batch analysis complete!
```

---

## テスト計画

### Unit Tests

- [ ] **test_query_target_activities**: DuckDB クエリが正しく動作
  - 全アクティビティ取得
  - 日付範囲フィルター
  - 未分析アクティビティのみフィルター（LEFT JOIN with section_analyses）
  - 空の結果を適切に処理

- [ ] **test_generate_agent_prompt**: プロンプト生成が正しく動作
  - 単一エージェントタイプのプロンプト生成
  - アクティビティリストのフォーマット
  - エージェントタイプ別の指示文
  - 10活動のリスト形式が正確

- [ ] **test_generate_all_prompts**: 全エージェント用プロンプト生成
  - 5エージェント分のプロンプト生成
  - 各プロンプトに同じアクティビティリスト
  - エージェント固有の指示が含まれる

- [ ] **test_verify_completion**: 完了確認が正しく動作
  - 5セクション全て存在する場合
  - 一部セクションが欠落している場合
  - 欠落セクションのリスト生成
  - DuckDBへのクエリが正確

- [ ] **test_format_output**: 出力フォーマットが正しい
  - コンソール出力フォーマット
  - ファイル出力（オプション）
  - ヘッダー情報（統計、最適化効果）

### Integration Tests

- [ ] **test_end_to_end_prompt_generation**: エンドツーエンドテスト
  - DuckDB接続 → クエリ → プロンプト生成 → 出力
  - 実際のデータベーススキーマを使用
  - テストデータでの完全なフロー

- [ ] **test_missing_only_filter**: 未分析フィルターの動作確認
  - 一部完了したアクティビティの扱い
  - 完全に完了したアクティビティは除外
  - 未分析アクティビティのみ抽出

- [ ] **test_grouping_logic**: グループ化ロジックの確認
  - 50活動 → 5グループ（10活動ずつ）
  - 端数の処理（48活動 → 5グループ、最後は8活動）
  - 空のグループが生成されない

- [ ] **test_verification_after_manual_execution**: 手動実行後の検証
  - エージェント実行後のDuckDB状態確認
  - 未完了アクティビティの特定
  - 再実行用プロンプト生成

### Acceptance Tests

- [ ] **test_real_world_scenario**: 実世界シナリオテスト
  - 実際のデータベースで10アクティビティ
  - プロンプト生成 → 手動実行 → 検証
  - 全5エージェントが正常動作
  - DuckDBに正しく保存される

---

## 実装フェーズ

### Phase 1: Core Classes（優先度: 高）
**Goal: DuckDB統合とデータ取得**

1. `ActivityQuery` クラス実装
   - DuckDB接続管理
   - 全アクティビティ取得クエリ
   - 未分析アクティビティ検出（LEFT JOIN with section_analyses）
   - 日付範囲フィルター
   - エラーハンドリング

2. `ResultVerifier` クラス実装
   - DuckDBでの完了確認クエリ
   - 5セクション全存在チェック
   - 欠落セクションのリスト生成
   - サマリー統計生成

### Phase 2: Prompt Generation（優先度: 高）
**Goal: エージェント用プロンプト生成**

1. `PromptGenerator` クラス実装
   - エージェント別プロンプトテンプレート定義
   - アクティビティリストのフォーマット（番号付きリスト）
   - 単一エージェント用プロンプト生成
   - 全5エージェント用プロンプト一括生成

2. グループ化ロジック実装
   - N活動を指定サイズでグループ分割
   - 端数処理（最後のグループが小さくなる場合）
   - 空グループの防止

3. 出力フォーマット実装
   - ヘッダー情報（統計、最適化効果）
   - Claude Code用フォーマット（Task: ... prompt: ...）
   - ファイル出力サポート

### Phase 3: CLI Interface（優先度: 中）
**Goal: コマンドラインツール完成**

1. argparse設定
   - `--all`: 全未分析アクティビティ
   - `--start`, `--end`: 日付範囲フィルター
   - `--activities-per-agent`: グループサイズ（デフォルト: 10）
   - `--output`: 出力ファイルパス
   - `--verify`: 検証モード（プロンプト生成なし）
   - `--force`: 既分析活動も含める

2. main() 関数実装
   - エントリーポイント
   - コマンドライン引数パース
   - モード分岐（生成 vs 検証）
   - 結果出力

3. ヘルプメッセージとエラーメッセージ

### Phase 4: Testing（優先度: 高）
**Goal: 品質保証**

1. Unit tests実装（pytest）
   - ActivityQuery tests（4テスト）
   - PromptGenerator tests（3テスト）
   - ResultVerifier tests（1テスト）
   - 出力フォーマット tests（1テスト）

2. Integration tests実装
   - エンドツーエンドフロー（1テスト）
   - 未分析フィルター動作（1テスト）
   - グループ化ロジック（1テスト）
   - 検証後再実行（1テスト）

3. Acceptance tests実装
   - 実データベースで10アクティビティテスト（1テスト）

### Phase 5: Documentation & Deployment（優先度: 中）
**Goal: ドキュメント整備とリリース**

1. CLAUDE.md更新
   - Common Development Commandsセクションに追記
   - 使用例とワークフロー説明

2. コード内docstring整備
   - 全クラス・メソッドにGoogle-styleドキュメント
   - 使用例コメント

3. 実環境での検証
   - 10アクティビティでテスト実行
   - プロンプト生成 → 手動実行 → 検証
   - 問題があれば修正

4. completion_report.md作成

---

## 受け入れ基準

### 機能要件
- [ ] DuckDBから未分析アクティビティを自動検出できる
  - LEFT JOIN with section_analyses table
  - 5セクション未満のアクティビティを抽出
- [ ] 全5エージェント用のプロンプトを一括生成できる
  - split, phase, summary, efficiency, environment
  - 各エージェントに同じアクティビティリスト
- [ ] 活動をグループ化してプロンプトを生成できる
  - デフォルト: 10活動/エージェント
  - カスタマイズ可能（--activities-per-agent）
- [ ] 完了状況を検証できる
  - DuckDBで5セクション存在確認
  - 欠落セクションのリスト表示
- [ ] 日付範囲を指定して対象をフィルターできる
  - --start, --end オプション
- [ ] ファイルまたはコンソールに出力できる
  - --output オプションでファイル保存
  - デフォルトはコンソール出力

### 非機能要件
- [ ] エージェント起動オーバーヘッドが90%削減される
  - 50活動: 250回起動 → 25回起動
  - オーバーヘッド: 20-40分 → 2-4分
- [ ] プロンプト生成が高速である
  - 50活動で1秒以内
- [ ] メモリ使用量が最小限である
  - プロンプト生成時 < 100MB

### コード品質
- [ ] 全Unit testsがパスする（カバレッジ80%以上）
  - ActivityQuery, PromptGenerator, ResultVerifier
- [ ] 全Integration testsがパスする
  - エンドツーエンド、フィルター、グループ化
- [ ] Acceptance testsがパスする
  - 実データベースでの10活動テスト
- [ ] Black, Ruff, Mypyのチェックがパスする
- [ ] Pre-commit hooksがパスする

### ドキュメント
- [ ] planning.mdが完成している
- [ ] completion_report.mdが作成されている
- [ ] CLAUDE.mdに使用方法が追記されている
- [ ] コード内にGoogle-style docstringが記述されている
- [ ] 使用例が明確に記載されている

---

## リスク管理

### 想定されるリスク

1. **エージェントの手動実行ミス**
   - 影響: プロンプトのコピペミス、一部エージェントの実行忘れ
   - 対策: 明確なフォーマットとチェックリスト提供
   - 緩和策: --verify オプションで実行後の完了確認

2. **エージェント実行時間の変動**
   - 影響: 10活動処理に想定以上の時間がかかる可能性
   - 対策: --activities-per-agent オプションで調整可能
   - 緩和策: 小さいグループサイズから開始（5活動など）

3. **DuckDB ロック競合**
   - 影響: 5エージェント並列書き込みでロック待機が発生
   - 対策: エージェントが insert_section_analysis_dict を使用（DuckDB側で排他制御）
   - 緩和策: エージェント側でリトライロジック実装済み

4. **未完了活動の見落とし**
   - 影響: 一部エージェントが失敗しても気づかない
   - 対策: --verify オプションで明示的に確認
   - 緩和策: 欠落セクションリストを表示

5. **プロンプトサイズの制限**
   - 影響: 活動数が多すぎるとプロンプトが長すぎる可能性
   - 対策: デフォルト10活動で制限
   - 緩和策: 大量の活動は複数回に分けて実行

---

## 実装ノート

### プロンプトテンプレート

**エージェント別プロンプトテンプレート:**

```python
AGENT_PROMPTS = {
    "split": """
以下のアクティビティを順次分析してください:

{activity_list}

各アクティビティについて:
- get_splits_pace_hr() でペース・心拍データ取得
- get_splits_form_metrics() でフォームデータ取得
- 全スプリットを分析
- insert_section_analysis_dict() で保存

✅ 各アクティビティ完了時に報告してください
""",
    "phase": """
以下のアクティビティのフェーズ評価を実行してください:

{activity_list}

各アクティビティについて:
- get_performance_section("performance_trends") でフェーズデータ取得
- ウォームアップ/メイン/クールダウンを評価
- insert_section_analysis_dict() で保存

✅ 各アクティビティ完了時に報告してください
""",
    "summary": """
以下のアクティビティのタイプ判定と総合評価を生成してください:

{activity_list}

各アクティビティについて:
- get_splits_all() で全データ取得
- get_vo2_max_data(), get_lactate_threshold_data() で生理学的データ取得
- アクティビティタイプ判定
- 総合評価と改善提案
- insert_section_analysis_dict() で保存

✅ 各アクティビティ完了時に報告してください
""",
    "efficiency": """
以下のアクティビティのフォーム効率と心拍効率を分析してください:

{activity_list}

各アクティビティについて:
- get_form_efficiency_summary() でフォーム効率データ取得
- get_hr_efficiency_analysis() で心拍効率データ取得
- get_heart_rate_zones_detail() でゾーン詳細取得
- insert_section_analysis_dict() で保存

✅ 各アクティビティ完了時に報告してください
""",
    "environment": """
以下のアクティビティの環境要因（気温、風速、地形）の影響を分析してください:

{activity_list}

各アクティビティについて:
- get_splits_elevation() で標高データ取得
- 気温・湿度・風速の影響評価
- 地形の影響評価
- insert_section_analysis_dict() で保存

✅ 各アクティビティ完了時に報告してください
""",
}
```

**アクティビティリストフォーマット:**
```python
def format_activity_list(activities: list[tuple[int, str]]) -> str:
    """
    Format activity list for prompt.

    Args:
        activities: List of (activity_id, date) tuples

    Returns:
        Formatted string like:
        1. Activity ID 20615445009 (2025-10-07)
        2. Activity ID 20612340123 (2025-10-06)
        ...
    """
    return "
".join(
        f"{i+1}. Activity ID {aid} ({date})"
        for i, (aid, date) in enumerate(activities)
    )
```

### エージェント名とタスクフォーマット

**5つのエージェント（`.claude/agents/` ディレクトリ）:**
1. `split-section-analyst` - スプリット詳細分析
2. `phase-section-analyst` - フェーズ評価（warmup/main/cooldown）
3. `summary-section-analyst` - アクティビティタイプ判定と総合評価
4. `efficiency-section-analyst` - フォーム効率と心拍効率
5. `environment-section-analyst` - 環境要因分析

**Claude Code Taskフォーマット:**
```
Task: {agent-name}
prompt: """
{multi-line prompt}
"""
```

**重要:** プロンプトは必ず3つのダブルクォートで囲む（複数行対応）

### DuckDB接続管理

**Read-only接続でクエリ実行:**
```python
import duckdb
from pathlib import Path

def get_db_connection(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Get read-only DuckDB connection for queries."""
    return duckdb.connect(str(db_path), read_only=True)

# 使用例
conn = get_db_connection(Path("data/database/garmin.db"))
result = conn.execute("""
    SELECT a.activity_id, a.date
    FROM activities a
    LEFT JOIN (
        SELECT activity_id, COUNT(DISTINCT section_type) as section_count
        FROM section_analyses
        GROUP BY activity_id
    ) s ON a.activity_id = s.activity_id
    WHERE s.section_count IS NULL OR s.section_count < 5
    ORDER BY a.date DESC
""").fetchall()
conn.close()
```

**書き込みはエージェントが実行:**
- エージェントが `mcp__garmin-db__insert_section_analysis_dict()` を使用
- DuckDB側で排他制御を実装済み
- Pythonツールは書き込み不要（検証のみ）

### 出力フォーマット設計

**コンソール出力:**
```python
def format_console_output(prompts: dict, stats: dict) -> str:
    """Format prompts for console display."""
    output = []
    output.append("=" * 60)
    output.append("Batch Section Analysis Prompt Generator")
    output.append("=" * 60)
    output.append("")
    output.append(f"📊 Statistics:")
    output.append(f"  Total Activities: {stats['total_activities']}")
    output.append(f"  Activities per Agent: {stats['activities_per_agent']}")
    output.append(f"  Number of Groups: {stats['num_groups']}")
    output.append(f"  Total Agent Invocations: {stats['total_invocations']}")
    output.append("")
    output.append(f"⚡ Optimization:")
    output.append(f"  Old: {stats['old_invocations']} invocations")
    output.append(f"  New: {stats['total_invocations']} invocations")
    output.append(f"  Reduction: {stats['reduction_percent']}%")
    output.append("")
    output.append("=" * 60)
    output.append("COPY AND PASTE INTO CLAUDE CODE")
    output.append("=" * 60)
    output.append("")

    for agent_type, prompt in prompts.items():
        output.append(f"Task: {agent_type}-section-analyst")
        output.append(f'prompt: """')
        output.append(prompt.strip())
        output.append('"""')
        output.append("")

    return "
".join(output)
```

---

## 実装進捗

- [ ] Phase 1: Core Classes
- [ ] Phase 2: Agent Integration
- [ ] Phase 3: CLI Interface
- [ ] Phase 4: Testing
- [ ] Phase 5: Documentation & Deployment
