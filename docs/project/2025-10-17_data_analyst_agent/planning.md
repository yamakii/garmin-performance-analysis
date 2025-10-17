# 計画: Data Analyst Agent Implementation

**GitHub Issue:** [#28](https://github.com/yamakii/garmin-performance-analysis/issues/28)

## プロジェクト情報

- **プロジェクト名**: `data_analyst_agent`
- **作成日**: `2025-10-17`
- **ステータス**: 計画中
- **優先度**: 中（ワークフロー効率向上）
- **推定期間**: 2-3日（Phase 1-4）
- **スコープ**: 新規エージェント実装 + CLAUDE.md更新
- **Base Project**: 2025-10-16_duckdb_mcp_llm_architecture (#25 Phase 0-3完了)

## 要件定義

### 目的

複数月にわたるパフォーマンスデータの分析を、DuckDB × MCP × LLM Architectureを活用して効率的に実行する専門エージェントを実装する。LLMコンテキストを保護しながら、統計的な分析とレース予測を実現する。

**核心的な課題:**
- 現在のワークフロー: 100+の個別MCPコール → 高トークンコスト（55,000+トークン）
- カラム名エラー: スキーマ確認なしの試行錯誤（5+回の失敗クエリ）
- 非効率なフォーマット: CSV使用による処理遅延とメモリ浪費
- 知識の分散: ベストプラクティスが文書化されていない

**核心的な解決策:**
- Single Export: 1回のexport()呼び出しで全データ取得（99.7%トークン削減）
- Schema-First: スキーマ確認後のクエリ構築（ゼロエラー）
- Parquet優先: 効率的なバイナリフォーマット（3x高速）
- 標準化ワークフロー: 5ステップのPLAN→EXPORT→CODE→RESULT→INTERPRETパターン

### 解決する問題

**現状の課題（Session 2025-10-17で確認）:**

1. **非効率な複数呼び出しパターン**
   - 例: 5ヶ月分析 = 107アクティビティ × 2コール = 214回のMCP呼び出し
   - トークンコスト: ~55,000トークン（get_activity_by_date + get_performance_trends）
   - 実行時間: 長時間（ネットワーク往復 × 214回）

2. **カラム名エラーの頻発**
   - スキーマ確認なしでクエリを試行
   - 5回以上の失敗クエリ: `avg_hr` → `hr` → `average_heart_rate` → `avg_heart_rate` → 成功
   - トークン浪費: エラーメッセージ × 失敗回数
   - 時間浪費: 試行錯誤による遅延

3. **CSVフォーマットの非効率性**
   - 50行以上のCSV: パース遅延、型情報欠落、メモリ効率悪化
   - Parquetと比較して3倍遅い読み込み速度
   - 数値型の文字列化によるエラー（例: "123"をfloat変換）

4. **知識の分散と標準化の欠如**
   - CLAUDE.mdに"For Data Analysis"セクションはあるがエージェント化されていない
   - ユーザーが毎回ワークフローを指示する必要がある
   - ベストプラクティスの適用漏れ（schema check忘れ、CSV使用など）

### ユースケース

**Primary Use Cases（このエージェントを呼び出すべき場面）:**

1. **5ヶ月間のパフォーマンス進捗分析**
   - **ユーザー**: "過去5ヶ月間のペース向上率を分析して"
   - **エージェント**:
     1. 日付範囲特定（today - 5 months）
     2. スキーマ確認（activities, splits, form_efficiency列）
     3. 単一エクスポート（CTEで集計: AVG(pace), AVG(heart_rate), activity_date）
     4. Python分析（線形回帰、成長率計算、信頼区間）
     5. 結果解釈（"1週間あたり3秒/km改善、R²=0.85で有意な向上傾向"）
   - **トークン効率**: 150トークン（vs 55,000トークン従来方式 = 99.7%削減）

2. **レース予測（ハーフマラソンタイム予測）**
   - **ユーザー**: "3ヶ月後のハーフマラソンの予測タイムは？"
   - **エージェント**:
     1. 直近3ヶ月のトレーニングデータをエクスポート
     2. VDOT計算（最近の10km/5kmタイム利用）
     3. Riegel式による予測（距離 × pace変換）
     4. 条件調整（気温+5℃予想 → ペース+10秒/km）
     5. 予測結果（"1:35:00 ± 3分、90%信頼区間"）
   - **トークン効率**: 200トークン（従来不可能だった複雑な分析）

3. **トレーニング期間比較（8月 vs 10月）**
   - **ユーザー**: "8月と10月のトレーニング効果を比較して"
   - **エージェント**:
     1. 2つの日付範囲でエクスポート（WHERE date BETWEEN）
     2. 各期間の平均ペース、心拍、VO2 max算出
     3. 統計的検定（Welch's t-test, p < 0.05）
     4. 効果量計算（Cohen's d）
     5. 結果解釈（"10月は8月より平均15秒/km改善、d=0.8で大きな効果"）
   - **トークン効率**: 180トークン（統計的妥当性を担保）

4. **相関分析（ペース vs 心拍 × 100ラン）**
   - **ユーザー**: "ペースと心拍の相関を過去100ランで分析"
   - **エージェント**:
     1. 直近100アクティビティをLIMIT句でエクスポート
     2. Pearson/Spearman相関係数計算
     3. 散布図生成（matplotlib）
     4. 結果解釈（"r=0.78で強い正相関、ペース向上時に心拍効率改善"）
   - **トークン効率**: 170トークン（可視化込み）

**DON'T Call This Agent（通常のMCPツールを使うべき場面）:**

- 単一アクティビティ分析 → `get_performance_trends(activity_id)`
- 10アクティビティ未満 → 個別MCPコールの方が効率的
- レポート生成 → section analysis agents（split/phase/efficiency/etc）
- メタデータ検索 → `get_activity_by_date`, `get_date_by_activity_id`
- 50行未満のデータ → `statistics_only=True`パラメータで十分

### 非機能要件

1. **効率性**: 10-100xトークン削減（従来比）
   - 5ヶ月分析: 150トークン（vs 55,000トークン = 99.7%削減）
   - 実行時間: <2分（従来5-10分）

2. **信頼性**: ゼロカラム名エラー
   - スキーマバリデーション必須（information_schema確認）
   - 型保持（Parquet使用）
   - 再現性（SQL + Python両方バージョン記録）

3. **保守性**: CLAUDE.mdとの一貫性
   - "For Data Analysis"セクションのエージェント実装
   - 既存ガイドラインの実行可能化
   - ベストプラクティスの標準化

4. **ユーザビリティ**: シンプルな呼び出し
   - 自然言語プロンプトで起動（"5ヶ月間の進捗分析"など）
   - 進捗報告（STEP 1/5: PLAN, STEP 2/5: EXPORT...）
   - アクション可能な洞察（"週3回ペースで続ければ3ヶ月後に目標達成"）

---

## 設計

### エージェント構造

**Location**: `.claude/agents/data-analyst.md`

**Frontmatter**:
```yaml
---
name: data-analyst
description: Bulk performance data analysis using DuckDB × MCP × LLM Architecture. For 10+ activities, multi-month trends, race prediction, statistical analysis.
tools: mcp__garmin-db__export, Bash
model: inherit
---
```

### アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Prompt                               │
│  "Analyze my 5-month progression"                                │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Data Analyst Agent (LLM)                      │
│  STEP 1: PLAN                                                    │
│    - Extract: date range, metrics, analysis type                │
│    - Schema check: information_schema.columns                   │
│    - Design query: Single SQL with CTEs                         │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Server (Garmin DB)                        │
│  STEP 2: EXPORT                                                  │
│    - Call: export(query, format="parquet", max_rows=1000)      │
│    - Return: {"handle": "path.parquet", "rows": 107, ...}      │
│    - Token cost: ~25 tokens (not 55,000!)                       │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│              Python Executor (via Bash tool)                     │
│  STEP 3: CODE                                                    │
│    - Load: df = pd.read_parquet(handle)                        │
│    - Process: Linear regression, growth rate, correlation       │
│    - Visualize: matplotlib plot (optional)                      │
│    - Output: Summary JSON (~500 bytes)                          │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Output Validation                             │
│  STEP 4: RESULT                                                  │
│    - Auto-validate: JSON <1KB, Table <10 rows                   │
│    - If exceeded: Auto-trim + warning                           │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Data Analyst Agent (LLM)                        │
│  STEP 5: INTERPRET                                               │
│    - Receive: Summary JSON (~125 tokens)                        │
│    - Interpret: Natural language explanation                    │
│    - Report: "Growth rate: 3 sec/km/week, significant (p<0.01)"│
└─────────────────────────────────────────────────────────────────┘
```

**設計原則:**

1. **Responsibility Separation**
   - LLM: Planning (STEP 1) + Interpretation (STEP 5)
   - MCP: Data extraction (STEP 2) - handle only, no raw data
   - Python: Processing (STEP 3) - summary only, no full展開

2. **Token Protection**
   - MCP returns handle (~25 tokens), not data
   - Python returns summary JSON (~125 tokens), not DataFrame
   - LLM never sees raw data (thousands of rows)

3. **Safety Guards**
   - Schema validation before query (zero column errors)
   - Parquet format enforced (efficiency + type safety)
   - Output size limits (JSON <1KB, Table <10 rows)

### API/インターフェース設計

#### Agent Prompt Components

**1. When to Use Section** - 明確な起動条件
**2. Architecture Awareness Section** - 責任分離の説明
**3. Workflow (5 Steps) Section** - 詳細な実行手順
**4. Tools Available Section** - export() + Bash使用方法
**5. Example Prompts Section** - 良い例・悪い例
**6. Token Cost Efficiency Section** - 効率化の数値証明

詳細は実装時に`data-analyst-agent-plan.md`を参照。

---

## 実装フェーズ

### Phase 1: Agent Creation (30 min)

**目標:** エージェントファイル作成と基本構造の実装

**Tasks:**

1. **エージェントファイル作成**
   - `.claude/agents/data-analyst.md` 作成
   - Frontmatter設定（name, description, tools, model）
   - テスト: エージェント呼び出し確認（Task toolで）

2. **プロンプト構造実装**
   - "When to Use" セクション: 起動条件の明確化
   - "Architecture Awareness" セクション: 責任分離の説明
   - "Workflow (5 Steps)" セクション: PLAN→EXPORT→CODE→RESULT→INTERPRET
   - "Tools Available" セクション: export() + Bash使用方法
   - "Example Prompts" セクション: 良い例・悪い例
   - "Token Cost Efficiency" セクション: 効率化の数値証明

3. **検証**
   - エージェント呼び出し: `Task("data-analyst", "Test prompt")`
   - プロンプト読み込み確認
   - ツール権限確認（export, Bash）

**受け入れ基準:**
- [ ] `.claude/agents/data-analyst.md` が存在
- [ ] Frontmatterが正しく設定されている
- [ ] 全セクションが記述されている
- [ ] エージェント呼び出しが成功する
- [ ] プロンプトが読み込まれる

### Phase 2: Core Workflows (1 hour)

**目標:** 3つの主要ワークフローの実装とテスト

#### Workflow 1: Time Series Analysis (成長率計算)

**実装内容:**
- 日付範囲抽出（"5ヶ月" → today - 5 months）
- スキーマ確認クエリ
- 単一エクスポートクエリ（CTEでsplits集計）
- Python線形回帰分析
- 成長率計算と信頼区間
- 自然言語解釈

**受け入れ基準:**
- [ ] 日付範囲が正しく計算される
- [ ] スキーマ確認が実行される
- [ ] エクスポートが1回のみ実行される
- [ ] Pythonで線形回帰が実行される
- [ ] 成長率がsec/km/weekで計算される
- [ ] トークンコスト <500トークン

#### Workflow 2: Performance Prediction (レース予測)

**実装内容:**
- 直近N週間のデータ抽出
- VDOT計算（Jack Daniels式）
- Riegel式によるレース予測
- 条件調整（気温、標高、トレーニング状態）
- 信頼区間付き予測

**受け入れ基準:**
- [ ] 直近N週間が正しく抽出される
- [ ] ベストタイムが識別される
- [ ] VDOT計算が実行される
- [ ] Riegel式でレース予測される
- [ ] 信頼区間が計算される
- [ ] 条件調整（気温など）が適用される

#### Workflow 3: Comparative Analysis (期間比較)

**実装内容:**
- 2つの期間の日付範囲抽出
- 各期間の統計量計算（mean, std, median）
- 統計的検定（Welch's t-test or Mann-Whitney U）
- 効果量計算（Cohen's d）
- 実用的有意性の評価

**受け入れ基準:**
- [ ] 2つの期間が正しく抽出される
- [ ] 統計量が各期間で計算される
- [ ] t-testまたはMann-Whitney Uが実行される
- [ ] 効果量が計算される
- [ ] p値と効果量の両方が解釈される
- [ ] 実用的有意性が評価される

### Phase 3: Testing (30 min)

**目標:** 実データでのEnd-to-Endテストと効率性検証

**Tasks:**

1. **5ヶ月進捗分析（実データ）**
   - プロンプト: "過去5ヶ月間のペース向上を分析して"
   - 検証項目:
     - [ ] スキーマ確認が実行される
     - [ ] エクスポートが1回のみ
     - [ ] トークンコスト <500トークン
     - [ ] 実行時間 <2分
     - [ ] 有意な結果が解釈される

2. **レース予測（実データ）**
   - プロンプト: "3ヶ月後のハーフマラソン予測タイムは？"
   - 検証項目:
     - [ ] 直近トレーニングデータが使用される
     - [ ] VDOT計算が実行される
     - [ ] 予測時間が妥当（±5分以内の精度）
     - [ ] 信頼区間が提示される

3. **期間比較（実データ）**
   - プロンプト: "8月と10月のパフォーマンスを比較"
   - 検証項目:
     - [ ] 2期間が正しく抽出される
     - [ ] 統計的検定が実行される
     - [ ] 効果量が計算される
     - [ ] p値 < 0.05で有意性が確認される

4. **エラーケーステスト**
   - 存在しないカラム名（schema checkで防止）
   - 大量データリクエスト（max_rowsで制限）
   - 空データ期間（エラーハンドリング）

**受け入れ基準:**
- [ ] 3つの実データテストが全てパス
- [ ] トークンコスト目標達成（99%削減）
- [ ] 実行時間目標達成（<2分）
- [ ] エラーケースが適切に処理される
- [ ] カラム名エラーがゼロ

### Phase 4: Documentation (15 min)

**目標:** CLAUDE.md更新とプロジェクト完了

**Tasks:**

1. **CLAUDE.md "For Data Analysis" セクション更新**
   - エージェント参照追加
   - 使用例追加（"Use data-analyst agent for..."）
   - ワークフロー図更新

2. **Agent Usage Examples追加**
   - 3つのユースケースを"Example Prompts"に追加
   - トークン効率の数値を"Token Cost Efficiency"に追加

3. **completion_report.md作成準備**
   - 実装完了項目リスト
   - トークン削減効果の測定結果
   - ユーザーへの使用ガイド

**受け入れ基準:**
- [ ] CLAUDE.md "For Data Analysis"にエージェント参照が追加
- [ ] 3つのユースケース例が文書化
- [ ] トークン効率が数値で示される（99%削減）
- [ ] completion_report.md準備完了

---

## テスト計画

### Unit Tests

**Agent Prompt Tests (`tests/test_data_analyst_agent.py`):**
- [ ] Agent file exists and has correct frontmatter
- [ ] Agent prompt includes all required sections
- [ ] "When to Use" section defines clear criteria
- [ ] "Workflow" section defines 5 steps

### Integration Tests

**Workflow Tests (`tests/integration/test_data_analyst_workflows.py`):**

**Time Series Analysis:**
- [ ] 5-month date range extraction
- [ ] Schema check query executed
- [ ] Single export call (not 100+)
- [ ] Linear regression executed
- [ ] Growth rate calculated (sec/km/week)
- [ ] R² and p-value computed
- [ ] Token cost <500 tokens

**Performance Prediction:**
- [ ] Recent training data extracted (3 months)
- [ ] VDOT calculation
- [ ] Riegel formula application
- [ ] Condition adjustment (temperature, altitude)
- [ ] Confidence interval calculation
- [ ] Token cost <500 tokens

**Comparative Analysis:**
- [ ] Two period extraction (August, October)
- [ ] Statistical test (t-test or Mann-Whitney U)
- [ ] Effect size calculation (Cohen's d)
- [ ] p-value < 0.05 for significant difference
- [ ] Token cost <500 tokens

### Performance Tests

**Efficiency Tests (`tests/performance/test_data_analyst_efficiency.py`):**
- [ ] 5-month analysis: <500 tokens (vs 55,000 baseline)
- [ ] Race prediction: <500 tokens
- [ ] Comparative analysis: <500 tokens
- [ ] Execution time: <2 minutes for 100+ activities
- [ ] Schema check overhead: <100ms

### Error Handling Tests

**Error Cases (`tests/integration/test_data_analyst_errors.py`):**
- [ ] Invalid column name (schema check prevents)
- [ ] Empty date range (returns user-friendly error)
- [ ] Max rows exceeded (auto-trim + warning)
- [ ] Missing data (graceful degradation)

---

## 受け入れ基準

### 機能要件

- [ ] エージェントファイル (`.claude/agents/data-analyst.md`) が実装されている
- [ ] 3つのコアワークフローが完全動作（Time Series, Prediction, Comparative）
- [ ] スキーマバリデーションがゼロカラム名エラーを保証
- [ ] Single exportパターンでトークン99%削減達成
- [ ] 自然言語解釈が実用的な洞察を提供

### 効率性要件

- [ ] 5ヶ月分析: <500トークン（従来55,000の99.1%削減）
- [ ] 実行時間: <2分（100+アクティビティ）
- [ ] エクスポート呼び出し: 1回のみ（従来100+回）

### 信頼性要件

- [ ] カラム名エラー: 0件（スキーマバリデーション）
- [ ] 型エラー: 0件（Parquetによる型保持）
- [ ] 再現性: 同じプロンプトで同じ結果

### ユーザビリティ要件

- [ ] シンプルな自然言語プロンプトで起動
- [ ] 進捗報告（STEP 1/5, STEP 2/5...）
- [ ] アクション可能な洞察（"週3回で3ヶ月後に目標達成"）
- [ ] エラーメッセージが明確（次のアクションを指示）

### ドキュメント要件

- [ ] CLAUDE.md "For Data Analysis"にエージェント参照追加
- [ ] 3つのユースケース例が文書化
- [ ] トークン効率が数値で示される
- [ ] Agent prompt内に"Example Prompts"が充実

---

## リスク評価

### 高リスク

**R1: LLMが生データ読み取りを試行する**
- 影響度: 高（アーキテクチャの根幹）
- 発生確率: 中
- 対策:
  - エージェントプロンプトで明示的に禁止（"❌ NO direct data reading"）
  - Architecture Awarenessセクションで責任分離を強調
  - 5-stepワークフローを明確化
- 軽減策: Phase 1でプロンプト設計に注力、Phase 3で実動作検証

**R2: スキーマ確認を忘れてカラム名エラー**
- 影響度: 高（信頼性の核心）
- 発生確率: 中
- 対策:
  - STEP 1: PLANでスキーマ確認を必須化
  - プロンプトに"Schema Check"セクションを独立させる
  - エラー時のリトライでスキーマ再確認を指示
- 軽減策: Phase 2でスキーマ確認パターンを標準化

### 中リスク

**R3: Python分析が複雑すぎてエラー**
- 影響度: 中
- 発生確率: 中
- 対策:
  - Phase 2で標準的な分析パターンを実装（線形回帰、t-test、相関）
  - エラー時はシンプルな集計に fallback
  - Try-exceptでエラーハンドリング
- 軽減策: Phase 3で実データテストを徹底

**R4: 出力サイズ制限が厳しすぎる**
- 影響度: 中
- 発生確率: 低
- 対策:
  - JSON 1KB制限は妥当（summary JSONは500バイト程度）
  - 超過時はトップN行のみ出力
  - グラフは外部ファイル保存（パスのみ返却）
- 軽減策: Phase 3で実データでサイズ検証

### 低リスク

**R5: VDOT/Riegel式の計算ミス**
- 影響度: 低（レース予測のみ影響）
- 発生確率: 低
- 対策:
  - 既存の実装（runner's calculatorなど）を参考
  - Unit testで既知の入力→出力を検証
- 軽減策: Phase 2でVDOT計算の正確性を確認

**R6: 統計的検定の誤解釈**
- 影響度: 低
- 発生確率: 低
- 対策:
  - p値と効果量の両方を報告
  - 実用的有意性を強調（"統計的有意だが実用的には小さい差"）
- 軽減策: Phase 2で標準的な解釈パターンを実装

---

## 次のステップ

1. **GitHub Issue作成**
   - タイトル: "Implement Data Analyst Agent for Bulk Performance Analysis"
   - ラベル: `enhancement`, `agent`, `priority: medium`
   - Assignee: @yamakii
   - planning.md URLをdescriptionに追加

2. **Git worktree作成 (tdd-implementer phase)**
   ```bash
   git worktree add -b feature/data_analyst_agent ../data-analyst-agent main
   cd ../data-analyst-agent
   uv sync --extra dev
   mcp__serena__activate_project("/absolute/path/to/data-analyst-agent")
   ```

3. **Phase 1開始（30分）**
   - `.claude/agents/data-analyst.md` 作成
   - プロンプト構造実装
   - エージェント呼び出しテスト

4. **Phase 2開始（1時間）**
   - 3つのコアワークフロー実装
   - 実データでテスト

5. **Phase 3開始（30分）**
   - End-to-Endテスト
   - トークン効率検証

6. **Phase 4完了（15分）**
   - CLAUDE.md更新
   - completion_report.md作成

---

## 参考資料

**Base Project:**
- `docs/project/2025-10-16_duckdb_mcp_llm_architecture/planning.md` - Phase 0-3完了済み
- `docs/project/data-analyst-agent-plan.md` - 詳細な実装プラン

**Architecture Documentation:**
- `docs/LLM_BEHAVIOR_RULES.md` - LLM行動規則（Phase 3で作成予定）
- `CLAUDE.md` - "For Data Analysis" セクション

**Existing Agents:**
- `.claude/agents/split-section-analyst.md` - スタイル参考
- `.claude/agents/efficiency-section-analyst.md` - MCP tool usage参考

**Session Reference:**
- Session 2025-10-17: Anti-pattern examples（複数呼び出し、カラム名エラー、CSV使用）

---

**計画作成日**: 2025-10-17
**最終更新日**: 2025-10-17
**ステータス**: 計画中
**推定期間**: 2-3日（Phase 1-4）
**変更履歴**:
- 2025-10-17: 初版作成
