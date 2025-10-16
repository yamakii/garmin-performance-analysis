# DuckDB × MCP × LLM アーキテクチャ: 実行例

このディレクトリには、DuckDB × MCP × LLM アーキテクチャの実際の使用例を示す Jupyter ノートブックが含まれています。

## 概要

これらのノートブックは、新しいアーキテクチャがどのように **95-98% のトークン削減** を達成し、LLM のコンテキストを保護しながら効率的なデータ分析を可能にするかを実証します。

## アーキテクチャの核心原則

### 責務分離

1. **LLM (Claude)**: データ要求の計画 + 結果の解釈のみ
   - ❌ 生データの直接読み取り禁止
   - ✅ ハンドル（パス）のみ受け取る
   - ✅ 要約データ（統計 + グラフ）で解釈

2. **MCP Server**: ハンドルベースのデータ抽出
   - ✅ `export()`: データを Parquet に出力し、ハンドルのみ返却（~25トークン）
   - ✅ `profile()`: 要約統計のみ返却（~125トークン）
   - ✅ `histogram()`: 分布集計のみ返却（~250トークン）
   - ❌ 生データの直接返却禁止

3. **Python (Code Executor)**: データ処理 + 可視化
   - ✅ ハンドルからデータをロード
   - ✅ リサンプリング・集計・相関分析
   - ✅ グラフ生成
   - ✅ 要約データのみを LLM に返却（1KB 制限）

### データフロー

```
ユーザー質問
    ↓
LLM: 計画立案
    ↓
MCP: export() → ハンドル返却 (25トークン)
    ↓
Python: データ処理 + グラフ生成
    ↓
Python: 要約JSON生成 (100トークン)
    ↓
LLM: 結果解釈 + 自然言語レポート
```

## ノートブック一覧

### 1. 秒単位インターバル分析 (`01_interval_analysis.ipynb`)

**ユースケース**: 「5:00-10:00のペース変動を秒単位で分析して」

**アーキテクチャフロー**:
- MCP `export()` でペース・心拍・ケイデンスをエクスポート
- Python でリサンプリング + ローリング平均計算
- グラフ生成 + 統計サマリー（平均・標準偏差・最大偏差）
- LLM が給水ポイントなどの異常を解釈

**トークン削減**:
- Before: 約3,000トークン（生データ直接読み込み）
- After: 約125トークン（ハンドル + 要約）
- **削減率: 95.8%** 🎉

---

### 2. フォーム異常深堀り分析 (`02_anomaly_drilldown.ipynb`)

**ユースケース**: 「GCTが急上昇した箇所の前後30秒を詳しく見たい」

**アーキテクチャフロー**:
- MCP `detect_form_anomalies_summary()` で異常概要を取得（700トークン）
- MCP `get_form_anomaly_details()` でフィルタして特定異常を取得
- MCP `export()` で異常前後30秒のデータをエクスポート
- Python で相関分析（ペース/HR/標高 vs GCT）
- 散布図 + 時系列プロット + 統計サマリー
- LLM が原因仮説（地形、疲労、ペース変化）を提示

**トークン削減**:
- Before: 約400トークン（全時系列データ）
- After: 約125トークン（個別異常分析のみ）
- **削減率: 68.75%** ✅
- 注: 異常サマリー（700トークン）は全アクティビティで1回のみ取得し再利用可能

---

### 3. 複数アクティビティ比較 (`03_multi_activity_comparison.ipynb`)

**ユースケース**: 「過去5回の10kmランの心拍ゾーン推移を比較したい」

**アーキテクチャフロー**:
- MCP `profile()` で各アクティビティの要約統計を取得（5 × 125トークン）
- MCP `export()` で5アクティビティの心拍データをエクスポート（5 × 25トークン）
- Python で時間軸を0-100%に正規化
- 重ね合わせグラフ + トレンドライン生成
- 統計サマリー（平均心拍・ペース・ゾーン分布の変化）
- LLM がパフォーマンス変化（改善・疲労）を解説

**トークン削減**:
- Before: 約67,500トークン（5アクティビティの全時系列データ）
- After: 約900トークン（プロファイル + ハンドル + 要約）
- **削減率: 98.7%** 🎉🎉🎉

---

## セットアップ

### 必要な依存関係

```bash
# 基本インストール
uv sync

# 開発ツール込み
uv sync --extra dev

# Jupyter サポート
uv pip install jupyter matplotlib seaborn scipy
```

### ノートブックの実行

```bash
# Jupyter Notebook を起動
jupyter notebook docs/examples/

# または JupyterLab
jupyter lab docs/examples/
```

### 注意事項

- **モックデータ使用**: これらのノートブックはモックデータを使用しています
- **実データでの実行**: 実際のデータベースがある場合、MCP Server の関数呼び出し部分のコメントを外して実行できます
- **環境変数**: `.env` ファイルで `GARMIN_DATA_DIR` を設定してください（実データ使用時）

## トークンコスト比較表

| ユースケース | Before（生データ） | After（新アーキテクチャ） | 削減率 |
|------------|-------------------|------------------------|--------|
| 秒単位インターバル分析 | 3,000トークン | 125トークン | 95.8% |
| フォーム異常深堀り | 400トークン | 125トークン | 68.8% |
| 複数アクティビティ比較 | 67,500トークン | 900トークン | 98.7% |

## アーキテクチャのメリット

### 1. コンテキスト保護
- LLM は生データを受け取らない
- ハンドル（パス文字列）のみ受け取る（~25トークン）
- トークン枯渇を防ぎ、複雑な分析が可能に

### 2. データ処理の最適化
- Python/DuckDB がデータ処理を担当（LLM ではなく）
- 高速なベクトル演算・SQL 集計を活用
- LLM は解釈のみに集中

### 3. セーフティガード
- 出力サイズ制限（JSON: 1KB、テーブル: 10行）
- 超過時の自動トリム + 警告
- LLM が誤って全データ展開を試みても安全

### 4. 再利用性
- 異常サマリー、プロファイルなどは1回取得で複数分析に再利用可能
- エクスポートされた Parquet ファイルは TTL（1時間）まで再利用可能
- トークンコストをさらに削減

## ベストプラクティス

### LLM 向けプロンプトガイドライン

```python
# ❌ 悪い例: 生データを直接読み取ろうとする
data = mcp__garmin_db__get_time_range_detail(
    activity_id=12345,
    start_time_s=0,
    end_time_s=3600,
    statistics_only=False  # 全データ返却 → トークン枯渇
)

# ✅ 良い例: ハンドルベースのアプローチ
# ステップ1: データをエクスポート（ハンドルのみ返却）
export_result = mcp__garmin_db__export(
    query="SELECT * FROM time_series_metrics WHERE activity_id = 12345",
    format="parquet"
)

# ステップ2: Python でデータ処理
df = safe_load_export(export_result['handle'])
summary = compute_statistics(df)  # Python 関数

# ステップ3: 要約のみを LLM に返却
llm_output = safe_json_output(summary)  # 1KB 制限
```

### Python 開発者向けガイドライン

```python
from tools.utils.llm_safe_data import (
    safe_load_export,      # Parquet ロード（サイズ制限付き）
    safe_json_output,      # JSON 出力（1KB 制限）
    safe_summary_table,    # テーブル出力（10行制限）
)

# データロード（10,000行制限）
df = safe_load_export(handle, max_rows=10000)

# 要約JSONを生成（1KB制限）
summary = {
    'mean': df['metric'].mean(),
    'std': df['metric'].std()
}
json_output = safe_json_output(summary)  # ValueError if > 1KB

# テーブル出力（10行制限）
table_output = safe_summary_table(df, max_rows=10)
```

## トラブルシューティング

### エラー: "JSON output exceeds max_size"

**原因**: 要約 JSON が 1KB を超えている

**解決策**:
- より少ない統計値に絞る
- グラフパスのみを返し、詳細は省略
- 配列を使う代わりにスカラー値（平均・中央値）のみ返す

### エラー: "Export exceeds max_rows"

**原因**: エクスポートされたデータが 10,000行を超えている

**解決策**:
- SQL クエリで時間範囲を絞る
- データを集計してから export（例: 秒単位 → 分単位）
- `max_rows` パラメータを調整（慎重に）

### ノートブックが実行できない

**解決策**:
- 依存関係を再インストール: `uv sync`
- Jupyter をインストール: `uv pip install jupyter`
- カーネルを再起動

## 参考資料

- **計画書**: `docs/project/2025-10-16_duckdb_mcp_llm_architecture/planning.md`
- **完了報告書**: `docs/project/2025-10-16_duckdb_mcp_llm_architecture/completion_report.md`
- **CLAUDE.md**: プロジェクトルートの `CLAUDE.md`（アーキテクチャガイド）
- **LLM Behavior Rules**: `docs/LLM_BEHAVIOR_RULES.md`

## フィードバック・質問

このアーキテクチャや例についての質問・フィードバックは、GitHub Issue または Pull Request でお寄せください。

---

**作成日**: 2025-10-16
**Phase**: Phase 4 - Example Analysis Flow
**ステータス**: 完了
