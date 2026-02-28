# Analysis Standards

Consolidated reference for all analysis rules.

## 1. Data Access

- **MCP tools only**: `mcp__garmin-db__*` を使う。直接 `duckdb.connect()`, SQL, `.duckdb` ファイルアクセス禁止
- **Token optimization**: `statistics_only=True` 優先 (67-80% 削減)。`get_splits_comprehensive()` で12フィールド一括取得
- **10+ activities**: Export workflow — PLAN(SQL設計) → EXPORT(parquet) → CODE(Python) → RESULT → INTERPRET

## 2. Agent Rules

5 section agents (split, phase, efficiency, environment, summary) の共通ルール:

- **独立動作**: 他セクション分析を参照しない。全データを MCP tools から直接取得
- **事前コンテキスト**: orchestrator 提供の JSON を信頼し、不足時のみ追加 MCP 呼び出し
- **出力**: 日本語テキスト + English key names。`{temp_dir}/{section_type}.json` に出力
- **JSON構造**: `{"activity_id": <int>, "activity_date": "<YYYY-MM-DD>", "section_type": "<type>", "analysis_data": {...}}`
- **星評価**: `(★★★★☆ N.N/5.0)`
- **HR zones**: Garmin native zones のみ (計算式禁止)
- **Dates**: `datetime.date` → `str()` 変換してから JSON 出力
- **文体**: 自然な日本語（体言止め回避）、コーチ的トーン、具体的数値、1-2文/ポイント

### Error Recovery

- 5/5 成功 → 通常フロー
- 4/5 成功 → 失敗セクション skip、レポートヘッダーに記載
- 3/5 以下 → レポート中止、全エラーをユーザーに報告。自動リトライしない

## 3. Evaluation Principles

### 4軸評価

1. **Effort**: HR / power / LT比
2. **Performance**: pace / distance
3. **Efficiency**: pace/HR, GCT/VR統合
4. **Execution**: plan vs actual, 目的合致度

### 改善提案

- `recommendations` 最大2件。次回アクションは1つに絞る（数値+成功判定条件付き）
- Easy run の提案 → HR 範囲で提示（ペースではなく）。例外条件を1つ添える
- 一般的助言禁止（「もっと練習しましょう」→ 具体数値必須）

### エージェント間の一貫性

- HR zone 評価 → efficiency-section-analyst の `evaluation` が権威的ソース
- plan target 存在時 → training_type 評価より plan 達成度を優先

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
