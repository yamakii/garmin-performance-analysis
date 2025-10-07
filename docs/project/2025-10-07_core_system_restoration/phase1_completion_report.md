# Phase 1 完了レポート: コアシステム復元

**作成日**: 2025-10-07
**ステータス**: ✅ 完了
**テスト結果**: 17/17 通過

---

## 概要

git filter-repo災害後のコアシステム復元Phase 1が完了しました。データ取得→変換→保存パイプラインの3コンポーネントを実装し、全17ユニット・統合テストが通過しました。

---

## 実装完了コンポーネント

### 1. GarminIngestWorker (tools/ingest/garmin_worker.py)

**責務**: Garmin Connect APIからのデータ取得とperformance.json生成

**主要機能**:
- ✅ キャッシュ優先戦略（raw_data → API → cache保存）
- ✅ シングルトン認証（セッション単位で1回のみ）
- ✅ Parquetデータセット生成（15カラム/split）
- ✅ performance.json生成（11セクション）
- ✅ 体組成データ収集（weight, vo2_max, lactate_threshold, training_effect）
- ✅ アクティビティ日付取得（DuckDB連携）

**テストカバレッジ**: 9テスト
- ✅ `test_get_activity_date_from_db`
- ✅ `test_get_activity_date_not_found`
- ✅ `test_collect_data_uses_cache_when_available`
- ✅ `test_create_parquet_dataset`
- ✅ `test_calculate_split_metrics`
- ✅ `test_save_data_creates_files`
- ✅ `test_process_activity_full_pipeline`
- ✅ `test_collect_data_with_real_garmin_api`
- ✅ `test_process_activity_full_integration`

**重要な設計判断**:
- MCPはClaude Codeからのみ呼び出し可能（Pythonから不可）
- garminconnectライブラリを使用（直接API接続）
- 環境変数からGARMIN_EMAIL/PASSWORD取得
- データ型は既存raw_dataと完全一致（list形式のhr_zones, gear）

### 2. PerformanceDataInserter (tools/database/inserters/performance.py)

**責務**: performance.jsonをDuckDBに挿入

**主要機能**:
- ✅ activitiesテーブルへのメタデータ挿入
- ✅ performance_dataテーブルへの全11セクション挿入
- ✅ トランザクション処理（FK制約遵守）

**テストカバレッジ**: 3テスト
- ✅ `test_insert_performance_data_success`
- ✅ `test_insert_performance_data_missing_file`
- ✅ `test_insert_performance_data_db_integration`

**挿入データ構造**:
```sql
activities: (activity_id, activity_date, distance_km, duration_seconds,
             avg_pace_seconds_per_km, avg_heart_rate)
performance_data: (activity_id, activity_date, basic_metrics, heart_rate_zones,
                   hr_efficiency_analysis, form_efficiency_summary,
                   performance_trends, split_metrics, efficiency_metrics,
                   training_effect, power_to_weight, lactate_threshold)
```

### 3. SectionAnalysisInserter (tools/database/inserters/section_analyses.py)

**責務**: セクション分析結果をDuckDBに挿入

**主要機能**:
- ✅ ファイルベース挿入（JSON読み込み）
- ✅ 辞書ベース挿入（推奨：ファイル作成不要）
- ✅ analysis_id自動採番（最大値+1方式）
- ✅ メタデータ抽出（analyst → agent_name, version → agent_version）

**テストカバレッジ**: 5テスト
- ✅ `test_insert_section_analysis_success`
- ✅ `test_insert_section_analysis_missing_file`
- ✅ `test_insert_section_analysis_dict_success`
- ✅ `test_insert_section_analysis_db_integration`
- ✅ `test_insert_section_analysis_dict_db_integration`

**挿入データ構造**:
```sql
section_analyses: (analysis_id, activity_id, activity_date, section_type,
                   analysis_data, agent_name, agent_version, created_at)
```

---

## 型一致確認

### performance.json構造（11セクション）

既存データ（data/performance/20594901208.json）と新実装の完全一致を確認：

| セクション | フィールド数 | 状態 |
|-----------|------------|------|
| basic_metrics | 8 | ✅ 一致 |
| heart_rate_zones | zone1-5 (各2フィールド) | ✅ 一致 |
| split_metrics | 配列（15フィールド/split） | ✅ 一致 |
| efficiency_metrics | 3 | ✅ 一致 |
| training_effect | 2 | ✅ 一致 |
| power_to_weight | 1 | ✅ 一致 |
| vo2_max | 1 | ✅ 一致 |
| lactate_threshold | 2 | ✅ 一致 |
| form_efficiency_summary | 18 | ✅ 一致 |
| hr_efficiency_analysis | 9 | ✅ 一致 |
| performance_trends | 10 | ✅ 一致 |

**検証コマンド**:
```bash
# 既存ファイル読み込み
cat data/performance/20594901208.json

# 新実装で生成
worker = GarminIngestWorker()
performance_data = worker._calculate_split_metrics(df, raw_data)
```

### section_analysesテーブルスキーマ

既存DuckDB（data/database/garmin_performance.duckdb）と新実装の完全一致を確認：

```sql
-- 既存スキーマ（DESCRIBE section_analyses）
CREATE TABLE section_analyses (
    analysis_id INTEGER PRIMARY KEY,
    activity_id BIGINT NOT NULL,
    activity_date DATE NOT NULL,
    section_type VARCHAR NOT NULL,
    analysis_data VARCHAR,  -- JSON型ではなくVARCHAR
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    agent_name VARCHAR,
    agent_version VARCHAR,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
)
```

**修正履歴**:
1. ❌ 初期実装：複合PK (activity_id, section_type)
2. ✅ 修正：INTEGER PRIMARY KEY (analysis_id) + 自動採番実装
3. ❌ フィールド名：analyst, version
4. ✅ 修正：agent_name, agent_version
5. ❌ データ型：JSON
6. ✅ 修正：VARCHAR（json.dumps()で文字列化）

**検証コマンド**:
```bash
# 既存スキーマ確認
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb', read_only=True)
result = conn.execute('DESCRIBE section_analyses').fetchall()
for row in result: print(row)
"

# 新実装テスト
PYTHONPATH=. uv run pytest tests/database/inserters/test_section_analyses.py -v
```

---

## 技術的課題と解決

### 課題1: MCPとPythonの分離

**問題**: MCP関数はClaude Codeからしか呼び出せず、Pythonから直接実行不可

**解決**:
- garminconnectライブラリを使用してAPI直接接続
- 環境変数からGARMIN_EMAIL/PASSWORDを取得
- シングルトンパターンでセッション管理

```python
@classmethod
def get_garmin_client(cls) -> Garmin:
    """Single authentication per session."""
    if cls._garmin_client is None:
        email = os.getenv("GARMIN_EMAIL")
        password = os.getenv("GARMIN_PASSWORD")
        cls._garmin_client = Garmin(email, password)
        cls._garmin_client.login()
    return cls._garmin_client
```

### 課題2: DuckDB自動インクリメント

**問題**: DuckDBの`INTEGER PRIMARY KEY`は自動インクリメントされない

**解決**: 最大analysis_id取得→+1方式で実装

```python
# Get next analysis_id
max_id_result = conn.execute(
    "SELECT COALESCE(MAX(analysis_id), 0) FROM section_analyses"
).fetchone()
next_analysis_id = max_id_result[0] + 1 if max_id_result else 1
```

### 課題3: テストでのAPI認証回避

**問題**: pre-commitフックでAPI認証が走るとrate limit到達

**解決**:
- unit testではモックまたはキャッシュ優先
- integration testでは既存キャッシュファイル使用
- pre-commitで全テスト実行可能（キャッシュのみ使用）

```yaml
# .pre-commit-config.yaml
- id: pytest
  name: pytest (all tests)
  entry: uv run pytest --tb=short -q
  pass_filenames: false
  always_run: true
```

### 課題4: 既存データ型との不一致

**問題**: テストフィクスチャが実際のGarmin API構造と異なる

**解決**: 既存raw_dataファイルを参照して型を修正

```python
# 誤り（初期想定）
"hr_zones": {
    "zone1": {"low": 100, "secs_in_zone": 300}
}

# 正解（実際のAPI）
"hr_zones": [
    {"zoneNumber": 1, "zoneLowBoundary": 100, "secsInZone": 300.0}
]
```

---

## ファイル構成

```
tools/
├── ingest/
│   └── garmin_worker.py          # GarminIngestWorker実装
└── database/
    └── inserters/
        ├── performance.py         # PerformanceDataInserter実装
        └── section_analyses.py    # SectionAnalysisInserter実装

tests/
├── ingest/
│   └── test_garmin_worker.py     # 9テスト
└── database/
    └── inserters/
        ├── test_performance.py    # 3テスト
        └── test_section_analyses.py # 5テスト

.pre-commit-config.yaml            # black, ruff, mypy, pytest
```

---

## 次のステップ（Phase 2以降）

### Phase 2: ワークフローオーケストレーション

- [ ] WorkflowPlannerの実装
- [ ] アクティビティ処理パイプライン統合
- [ ] バッチ処理機能

### Phase 3: エージェントシステム復元

- [ ] efficiency-section-analyst
- [ ] environment-section-analyst
- [ ] phase-section-analyst
- [ ] split-section-analyst
- [ ] summary-section-analyst

### Phase 4: レポート生成システム

- [ ] report-generator-worker
- [ ] MCPテンプレートサーバー統合

---

## まとめ

Phase 1では、データ取得→変換→保存の基盤パイプラインを完全復元しました。

**達成指標**:
- ✅ 全17テスト通過
- ✅ performance.json型一致（既存と100%互換）
- ✅ section_analysesスキーマ一致（既存DuckDBと100%互換）
- ✅ キャッシュ優先戦略（rate limit回避）
- ✅ TDDワークフロー遵守（Red-Green-Refactor）

**技術的成果**:
- MCPとPythonの明確な役割分担
- DuckDB自動採番の実装パターン確立
- 既存システムとの後方互換性保証

Phase 2以降で、このパイプラインを活用したワークフローオーケストレーションを実装します。
