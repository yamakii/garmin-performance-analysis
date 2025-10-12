# 計画: HR Zone Percentage Pre-calculation

## プロジェクト情報
- **プロジェクト名**: `2025-10-12_hr_zone_percentage_precalc`
- **作成日**: `2025-10-12`
- **ステータス**: 計画中

---

## 要件定義

### 目的
心拍ゾーンの滞在時間から各ゾーンのパーセンテージ（zone1_percentage ~ zone5_percentage）を計算し、`performance.json` の `hr_efficiency_analysis` セクションと DuckDB の `hr_efficiency` テーブルに保存する。

### 解決する問題

**現状の問題:**
1. `performance.json` の `hr_efficiency_analysis` に心拍ゾーンのパーセンテージ（zone1_percentage ~ zone5_percentage）が含まれていない
2. `_calculate_hr_efficiency_analysis()` メソッドは、各ゾーンのパーセンテージを計算していない
3. DuckDB の `hr_efficiency` テーブルにゾーンパーセンテージが挿入されていない
4. `docs/spec/duckdb_schema_mapping.md` の仕様では、これらのフィールドが必要とされている

**影響範囲:**
- `tools/ingest/garmin_worker.py`: `_calculate_hr_efficiency_analysis` メソッド（928-973行目）
- `tools/database/inserters/hr_efficiency.py`: `insert_hr_efficiency` 関数
- 既存の `performance.json` ファイル（再生成が必要）
- DuckDB データ（再挿入が必要）

### ユースケース

**UC1: 心拍ゾーンパーセンテージの計算**
- データ取り込み時に、心拍ゾーンの滞在時間（`secs_in_zone`）から各ゾーンのパーセンテージを自動計算
- 計算式: `zone_percentage = (secs_in_zone / total_secs_in_all_zones) * 100`

**UC2: performance.json への保存**
- `hr_efficiency_analysis` セクションに `zone1_percentage` ~ `zone5_percentage` を追加
- 既存のフィールド（`training_type`, `hr_stability`）との互換性を維持

**UC3: DuckDB への挿入**
- `hr_efficiency` テーブルに zone1_percentage ~ zone5_percentage を挿入
- 既存のレコードを更新（再挿入）

**UC4: 既存データの再生成**
- `bulk_regenerate.py` を使用して全ての performance.json を再生成
- `reingest_duckdb_data.py` を使用して DuckDB データを再挿入

---

## 設計

### アーキテクチャ

**データフロー:**
```
Raw Data (heart_rate_zones with secs_in_zone)
    ↓
_calculate_hr_efficiency_analysis() [NEW: Calculate percentages]
    ↓
performance.json (hr_efficiency_analysis with zone1-5_percentage)
    ↓
insert_hr_efficiency() [NEW: Insert percentages]
    ↓
DuckDB hr_efficiency table (zone1-5_percentage columns)
```

**修正対象コンポーネント:**
1. **GarminIngestWorker._calculate_hr_efficiency_analysis()**: ゾーンパーセンテージ計算ロジック追加
2. **hr_efficiency inserter**: ゾーンパーセンテージのINSERT文更新

### データモデル

**performance.json の hr_efficiency_analysis セクション（修正後）:**
```json
{
  "hr_efficiency_analysis": {
    "avg_heart_rate": 145.2,
    "training_type": "tempo_run",
    "hr_stability": "優秀",
    "description": "適切な心拍ゾーンで実施",
    "zone1_percentage": 10.5,
    "zone2_percentage": 25.3,
    "zone3_percentage": 40.2,
    "zone4_percentage": 20.0,
    "zone5_percentage": 4.0
  }
}
```

**DuckDB hr_efficiency テーブル（スキーマ確認）:**
```sql
-- 既存のスキーマ（変更なし）
CREATE TABLE IF NOT EXISTS hr_efficiency (
    activity_id BIGINT PRIMARY KEY,
    primary_zone VARCHAR,
    zone_distribution_rating VARCHAR,
    hr_stability VARCHAR,
    aerobic_efficiency VARCHAR,
    training_quality VARCHAR,
    zone2_focus BOOLEAN,
    zone4_threshold_work BOOLEAN,
    training_type VARCHAR,
    zone1_percentage DOUBLE,
    zone2_percentage DOUBLE,
    zone3_percentage DOUBLE,
    zone4_percentage DOUBLE,
    zone5_percentage DOUBLE
)
```

### API/インターフェース設計

**1. _calculate_hr_efficiency_analysis() の修正:**
```python
def _calculate_hr_efficiency_analysis(
    self, df: pd.DataFrame, hr_zones: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Calculate HR efficiency analysis with zone percentages.

    Args:
        df: Performance DataFrame
        hr_zones: List of {zoneNumber, secsInZone, zoneLowBoundary}

    Returns:
        HR zone distribution with percentages and training type classification
    """
    # Existing logic...

    # NEW: Calculate zone percentages
    total_time = sum(zone.get("secsInZone", 0) for zone in hr_zones)
    zone_percentages = {}

    for zone in hr_zones:
        zone_num = zone.get("zoneNumber")
        secs_in_zone = zone.get("secsInZone", 0)

        if total_time > 0 and zone_num:
            percentage = (secs_in_zone / total_time) * 100
            zone_percentages[f"zone{zone_num}_percentage"] = round(percentage, 2)

    return {
        "avg_heart_rate": avg_hr,
        "training_type": training_type,
        "hr_stability": stability,
        "description": description,
        **zone_percentages  # zone1_percentage ~ zone5_percentage
    }
```

**2. insert_hr_efficiency() の修正:**
```python
def insert_hr_efficiency(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert hr_efficiency_analysis with zone percentages into DuckDB.
    """
    # Extract hr_efficiency_analysis
    hr_eff = performance_data.get("hr_efficiency_analysis")

    # Insert with zone percentages
    conn.execute(
        """
        INSERT INTO hr_efficiency (
            activity_id,
            hr_stability,
            training_type,
            zone1_percentage,
            zone2_percentage,
            zone3_percentage,
            zone4_percentage,
            zone5_percentage
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            activity_id,
            hr_eff.get("hr_stability"),
            hr_eff.get("training_type"),
            hr_eff.get("zone1_percentage"),
            hr_eff.get("zone2_percentage"),
            hr_eff.get("zone3_percentage"),
            hr_eff.get("zone4_percentage"),
            hr_eff.get("zone5_percentage"),
        ],
    )
```

---

## 実装フェーズ

### Phase 0: 現状分析と影響範囲確認 ✅
- ✅ 現在の `_calculate_hr_efficiency_analysis` メソッドの調査
- ✅ `hr_efficiency` inserter の調査
- ✅ DuckDB スキーマの確認
- ✅ `performance.json` のデータ構造確認

### Phase 1: _calculate_hr_efficiency_analysis メソッドの修正 ✅
**実装内容:**
- ✅ ゾーンパーセンテージ計算ロジックの追加
- ✅ `hr_zones` から `secsInZone` を取得し、総時間に対する割合を計算
- ✅ 戻り値に `zone1_percentage` ~ `zone5_percentage` を追加
- ✅ 総時間が0またはhr_zonesが空の場合は zone_percentages を含めない

**テスト内容:**
- ✅ Unit test: ゾーンパーセンテージ計算の正確性 (test_calculate_hr_efficiency_analysis_with_zone_percentages)
- ✅ Edge case: `hr_zones` が空の場合の処理 (test_calculate_hr_efficiency_analysis_empty_zones)
- ✅ Edge case: 総時間が0の場合の処理 (test_calculate_hr_efficiency_analysis_zero_total_time)
- ✅ Edge case: zoneNumber が欠けている場合の処理 (test_calculate_hr_efficiency_analysis_missing_zone_number)
- ✅ Validation: 2桁精度への丸め処理 (test_calculate_hr_efficiency_analysis_rounding)
- ✅ Validation: 全ゾーンパーセンテージの合計が100%に近い (test_zone_percentage_sum_equals_100)

**Commit:** `a17e2ea` - feat(ingest): add HR zone percentage calculation to _calculate_hr_efficiency_analysis

### Phase 2: hr_efficiency inserter の修正 ✅
**実装内容:**
- ✅ `insert_hr_efficiency()` の INSERT 文にゾーンパーセンテージカラムを追加
- ✅ `performance.json` からゾーンパーセンテージを抽出 (`.get()` で NULL を許容)
- ✅ 既存レコードの削除後に再挿入（UPDATE ではなく DELETE + INSERT）

**テスト内容:**
- ✅ Unit test: ゾーンパーセンテージの正しい挿入 (test_insert_hr_efficiency_with_zone_percentages)
- ✅ Unit test: ゾーンパーセンテージがない場合の NULL 挿入 (test_insert_hr_efficiency_missing_zone_percentages)
- ✅ Unit test: 既存レコードの再挿入 (test_insert_hr_efficiency_reinsertion)
- ✅ Unit test: 部分的なゾーンパーセンテージの挿入 (test_insert_hr_efficiency_partial_zone_percentages)

**Commit:** `e45c380` - feat(database): add zone percentage insertion to hr_efficiency inserter

### Phase 3: テストとバリデーション
**実装内容:**
- 既存の単体テスト実行
- 新規テストケース追加
- コードカバレッジ確認

**テスト内容:**
- Unit test: GarminIngestWorker の修正部分
- Unit test: hr_efficiency inserter の修正部分
- Integration test: 完全なデータ取り込みフロー

### Phase 4: 既存データの再生成
**実装内容:**
- `bulk_regenerate.py` を実行して全 performance.json を再生成
- `reingest_duckdb_data.py` を実行して DuckDB データを再挿入
- 既存データとの互換性確認

**テスト内容:**
- Performance test: 再生成の速度測定
- Validation: サンプルデータのゾーンパーセンテージ検証
- Validation: DuckDB のゾーンパーセンテージデータ確認

### Phase 5: ドキュメント更新
**実装内容:**
- `CLAUDE.md` の performance.json 構造説明を更新
- `docs/spec/duckdb_schema_mapping.md` のマッピング確認
- 実装完了報告書の作成

---

## テスト計画

### Unit Tests

**test_garmin_worker.py:**
- [ ] `test_calculate_hr_efficiency_analysis_with_zone_percentages`: ゾーンパーセンテージが正しく計算されることを確認
- [ ] `test_calculate_hr_efficiency_analysis_empty_zones`: hr_zones が空の場合、ゾーンパーセンテージが含まれないことを確認
- [ ] `test_calculate_hr_efficiency_analysis_zero_total_time`: 総時間が0の場合の処理を確認
- [ ] `test_zone_percentage_sum_equals_100`: 全ゾーンのパーセンテージ合計が100%に近いことを確認（誤差許容）

**test_hr_efficiency_inserter.py:**
- [ ] `test_insert_hr_efficiency_with_zone_percentages`: ゾーンパーセンテージが正しく挿入されることを確認
- [ ] `test_insert_hr_efficiency_missing_zone_percentages`: ゾーンパーセンテージがない場合、NULL が挿入されることを確認
- [ ] `test_insert_hr_efficiency_reinsertion`: 既存レコードの再挿入が正常に動作することを確認

### Integration Tests

- [ ] **完全なデータフローテスト**: Raw data → performance.json → DuckDB の全工程を実行し、ゾーンパーセンテージが正しく伝播することを確認
- [ ] **実データテスト**: 実際のアクティビティデータ（例: activity_id=20652528219）でゾーンパーセンテージを計算し、妥当性を検証
- [ ] **後方互換性テスト**: 既存の performance.json（ゾーンパーセンテージなし）が正常に処理できることを確認

### Performance Tests

- [ ] **bulk_regenerate.py 実行時間**: 全 performance.json の再生成時間を測定（目標: 既存処理から +5% 以内）
- [ ] **reingest_duckdb_data.py 実行時間**: DuckDB 再挿入時間を測定（目標: 既存処理から +5% 以内）
- [ ] **メモリ使用量**: 大量データ処理時のメモリ使用量を確認（目標: 既存処理から +10% 以内）

### Validation Tests

- [ ] **ゾーンパーセンテージの合計**: 各アクティビティのゾーンパーセンテージ合計が 99.0% ~ 101.0% の範囲内であることを確認（浮動小数点誤差を考慮）
- [ ] **DuckDB データ整合性**: performance.json と DuckDB のゾーンパーセンテージが一致することを確認
- [ ] **サンプルデータ検証**: 10件のサンプルアクティビティでゾーンパーセンテージの妥当性を手動確認

---

## 受け入れ基準

- [ ] `_calculate_hr_efficiency_analysis()` がゾーンパーセンテージを計算し、戻り値に含めている
- [ ] `insert_hr_efficiency()` がゾーンパーセンテージを DuckDB に挿入している
- [ ] 全 Unit Tests がパスする（カバレッジ 80% 以上）
- [ ] 全 Integration Tests がパスする
- [ ] 全 Performance Tests が目標値を満たす
- [ ] 全 Validation Tests がパスする（ゾーンパーセンテージ合計が妥当）
- [ ] Pre-commit hooks（Black, Ruff, Mypy）がパスする
- [ ] 既存の全 performance.json が再生成されている
- [ ] DuckDB データが再挿入されている
- [ ] ドキュメント（CLAUDE.md, duckdb_schema_mapping.md）が更新されている
- [ ] 後方互換性が保たれている（既存の performance.json が処理できる）

---

## リスクと対策

### リスク1: 既存データの再生成時間が長い
**対策:**
- `bulk_regenerate.py` の並列処理を活用
- 段階的な再生成（月ごと、年ごと）を検討
- 最小限のサンプルで先に動作確認

### リスク2: ゾーンパーセンテージの計算誤差
**対策:**
- 浮動小数点演算の誤差を考慮した検証ロジック（99% ~ 101% の範囲）
- 高精度計算（Decimal 型）の検討（必要に応じて）

### リスク3: 後方互換性の問題
**対策:**
- ゾーンパーセンテージがない古い performance.json でも正常に動作するようにする
- `get()` メソッドで None を許容
- DuckDB inserter で NULL 値を適切に処理

---

## 参考資料

- `docs/spec/duckdb_schema_mapping.md`: DuckDB スキーマとマッピング仕様
- `tools/ingest/garmin_worker.py`: GarminIngestWorker の実装
- `tools/database/inserters/hr_efficiency.py`: hr_efficiency inserter の実装
- `docs/project/2025-10-09_garmin_ingest_refactoring/`: 関連プロジェクト（GarminIngestWorker リファクタリング）
