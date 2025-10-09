# Phase 1 調査レポート: GarminIngestWorker リファクタリング

**日付**: 2025-10-09
**フェーズ**: Phase 1 - 調査・準備

---

## 1. 新フォーマットのtraining_effect格納場所調査

### 調査対象
- **ファイル**: `data/raw/activity/20615445009/activity_details.json`
- **サイズ**: 2.1MB（旧フォーマットの65倍）
- **行数**: 85,217行

### 調査結果

#### トップレベルキー構造
```json
{
  "activityId": 20615445009,
  "activityDetailMetrics": [...],  // 1,398個の秒単位メトリクス
  "geoPolylineDTO": {...},         // 2,771個のGPSポイント
  "heartRateDTOs": [],
  "metricDescriptors": [...],      // 26種類のメトリクス定義
  "measurementCount": 26,
  "metricsCount": 1398,
  "totalMetricsCount": 2771,
  "detailsAvailable": true,
  "pendingData": false
}
```

#### 重要な発見

**✅ 正しいAPI: `get_activity()` にtraining_effectデータが存在する**

1. **get_activity_details() vs get_activity()**
   - `get_activity_details(activity_id, maxchart=2000)`: チャートデータ詳細取得、summaryDTO**なし**（2.1MB）
   - `get_activity(activity_id)`: 基本情報取得、summaryDTO**あり**（10KB）

2. **get_activity() のsummaryDTOにtraining_effectが含まれる**
   - 新フォーマット（20615445009）: trainingEffect=3.6, anaerobicTrainingEffect=2.1, trainingEffectLabel="VO2MAX"
   - 旧フォーマット（20594901208）: trainingEffect=2.4, anaerobicTrainingEffect=0.0, trainingEffectLabel="RECOVERY"

3. **get_activity() のレスポンスサイズ**
   - 約10KB（10,577文字）
   - get_activity_details(maxchart=2000)の200分の1のサイズ

4. **get_activity_details(maxchart=2000)の特性**
   - チャートデータ取得用API
   - summaryDTOキー自体が省略される
   - metricDescriptors（26種類）にもtraining関連なし
   - activityDetailMetrics（時系列データ）にもtraining関連なし

### 結論

**`get_activity()` APIを追加で呼び出すことでtraining_effectデータを取得できる。**

#### 対応方針

1. **get_activity() APIの追加**
   - `collect_data()`で`get_activity()`を最初に呼び出す
   - `activity.json`として保存（約10KB）
   - summaryDTOからtraining_effectを抽出

2. **get_activity_details() の役割明確化**
   - 純粋にチャートデータ取得用（maxchart=2000）
   - summaryDTOには依存しない

3. **推奨アプローチ**
   ```python
   # 1. Basic info with summaryDTO (10KB)
   activity_basic = client.get_activity(activity_id)
   # Save to activity.json

   # 2. Chart data (2.1MB, optional polyline control)
   activity_details = client.get_activity_details(activity_id, maxchart=2000, maxpoly=0)
   # Save to activity_details.json
   ```

4. **Rate Limit対策**
   - API呼び出しは1回増加（get_activity追加）
   - ただしレスポンスサイズは小さく、基本情報取得のみ
   - キャッシュファーストで既存ファイルがあればAPI呼び出しなし

---

## 2. DuckDB reader/writerの既存実装確認

### GarminDBReader（`tools/database/db_reader.py`）

#### 主要メソッド

| メソッド | 機能 | Phase 2での利用 |
|---------|------|----------------|
| `get_activity_date(activity_id)` | activity_idから日付を取得 | ✅ キャッシュチェックに使用 |
| `get_performance_section(activity_id, section)` | 特定セクションのデータ取得 | ✅ 完全性チェックに使用 |
| `get_section_analysis(activity_id, section_type)` | セクション分析データ取得 | ⚠️ Phase 3で使用 |
| `get_splits_pace_hr(activity_id)` | スプリット詳細取得 | ⚠️ Phase 3で使用 |
| `get_splits_form_metrics(activity_id)` | フォームメトリクス取得 | ⚠️ Phase 3で使用 |
| `get_splits_elevation(activity_id)` | 標高データ取得 | ⚠️ Phase 3で使用 |

#### 実装の特徴

1. **セクションベースアクセス**
   ```python
   # performance_trendsは正規化テーブルから読み込み
   if section == "performance_trends":
       # performance_trendsテーブルから直接取得
   else:
       # performance_dataテーブルのJSONカラムから取得
   ```

2. **read_only接続**
   - 並行アクセスを考慮した安全な実装
   - `duckdb.connect(str(self.db_path), read_only=True)`

3. **エラーハンドリング**
   - すべてのメソッドでtry-exceptを実装
   - エラー時はNoneを返却

### GarminDBWriter（`tools/database/db_writer.py`）

#### 主要メソッド

| メソッド | 機能 | Phase 2での利用 |
|---------|------|----------------|
| `_ensure_tables()` | テーブルスキーマ作成 | ✅ 自動実行 |
| `insert_activity(...)` | activitiesテーブルに挿入 | ✅ キャッシュ作成時に使用 |
| `insert_performance_data(...)` | performance_dataテーブルに挿入 | ✅ キャッシュ作成時に使用 |
| `insert_section_analysis(...)` | section_analysisテーブルに挿入 | ⚠️ Phase 3で使用 |
| `insert_body_composition(...)` | body_compositionテーブルに挿入 | ⚠️ 体組成データ用 |

#### テーブルスキーマ（Phase 2関連）

```sql
-- activities テーブル
CREATE TABLE IF NOT EXISTS activities (
    activity_id INTEGER PRIMARY KEY,
    date DATE NOT NULL,
    activity_name TEXT,
    location_name TEXT,
    weight_kg DOUBLE,
    weight_source TEXT,
    weight_method TEXT,
    distance_km DOUBLE,
    duration_seconds DOUBLE,
    avg_pace_seconds_per_km DOUBLE,
    avg_heart_rate DOUBLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- performance_data テーブル
CREATE TABLE IF NOT EXISTS performance_data (
    activity_id INTEGER PRIMARY KEY,
    basic_metrics TEXT,              -- JSON
    heart_rate_zones TEXT,           -- JSON
    split_metrics TEXT,              -- JSON
    efficiency_metrics TEXT,         -- JSON
    training_effect TEXT,            -- JSON ← ここにtraining_effectが格納
    power_to_weight TEXT,            -- JSON
    vo2_max TEXT,                    -- JSON
    lactate_threshold TEXT,          -- JSON
    form_efficiency_summary TEXT,    -- JSON (Phase 1)
    hr_efficiency_analysis TEXT,     -- JSON (Phase 1)
    performance_trends TEXT,         -- JSON (deprecated, use performance_trends table)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 実装の特徴

1. **UPSERT方式**
   - `ON CONFLICT DO UPDATE`で重複時は更新
   - 再処理時の安全性を確保

2. **JSON保存**
   - DictをJSON文字列に変換して保存
   - `json.dumps(data, ensure_ascii=False)`

3. **自動スキーマ管理**
   - `__init__`で`_ensure_tables()`を自動実行
   - テーブルが存在しない場合は自動作成

### Phase 2での活用方針

#### キャッシュチェック実装

```python
def _check_duckdb_cache(self, activity_id: int) -> dict[str, Any] | None:
    """
    Check if complete performance data exists in DuckDB.

    Returns:
        Complete performance data dict if all sections exist, None otherwise
    """
    reader = GarminDBReader(db_path=self.db_path)

    # 必須セクションのリスト
    required_sections = [
        "basic_metrics",
        "heart_rate_zones",
        "split_metrics",
        "efficiency_metrics",
        "training_effect",
        "power_to_weight",
        "vo2_max",
        "lactate_threshold",
        "form_efficiency_summary",
        "hr_efficiency_analysis",
        "performance_trends",
    ]

    performance_data = {}

    for section in required_sections:
        data = reader.get_performance_section(activity_id, section)
        if data is None:
            # 1つでも欠けていればNone
            return None
        performance_data[section] = data

    return performance_data
```

---

## 3. テストデータ準備状況

### 既存データ確認

| Activity ID | フォーマット | 日付 | DuckDB登録 | 新ディレクトリ構造 |
|------------|-------------|------|-----------|------------------|
| 20594901208 | 旧（32KB） | 2025-10-05 | ✅ あり | ✅ `data/raw/activity/20594901208/` |
| 20615445009 | 新（2.1MB） | 2025-10-07 | ✅ あり | ✅ `data/raw/activity/20615445009/` |

### ファイル構成

#### 20594901208（旧フォーマット）
```
data/raw/activity/20594901208/
├── activity_details.json (9.1KB) ← summaryDTOあり
├── splits.json (16.8KB)
├── weather.json (481B)
├── gear.json (598B)
├── hr_zones.json (411B)
├── vo2_max.json (2B)
└── lactate_threshold.json (617B)
```

#### 20615445009（新フォーマット）
```
data/raw/activity/20615445009/
├── activity_details.json (2.1MB) ← summaryDTOなし、チャートデータあり
├── splits.json
├── weather.json
├── gear.json
├── hr_zones.json
├── vo2_max.json
└── lactate_threshold.json
```

### テストデータの準備完了

✅ **両フォーマットのテストデータが新ディレクトリ構造で利用可能**
✅ **両方ともDuckDBに登録済み**
✅ **Phase 2のテスト実装に即座に使用可能**

---

## 4. Phase 2への推奨事項

### 4.1. training_effect問題の対応（解決済み）

**✅ 解決方法: `get_activity()` APIを追加で呼び出す**

```python
# collect_data()で以下の順序で取得
# 0. Activity basic info (summaryDTO with training_effect, 10KB)
activity_file = activity_dir / "activity.json"
if not activity_file.exists():
    activity_basic = client.get_activity(str(activity_id))
    # Save to activity.json
    with open(activity_file, "w", encoding="utf-8") as f:
        json.dump(activity_basic, f, ensure_ascii=False, indent=2)

# 1. Chart data details (2.1MB with maxchart=2000)
activity_details_file = activity_dir / "activity_details.json"
if not activity_details_file.exists():
    activity_details = client.get_activity_details(activity_id, maxchart=2000, maxpoly=0)
    # Save to activity_details.json
```

**メリット:**
- training_effectデータを確実に取得
- get_activity()のレスポンスサイズは小さい（10KB）
- 既存のactivity_details.jsonはチャートデータ専用として役割明確化
- Rate limit: +1 API call（ただしレスポンスサイズは小さく、キャッシュファースト）

**デメリット:**
- API呼び出し回数が1回増加（許容範囲内）

**実装変更点:**
1. `collect_data()`: get_activity()を最初に呼び出し、activity.jsonに保存
2. `load_from_cache()`: activity.jsonからsummaryDTOを読み込む
3. テストファイル: 既存の2活動にactivity.jsonを生成して検証

### 4.2. DuckDBキャッシュチェック実装

```python
def _check_duckdb_cache(self, activity_id: int) -> dict[str, Any] | None:
    """DuckDBから完全なperformance_dataを取得"""
    # 上記「キャッシュチェック実装」参照
```

**実装ポイント:**
- 11セクションすべての存在確認
- 1つでも欠けていればNone返却
- エラーハンドリング必須

### 4.3. process_activity()への統合

```python
def process_activity(self, activity_id: int, date: str) -> dict[str, Any]:
    # 1. DuckDBキャッシュチェック（最優先）
    cached_data = self._check_duckdb_cache(activity_id)
    if cached_data:
        logger.info(f"DuckDB cache hit for activity {activity_id}")
        return {
            "activity_id": activity_id,
            "date": date,
            "source": "duckdb_cache",
            "status": "success",
        }

    # 2. raw_dataキャッシュチェック
    raw_data = self.load_from_cache(activity_id)
    if raw_data is None:
        # 3. API取得
        raw_data = self.collect_data(activity_id)

    # 4. データ加工・保存
    df = self.create_parquet_dataset(raw_data)
    performance_data = self._calculate_split_metrics(df, raw_data)
    self.save_data(activity_id, raw_data, df, performance_data)

    return {"activity_id": activity_id, "date": date, "status": "success"}
```

---

## 5. Phase 2実装タスク

### 優先度: 高

- [ ] `_check_duckdb_cache()` 実装
- [ ] `process_activity()` にDuckDBキャッシュチェック追加
- [ ] training_effect問題の対応方針決定（Option 1 or 2）
- [ ] Unit Tests作成

### 優先度: 中

- [ ] maxchart=0の挙動検証
- [ ] Performance Tests（DuckDBキャッシュヒット時 < 100ms）

### 優先度: 低

- [ ] ログレベル調整
- [ ] エラーメッセージ改善

---

## 6. リスク・課題

### 高リスク

1. **新フォーマットのtraining_effect取得不可**
   - 影響: 分析の完全性が損なわれる
   - 対策: maxchart=0での取得を検証、失敗時はOption 2

### 中リスク

2. **DuckDBキャッシュの不完全性**
   - 影響: 一部セクションのみ存在する場合の挙動
   - 対策: 完全性チェック必須、不完全な場合は再処理

3. **APIパラメータ変更の影響**
   - 影響: maxchart=0でsummaryDTOが返らない可能性
   - 対策: Phase 2で検証、失敗時は既存実装に戻す

---

## 7. 次のステップ

1. **Phase 2開始**: DuckDBキャッシュ機能実装
2. **training_effect対応**: maxchart=0の検証から開始
3. **TDDサイクル**: テストファースト開発で進行
