# 計画: Workout Similarity Improvement

## プロジェクト情報
- **プロジェクト名**: `workout_similarity_improvement`
- **作成日**: `2025-10-13`
- **ステータス**: 計画中
- **担当コンポーネント**: `tools/rag/queries/comparisons.py`

## 要件定義

### 目的
類似ワークアウト検索機能（`compare_similar_workouts`）の精度と有用性を向上させる。トレーニングタイプと環境要因（気温）を考慮した、より実用的な類似度計算を実現する。

### 解決する問題

#### 問題1: トレーニングタイプを考慮していない
**現状**: ペース・距離のみで類似度を計算しているため、異なるトレーニングタイプ（Tempo vs Anaerobic）が同列に評価される。

**影響**:
- 中強度ワークアウト（Tempo走）を検索すると、高強度ワークアウト（Anaerobic走）が上位に表示される
- トレーニング目的が異なる活動が比較されてしまう
- ユーザーが過去の同種トレーニングを振り返れない

**解決策**: トレーニングタイプ階層的類似度マトリックスを導入

#### 問題2: 心拍数を類似度計算に使用（気温変動影響）
**現状**: 心拍数を類似度計算に使用しているが、気温による変動が大きい（夏場は+15-20bpm）。

**影響**:
- 同じペースでも気温が異なると類似度が大幅に低下
- 季節間での比較が不正確
- 心拍数差が誤解を招く（実際は気温の影響）

**解決策**: 心拍数を類似度計算から除外し、参考情報として気温差と共に表示

#### 問題3: 気温差が考慮されていない
**現状**: 心拍数差のみが表示され、気温差による影響が不明。

**影響**:
- ユーザーが心拍数上昇の原因を誤解する
- コンディション評価が不正確

**解決策**: `weather.json`から気温データを取得し、"心拍: +12bpm（気温+6°C影響）"のように表示

### ユースケース

#### UC1: Tempo走の類似ワークアウト検索
**シナリオ**: 2025-10-13のTempo走（10km, 4:30/km）で過去の類似ワークアウトを検索

**期待結果**:
1. 同種のTempo/Threshold走が上位表示（類似度80%以上）
2. Base/Long Runは中程度の類似度（50-60%）
3. Anaerobic/Sprintは低類似度（30%以下）
4. 気温差と心拍数の関係が明示的に表示

#### UC2: 季節をまたいだパフォーマンス比較
**シナリオ**: 夏場（30°C）と冬場（10°C）の同ペースTempo走を比較

**期待結果**:
1. ペース・距離・トレーニングタイプから高類似度（90%以上）
2. 心拍数差が+18bpm（気温+20°C影響）と明示
3. パフォーマンス評価が気温差を考慮して行われる

#### UC3: トレーニングタイプフィルタリング
**シナリオ**: Threshold走のみで過去の類似ワークアウトを検索

**期待結果**:
1. 同じThreshold走が優先表示
2. 近縁トレーニング（Tempo）が次点
3. 異種トレーニング（Base/Recovery）は除外または低順位

---

## 設計

### アーキテクチャ

#### コンポーネント構成
```
WorkoutComparator (comparisons.py)
  ├── TrainingTypeSimilarity (新規追加)
  │   ├── 階層的類似度マトリックス
  │   └── get_similarity_score(type1, type2)
  ├── WeatherDataRetriever (新規追加)
  │   └── get_temperature(activity_id)
  └── 既存メソッド改善
      ├── find_similar_workouts() (重み調整)
      ├── _calculate_similarity_score() (式変更)
      ├── _generate_interpretation() (気温差追加)
      └── _get_target_activity() (トレーニングタイプ追加)
```

#### データフロー
```
1. Target Activity取得
   └→ DuckDB: activities, heart_rate_zones
   └→ ActivityClassifier: トレーニングタイプ分類

2. 類似Candidate検索
   └→ DuckDB: activities (pace/distance範囲)
   └→ ActivityClassifier: 各Candidateのトレーニングタイプ

3. 類似度計算
   ├→ ペース類似度: 45%
   ├→ 距離類似度: 35%
   └→ トレーニングタイプ類似度: 20%

4. 気温データ取得 (解釈用)
   └→ weather.json (GarminDBReader経由)

5. 解釈文生成
   └→ "ペース: -3.2秒/km速い, 心拍: +12bpm高い（気温+6°C影響）"
```

### データモデル

#### トレーニングタイプ階層的類似度マトリックス

**階層構造**:
```
Level 1: 強度カテゴリ
  - 超低強度: Recovery
  - 低強度: Base, Long Run
  - 中強度: Tempo, Threshold
  - 高強度: VO2 Max, Anaerobic, Interval
  - 超高強度: Sprint

Level 2: トレーニングタイプ
  - Recovery → Base (0.6)
  - Base ↔ Long Run (0.9)
  - Tempo ↔ Threshold (0.8)
  - VO2 Max ↔ Anaerobic (0.7)
  - Anaerobic ↔ Interval (0.8)
  - Interval ↔ Sprint (0.7)
```

**類似度マトリックス** (Python dict):
```python
TRAINING_TYPE_SIMILARITY = {
    ("recovery", "recovery"): 1.0,
    ("recovery", "base"): 0.6,
    ("recovery", "long_run"): 0.5,
    # 他タイプとは0.2-0.3

    ("base", "base"): 1.0,
    ("base", "long_run"): 0.9,
    ("base", "tempo"): 0.4,
    # 中強度以上は0.2-0.3

    ("long_run", "long_run"): 1.0,
    ("long_run", "base"): 0.9,

    ("tempo", "tempo"): 1.0,
    ("tempo", "threshold"): 0.8,
    ("tempo", "vo2_max"): 0.3,

    ("threshold", "threshold"): 1.0,
    ("threshold", "tempo"): 0.8,
    ("threshold", "vo2_max"): 0.4,

    ("vo2_max", "vo2_max"): 1.0,
    ("vo2_max", "anaerobic"): 0.7,
    ("vo2_max", "threshold"): 0.4,

    ("anaerobic", "anaerobic"): 1.0,
    ("anaerobic", "vo2_max"): 0.7,
    ("anaerobic", "interval"): 0.8,

    ("interval", "interval"): 1.0,
    ("interval", "anaerobic"): 0.8,
    ("interval", "sprint"): 0.7,

    ("sprint", "sprint"): 1.0,
    ("sprint", "interval"): 0.7,

    # Unknown/クロスカテゴリはデフォルト0.3
}

def get_similarity_score(type1: str, type2: str) -> float:
    """Get training type similarity score.

    Returns:
        1.0: Same type
        0.7-0.9: Same category (e.g., Tempo-Threshold)
        0.4-0.6: Adjacent category (e.g., Base-Tempo)
        0.2-0.3: Different category (e.g., Recovery-Sprint)
    """
    key = tuple(sorted([type1, type2]))
    return TRAINING_TYPE_SIMILARITY.get(key, 0.3)
```

#### 気温データ取得

**データソース**: `data/raw/weather/{date}.json`

**アクセス方法**:
```python
# GarminDBReaderにメソッド追加
def get_activity_temperature(activity_id: int) -> float | None:
    """Get temperature for activity from weather.json.

    Returns:
        Temperature in Celsius, or None if not available
    """
    activity = self.get_activity_by_id(activity_id)
    if not activity:
        return None

    date = activity["date"]
    weather_path = f"data/raw/weather/{date}.json"

    if not os.path.exists(weather_path):
        return None

    with open(weather_path) as f:
        weather_data = json.load(f)

    return weather_data.get("temperature")
```

### API/インターフェース設計

#### 改善後のWorkoutComparator API

```python
class WorkoutComparator:
    """Find and compare similar past workouts with training type awareness."""

    # 新規追加: トレーニングタイプ類似度マトリックス
    TRAINING_TYPE_SIMILARITY = {...}  # 上記定義

    def find_similar_workouts(
        self,
        activity_id: int,
        pace_tolerance: float = 0.1,
        distance_tolerance: float = 0.1,
        terrain_match: bool = False,
        activity_type_filter: str | None = None,
        date_range: tuple[str, str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Find similar workouts with training type similarity.

        Changes:
        - トレーニングタイプを類似度計算に追加（20%重み）
        - 心拊数は類似度計算から除外（参考表示のみ）
        - 気温差を解釈文に追加

        Returns:
            {
                "target_activity": {
                    ...
                    "training_type": str,  # 新規追加
                    "temperature": float | None,  # 新規追加
                },
                "similar_activities": [
                    {
                        ...
                        "training_type": str,  # 新規追加
                        "training_type_similarity": float,  # 新規追加
                        "temperature": float | None,  # 新規追加
                        "temperature_diff": float | None,  # 新規追加
                        "interpretation": str,  # 改善（気温差含む）
                    }
                ],
                ...
            }
        """
        pass

    def _calculate_similarity_score(
        self,
        target: dict[str, Any],
        candidate: dict[str, Any]
    ) -> float:
        """Calculate similarity with training type awareness.

        New formula:
        - Pace similarity: 45% (was 60%)
        - Distance similarity: 35% (was 40%)
        - Training type similarity: 20% (new)

        Returns:
            Similarity score (0-100%)
        """
        # ペース類似度
        pace_similarity = 1 - abs(candidate["avg_pace"] - target["avg_pace"]) / target["avg_pace"]

        # 距離類似度
        distance_similarity = 1 - abs(candidate["distance_km"] - target["distance_km"]) / target["distance_km"]

        # トレーニングタイプ類似度（新規）
        target_type = target.get("training_type", "unknown")
        candidate_type = candidate.get("training_type", "unknown")
        type_similarity = self._get_training_type_similarity(target_type, candidate_type)

        # 重み付き平均
        similarity = (
            pace_similarity * 0.45 +
            distance_similarity * 0.35 +
            type_similarity * 0.20
        ) * 100

        return float(max(0.0, min(100.0, similarity)))

    def _get_training_type_similarity(self, type1: str, type2: str) -> float:
        """Get training type similarity score from matrix.

        Args:
            type1: Training type 1 (e.g., "tempo")
            type2: Training type 2 (e.g., "threshold")

        Returns:
            Similarity score (0.0-1.0)
        """
        key = tuple(sorted([type1, type2]))
        return self.TRAINING_TYPE_SIMILARITY.get(key, 0.3)

    def _generate_interpretation(
        self,
        pace_diff: float,
        hr_diff: float,
        temp_diff: float | None
    ) -> str:
        """Generate interpretation with temperature context.

        Args:
            pace_diff: Pace difference in seconds/km
            hr_diff: Heart rate difference in bpm
            temp_diff: Temperature difference in Celsius (None if unavailable)

        Returns:
            Japanese interpretation string

        Examples:
            - "ペース: 3.2秒/km速い, 心拍: 12bpm高い（気温+6°C影響）"
            - "ペース: 2.1秒/km遅い, 心拍: 5bpm低い（気温-2°C影響）"
            - "ペース: 1.0秒/km速い, 心拍: 3bpm高い"  # 気温データなし
        """
        pace_text = f"{abs(pace_diff):.1f}秒/km{'速い' if pace_diff < 0 else '遅い'}"

        hr_text = f"{abs(hr_diff):.0f}bpm{'低い' if hr_diff < 0 else '高い'}"

        # 気温差の影響を追記
        if temp_diff is not None and abs(temp_diff) > 1.0:
            temp_context = f"（気温{'+' if temp_diff > 0 else ''}{temp_diff:.0f}°C影響）"
            hr_text += temp_context

        return f"ペース: {pace_text}, 心拍: {hr_text}"

    def _get_target_activity(self, activity_id: int) -> dict[str, Any] | None:
        """Get target activity with training type and temperature.

        Changes:
        - トレーニングタイプを追加（ActivityClassifier使用）
        - 気温データを追加（weather.json使用）

        Returns:
            Activity data with training_type and temperature fields
        """
        pass
```

---

## 実装フェーズ

### Phase 1: トレーニングタイプ類似度マトリックス実装
**目標**: 階層的類似度マトリックスの定義と取得関数の実装

**実装内容**:
1. `TRAINING_TYPE_SIMILARITY` 定数を追加（全組み合わせ定義）
2. `_get_training_type_similarity()` メソッド実装
3. 対称性・完全性のバリデーション関数追加

**テスト内容**:
- Unit: 全トレーニングタイプ組み合わせの類似度取得
- Unit: 対称性確認（(A,B) == (B,A)）
- Unit: 同一タイプは1.0、unknownは0.3デフォルト

**受け入れ基準**:
- [ ] 全9種類のトレーニングタイプ組み合わせ定義完了（81パターン）
- [ ] 類似度範囲: 同カテゴリ0.7-1.0, 隣接0.4-0.6, 異種0.2-0.3
- [ ] 対称性テスト全パス

### Phase 2: 気温データ取得機能実装
**目標**: weather.jsonから気温データを取得する機能の実装

**実装内容**:
1. `GarminDBReader.get_activity_temperature()` メソッド追加
2. `_get_target_activity()` で気温データ取得
3. Candidate活動の気温データ取得

**テスト内容**:
- Unit: 気温データが存在する場合の取得
- Unit: 気温データが存在しない場合（None返却）
- Integration: 複数活動の気温データ一括取得

**受け入れ基準**:
- [ ] weather.jsonから気温データ正常取得
- [ ] データ不在時もエラーなく処理
- [ ] 気温差計算が正確（±0.1°C以内）

### Phase 3: 類似度計算式改善
**目標**: 新しい重み配分とトレーニングタイプ考慮の実装

**実装内容**:
1. `_calculate_similarity_score()` のロジック変更
   - ペース: 60% → 45%
   - 距離: 40% → 35%
   - トレーニングタイプ: 0% → 20%
2. 心拊数を類似度計算から除外
3. トレーニングタイプ類似度の組み込み

**テスト内容**:
- Unit: 同タイプ同ペース = 100%類似度
- Unit: 同タイプペース差10% = 85-90%類似度
- Unit: 異タイプ同ペース = 70-80%類似度（タイプ類似度による）
- Integration: Tempo走でThreshold/Base/Anaerobicとの類似度比較

**受け入れ基準**:
- [ ] 類似度計算が新式に従っている
- [ ] トレーニングタイプの影響が20%以内
- [ ] テストケース全パス（10ケース以上）

### Phase 4: 解釈文生成改善
**目標**: 気温差を考慮した解釈文の生成

**実装内容**:
1. `_generate_interpretation()` に気温差パラメータ追加
2. 気温差±1°C以上の場合に影響表示
3. 日本語フォーマットの調整

**テスト内容**:
- Unit: 気温差+6°C, HR+12bpm → "心拍: 12bpm高い（気温+6°C影響）"
- Unit: 気温差-3°C, HR-5bpm → "心拍: 5bpm低い（気温-3°C影響）"
- Unit: 気温差±1°C未満 → 気温影響表示なし
- Unit: 気温データなし → 心拍数のみ表示

**受け入れ基準**:
- [ ] 気温差表示が正確
- [ ] 日本語表示が自然
- [ ] エッジケース（None, 0, 極値）正常処理

### Phase 5: エンドツーエンド統合テスト
**目標**: 実データでの動作確認と精度検証

**実装内容**:
1. 2025-10-13のTempo走でテスト実行
2. 上位結果のトレーニングタイプ確認
3. 気温差表示の確認
4. パフォーマンス測定（クエリ時間）

**テスト内容**:
- Integration: Tempo走検索でTempo/Threshold上位表示
- Integration: 季節間比較（夏/冬）で気温差正確表示
- Integration: activity_type_filter動作確認
- Performance: 10件検索 < 1秒

**受け入れ基準**:
- [ ] Tempo走でTempo/Thresholdが上位3件に含まれる
- [ ] 気温差±5°C以上で影響が明示される
- [ ] クエリ時間1秒以内
- [ ] エラー・警告なし

---

## テスト計画

### Unit Tests

#### 1. Training Type Similarity Matrix
```python
def test_training_type_similarity_same_type():
    """同一タイプは類似度1.0"""
    assert get_similarity("tempo", "tempo") == 1.0

def test_training_type_similarity_same_category():
    """同カテゴリは類似度0.7-0.9"""
    assert 0.7 <= get_similarity("tempo", "threshold") <= 0.9

def test_training_type_similarity_different_category():
    """異カテゴリは類似度0.2-0.4"""
    assert 0.2 <= get_similarity("recovery", "sprint") <= 0.4

def test_training_type_similarity_symmetry():
    """対称性確認"""
    assert get_similarity("tempo", "base") == get_similarity("base", "tempo")

def test_training_type_similarity_unknown():
    """unknownはデフォルト0.3"""
    assert get_similarity("unknown", "tempo") == 0.3
```

#### 2. Temperature Data Retrieval
```python
def test_get_activity_temperature_exists():
    """気温データ存在時の取得"""
    temp = db_reader.get_activity_temperature(12345678)
    assert isinstance(temp, float)
    assert -10 <= temp <= 40

def test_get_activity_temperature_not_exists():
    """気温データ不在時はNone"""
    temp = db_reader.get_activity_temperature(99999999)
    assert temp is None

def test_temperature_difference_calculation():
    """気温差計算の精度"""
    temp1 = 25.3
    temp2 = 19.7
    diff = temp1 - temp2
    assert abs(diff - 5.6) < 0.1
```

#### 3. Similarity Score Calculation
```python
def test_similarity_same_type_same_pace():
    """同タイプ同ペース = 100%"""
    target = {"avg_pace": 270, "distance_km": 10, "training_type": "tempo"}
    candidate = {"avg_pace": 270, "distance_km": 10, "training_type": "tempo"}
    assert calculate_similarity(target, candidate) == 100.0

def test_similarity_same_type_different_pace():
    """同タイプペース差10% = 85-90%"""
    target = {"avg_pace": 270, "distance_km": 10, "training_type": "tempo"}
    candidate = {"avg_pace": 297, "distance_km": 10, "training_type": "tempo"}
    score = calculate_similarity(target, candidate)
    assert 85 <= score <= 90

def test_similarity_different_type_same_pace():
    """異タイプ同ペース = 70-85%（タイプ類似度による）"""
    target = {"avg_pace": 270, "distance_km": 10, "training_type": "tempo"}
    candidate = {"avg_pace": 270, "distance_km": 10, "training_type": "threshold"}
    score = calculate_similarity(target, candidate)
    assert 70 <= score <= 85  # Tempo-Threshold類似度0.8

def test_similarity_clamp():
    """類似度は0-100%に制限"""
    target = {"avg_pace": 270, "distance_km": 10, "training_type": "tempo"}
    candidate = {"avg_pace": 500, "distance_km": 5, "training_type": "sprint"}
    score = calculate_similarity(target, candidate)
    assert 0 <= score <= 100
```

#### 4. Interpretation Generation
```python
def test_interpretation_with_temp_increase():
    """気温上昇時の解釈文"""
    result = generate_interpretation(-3.2, 12, 6.0)
    assert "3.2秒/km速い" in result
    assert "12bpm高い" in result
    assert "気温+6°C影響" in result

def test_interpretation_with_temp_decrease():
    """気温低下時の解釈文"""
    result = generate_interpretation(2.1, -5, -2.0)
    assert "2.1秒/km遅い" in result
    assert "5bpm低い" in result
    assert "気温-2°C影響" in result

def test_interpretation_no_temp():
    """気温データなし"""
    result = generate_interpretation(1.0, 3, None)
    assert "1.0秒/km速い" in result
    assert "3bpm高い" in result
    assert "気温" not in result

def test_interpretation_small_temp_diff():
    """気温差±1°C未満は影響表示なし"""
    result = generate_interpretation(0.5, 2, 0.8)
    assert "気温" not in result
```

### Integration Tests

#### 1. End-to-End Similarity Search
```python
def test_tempo_run_similarity_search():
    """Tempo走で類似検索（上位はTempo/Threshold）"""
    comparator = WorkoutComparator()
    result = comparator.find_similar_workouts(
        activity_id=17549685982,  # 2025-10-13 Tempo走
        limit=10
    )

    assert result["target_activity"]["training_type"] in ["tempo", "threshold"]

    # 上位3件にTempo/Thresholdが含まれる
    top_3_types = [a["training_type"] for a in result["similar_activities"][:3]]
    assert any(t in ["tempo", "threshold"] for t in top_3_types)

def test_seasonal_comparison():
    """季節間比較（気温差表示確認）"""
    comparator = WorkoutComparator()
    result = comparator.find_similar_workouts(
        activity_id=12345678,  # 夏のTempo走
        date_range=("2025-01-01", "2025-12-31"),
        limit=20
    )

    # 冬の類似走を抽出
    winter_activities = [
        a for a in result["similar_activities"]
        if a.get("temperature_diff") and a["temperature_diff"] < -10
    ]

    # 気温差が解釈文に反映されている
    for activity in winter_activities:
        assert "気温" in activity["interpretation"]

def test_activity_type_filter():
    """トレーニングタイプフィルタリング"""
    comparator = WorkoutComparator()
    result = comparator.find_similar_workouts(
        activity_id=17549685982,
        activity_type_filter="Tempo",
        limit=10
    )

    # 全結果がTempo/Threshold（類似タイプ）
    for activity in result["similar_activities"]:
        assert activity["training_type"] in ["tempo", "threshold"]
```

#### 2. Data Integration
```python
def test_training_type_classification_integration():
    """ActivityClassifierとの統合"""
    comparator = WorkoutComparator()
    result = comparator.find_similar_workouts(activity_id=17549685982)

    # 全活動にtraining_typeが付与されている
    assert result["target_activity"]["training_type"] is not None
    for activity in result["similar_activities"]:
        assert activity["training_type"] is not None

def test_weather_data_integration():
    """weather.jsonとの統合"""
    comparator = WorkoutComparator()
    result = comparator.find_similar_workouts(activity_id=17549685982)

    # 気温データが取得されている（存在する場合）
    if result["target_activity"]["temperature"] is not None:
        assert isinstance(result["target_activity"]["temperature"], float)
```

### Performance Tests

#### 1. Query Performance
```python
def test_similarity_search_performance():
    """類似検索のパフォーマンス（< 1秒）"""
    import time

    comparator = WorkoutComparator()
    start = time.time()
    result = comparator.find_similar_workouts(activity_id=17549685982, limit=10)
    elapsed = time.time() - start

    assert elapsed < 1.0
    assert len(result["similar_activities"]) <= 10

def test_large_date_range_performance():
    """広範囲日付検索のパフォーマンス（< 2秒）"""
    import time

    comparator = WorkoutComparator()
    start = time.time()
    result = comparator.find_similar_workouts(
        activity_id=17549685982,
        date_range=("2020-01-01", "2025-12-31"),
        limit=20
    )
    elapsed = time.time() - start

    assert elapsed < 2.0
```

#### 2. Memory Usage
```python
def test_memory_usage():
    """メモリ使用量確認（< 50MB増加）"""
    import tracemalloc

    tracemalloc.start()

    comparator = WorkoutComparator()
    result = comparator.find_similar_workouts(activity_id=17549685982, limit=50)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert peak < 50 * 1024 * 1024  # 50MB
```

---

## 受け入れ基準

### 機能要件
- [ ] トレーニングタイプ階層的類似度マトリックス実装完了（81パターン）
- [ ] 類似度計算式が新重み配分に従っている（45% / 35% / 20%）
- [ ] 気温データ取得機能実装完了（weather.json読み込み）
- [ ] 解釈文に気温差が反映されている（±1°C以上）
- [ ] 心拊数が類似度計算から除外されている

### テスト要件
- [ ] 全Unit Testsがパスする（20ケース以上）
- [ ] 全Integration Testsがパスする（5ケース以上）
- [ ] Performance Tests基準達成（< 1秒）
- [ ] コードカバレッジ85%以上

### 品質要件
- [ ] Pre-commit hooksがパスする（Black, Ruff, Mypy）
- [ ] 型ヒント完備（Mypy strict mode）
- [ ] Docstring完備（Google style）
- [ ] ログ出力適切（エラー時詳細情報）

### 実用性検証
- [ ] 2025-10-13 Tempo走で類似検索実行成功
- [ ] 上位3件にTempo/Thresholdが含まれる
- [ ] 季節間比較で気温差が正確表示（±0.5°C以内）
- [ ] Base/Long Run/Anaerobicは類似度が適切に低い（< 70%）

### ドキュメント
- [ ] CLAUDE.mdに変更内容反映
- [ ] API docstring更新（新パラメータ・戻り値）
- [ ] completion_report.md作成（実装完了後）

---

## リスクと対策

### リスク1: ActivityClassifierの精度不足
**リスク**: トレーニングタイプ分類が不正確で、類似度計算に悪影響

**対策**:
1. Phase 1でActivityClassifierのテストを実行し精度確認
2. 信頼度（confidence）低い場合は類似度計算での重みを下げる（20% → 10%）
3. 必要に応じてActivityClassifierの改善プロジェクトを別途起票

### リスク2: weather.jsonデータ欠損
**リスク**: 古い活動や一部活動で気温データが存在しない

**対策**:
1. 気温データNoneの場合は解釈文に含めない（必須ではない）
2. ログに警告出力（デバッグ用）
3. 気温データ取得率をメトリクス化（モニタリング用）

### リスク3: 類似度計算の重み調整
**リスク**: 45% / 35% / 20%の重み配分が最適でない可能性

**対策**:
1. Phase 5で複数パターン（Tempo/Base/Interval）で検証
2. ユーザーフィードバック収集
3. 必要に応じて重みを微調整（40% / 30% / 30%など）

### リスク4: パフォーマンス劣化
**リスク**: ActivityClassifier呼び出しでクエリ時間増加

**対策**:
1. ActivityClassifier結果をDuckDBにキャッシュ（future work）
2. バッチ分類でN+1問題回避
3. Performance Testで閾値監視（< 1秒）

---

## 今後の拡張案

### Future Work 1: トレーニングタイプキャッシュ
ActivityClassifier結果をDuckDBに保存し、再計算を回避。

### Future Work 2: 地形マッチング強化
`terrain_match=True`時に標高差・累積獲得標高も考慮。

### Future Work 3: ユーザー設定可能な重み
類似度計算の重み配分をユーザーが調整可能に（API拡張）。

### Future Work 4: 気温正規化
気温による心拍数影響を数式化し、正規化した心拍数で比較。

---

## 参考資料

### 既存実装
- `tools/rag/queries/comparisons.py`: WorkoutComparator
- `tools/rag/utils/activity_classifier.py`: ActivityClassifier
- `tools/database/db_reader.py`: GarminDBReader

### 関連プロジェクト
- `docs/project/2025-10-13_rag_wellness_integration/`: wellness_data.jsonとの統合
- `docs/project/_archived/2025-10-08_performance_trends/`: パフォーマンストレンド分析

### トレーニングタイプ定義
- Recovery: HR Zone 1 >= 70%
- Base: HR Zone 1+2 >= 60%
- Long Run: distance > 15km and Base条件
- Tempo: 中強度走行（Zone 3-4主体）
- Threshold: HR Zone 4 >= 30%
- VO2 Max: 高強度走行
- Anaerobic: power > 300W or HR Zone 5 >= 50%
- Interval: HR Zone 5 >= 20%
- Sprint: 超高強度走行
