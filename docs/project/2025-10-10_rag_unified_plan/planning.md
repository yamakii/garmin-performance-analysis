# RAG System 統一実装計画

**作成日**: 2025-10-10
**プロジェクト名**: rag_unified_plan
**ステータス**: 計画中

---

## 現状分析

### 重要な発見: 実装とドキュメントのギャップ

#### 記録上の状態（メモリ・ドキュメント）
- **Phase 0-2**: 完了と記録
  - Phase 1: 3つのクエリツール（comparisons, trends, insights）実装済み
  - Phase 2.1: ActivityClassifier実装、フィルタリング機能追加
  - Phase 2.2: BM25検索スキップ
  - テスト100%パス、ユーザー検証済み

#### 実際の状態（コードベース）
- **Phase 0-2**: ❌ **実装が存在しない**
  ```bash
  tools/rag/
  ├── __init__.py           # 空ファイル
  ├── queries/__init__.py   # 空ファイル
  └── utils/__init__.py     # 空ファイル
  ```
  - `comparisons.py`: 存在しない
  - `trends.py`: 存在しない
  - `insights.py`: 存在しない
  - `activity_classifier.py`: 存在しない
  - テストファイル: 存在しない

#### データ準備状況
- ✅ `activity_details.json`: 103ファイル存在
- ✅ DuckDB: 正規化テーブル完備
- ✅ performance.json: 全アクティビティ分存在

### 既存プロジェクトの整理

#### 1. 2025-10-05_rag_system (Phase 0-3計画)
**目的**: Wellness metrics統合による多変量相関分析

**計画内容**:
- Phase 0: データインベントリ（完了と記録、実装なし）
- Phase 1: DuckDBクエリツール（完了と記録、実装なし）
- Phase 2: トレンド分析フィルタリング（完了と記録、実装なし）
- Phase 3: Wellness統合（計画のみ、9-13日見積もり）

**問題点**:
- 実装が存在しないため、Phase 3の前提条件が未達成
- Wellness APIの可用性が未検証
- 複雑度が高く、実装期間が長い

#### 2. 2025-10-09_rag_interval_analysis_tools (Phase 2.5相当)
**目的**: activity_details.json活用によるインターバル分析

**計画内容**:
- Phase 1: ActivityDetailsLoader実装（2日）
- Phase 2: インターバル分析実装（3日）
- Phase 3: 時系列詳細取得実装（2日）
- Phase 4: フォーム異常検出実装（3日）
- Phase 5: MCPサーバー統合（1日）
- Phase 6: ドキュメント作成（1日）

**特徴**:
- 具体的な実装計画あり
- データ準備完了（activity_details.json 103件）
- 比較的小規模（12日見積もり）
- 実用性が高い（インターバルトレーニング分析）

---

## 統合計画の方針

### 実装優先順位の決定

#### 優先度1: インターバル分析ツール（2025-10-09プロジェクト）
**理由**:
1. ✅ データ準備完了（activity_details.json）
2. ✅ 具体的な実装計画あり
3. ✅ 実用性が高い（即座に使える）
4. ✅ 複雑度が低い（API依存なし）
5. ✅ 段階的実装可能

#### 優先度2: 基本RAGツール（2025-10-05 Phase 1-2相当）
**理由**:
1. トレンド分析の基盤として必要
2. シンプルなDuckDBクエリツール
3. インターバル分析と並行実装可能

#### 優先度3: Wellness統合（2025-10-05 Phase 3）
**理由**:
1. API可用性の検証が必要
2. 複雑度が高い
3. 優先度1,2の完了後に実施

### 統合アプローチ

**戦略**: 段階的実装 + 並行開発

```
Timeline:
Week 1-2: [Priority 1] インターバル分析ツール実装
          └─ Phase 1-4 (ActivityDetailsLoader, Interval, TimeSeries, FormAnomaly)

Week 2-3: [Priority 2] 基本RAGツール実装（並行）
          └─ Trends, Insights, ActivityClassifier

Week 3-4: [Priority 1] MCP統合 + テスト
          [Priority 2] MCP統合 + テスト

Week 5+:  [Priority 3] Wellness統合（API検証から開始）
```

---

## 新・統一実装計画

### Phase 1: インターバル分析基盤（Week 1、5日）

#### 目標
activity_details.jsonを効率的に処理する基盤を構築

#### 実装内容

**1.1 ActivityDetailsLoader クラス**
- ファイル: `tools/rag/loaders/activity_details_loader.py`
- 機能:
  - `load_activity_details(activity_id)`: JSON読み込み
  - `parse_metric_descriptors()`: 26メトリクスマッピング
  - `extract_time_series(metrics, start_time, end_time)`: 時系列抽出
  - `apply_unit_conversion(metric_index, value)`: 単位変換

**1.2 テストスイート**
- ファイル: `tests/rag/loaders/test_activity_details_loader.py`
- カバレッジ: 85%以上

**1.3 ドキュメント**
- CLAUDE.mdに26メトリクス表追加
- 使用例追加

#### 受け入れ基準
- [x] activity_details.json（103件）を正しく読み込める
- [x] 26メトリクス全てが正確に解析される
- [x] 単位変換が正確（factor適用）
- [x] 全テストパス (10/10 tests passed, 97% coverage)

#### 実装完了 (2025-10-10)
- ✅ **ActivityDetailsLoader**: 184行実装
- ✅ **テストスイート**: 10テストケース（172行）
- ✅ **フィクスチャ作成**: tests/fixtures/data/raw/activity/12345678901/
- ✅ **コード品質**: Black/Ruff/Mypy パス
- ✅ **コミット**: `584316d` (feature/rag_interval_tools)

---

### Phase 2: インターバル分析ツール（Week 1-2、6日）

#### 目標
3つのインターバル分析MCPツールを実装

#### 2.1 インターバル分析（2日） ✅ **完了**

**実装**: `tools/rag/queries/interval_analysis.py`

**クラス**: `IntervalAnalyzer`

**機能**:
- Work/Recovery区間自動検出
- 各区間のメトリクス集計（HR, ペース, GCT, VO, VR）
- 疲労蓄積検出（最終インターバルでのHR/ペース悪化）
- HR回復速度計算

**MCPツール**: `get_interval_analysis`

**テスト**: `tests/rag/queries/test_interval_analysis.py`

**実装結果** (2025-10-10 完了):
- ✅ IntervalAnalyzer クラス実装 (224行)
- ✅ 6テストケース実装 (255行)
- ✅ テストカバレッジ: 85%
- ✅ コード品質: Black/Ruff/Mypy パス
- ✅ コミット: `da52422` (feature/rag_interval_tools)

#### 2.2 時系列詳細取得（2日）

**実装**: `tools/rag/queries/time_series_detail.py`

**クラス**: `TimeSeriesDetailExtractor`

**機能**:
- 特定split（1km）の秒単位データ抽出
- 統計値計算（平均、標準偏差、最大最小）
- Split内異常検出

**MCPツール**: `get_split_time_series_detail`

**テスト**: `tests/rag/queries/test_time_series_detail.py`

#### 2.3 フォーム異常検出（2日）

**実装**: `tools/rag/queries/form_anomaly_detector.py`

**クラス**: `FormAnomalyDetector`

**機能**:
- GCT/VO/VR異常検出（Z-scoreベース）
- 原因分析（標高変化/ペース変化/疲労）
- 相関係数計算
- 改善提案生成

**MCPツール**: `detect_form_anomalies`

**テスト**: `tests/rag/queries/test_form_anomaly_detector.py`

#### 実装完了 - Phase 2.1 (2025-10-10)
- ✅ **IntervalAnalyzer**: 224行実装
- ✅ **テストスイート**: 6テストケース（255行）
- ✅ **カバレッジ**: 85%
- ✅ **コード品質**: Black/Ruff/Mypy パス
- ✅ **コミット**: `da52422` (feature/rag_interval_tools)
- ✅ **追加作業**: 全テストfixture化完了（177 passed, 0 skipped）
  - test_body_composition.py: 2テスト
  - test_raw_data_extractor_integration.py: 3テスト
  - test_backward_compatibility.py: 3テスト
  - test_interval_analysis.py: 1テスト
- ✅ **コミット**: `a6321c8` (fixture化)

#### 受け入れ基準
- [x] **Phase 2.1 完了**: IntervalAnalyzer 実装・テスト完了 (6/6 tests passed)
- [ ] **Phase 2.2**: TimeSeriesDetailExtractor 実装
- [ ] **Phase 2.3**: FormAnomalyDetector 実装
- [ ] インターバル検出精度90%以上（Phase 2.1で実装済み）
- [ ] 異常検出の誤検知率10%以下（Phase 2.3完了後に検証）
- [x] 全テストパス（177 passed, 0 skipped, 4 deselected）

---

### Phase 3: 基本RAGツール（Week 2-3、4日、並行実装）

#### 目標
トレンド分析・インサイト抽出の基本ツールを実装

#### 3.1 PerformanceTrendAnalyzer（2日）

**実装**: `tools/rag/queries/trends.py`

**機能**:
- 10メトリクスのトレンド分析（pace, HR, cadence, power, etc.）
- 線形回帰による傾向検出
- 3つのフィルタ（activity_type, temperature_range, distance_range）

**MCPツール**: `get_performance_trends`

**テスト**: `tests/rag/queries/test_trends.py`

#### 3.2 InsightExtractor（1日）

**実装**: `tools/rag/queries/insights.py`

**機能**:
- キーワードベース検索（improvements, concerns, patterns）
- ページネーション（limit/offset）

**MCPツール**: `extract_insights`

**テスト**: `tests/rag/queries/test_insights.py`

#### 3.3 ActivityClassifier（1日）

**実装**: `tools/rag/utils/activity_classifier.py`

**機能**:
- 6つのトレーニングタイプ分類（Base, Threshold, Sprint, Anaerobic, Long Run, Recovery）
- 英語・日本語キーワード対応

**テスト**: `tests/rag/utils/test_activity_classifier.py`

#### 受け入れ基準
- [ ] トレンド分析が10メトリクスで動作
- [ ] フィルタリングが正確
- [ ] インサイト抽出のトークン制限対応
- [ ] 全テストパス

---

### Phase 4: MCPサーバー統合（Week 3、2日）

#### 目標
全6つのRAGツールをGarmin DB MCPサーバーに統合

#### 4.1 servers/garmin_db_server.py 更新

**追加ツール**:
1. `get_interval_analysis`
2. `get_split_time_series_detail`
3. `detect_form_anomalies`
4. `get_performance_trends`
5. `extract_insights`
6. `classify_activity_type` (optional)

#### 4.2 統合テスト

**テスト**: `tests/integration/test_rag_mcp_integration.py`

**検証項目**:
- MCP経由でのツール呼び出し
- エラーハンドリング
- エンドツーエンド動作確認

#### 受け入れ基準
- [ ] 全6ツールがMCP経由で動作
- [ ] 統合テストパス
- [ ] Claude Code UIから正常動作

---

### Phase 5: ドキュメント・完了報告（Week 3-4、1日）

#### 5.1 CLAUDE.md 更新

**追加内容**:
- RAG Tools セクション（6ツール）
- 使用例
- activity_details.json メトリクス表

#### 5.2 completion_report.md 作成

**内容**:
- テスト結果まとめ
- カバレッジレポート
- パフォーマンステスト結果
- 受け入れ基準チェック

#### 5.3 既存プロジェクトの整理

**アクション**:
- 2025-10-05プロジェクトのステータス更新（Phase 1-2実装完了、Phase 3保留）
- 2025-10-09プロジェクトのステータス更新（完了）
- メモリ更新（実装完了状態を正確に反映）

---

### Phase 6: Wellness統合（Week 5+、9-13日、保留）

#### 前提条件
- Phase 1-5完了
- Garmin Wellness API可用性検証

#### 6.1 API検証（1日）

**検証項目**:
- Sleep API
- Stress API
- Body Battery API
- Training Readiness API

**検証内容**:
- 過去60-90日データ取得可否
- レート制限
- データ品質

#### 6.2 実装（API検証成功の場合のみ）

**参照**: `docs/project/2025-10-05_rag_system/phase3_specifications.md`

**サブフェーズ**:
1. データ収集基盤（3日）
2. Training Load計算（2日）
3. 相関分析エンジン（3日）
4. MCP統合（2日）
5. 検証・ドキュメント（3日）

---

## 実装スケジュール

### Week 1: インターバル分析基盤 + ツール実装開始
- **Day 1-2**: ActivityDetailsLoader実装 + テスト
- **Day 3-4**: IntervalAnalyzer実装 + テスト
- **Day 5**: TimeSeriesDetailExtractor実装開始

### Week 2: インターバル分析完成 + 基本RAGツール開始
- **Day 1**: TimeSeriesDetailExtractor完成 + テスト
- **Day 2-3**: FormAnomalyDetector実装 + テスト
- **Day 4**: PerformanceTrendAnalyzer実装開始（並行）
- **Day 5**: PerformanceTrendAnalyzer完成 + テスト

### Week 3: 基本RAGツール完成 + MCP統合
- **Day 1**: InsightExtractor実装 + テスト
- **Day 2**: ActivityClassifier実装 + テスト
- **Day 3-4**: MCPサーバー統合（全6ツール）
- **Day 5**: 統合テスト

### Week 4: テスト・ドキュメント・完了報告
- **Day 1**: エンドツーエンドテスト
- **Day 2**: ドキュメント作成（CLAUDE.md更新）
- **Day 3**: completion_report.md作成
- **Day 4**: ユーザー検証
- **Day 5**: プロジェクト整理・完了

### Week 5+ (Optional): Wellness統合
- API検証から開始
- 検証成功の場合のみ実装

---

## Git Worktree戦略

### Worktree構成

```
claude_workspace/
├── garmin/                              # Main worktree (main branch)
├── garmin-rag_interval_tools/           # Phase 1-2 worktree
│   └── feature/rag_interval_tools       # インターバル分析実装
└── garmin-rag_basic_tools/              # Phase 3 worktree
    └── feature/rag_basic_tools          # トレンド分析実装
```

### Worktree作成コマンド

```bash
# Phase 1-2: インターバル分析ツール
git worktree add -b feature/rag_interval_tools ../garmin-rag_interval_tools main
cd ../garmin-rag_interval_tools
uv sync

# Phase 3: 基本RAGツール（並行開発）
git worktree add -b feature/rag_basic_tools ../garmin-rag_basic_tools main
cd ../garmin-rag_basic_tools
uv sync
```

### マージ戦略

1. **Phase 2完了時**: feature/rag_interval_tools → main
2. **Phase 3完了時**: feature/rag_basic_tools → main
3. **Phase 4統合完了時**: 両機能がmainで統合

---

## リスク管理

### リスク1: activity_details.json欠損
**確率**: 低（103件確認済み）
**対策**: ファイル存在チェック、performance.jsonフォールバック

### リスク2: メトリクス仕様変更
**確率**: 中（Garmin API仕様変更）
**対策**: metricDescriptorsのkey名でマッピング、バリデーションテスト

### リスク3: パフォーマンス劣化
**確率**: 中（26メトリクス × 1400秒）
**対策**: 必要メトリクスのみ抽出、NumPy活用

### リスク4: Wellness API可用性
**確率**: 高（未検証）
**対策**: Phase 6を最後に配置、API検証を先行実施

### リスク5: 実装期間超過
**確率**: 中（複雑度の見積もり誤差）
**対策**: 段階的実装、並行開発、定期進捗確認

---

## 成功基準

### Phase 1-4（インターバル分析 + 基本RAGツール）
- [ ] 全6つのMCPツールが実装され動作する
- [ ] activity_details.json（103件）が正しく処理される
- [ ] 全テストパス（ユニット + 統合）
- [ ] カバレッジ85%以上
- [ ] Black, Ruff, Mypy チェックパス
- [ ] ユーザー検証完了
- [ ] ドキュメント完備

### Phase 6（Wellness統合、Optional）
- [ ] Wellness API検証完了
- [ ] データ収集パイプライン動作（>95%成功率）
- [ ] 統計的相関分析実装
- [ ] "Why"質問に回答可能
- [ ] ユーザー精度確認（>80%）

---

## 次のステップ

### 即座のアクション

1. **ユーザー承認**
   - この統合計画をレビュー
   - 優先順位の確認
   - Phase 6（Wellness）の要否判断

2. **Phase 1開始準備**
   - Git worktree作成（feature/rag_interval_tools）
   - ActivityDetailsLoaderのTDD開始

3. **project-planner エージェント不要**
   - この計画書が既に詳細計画になっている
   - 直接 tdd-implementer エージェント起動可能

### 推奨コマンド

```bash
# Phase 1-2開始（インターバル分析）
Task: tdd-implementer
prompt: "docs/project/2025-10-10_rag_unified_plan/planning.md のPhase 1から実装を開始してください。Git worktree（feature/rag_interval_tools）を作成し、ActivityDetailsLoaderをTDDで実装してください。"
```

---

## 関連ドキュメント

- **2025-10-05_rag_system/**: Phase 3（Wellness統合）の詳細仕様
- **2025-10-09_rag_interval_analysis_tools/**: インターバル分析の詳細仕様
- **CLAUDE.md**: システム全体のドキュメント
- **DEVELOPMENT_PROCESS.md**: TDD開発プロセス

---

**最終更新**: 2025-10-10
**作成者**: Claude Code
**ステータス**: ユーザー承認待ち
**次のアクション**: ユーザーレビュー → Phase 1実装開始
