# Analysis Standards

Consolidated reference for all analysis rules.

## 1. Data Access

- **MCP tools only**: `mcp__garmin-db__*` を使う。直接 `duckdb.connect()`, SQL, `.duckdb` ファイルアクセス禁止
- **Token optimization**: `statistics_only=True` 優先 (67-80% 削減)。`get_splits_comprehensive()` で12フィールド一括取得
- **10+ activities**: Export workflow — PLAN(SQL設計) → EXPORT(parquet) → CODE(Python) → RESULT → INTERPRET
- **数値は当該テーブルから**: VO2max / LTHR / 体重 / HR ゾーン境界などの数値は、`athlete_profile.focus_notes` 等のプロフィール散文ではなく該当ツール（`get_vo2_max_data`、`get_lactate_threshold_data`、`get_body_composition_trend`、`get_heart_rate_zones_detail`）から取る。プロフィール記述は執筆時点のスナップショットで陳腐化する（"now 44" と書かれた VO2max の実値は 45.8 だった）

## 2. Agent Rules

5 section type (split, phase, efficiency, environment, summary) を生成する3エージェント（unified-section-analyst が efficiency/phase/environment を、summary-section-analyst が summary を、split-section-analyst が split を担当）の共通ルール:

- **独立動作**: 全データを CONTEXT / MCP tools から直接取得。全セクションは並列生成のため、summary のセクション間整合（他セクションの結論と矛盾しない）は共有 CONTEXT から導出する（他セクションの出力 JSON は参照できない）
- **事前コンテキスト**: orchestrator 提供の JSON を信頼し、不足時のみ追加 MCP 呼び出し
- **出力**: 日本語テキスト + English key names。`{ANALYSIS_TEMP_DIR}/{section_type}.json` に出力（ANALYSIS_TEMP_DIR は orchestrator が timestamp 付きユニークパスとして提供）。**事前の mkdir は不要**（Write tool が親ディレクトリを自動作成する）
- **JSON構造**: `{"activity_id": <int>, "activity_date": "<YYYY-MM-DD>", "section_type": "<type>", "analysis_data": {...}}`
- **星評価**: `(★★★★☆ N.N/5.0)`
- **HR zones**: Garmin native zones のみ (計算式禁止)
- **Dates**: `datetime.date` → `str()` 変換してから JSON 出力
- **文体**: 自然な日本語（体言止め回避）、コーチ的トーン、具体的数値、1-2文/ポイント

### Error Recovery

- 5/5 成功 → 通常フロー（全セクションを DuckDB に登録）
- 4/5 成功 → 失敗セクションを skip、成功した4セクションのみ DuckDB に登録。skip 内容をユーザーに報告
- 3/5 以下 → 分析中止、DuckDB 登録は行わず、全エラーをユーザーに報告。自動リトライしない

## 3. Evaluation Principles

### 4軸評価

1. **Effort**: HR / power / LT比
2. **Performance**: pace / distance
3. **Efficiency**: pace/HR, GCT/VR統合
4. **Execution**: training_type の目的合致度

### 改善提案

- `recommendations` 最大2件。次回アクションは1つに絞る（数値+成功判定条件付き）
- Easy run の提案 → HR 範囲で提示（ペースではなく）。例外条件を1つ添える
- 一般的助言禁止（「もっと練習しましょう」→ 具体数値必須）
- **`success_criterion` は次回の refinement 目安であり今回の合否ではない**。目的を達したランには「成功条件」「失敗」の表現を使わず、「維持目標」「改善余地」として提示する（agent の prose・会話での引用の双方）
- **過敏な評価は閾値緩和ではなくカテゴリ分離で解く**: 「厳しすぎる」フィードバックの最初の一手は「一律に測っているものを training_type / 文脈で分けられないか」を問う（例: ペース CV はテンポ走はシビアに、LSD / 時間重視ロングは緩く）。既存の category 分離を確認し、閾値変更ではなく category 別の評価方針で分岐させる

### エージェント間の一貫性

- HR zone 評価 → unified-section-analyst の efficiency セクションの `evaluation` が権威的ソース
- 各セクションの評価は training_type を基準に判定する

## 4. Training Plans

- **Volume**: 初週 = 直近 median ±10%。週間増加 15% warning / 25% reject（自動検証）
- **gap_detected=true**: recent_runs ベースライン使用
- **Schedule**: 曜日検証必須。連続ラン制限（3-4回/週→3日連続禁止、5回→4日連続禁止、6回→週1休養+高強度連続禁止）
- **HR zone target**: Garmin native zones 内に収まること
- **Intent**: "プラン生成" = `/plan-training` 実行。コード分析ではない

## 5. Data Safety

- **data/ と result/ は git 未管理 — 削除したら復元不可能**
- 削除前: `ls -la` で中身確認 → ユーザーデータ有無判断 → ユーザー確認
- `rm -rf` をファイル有無未確認で実行禁止
- 誤配置ファイル → 正しいパスに移動してから削除
