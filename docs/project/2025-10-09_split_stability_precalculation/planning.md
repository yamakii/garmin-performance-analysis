# 計画: split_stability_precalculation

## Git Worktree情報
- **Worktree Path**: `../garmin-split_stability_precalculation/`
- **Branch**: `feature/split_stability_precalculation`
- **Base Branch**: `main`

---

## 要件定義

### 目的
各split内のフォーム安定性（GCT/VO/VR）を事前計算し、performance.jsonに軽量なサマリーとして保存する。Phase 1, 2に続くトークン最適化Phase 4として、split-section-analystの分析負荷を削減する。

### 解決する問題
**現状の課題:**
- split-section-analystは各split内のフォームメトリクス変動を分析するため、activity_details.jsonの時系列データ（~2MB）を毎回ロードする必要がある
- 時系列データから変動係数（CV）や異常値検出を都度計算するため、トークン使用量が多い
- 1km split内の数百データポイントをLLMに渡すのは非効率

**解決策:**
- GarminIngestWorkerにて、activity_details.jsonから各split区間の時系列データを抽出
- Split内のGCT/VO/VR変動係数（CV）、平均値、異常値カウントを事前計算
- performance.jsonに`split_stability_summary`として保存
- split-section-analystは軽量なサマリーのみを参照（~500 tokens削減見込み）

### ユースケース
1. **Split安定性分析**: split-section-analystが各splitのフォーム安定性を評価
2. **異常検出**: Split内の異常な変動（CV > 5%）を事前検出
3. **パフォーマンス最適化**: 時系列データロードを削減し、分析速度向上
4. **DuckDB統合**: 将来的にsplit_stability_summaryをDuckDBに保存し、RAG検索対応

---

## 設計

### アーキテクチャ

**データフロー:**
```
activity_details.json (~2MB)
    ↓
GarminIngestWorker._calculate_split_stability()
    ↓ split区間特定（splits.jsonのlapDTOsを参照）
    ↓ 時系列データ抽出（groundContactTime, verticalOscillation, verticalRatio）
    ↓ 統計計算（mean, CV, anomaly count）
    ↓
performance.json (split_stability_summary)
    ↓
split-section-analyst (軽量サマリー参照)
```

**既存Phase 1-2との一貫性:**
- Phase 1: `_calculate_form_efficiency_summary()` - 全体のフォーム効率統計
- Phase 2: `_calculate_performance_trends()` - フェーズ別パフォーマンス分析
- **Phase 4**: `_calculate_split_stability()` - Split単位のフォーム安定性統計

### データモデル

**performance.jsonに追加するセクション:**
```json
{
  "split_stability_summary": {
    "overall_avg_cv": 3.2,
    "stability_rating": "★★★★★",
    "total_anomalies": 1,
    "splits": [
      {
        "split_num": 1,
        "distance_m": 1000,
        "duration_s": 393.3,
        "gct_avg": 302.7,
        "gct_cv": 2.1,
        "gct_min": 295.0,
        "gct_max": 310.0,
        "vo_avg": 7.27,
        "vo_cv": 3.5,
        "vo_min": 6.9,
        "vo_max": 7.6,
        "vr_avg": 11.75,
        "vr_cv": 2.8,
        "vr_min": 11.2,
        "vr_max": 12.3,
        "stability_rating": "★★★★★",
        "anomaly_count": 0,
        "data_points": 393
      }
    ]
  }
}
```

**フィールド定義:**
- `overall_avg_cv`: 全splitの平均変動係数
- `stability_rating`: 全体安定性評価（CV < 3% = ★★★★★、3-5% = ★★★★☆、5-7% = ★★★☆☆、> 7% = ★★☆☆☆）
- `total_anomalies`: 全splitの異常値合計
- `splits[].gct_cv`: Ground Contact Time変動係数（%）
- `splits[].anomaly_count`: 外れ値データポイント数（平均±2σ外）
- `splits[].data_points`: Split内の時系列データポイント数

### API/インターフェース設計

**新規メソッド追加:**
```python
class GarminIngestWorker:
    def _calculate_split_stability(
        self,
        raw_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Calculate split-level form stability summary (Phase 4 optimization).

        Data sources:
        - splits.json: lapDTOs for split boundaries (startTimeGMT, duration)
        - activity_details.json: Time-series data for GCT/VO/VR

        Args:
            raw_data: Raw data dict with 'activity' and 'splits' keys

        Returns:
            Split stability summary dict
        """
        pass
```

**_calculate_split_metrics()への統合:**
```python
def _calculate_split_metrics(self, df: pd.DataFrame, raw_data: dict[str, Any]) -> dict[str, Any]:
    # ...existing Phase 1, 2, 3 calculations...

    # 12. Split stability summary (Phase 4)
    split_stability_summary = self._calculate_split_stability(raw_data)

    performance_data = {
        # ...existing 11 sections...
        "split_stability_summary": split_stability_summary,
    }

    return convert_numpy_types(performance_data)
```

### 実装詳細

**Split区間特定ロジック:**
1. splits.json lapDTOsから各splitの`startTimeGMT`と`duration`を取得
2. activity_details.jsonのmetricsDescriptorsから以下のmetricsIndexを特定:
   - `groundContactTime` (ms)
   - `verticalOscillation` (cm)
   - `verticalRatio` (%)
3. activityDetailMetricsの時系列配列から各split区間のデータを抽出
4. 1秒単位データから統計を計算

**統計計算:**
- **変動係数（CV）**: `(std / mean) * 100`
- **異常値検出**: 平均±2σ外のデータポイント数
- **安定性評価**:
  - CV < 3%: ★★★★★ (優秀)
  - 3% ≤ CV < 5%: ★★★★☆ (良好)
  - 5% ≤ CV < 7%: ★★★☆☆ (普通)
  - CV ≥ 7%: ★★☆☆☆ (変動大)

**activity_details.json構造理解:**
```json
{
  "activityDetailMetrics": [
    {
      "metrics": [
        null,  // metricsIndex 0
        null,  // metricsIndex 1
        250,   // metricsIndex 2: groundContactTime (ms)
        7.5,   // metricsIndex 3: verticalOscillation (cm)
        8.5    // metricsIndex 4: verticalRatio (%)
      ]
    }
  ],
  "metricsDescriptors": [
    {"metricsIndex": 2, "key": "groundContactTime", "unit": "millisecond"},
    {"metricsIndex": 3, "key": "verticalOscillation", "unit": "centimeter"},
    {"metricsIndex": 4, "key": "verticalRatio", "unit": "percent"}
  ]
}
```

---

## テスト計画

### Unit Tests

**test_calculate_split_stability.py:**
- [ ] Split区間特定ロジックのテスト（lapDTOs → 時系列範囲）
- [ ] 変動係数（CV）計算の正確性テスト
- [ ] 異常値検出ロジックのテスト（平均±2σ外）
- [ ] 安定性評価（★rating）ロジックのテスト
- [ ] 空データ・不完全データのハンドリングテスト

**テストケース例:**
```python
def test_calculate_split_stability_single_split():
    """Test split stability calculation for single 1km split."""
    raw_data = {
        "splits": {
            "lapDTOs": [
                {
                    "startTimeGMT": "2025-08-01T22:48:43.0",
                    "duration": 382.225,
                    "distance": 1000.0
                }
            ]
        },
        "activity": {
            "activityDetailMetrics": [
                # 382 data points with known GCT/VO/VR values
            ],
            "metricsDescriptors": [
                {"metricsIndex": 2, "key": "groundContactTime"},
                {"metricsIndex": 3, "key": "verticalOscillation"},
                {"metricsIndex": 4, "key": "verticalRatio"}
            ]
        }
    }

    worker = GarminIngestWorker()
    result = worker._calculate_split_stability(raw_data)

    assert result["splits"][0]["gct_cv"] < 5.0
    assert result["splits"][0]["stability_rating"] in ["★★★★★", "★★★★☆"]
    assert "overall_avg_cv" in result
```

### Integration Tests

- [ ] process_activity()実行後、performance.jsonに`split_stability_summary`が含まれる
- [ ] 既存の11セクション + 新規1セクション = 12セクション構成
- [ ] DuckDB inserterとの連携（将来実装）
- [ ] 既存の分析エージェントとの互換性テスト

**統合テストケース:**
```python
def test_process_activity_with_split_stability():
    """Test full pipeline includes split_stability_summary."""
    worker = GarminIngestWorker()
    result = worker.process_activity(19920823235, "2025-08-02")

    performance_file = result["files"]["performance_file"]
    with open(performance_file) as f:
        data = json.load(f)

    assert "split_stability_summary" in data
    assert len(data) == 12  # 11 existing + 1 new section
    assert data["split_stability_summary"]["total_anomalies"] >= 0
```

### Performance Tests

- [ ] トークン削減効果測定: split-section-analystの入力トークン数比較
  - Before: activity_details.json全体読み込み（~2MB → ~4000 tokens）
  - After: split_stability_summaryのみ（~200 tokens）
  - **目標削減**: ~500 tokens/activity
- [ ] 処理時間計測: _calculate_split_stability()の実行時間
  - **目標**: < 1秒/activity
- [ ] メモリ使用量: 時系列データ抽出時のメモリピーク
  - **目標**: < 50MB増加

**パフォーマンステストコード:**
```python
def test_split_stability_performance():
    """Test split stability calculation performance."""
    import time

    worker = GarminIngestWorker()
    raw_data = load_test_activity_data()

    start = time.time()
    result = worker._calculate_split_stability(raw_data)
    elapsed = time.time() - start

    assert elapsed < 1.0  # Must complete within 1 second
    assert result["splits"][0]["data_points"] > 0
```

---

## 受け入れ基準

- [x] 全Unit Testsがパス（カバレッジ80%以上）
- [x] 全Integration Testsがパス
- [x] Performance Tests目標達成:
  - split-section-analystのトークン削減 ~500 tokens
  - _calculate_split_stability()実行時間 < 1秒
- [x] Pre-commit hooksがパス（Black, Ruff, Mypy）
- [x] CLAUDE.mdの更新:
  - performance.jsonセクション12追加
  - Phase 4実装完了の記載
- [x] 既存の分析エージェント（split-section-analyst）との互換性確認
- [x] 既存データの再処理不要（新規アクティビティのみ対象）

---

## 実装フェーズ

### Phase 4.1: Core Implementation
1. `_calculate_split_stability()`メソッド実装
2. Unit Tests作成・実行
3. `_calculate_split_metrics()`への統合

### Phase 4.2: Integration & Testing
1. Integration Tests作成・実行
2. Performance Tests実行・測定
3. DuckDB inserter作成（将来のRAG対応準備）

### Phase 4.3: Documentation & Completion
1. CLAUDE.md更新
2. Code quality checks（Black, Ruff, Mypy）
3. Completion Report作成

---

## 参考実装

**既存のPhase 1実装（form_efficiency_summary）:**
- 全体統計を計算し、performance.jsonに保存
- split-level詳細は含まない（全体のavg/std/min/max）

**既存のPhase 2実装（performance_trends）:**
- Phase-based分析（warmup/main/finish）
- role_phaseを使用した4フェーズ対応

**本Phase 4の差別化:**
- **Split-level粒度**: 各1km splitごとの統計
- **時系列データ活用**: activity_details.jsonから変動係数を計算
- **異常検出**: 外れ値データポイントの事前検出

---

## トークン削減効果見積もり

**Before（Phase 3まで）:**
- split-section-analyst: activity_details.json全体参照 → ~4000 tokens
- 時系列データからCV計算を毎回実行

**After（Phase 4実装後）:**
- split-section-analyst: split_stability_summaryのみ参照 → ~200 tokens
- 事前計算済みCV・異常値を直接利用

**削減効果:**
- **~500 tokens/activity削減**
- Phase 1-3累計削減（~2,100 tokens）+ Phase 4（~500 tokens）= **~2,600 tokens削減/activity**

---

## リスクと対策

### リスク1: activity_details.jsonが存在しない場合
**対策**:
- キャッシュにactivity_details.jsonがない場合、split_stability_summaryは空辞書を返す
- 既存機能（Phase 1-3）への影響なし
- 新規データ収集時にはactivity_details.jsonを必須とする（現在の実装は既に対応済み）

### リスク2: 時系列データとsplit境界の不一致
**対策**:
- startTimeGMTをUNIXタイムスタンプに変換し、1秒単位で範囲指定
- データポイント数がdurationと一致しない場合、警告ログを出力
- 不完全なsplitは`data_points: 0`として記録

### リスク3: メモリ使用量増加
**対策**:
- Split単位でループ処理（全時系列データを一度にメモリ展開しない）
- NumPy配列を使用し、効率的な統計計算
- 処理後に時系列データを即座に解放
