# 計画: Power Efficiency Evaluation System Integration

## プロジェクト情報
- **プロジェクト名**: `power_efficiency_evaluation`
- **作成日**: `2025-10-28`
- **ステータス**: 計画中
- **GitHub Issue**: [#43](https://github.com/yamakii/garmin-performance-analysis/issues/43)
- **優先度**: High
- **推定工数**:
  - Phase 0: 1-2時間
  - Phase 1: 6-8時間
  - Phase 2: 2-3時間
  - **Total**: 9-13時間 (Phase 3除く)

---

## 要件定義

### 目的
VO/パワー比を新しいフォーム効率指標として統合し、「地面反発を推進力に変換する効率」を定量的に評価できるようにする。これにより、フォーム改善の新しい軸を提供し、パワーデータを活用した包括的なランニング効率分析を実現する。

### 解決する問題

**Current Issue:**
- 現在のフォーム評価システムは速度ベースでGCT/VO/VRを評価
- 実データ分析により、VO増加は必ずしも悪くなく「地面反発を効率的に利用」の指標であることが判明
- パワーメーターデータ（2025年のみ利用可能）が活用されていない
- VO増加時にパワー効率が良い場合と悪い場合を区別できない

**Impact:**
- フォーム評価が不完全（VO増加=悪、という単純評価）
- パワー効率の良いVO増加を見逃す（例: 地面反発を利用した推進力向上）
- パワーメーターを持つランナーへの価値提供が不足
- 実データに基づく洞察（VO vs パワー相関）が活用されていない

**Example:**
```python
# 現在: VO増加は一律に悪いとみなされる
VO = 12.0 cm (expected: 10.5 cm) → "★★☆☆☆ 改善必要"

# 提案: パワー効率で区別
Case A: VO=12.0cm, Power=250W → VO/Power=0.048 (効率悪い) → "★★☆☆☆"
Case B: VO=12.0cm, Power=220W → VO/Power=0.055 (効率良い) → "★★★★☆"
# Case Bは地面反発を効率的に使っている = 推進力向上
```

### ユースケース

1. **パワー効率による新しいフォーム評価軸**
   - ユーザー: パワーメーター搭載デバイスを持つランナー（2025年データ）
   - システム: VO/パワー比を計算し、期待値と比較
   - 結果: 「VO増加しているがパワー効率良好」など、より洞察的な評価

2. **長期トレンド分析**
   - ユーザー: 2ヶ月分のトレーニングデータ蓄積
   - システム: パワー効率のbaseline（速度別期待値）を訓練
   - 結果: 個人の成長曲線に基づく評価（集団平均ではなく）

3. **後方互換性**
   - ユーザー: パワーデータなしのアクティビティ（2021年など）
   - システム: パワー効率評価をスキップ、従来の評価のみ実施
   - 結果: エラーなく動作、既存レポート生成可能

4. **MCP経由のデータアクセス**
   - エージェント: efficiency-section-analyst
   - MCP Tool: `get_power_efficiency_analysis(activity_id)` 呼び出し
   - 結果: パワー効率データを含むform_evaluations取得

5. **レポート統合**
   - システム: レポート生成時にパワー効率セクション追加
   - ユーザー: 「パワー効率」として新セクション表示
   - 結果: GCT/VO/VR評価と並列でパワー効率評価を確認

---

## 設計

### アーキテクチャ

**Current State:**
```
Raw Data (API) → DuckDB (splits.power) → (unused)
                        ↓
                  GCT/VO/VR Baseline Training (速度ベース)
                        ↓
                  form_baseline_history (gct, vo, vr)
                        ↓
                  form_evaluations (パワー効率なし)
                        ↓
                  efficiency-section-analyst → Report
```

**Target State (Phase 1):**
```
Raw Data (API) → DuckDB
                   ├─ splits.power (1km laps)
                   ├─ body_composition.body_mass_kg
                   └─ activities.body_mass_kg (NEW)
                        ↓
                  W/kg Normalization (power_w / body_mass_kg)
                        ↓
                  Power Efficiency Baseline Training
                  Model: speed = a + b * power_wkg
                        ↓
                  form_baseline_history (NEW: metric='power')
                        ↓
                  Form Evaluation (activity単位)
                        ↓
                  form_evaluations (パワー効率列追加)
                        ↓
                  MCP Tools (get_form_evaluations)
                        ↓
                  efficiency-section-analyst → Report (パワー効率セクション追加)
```

**Components:**

1. **Phase 0: 準備（1-2時間）**
   - form_baselinesテーブル削除（0レコード、未使用）
   - 依存コード削除
   - activitiesテーブルにbody_mass_kg列追加

2. **Phase 1: 基本実装（6-8時間）**
   - Baseline Training: `speed = a + b * power_wkg`モデル
   - 時間窓: 1km splits使用（既存構造活用）
   - スコアリング: 個別星評価のみ（既存システムと並列）
   - モード: 単一評価基準（全アクティビティ共通）

3. **Phase 2: 統合スコア（2-3時間）**
   - 100点満点統合スコア導入
   - トレーニングモード別重み付け（hr_efficiency.training_type活用）

4. **Phase 3: 高精度化（将来拡張）**
   - 60-120s時間窓実装（time_series_metricsから生成）
   - モード別重み最適化

**Design Decisions:**

**Decision 1: 専門家設計（Option B）ベース + 段階的実装**
- **採用理由**: W/kg正規化、因果関係明確なモデル、統合スコアの先進性
- **修正点**: 既存システム（1km splits, form_baseline_history）を活用してコスト削減

**Decision 2: 時間窓 - Phase分割アプローチ**
- **Phase 1**: 1km splits使用（240-420秒窓、実装コスト最小）
- **Phase 3**: 60-120s窓実装（time_series_metricsから新規作成）
- **理由**: 早期リリース優先、将来の精度向上も担保

**Decision 3: W/kg正規化 - activitiesテーブル拡張**
- **Schema**: `ALTER TABLE activities ADD COLUMN body_mass_kg DOUBLE;`
- **理由**:
  - 1アクティビティ1体重が自然
  - splitsへのデータ重複回避
  - body_compositionからJOINで取得容易

**Decision 4: モデル方向 - 専門家設計採用**
- **Model**: `speed_mps = a + b * power_wkg`
- **理由**:
  - 因果関係明確（パワー→速度）
  - W/kg正規化と整合
  - efficiency_index = speed / power_wkg が直感的

**Decision 5: スコアリング - 段階的実装**
- **Phase 1**: 個別星評価（power_efficiency_rating = "★★★★☆"）
- **Phase 2**: 統合100点スコア + モード別重み
- **理由**: ベースライン確立後に最適化

**Decision 6: form_baselines削除**
- **Action**: `DROP TABLE form_baselines;`
- **理由**: 0レコード、未使用、form_baseline_historyが実運用

### データモデル

**Phase 0: 準備（テーブル削除 + 拡張）**

```sql
-- 1. 未使用テーブル削除
DROP TABLE IF EXISTS form_baselines;  -- 0レコード、未使用

-- 2. activitiesテーブル拡張（体重データ追加）
ALTER TABLE activities ADD COLUMN IF NOT EXISTS body_mass_kg DOUBLE;

-- 3. body_compositionから体重データをpopulate
UPDATE activities a
SET body_mass_kg = (
  SELECT bc.body_mass_kg
  FROM body_composition bc
  WHERE bc.activity_date <= a.activity_date
  ORDER BY bc.activity_date DESC
  LIMIT 1
);
```

**Phase 1: form_baseline_history拡張（パワーモデル係数）**

```sql
-- 既存テーブルにパワーモデル用列を追加
ALTER TABLE form_baseline_history ADD COLUMN IF NOT EXISTS power_a DOUBLE;
ALTER TABLE form_baseline_history ADD COLUMN IF NOT EXISTS power_b DOUBLE;
ALTER TABLE form_baseline_history ADD COLUMN IF NOT EXISTS power_rmse DOUBLE;

-- 新しい行の挿入例（metric='power'）
INSERT INTO form_baseline_history (
    user_id, condition_group, metric,
    coef_alpha, coef_d, coef_a, coef_b,  -- GCT/VO/VR用（NULL）
    power_a, power_b, power_rmse,        -- パワーモデル用
    period_start, period_end, n_samples
) VALUES (
    'default', 'flat_road', 'power',
    NULL, NULL, NULL, NULL,  -- GCT/VO/VR用は未使用
    2.5, 0.8, 0.12,          -- Model: speed = 2.5 + 0.8 * power_wkg
    '2025-09-01', '2025-10-31', 357
);
```

**モデル定義:**
```
speed_mps = power_a + power_b * power_wkg

Where:
  - speed_mps: 速度 (m/s)
  - power_wkg: 体重補正済みパワー (W/kg) = power_w / body_mass_kg
  - power_a: 切片（ベース速度）
  - power_b: 傾き（パワー感度、正の値）

Interpretation:
  - power_b が大きい: パワー増加に対して速度が増えやすい（効率的）
  - power_a が大きい: 低パワーでも速い（ベース効率が高い）

Efficiency Metrics:
  - efficiency_index = speed / power_wkg (m/s per W/kg)
  - cost_per_speed = power_wkg / speed (W/kg per m/s)
```

**form_evaluations 拡張:**

```sql
-- Phase 1: 基本パワー効率評価
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_avg_w DOUBLE;
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_wkg DOUBLE;
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS speed_actual_mps DOUBLE;
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS speed_expected_mps DOUBLE;
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_efficiency_score DOUBLE;
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_efficiency_rating VARCHAR;
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_efficiency_needs_improvement BOOLEAN;

-- Phase 2: 統合スコア
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS integrated_score DOUBLE;
ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS training_mode VARCHAR;
```

**Column Definitions (Phase 1):**
- `power_avg_w`: 平均パワー（W）、splits.powerから計算
- `power_wkg`: 体重補正済みパワー（W/kg）= power_avg_w / body_mass_kg
- `speed_actual_mps`: 実測速度（m/s）、splitsから計算
- `speed_expected_mps`: baseline予測速度（m/s）= power_a + power_b * power_wkg
- `power_efficiency_score`: 乖離率 = (actual - expected) / expected
- `power_efficiency_rating`: 星評価（★☆☆☆☆～★★★★★）
  - score < -0.05: ★★★★★ (期待より5%以上速い = 非常に効率的)
  - score < -0.02: ★★★★☆ (期待より2-5%速い = 効率的)
  - -0.02 <= score <= 0.02: ★★★☆☆ (期待通り = 標準)
  - score > 0.02: ★★☆☆☆ (期待より2-5%遅い = やや非効率)
  - score > 0.05: ★☆☆☆☆ (期待より5%以上遅い = 非効率)
- `power_efficiency_needs_improvement`: 改善必要フラグ（score > 0.05）

**Column Definitions (Phase 2):**
- `integrated_score`: 統合100点スコア
  ```python
  integrated_score = 100 - (
    w_gct * penalty_gct +
    w_vo * penalty_vo +
    w_vr * penalty_vr +
    w_power * penalty_power
  )
  ```
- `training_mode`: トレーニングモード（hr_efficiency.training_typeから取得）
  - "interval_sprint": w_power=0.40 (パワー効率重視)
  - "tempo_threshold": w_power=0.35
  - "low_moderate": w_power=0.20 (パワー効率軽視)

**データフロー例:**
```python
# Phase 1実装時
1. splitsテーブルから取得:
   - power_avg = 250W
   - speed_avg = 3.5 m/s

2. activitiesテーブルから体重取得:
   - body_mass_kg = 65 kg

3. W/kg計算:
   - power_wkg = 250 / 65 = 3.85 W/kg

4. baseline予測（form_baseline_historyから取得）:
   - power_a = 2.5, power_b = 0.8
   - speed_expected = 2.5 + 0.8 * 3.85 = 5.58 m/s

5. 評価:
   - speed_actual = 3.5 m/s
   - score = (3.5 - 5.58) / 5.58 = -0.373 (期待より37%遅い)
   - rating = "★☆☆☆☆" (非効率)
   - needs_improvement = True
```

### API/インターフェース設計

**1. Baseline Training (tools/form_baseline/trainer.py)**

```python
class PowerEfficiencyModel:
    """速度をW/kgで回帰するモデル（専門家設計）。

    Model: speed = a + b * power_wkg
    - speed: 速度 (m/s)
    - power_wkg: 体重補正済みパワー (W/kg)

    Interpretation:
    - b > 0: パワーが増えれば速度も増える（正の相関）
    - a が大きい: ベース速度が高い（低パワーでも速い = 効率的）
    """

    def __init__(self):
        self.power_a: float = 0.0  # 切片
        self.power_b: float = 0.0  # 傾き
        self.power_rmse: float = 0.0

    def fit(self, power_wkg_values: list[float], speeds: list[float]) -> None:
        """線形回帰で係数を学習。

        Args:
            power_wkg_values: W/kg値のリスト
            speeds: 対応する速度 (m/s) のリスト
        """
        from scipy.stats import linregress

        slope, intercept, r_value, p_value, std_err = linregress(
            power_wkg_values, speeds
        )

        self.power_b = slope
        self.power_a = intercept

        # RMSE計算
        predictions = [self.predict(p) for p in power_wkg_values]
        residuals = [(actual - pred) ** 2 for actual, pred in zip(speeds, predictions)]
        self.power_rmse = (sum(residuals) / len(residuals)) ** 0.5

    def predict(self, power_wkg: float) -> float:
        """W/kgから速度を予測。

        Args:
            power_wkg: 体重補正済みパワー (W/kg)

        Returns:
            予測速度 (m/s)
        """
        return self.power_a + self.power_b * power_wkg


def train_power_efficiency_baseline(
    user_id: str = "default",
    condition_group: str = "flat_road",
    end_date: str = None,
    window_months: int = 2,
    db_path: str = None,
) -> dict:
    """パワー効率のbaselineを訓練。

    Args:
        user_id: ユーザーID
        condition_group: 条件グループ（'flat_road' など）
        end_date: 終了日（YYYY-MM-DD）、Noneなら最新アクティビティ
        window_months: 学習ウィンドウ（月）
        db_path: DuckDB パス

    Returns:
        {
            'power_a': float,        # 切片
            'power_b': float,        # 傾き
            'power_rmse': float,     # RMSE
            'n_samples': int,
            'period_start': str,
            'period_end': str
        }

    Implementation:
        1. DuckDB から splits データ取得
           - splits.average_speed (m/s)
           - splits.power (W)
           - activities.body_mass_kg
        2. 条件フィルタ（condition_group、期間）
        3. W/kg計算: power_wkg = power / body_mass_kg
        4. PowerEfficiencyModel で回帰
        5. form_baseline_history に挿入（metric='power'）
    """
    pass
```

**2. Evaluation (tools/form_baseline/evaluator.py)**

```python
def evaluate_power_efficiency(
    activity_id: int,
    activity_date: str,
    user_id: str = "default",
    condition_group: str = "flat_road",
    db_path: str = None,
) -> dict:
    """アクティビティのパワー効率を評価。

    Args:
        activity_id: アクティビティID
        activity_date: アクティビティ日付（YYYY-MM-DD）
        user_id: ユーザーID
        condition_group: 条件グループ
        db_path: DuckDB パス

    Returns:
        {
            'power_avg_w': float,              # 平均パワー (W)
            'power_wkg': float,                # W/kg
            'speed_actual_mps': float,         # 実測速度 (m/s)
            'speed_expected_mps': float,       # 予測速度 (m/s)
            'power_efficiency_score': float,   # 乖離率
            'power_efficiency_rating': str,    # ★★★☆☆
            'power_efficiency_needs_improvement': bool,
            'efficiency_index': float,         # speed / power_wkg
            'cost_per_speed': float            # power_wkg / speed
        }

        パワーデータがない場合: None を返す（エラーにしない、後方互換性）

    Implementation:
        1. form_baseline_historyからbaseline取得（metric='power', activity_date時点）
        2. splitsから平均パワーと速度を取得
        3. パワーがNoneなら None を返す（2021年などパワーなし）
        4. activitiesから体重を取得
        5. W/kg計算: power_wkg = power_avg / body_mass_kg
        6. 予測速度計算: speed_expected = power_a + power_b * power_wkg
        7. 乖離率計算: score = (speed_actual - speed_expected) / speed_expected
        8. 星評価付与（_calculate_power_efficiency_rating）
        9. efficiency_index, cost_per_speed計算
        10. form_evaluationsに挿入
    """
    pass


def _calculate_power_efficiency_rating(score: float) -> str:
    """スコアから星評価を計算。"""
    if score <= -0.05:
        return "★★★★★"
    elif score <= -0.02:
        return "★★★★☆"
    elif score <= 0.02:
        return "★★★☆☆"
    elif score <= 0.05:
        return "★★☆☆☆"
    else:
        return "★☆☆☆☆"
```

**3. Database Operations (tools/database/writer.py)**

```python
class GarminDBWriter:
    # ... existing methods ...

    def insert_power_efficiency_baseline(
        self,
        user_id: str,
        condition_group: str,
        coef_a: float,
        coef_b: float,
        rmse: float,
        period_start: str,
        period_end: str,
        n_samples: int,
    ) -> None:
        """パワー効率baselineをform_baseline_historyに挿入。

        metric='vo_per_power' として挿入。
        既存GCT/VO/VRとは別行として保存。
        """
        pass

    def update_form_evaluations_with_power(
        self,
        activity_id: int,
        power_actual: float,
        vo_per_power_actual: float,
        vo_per_power_expected: float,
        power_efficiency_score: float,
        power_efficiency_rating: str,
        power_efficiency_needs_improvement: bool,
    ) -> None:
        """form_evaluationsにパワー効率データを追加。

        INSERT ON CONFLICT DO UPDATE で既存行に列追加。
        """
        pass
```

**4. MCP Tools (servers/garmin_db_server.py)**

```python
@mcp_server.tool()
async def get_power_efficiency_analysis(activity_id: int) -> dict:
    """パワー効率分析データを取得。

    Args:
        activity_id: アクティビティID

    Returns:
        {
            'activity_id': int,
            'power_actual': float | None,
            'vo_per_power_actual': float | None,
            'vo_per_power_expected': float | None,
            'power_efficiency_score': float | None,
            'power_efficiency_rating': str | None,
            'power_efficiency_needs_improvement': bool | None
        }

        パワーデータがない場合: 各値が None
    """
    # form_evaluations からパワー効率列を取得
    pass


# 既存ツール拡張
@mcp_server.tool()
async def get_form_evaluations(activity_id: int) -> dict:
    """フォーム評価を取得（パワー効率データ含む）。

    Returns:
        {
            'gct_actual': float,
            'gct_expected': float,
            # ... 既存フィールド ...
            'power_actual': float | None,           # NEW
            'vo_per_power_actual': float | None,    # NEW
            'vo_per_power_expected': float | None,  # NEW
            'power_efficiency_score': float | None, # NEW
            'power_efficiency_rating': str | None,  # NEW
            'power_efficiency_needs_improvement': bool | None  # NEW
        }
    """
    # 既存クエリにパワー効率列を追加
    pass
```

**5. Agent Integration (.claude/agents/efficiency-section-analyst.md)**

```markdown
## データ取得

1. **フォーム効率データ取得（パワー効率含む）:**
   - MCP Tool: `mcp__garmin-db__get_form_evaluations(activity_id)`
   - 取得データ: GCT/VO/VR評価 + パワー効率評価

## 分析フロー

### 3. パワー効率評価（新規）

**条件:** power_actualがNoneでない場合のみ実施

**評価ロジック:**
- VO/パワー比: 小さいほど効率的（同じパワーで少ないVO）
- 評価: power_efficiency_rating（★☆☆☆☆～★★★★★）
- 改善判定: power_efficiency_needs_improvement

**レポート出力:**
```markdown
### パワー効率

**評価:** {power_efficiency_rating}

- 実測VO/パワー比: {vo_per_power_actual:.3f} cm/W
- 期待値: {vo_per_power_expected:.3f} cm/W
- 乖離率: {power_efficiency_score:+.1%}

{評価コメント}
```

**評価コメント例:**
- ★★★★★: "素晴らしいパワー効率です。地面反発を推進力に効率的に変換できています。"
- ★★★☆☆: "標準的なパワー効率です。"
- ★☆☆☆☆: "パワー効率が低下しています。無駄な上下動が多い可能性があります。"
```

**6. Report Template (tools/reporting/templates/individual_report.md.j2)**

```jinja2
{# 既存: GCT/VO/VR評価 #}

{% if efficiency_section.power_efficiency_rating %}
## パワー効率

**評価:** {{ efficiency_section.power_efficiency_rating }}

- 実測VO/パワー比: {{ efficiency_section.vo_per_power_actual | round(3) }} cm/W
- 期待値: {{ efficiency_section.vo_per_power_expected | round(3) }} cm/W
- 乖離率: {{ efficiency_section.power_efficiency_score | format_percent }}

{{ efficiency_section.power_efficiency_comment }}
{% endif %}
```

---

## 実装フェーズ

### Phase 0: 準備（1-2時間）

**目的:** 未使用テーブル削除 + 体重データ追加

**Branch:** `feature/power-efficiency-prep`

**Tasks:**

1. **form_baselinesテーブル削除**
   ```python
   # Test
   def test_form_baselines_table_not_exists():
       """form_baselinesテーブルが存在しない。"""
       tables = conn.execute("SHOW TABLES").fetchall()
       table_names = [row[0] for row in tables]
       assert "form_baselines" not in table_names
   ```

   ```python
   # Implementation
   conn.execute("DROP TABLE IF EXISTS form_baselines")
   ```

2. **依存コード削除**
   ```bash
   # form_baselinesへの参照を検索
   grep -r "form_baselines" tools/ servers/ --include="*.py"

   # 見つかった場合、削除または form_baseline_history に修正
   ```

3. **activitiesテーブルにbody_mass_kg追加**
   ```python
   # Test
   def test_activities_has_body_mass_column():
       """activitiesテーブルにbody_mass_kg列が存在する。"""
       schema = conn.execute("PRAGMA table_info(activities)").fetchall()
       column_names = [row[1] for row in schema]
       assert "body_mass_kg" in column_names
   ```

   ```python
   # Migration
   conn.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS body_mass_kg DOUBLE")

   # body_compositionから体重データをpopulate
   conn.execute("""
       UPDATE activities a
       SET body_mass_kg = (
         SELECT bc.body_mass_kg
         FROM body_composition bc
         WHERE bc.activity_date <= a.activity_date
         ORDER BY bc.activity_date DESC
         LIMIT 1
       )
   """)
   ```

**Acceptance Criteria:**
- [ ] form_baselinesテーブルが削除されている
- [ ] form_baselinesへの参照がコードベースに存在しない
- [ ] activitiesテーブルにbody_mass_kg列が追加されている
- [ ] 全activitiesレコードにbody_mass_kgが設定されている（NULL許容）

---

### Phase 1: 基本実装（6-8時間）

**目的:** speed = a + b * power_wkg モデルの実装

**Branch:** `feature/power-efficiency-phase1`

**Tasks:**

#### 1-1. Database Schema Migration

```python
# Test
def test_form_baseline_history_has_power_columns():
    """form_baseline_historyにパワーモデル列が存在する。"""
    schema = conn.execute("PRAGMA table_info(form_baseline_history)").fetchall()
    column_names = [row[1] for row in schema]
    assert "power_a" in column_names
    assert "power_b" in column_names
    assert "power_rmse" in column_names

def test_form_evaluations_has_power_columns():
    """form_evaluationsにパワー効率列が存在する。"""
    schema = conn.execute("PRAGMA table_info(form_evaluations)").fetchall()
    column_names = [row[1] for row in schema]
    assert "power_avg_w" in column_names
    assert "power_wkg" in column_names
    assert "speed_actual_mps" in column_names
    assert "speed_expected_mps" in column_names
    assert "power_efficiency_score" in column_names
    assert "power_efficiency_rating" in column_names
```

```python
# Migration
conn.execute("ALTER TABLE form_baseline_history ADD COLUMN IF NOT EXISTS power_a DOUBLE")
conn.execute("ALTER TABLE form_baseline_history ADD COLUMN IF NOT EXISTS power_b DOUBLE")
conn.execute("ALTER TABLE form_baseline_history ADD COLUMN IF NOT EXISTS power_rmse DOUBLE")

conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_avg_w DOUBLE")
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_wkg DOUBLE")
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS speed_actual_mps DOUBLE")
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS speed_expected_mps DOUBLE")
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_efficiency_score DOUBLE")
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_efficiency_rating VARCHAR")
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS power_efficiency_needs_improvement BOOLEAN")
```

#### 1-2. PowerEfficiencyModel Implementation

```python
# Test
def test_power_efficiency_model_fit():
    """W/kgから速度への線形回帰。"""
    model = PowerEfficiencyModel()
    power_wkg_values = [3.5, 4.0, 4.5, 5.0]  # W/kg
    speeds = [2.8, 3.2, 3.6, 4.0]  # m/s (正の相関)

    model.fit(power_wkg_values, speeds)

    assert model.power_b > 0  # パワー増加で速度増加
    assert model.power_a > 0  # ベース速度
    assert model.power_rmse >= 0

def test_power_efficiency_model_predict():
    """予測速度計算。"""
    model = PowerEfficiencyModel()
    model.power_a = 1.0
    model.power_b = 0.6

    predicted = model.predict(4.0)  # power_wkg = 4.0
    assert abs(predicted - 3.4) < 0.001  # 1.0 + 0.6 * 4.0 = 3.4
```

#### 1-3. Baseline Training

```python
# Test
def test_train_power_efficiency_baseline(tmp_db_path):
    """2ヶ月窓でパワー効率baselineを訓練。"""
    result = train_power_efficiency_baseline(
        end_date="2025-10-28",
        window_months=2,
        db_path=tmp_db_path
    )

    assert result['power_a'] > 0
    assert result['power_b'] > 0  # パワー増加で速度増加
    assert result['n_samples'] > 0
    assert 'period_start' in result
    assert 'period_end' in result

def test_train_power_efficiency_baseline_no_power_data(tmp_db_path):
    """パワーデータなし（2021年など）の場合、エラーにしない。"""
    result = train_power_efficiency_baseline(
        end_date="2021-06-01",
        db_path=tmp_db_path
    )
    assert result is None  # パワーデータなしでもエラーなし
```

#### 1-4. Evaluation

```python
# Test
def test_evaluate_power_efficiency(tmp_db_path):
    """パワー効率を評価し、form_evaluationsに挿入。"""
    result = evaluate_power_efficiency(
        activity_id=12345,
        activity_date="2025-10-28",
        db_path=tmp_db_path
    )

    assert result['power_avg_w'] > 0
    assert result['power_wkg'] > 0
    assert result['speed_actual_mps'] > 0
    assert result['speed_expected_mps'] > 0
    assert -1.0 < result['power_efficiency_score'] < 1.0
    assert result['power_efficiency_rating'] in ["★☆☆☆☆", "★★☆☆☆", "★★★☆☆", "★★★★☆", "★★★★★"]
    assert isinstance(result['power_efficiency_needs_improvement'], bool)

def test_evaluate_power_efficiency_no_power(tmp_db_path):
    """パワーデータなしの場合、Noneを返す。"""
    result = evaluate_power_efficiency(
        activity_id=67890,
        activity_date="2021-06-01",
        db_path=tmp_db_path
    )
    assert result is None  # エラーなし、後方互換性

def test_power_efficiency_rating_calculation():
    """スコアから星評価を計算。"""
    assert _calculate_power_efficiency_rating(-0.06) == "★★★★★"
    assert _calculate_power_efficiency_rating(-0.03) == "★★★★☆"
    assert _calculate_power_efficiency_rating(0.0) == "★★★☆☆"
    assert _calculate_power_efficiency_rating(0.03) == "★★☆☆☆"
    assert _calculate_power_efficiency_rating(0.06) == "★☆☆☆☆"
```

#### 1-5. MCP Tool Integration

```python
# servers/garmin_db_server.py に追加
elif name == "get_power_efficiency_analysis":
    activity_id = arguments["activity_id"]
    result = db_reader.get_power_efficiency_analysis(activity_id)
    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
```

**Acceptance Criteria:**
- [ ] PowerEfficiencyModel が speed = a + b * power_wkg を学習・予測できる
- [ ] train_power_efficiency_baseline が動作し、form_baseline_historyに挿入される
- [ ] evaluate_power_efficiency が動作し、form_evaluationsに挿入される
- [ ] パワーデータなしの場合、エラーなく None を返す（後方互換性）
- [ ] MCP tool get_power_efficiency_analysis が動作する
- [ ] 全Unit tests pass (pytest -m unit)
- [ ] 全Integration tests pass (pytest -m integration)

---

### Phase 2: 統合スコア + モード別重み（2-3時間）

**目的:** 100点満点スコア + トレーニングモード別重み付け

**Branch:** `feature/power-efficiency-phase2`

**Tasks:**

#### 2-1. Schema Extension

```python
# Test
def test_form_evaluations_has_integrated_score_columns():
    schema = conn.execute("PRAGMA table_info(form_evaluations)").fetchall()
    column_names = [row[1] for row in schema]
    assert "integrated_score" in column_names
    assert "training_mode" in column_names
```

```python
# Migration
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS integrated_score DOUBLE")
conn.execute("ALTER TABLE form_evaluations ADD COLUMN IF NOT EXISTS training_mode VARCHAR")
```

#### 2-2. Integrated Score Calculation

```python
# Test
def test_calculate_integrated_score():
    """統合スコア計算（100点満点、モード別重み）。"""
    penalties = {
        'gct': 0.1,  # 10% 悪化
        'vo': 0.05,  # 5% 悪化
        'vr': -0.02,  # 2% 改善
        'power': 0.08  # 8% 悪化
    }

    # interval_sprint mode: w_power=0.40
    score = calculate_integrated_score(penalties, training_mode="interval_sprint")
    # 100 - (0.25*0.1 + 0.25*0.05 + 0.25*0.02 + 0.40*0.08) = 100 - 0.0695 = 93.05
    assert 92.0 < score < 94.0

    # low_moderate mode: w_power=0.20
    score = calculate_integrated_score(penalties, training_mode="low_moderate")
    assert 94.0 < score < 96.0  # パワーペナルティ軽減
```

#### 2-3. Training Mode Detection

```python
# Implementation
def get_training_mode(activity_id: int) -> str:
    """hr_efficiency.training_typeからトレーニングモードを取得。"""
    hr_data = db_reader.get_hr_efficiency_analysis(activity_id)
    return hr_data.get("training_type", "low_moderate")

# Mode weights
TRAINING_MODE_WEIGHTS = {
    "interval_sprint": {"w_gct": 0.30, "w_vo": 0.15, "w_vr": 0.15, "w_power": 0.40},
    "tempo_threshold": {"w_gct": 0.25, "w_vo": 0.20, "w_vr": 0.20, "w_power": 0.35},
    "low_moderate": {"w_gct": 0.30, "w_vo": 0.25, "w_vr": 0.25, "w_power": 0.20},
}
```

**Acceptance Criteria:**
- [ ] integrated_score列が追加されている
- [ ] calculate_integrated_score がモード別重みで動作する
- [ ] training_modeがhr_efficiencyから取得される
- [ ] 全tests pass

---

### Phase 3: 高精度化（将来拡張）

**目的:** 60-120s時間窓 + モード別重み最適化

**Status:** 計画のみ（Phase 1-2完了後に実装判断）

**Tasks:**

1. **60-120s時間窓テーブル作成**
   - time_series_metricsから60-120s windowsを生成
   - power_wkg, speed, form metrics を集約

2. **Window-based Baseline Training**
   - 1km splitsの代わりに60-120s windowsで学習
   - より細かい変化を捉える

3. **モード別重み最適化**
   - Phase 1-2で蓄積したデータを分析
   - 最適な重み係数を統計的に決定

**Acceptance Criteria:**
- TBD（Phase 1-2完了後に決定
       assert _calculate_power_efficiency_rating(-0.03) == "★★★★☆"
       assert _calculate_power_efficiency_rating(0.0) == "★★★☆☆"
       assert _calculate_power_efficiency_rating(0.03) == "★★☆☆☆"
       assert _calculate_power_efficiency_rating(0.06) == "★☆☆☆☆"
   ```

2. **form_evaluations挿入 (TDD: Green)**
   - writer.update_form_evaluations_with_power() 実装
   - INSERT ON CONFLICT DO UPDATE パターン

### Phase 4: MCP Tools Integration

**Files:**
- `servers/garmin_db_server.py` (拡張)
- `tests/mcp/test_garmin_db_server.py` (拡張)

**Tasks:**

1. **get_power_efficiency_analysis ツール (TDD: Red → Green)**
   ```python
   # Test
   @pytest.mark.asyncio
   async def test_get_power_efficiency_analysis():
       """パワー効率分析データを取得。"""
       result = await get_power_efficiency_analysis(activity_id=12345)
       assert result['power_actual'] > 0
       assert result['power_efficiency_rating'] is not None

   @pytest.mark.asyncio
   async def test_get_power_efficiency_analysis_no_power():
       """パワーなしの場合、None値を返す。"""
       result = await get_power_efficiency_analysis(activity_id=67890)
       assert result['power_actual'] is None
       assert result['power_efficiency_rating'] is None
   ```

2. **get_form_evaluations拡張 (TDD: Green)**
   - 既存クエリにパワー効率列を追加
   - 後方互換性確保（パワーなしでもエラーなし）

### Phase 5: Agent Integration

**Files:**
- `.claude/agents/efficiency-section-analyst.md` (拡張)
- `tools/reporting/templates/individual_report.md.j2` (拡張)

**Tasks:**

1. **Agent Prompt更新**
   - パワー効率評価ロジック追加
   - レポート出力フォーマット定義

2. **Report Template拡張**
   - パワー効率セクション追加
   - 条件付き表示（power_actualがある場合のみ）

3. **Manual Testing**
   - 2025年アクティビティ（パワーあり）でレポート生成
   - 2021年アクティビティ（パワーなし）でレポート生成
   - エラーがないことを確認

### Phase 6: Documentation and Cleanup

**Files:**
- `CLAUDE.md` (更新)
- `docs/duckdb_schema_mapping.md` (更新)
- `docs/project/2025-10-28_power_efficiency_evaluation/completion_report.md` (生成)

**Tasks:**

1. **CLAUDE.md更新**
   - 新MCPツール: get_power_efficiency_analysis() 説明追加
   - get_form_evaluations() にパワー効率フィールド追加
   - DuckDBスキーマにパワー効率列追加

2. **duckdb_schema_mapping.md更新**
   - form_baseline_history: power_* 列追加
   - form_evaluations: パワー効率列追加

3. **completion_report.md生成**
   - 実装内容サマリー
   - テスト結果
   - 使用例（2025年アクティビティ）
   - マイグレーション手順

---

## 影響分析

### Affected Components

**1. Database Schema:**
- ✅ form_baseline_history (3列追加: power_coef_a, power_coef_b, power_rmse)
- ✅ form_evaluations (6列追加: power_actual, vo_per_power_actual/expected, score, rating, needs_improvement)
- ❌ splits (既存power列を使用、変更なし)

**2. Baseline Training:**
- ✅ `tools/form_baseline/trainer.py` (PowerEfficiencyModel追加、train_power_efficiency_baseline追加)
- ✅ GCT/VO/VR baseline training (変更なし、並列実行)

**3. Evaluation:**
- ✅ `tools/form_baseline/evaluator.py` (evaluate_power_efficiency追加)
- ✅ 既存GCT/VO/VR evaluation (変更なし)

**4. MCP Tools:**
- ✅ `servers/garmin_db_server.py` (新規: get_power_efficiency_analysis、拡張: get_form_evaluations)

**5. Agents:**
- ✅ `.claude/agents/efficiency-section-analyst.md` (パワー効率評価追加)
- ❌ 他のエージェント (変更なし)

**6. Report Templates:**
- ✅ `tools/reporting/templates/individual_report.md.j2` (パワー効率セクション追加)

**7. Scripts:**
- ❌ regenerate_duckdb.py (変更なし、新列は自動挿入されないためマイグレーションスクリプト必要)

### Risk Assessment

**Risk 1: パワーデータ欠損時のエラー**
- **Probability:** Medium (2021年データはパワーなし)
- **Impact:** High (システム全体が停止)
- **Mitigation:**
  - evaluate_power_efficiency() でパワーなしを検出 → None 返却
  - Agent で power_actual チェック → Noneならスキップ
  - テストで後方互換性を確認
- **Detection:** Integration test (2021年アクティビティ)

**Risk 2: Baseline訓練失敗（サンプル不足）**
- **Probability:** Low (2ヶ月窓なら十分なデータ）
- **Impact:** Medium (評価不能)
- **Mitigation:**
  - n_samples < 10 ならエラー（最小サンプル数）
  - エラーメッセージで必要期間を通知
- **Detection:** Unit test (サンプル不足ケース)

**Risk 3: VO/パワー比の単位エラー**
- **Probability:** Low
- **Impact:** High (評価が逆になる）
- **Mitigation:**
  - Unit test で既知データ（VO=10cm, Power=250W → 0.04 cm/W）を検証
  - Integration test で実データと突合
- **Detection:** Automated tests

**Risk 4: Schema Migration失敗**
- **Probability:** Low
- **Impact:** High (データベース破損）
- **Mitigation:**
  - Migration script を手動実行（regenerate_duckdb.py は自動挿入しない）
  - 本番データベースのバックアップ
  - テスト環境で事前検証
- **Rollback:** バックアップから復元、ALTER TABLE DROP COLUMN

**Risk 5: レポート生成失敗（テンプレートエラー）**
- **Probability:** Low
- **Impact:** Medium (レポート生成不能）
- **Mitigation:**
  - Jinja2テンプレートでNoneチェック（{% if power_actual %}）
  - Manual testing でパワーあり/なし両ケース確認
- **Detection:** Manual testing

### Breaking Changes

**None Expected:**
- 既存テーブルに列追加のみ（既存行にNULL挿入）
- 既存MCP Tools は変更なし（get_form_evaluations拡張は後方互換）
- 既存Agent は変更なし（efficiency-section-analyst拡張のみ）
- パワーなしアクティビティは従来通り動作

**Deprecation Notice:**
なし（既存機能は維持）

---

## テスト計画

### Unit Tests

**File:** `tests/form_baseline/test_trainer.py`

- [ ] **test_power_efficiency_model_init()**
  - PowerEfficiencyModelインスタンス化
  - 初期値確認（coef_a=0, coef_b=0, rmse=0）

- [ ] **test_power_efficiency_model_fit()**
  - 3点データで線形回帰
  - coef_b < 0 確認（速度増加でVO/パワー比減少）
  - RMSE > 0 確認

- [ ] **test_power_efficiency_model_predict()**
  - 係数セット後、速度から予測
  - 予測値が期待範囲内（0.02～0.06 cm/W）

- [ ] **test_train_power_efficiency_baseline_success()**
  - Mock splitsデータで訓練
  - 戻り値にcoef_a, coef_b, rmse, n_samples含まれる
  - n_samples > 0

- [ ] **test_train_power_efficiency_baseline_no_power_data()**
  - パワーデータなしの期間で訓練
  - 戻り値 None（エラーなし）

- [ ] **test_train_power_efficiency_baseline_insufficient_samples()**
  - サンプル数 < 10 の場合
  - 例外発生またはNone返却（設計次第）

**File:** `tests/form_baseline/test_evaluator.py`

- [ ] **test_evaluate_power_efficiency_success()**
  - Mock baseline, splits で評価
  - 戻り値に power_actual, vo_per_power_actual, rating 含まれる

- [ ] **test_evaluate_power_efficiency_no_power()**
  - splitsにパワーデータなし
  - 戻り値 None（エラーなし）

- [ ] **test_evaluate_power_efficiency_no_baseline()**
  - Baselineが存在しない場合
  - 例外発生またはNone返却

- [ ] **test_calculate_power_efficiency_rating_excellent()**
  - score = -0.06 → "★★★★★"

- [ ] **test_calculate_power_efficiency_rating_good()**
  - score = -0.03 → "★★★★☆"

- [ ] **test_calculate_power_efficiency_rating_average()**
  - score = 0.0 → "★★★☆☆"

- [ ] **test_calculate_power_efficiency_rating_poor()**
  - score = 0.03 → "★★☆☆☆"

- [ ] **test_calculate_power_efficiency_rating_very_poor()**
  - score = 0.06 → "★☆☆☆☆"

**File:** `tests/database/test_writer.py`

- [ ] **test_insert_power_efficiency_baseline()**
  - Baselineをform_baseline_historyに挿入
  - metric='vo_per_power' で挿入
  - power_coef_a, power_coef_b, power_rmse 確認

- [ ] **test_update_form_evaluations_with_power()**
  - form_evaluationsにパワー効率列を追加
  - INSERT ON CONFLICT DO UPDATE で既存行更新
  - 全6列が正しく挿入される

**File:** `tests/database/test_power_efficiency_schema.py` (新規)

- [ ] **test_form_baseline_history_has_power_columns()**
  - PRAGMA table_info で列存在確認
  - power_coef_a, power_coef_b, power_rmse

- [ ] **test_form_evaluations_has_power_columns()**
  - 6列存在確認
  - 型確認（DOUBLE, VARCHAR, BOOLEAN）

### Integration Tests

**File:** `tests/integration/test_power_efficiency_integration.py` (新規)

- [ ] **test_power_efficiency_end_to_end_with_power()**
  - 2025年アクティビティ（パワーあり）
  - Baseline訓練 → 評価 → form_evaluations挿入
  - MCP Tool でデータ取得
  - 値が妥当（vo_per_power_actual: 0.02～0.06）

- [ ] **test_power_efficiency_end_to_end_no_power()**
  - 2021年アクティビティ（パワーなし）
  - 評価がNone返却
  - form_evaluationsにNULL挿入
  - エラー発生しない

- [ ] **test_baseline_training_with_real_data()**
  - 実データ（2025-08-28～2025-10-28）で訓練
  - Baseline挿入成功
  - coef_b < 0 確認

- [ ] **test_cross_activity_evaluation()**
  - 3アクティビティで評価
  - 各アクティビティでrating異なる
  - needs_improvement フラグが正しく設定される

**File:** `tests/mcp/test_garmin_db_server.py`

- [ ] **test_get_power_efficiency_analysis_with_power()**
  - MCP Tool呼び出し（パワーあり）
  - 戻り値に全フィールド含まれる
  - rating が ★ 形式

- [ ] **test_get_power_efficiency_analysis_no_power()**
  - MCP Tool呼び出し（パワーなし）
  - 戻り値の各フィールドが None

- [ ] **test_get_form_evaluations_includes_power()**
  - 既存MCP Tool（拡張版）呼び出し
  - パワー効率フィールドが追加されている
  - 後方互換性確保（既存フィールドも取得）

### Performance Tests (Optional)

**File:** `tests/performance/test_power_efficiency_performance.py`

- [ ] **test_baseline_training_performance()**
  - 2ヶ月分（50アクティビティ）で訓練
  - 実行時間 < 5秒

- [ ] **test_evaluation_performance()**
  - 100アクティビティ連続評価
  - 実行時間 < 30秒（1アクティビティ < 0.3秒）

### Manual Testing Checklist

- [ ] **Schema Verification:**
  - [ ] PRAGMA table_info(form_baseline_history) 実行
  - [ ] power_coef_a, power_coef_b, power_rmse 存在確認
  - [ ] PRAGMA table_info(form_evaluations) 実行
  - [ ] 6列存在確認

- [ ] **Baseline Training:**
  - [ ] train_power_efficiency_baseline() 実行（2025-08-28～2025-10-28）
  - [ ] form_baseline_history にデータ挿入確認
  - [ ] coef_b < 0 確認（速度増加でVO/パワー比減少）

- [ ] **Evaluation:**
  - [ ] 2025年アクティビティで評価
  - [ ] form_evaluations にデータ挿入確認
  - [ ] rating が妥当（VO/パワー比と一致）

- [ ] **MCP Tools:**
  - [ ] get_power_efficiency_analysis(activity_id) 呼び出し
  - [ ] 戻り値確認（全フィールド）
  - [ ] get_form_evaluations(activity_id) 呼び出し
  - [ ] パワー効率フィールド含まれる確認

- [ ] **Agent Integration:**
  - [ ] efficiency-section-analyst でレポート生成（2025年）
  - [ ] パワー効率セクション表示確認
  - [ ] efficiency-section-analyst でレポート生成（2021年）
  - [ ] パワー効率セクション非表示確認（エラーなし）

- [ ] **Code Quality:**
  - [ ] uv run black .
  - [ ] uv run ruff check .
  - [ ] uv run mypy .
  - [ ] uv run pytest
  - [ ] uv run pre-commit run --all-files

---

## 受け入れ基準

### Functional Requirements

- [ ] form_baseline_historyにパワー効率列追加（power_coef_a, power_coef_b, power_rmse）
- [ ] form_evaluationsにパワー効率列追加（6列）
- [ ] PowerEfficiencyModelクラスが線形回帰を実行できる
- [ ] train_power_efficiency_baseline() が2ヶ月窓でbaselineを訓練できる
- [ ] evaluate_power_efficiency() がアクティビティを評価できる
- [ ] パワーデータなしの場合、エラーにならず None 返却
- [ ] MCP Tool get_power_efficiency_analysis() が動作する
- [ ] MCP Tool get_form_evaluations() にパワー効率データ含まれる
- [ ] efficiency-section-analyst がパワー効率を評価できる
- [ ] レポートにパワー効率セクションが表示される（条件付き）

### Code Quality

- [ ] 全Unit Testsがパス（pytest -m unit）
- [ ] 全Integration Testsがパス（pytest -m integration）
- [ ] コードカバレッジ ≥80%（新規コード）
- [ ] uv run black . - フォーマット問題なし
- [ ] uv run ruff check . - リント問題なし
- [ ] uv run mypy . - 型エラーなし
- [ ] Pre-commit hooks がパス

### Documentation

- [ ] CLAUDE.md更新（新MCPツール、スキーマ変更）
- [ ] docs/duckdb_schema_mapping.md更新（パワー効率列）
- [ ] コードコメント追加（VO/パワー比の意味、評価基準）
- [ ] completion_report.md生成（実装サマリー、使用例）
- [ ] planning.md更新（完了ステータス）

### Testing

- [ ] 18+ Unit Tests実装・合格
- [ ] 6 Integration Tests実装・合格
- [ ] Manual Testing Checklist完了
- [ ] 後方互換性検証（2021年アクティビティでエラーなし）
- [ ] 実データ検証（2025年アクティビティで妥当な評価）

### Git Workflow

- [ ] Planning committed to main branch
- [ ] Implementation in feature branch (worktree)
- [ ] Commits follow Conventional Commits format
- [ ] All commits include co-author tag
- [ ] PR created with completion_report.md
- [ ] Merged to main, worktree removed

### Data Integrity

- [ ] Schema Migration成功（列追加）
- [ ] 既存データに影響なし（NULL挿入のみ）
- [ ] パワー効率評価が妥当（実データで確認）
- [ ] パワーなしアクティビティで動作（エラーなし）
- [ ] Baseline訓練が成功（2ヶ月窓で十分なサンプル）

---

## 成功メトリクス

### Quantitative Metrics

- **Test Coverage:** ≥80% for new code (trainer.py, evaluator.py拡張部分)
- **Baseline Training Time:** <5秒（2ヶ月分50アクティビティ）
- **Evaluation Time:** <0.3秒/アクティビティ
- **Data Consistency:** 100%（パワーありアクティビティで評価成功）
- **Implementation Time:** ≤10時間（target: 8時間）

### Qualitative Metrics

- コードレビュー承認（major issue なし）
- VO/パワー比の意味が明確（ドキュメント・コメント）
- パワーなしアクティビティで後方互換性確保
- レポートがわかりやすい（パワー効率セクションが直感的）
- Serena MCP でシンボルベース編集成功

---

## 参考資料

### Current Implementation

- **Form Baseline:** `tools/form_baseline/trainer.py` (GCT/VO/VR訓練)
- **Form Evaluation:** `tools/form_baseline/evaluator.py` (GCT/VO/VR評価)
- **Database Writer:** `tools/database/writer.py` (挿入ロジック)
- **MCP Server:** `servers/garmin_db_server.py` (get_form_evaluations)
- **Agent:** `.claude/agents/efficiency-section-analyst.md`

### Related Tables

- **splits:** power列（1km lap単位の平均パワー）
- **form_baseline_history:** GCT/VO/VR baseline（metric列で区別）
- **form_evaluations:** GCT/VO/VR評価結果

### Test Examples

- **Existing Tests:** `tests/form_baseline/test_trainer.py`, `tests/form_baseline/test_evaluator.py`
- **Real Data:** `/home/yamakii/garmin_data/data/raw/activity/20721683500/` (2025年、パワーあり)
- **Real Data:** `/home/yamakii/garmin_data/data/raw/activity/14810988218/` (2021年、パワーなし)

### Statistical Model

**Model:** VO/Power = a + b * speed
- **VO/Power:** cm/W（小さいほど効率的）
- **speed:** m/s
- **Interpretation:** 同じ速度で比較し、パワー当たりのVO量を評価

**Evaluation Criteria:**
```python
deviation = (actual - expected) / expected
if deviation <= -0.05:    # 期待値より5%以上低い
    rating = "★★★★★"  # 非常に効率的
elif deviation <= -0.02:  # 期待値より2-5%低い
    rating = "★★★★☆"  # 効率的
elif deviation <= 0.02:   # ±2%以内
    rating = "★★★☆☆"  # 標準
elif deviation <= 0.05:   # 期待値より2-5%高い
    rating = "★★☆☆☆"  # やや非効率
else:                      # 期待値より5%以上高い
    rating = "★☆☆☆☆"  # 非効率
```

### Similar Projects

- **Cadence Column Refactoring:** `docs/project/2025-10-19_cadence_column_refactoring/`
  - 類似パターン: 既存テーブルに列追加、後方互換性確保
  - TDD approach、Unit + Integration tests
  - Schema migration with ALTER TABLE

- **Body Composition Table Support:** `docs/project/2025-10-18_body_composition_table_support/`
  - 類似パターン: 新テーブル作成、API連携
  - Database regeneration、TDD approach

---

## Next Steps

### Immediate Actions (Planning Phase)

1. ✅ Create planning.md (this document)
2. ⬜ Create GitHub Issue with planning.md content
3. ⬜ User review and approval
4. ⬜ Create worktree for implementation

### Handoff to tdd-implementer

After planning approval:
1. Create worktree: `git worktree add -b feature/power-efficiency-evaluation ../garmin-power-efficiency main`
2. Change directory: `cd ../garmin-power-efficiency`
3. Setup environment: `uv sync --extra dev`
4. Activate Serena MCP: `mcp__serena__activate_project("/absolute/path/to/worktree")`
5. Execute Phase 1: Schema Migration (TDD)
6. Execute Phase 2: Baseline Training Implementation (TDD)
7. Execute Phase 3: Evaluation Implementation (TDD)
8. Execute Phase 4: MCP Tools Integration (TDD)
9. Execute Phase 5: Agent Integration (Manual Testing)
10. Execute Phase 6: Documentation Updates
11. Generate completion_report.md
12. Create PR and merge to main

### Long-term Enhancements (Out of Scope)

- **Phase 7: 他のフォームメトリクスとの統合**
  - GCT/パワー比、VR/パワー比なども評価
  - 多変量解析（GCT, VO, VR, Power の相関）

- **Phase 8: パワーゾーン分析**
  - パワーゾーン別のフォーム効率評価
  - ゾーン別のbaseline訓練

- **Phase 9: 長期トレンド可視化**
  - パワー効率の月次推移グラフ
  - 成長曲線の可視化

---

## Appendix: Data Analysis

### Sample Activity Data (20721683500 - 2025年)

**Expected Values:**
- Average Power: ~240W
- Average VO: ~10.5 cm
- VO/Power: ~0.044 cm/W

**Query Example:**
```sql
SELECT
    activity_id,
    AVG(power) AS avg_power,
    AVG(vertical_oscillation_cm) AS avg_vo,
    AVG(vertical_oscillation_cm) / NULLIF(AVG(power), 0) AS vo_per_power
FROM splits
WHERE activity_id = 20721683500
GROUP BY activity_id;
```

### Baseline Training Query

```sql
-- 2ヶ月窓でパワー効率データ取得
SELECT
    activity_id,
    activity_date,
    AVG(speed_mps) AS avg_speed,
    AVG(vertical_oscillation_cm) AS avg_vo,
    AVG(power) AS avg_power,
    AVG(vertical_oscillation_cm) / NULLIF(AVG(power), 0) AS vo_per_power
FROM splits
WHERE
    activity_date >= '2025-08-28' AND activity_date <= '2025-10-28'
    AND power IS NOT NULL
    AND vertical_oscillation_cm IS NOT NULL
GROUP BY activity_id, activity_date
ORDER BY activity_date;
```

### Evaluation Verification Query

```sql
-- パワー効率評価結果確認
SELECT
    fe.activity_id,
    a.activity_date,
    fe.power_actual,
    fe.vo_per_power_actual,
    fe.vo_per_power_expected,
    fe.power_efficiency_score,
    fe.power_efficiency_rating,
    fe.power_efficiency_needs_improvement
FROM form_evaluations fe
JOIN activities a ON fe.activity_id = a.activity_id
WHERE fe.power_actual IS NOT NULL
ORDER BY a.activity_date DESC
LIMIT 10;
```

**Expected Output:**
```
activity_id  | activity_date | power_actual | vo_per_power_actual | vo_per_power_expected | power_efficiency_score | power_efficiency_rating | needs_improvement
-------------|---------------|--------------|---------------------|-----------------------|------------------------|-------------------------|------------------
20721683500  | 2025-10-28    | 242.5        | 0.043               | 0.045                 | -0.044                 | ★★★★☆              | false
...
```

---

**Planning Document Version:** 1.0
**Last Updated:** 2025-10-28
**Status:** Ready for Review
