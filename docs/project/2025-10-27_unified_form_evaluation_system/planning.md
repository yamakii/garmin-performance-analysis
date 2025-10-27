# 計画: Unified Form Evaluation System

## プロジェクト情報

- **プロジェクト名**: `unified_form_evaluation_system`
- **作成日**: 2025-10-27
- **ステータス**: 計画中
- **想定期間**: 13-19時間（2-3日）
- **優先度**: 高（評価の矛盾は重要な品質問題）
- **GitHub Issue**: #42

---

## 要件定義

### 目的

**個人データから学習したペース補正基準値により、フォーム指標の一貫した評価を実現する**

現在の課題を解決し、データドリブンで統一された評価システムを構築する。

### 解決する問題

#### 1. **評価の矛盾**
- **現象**: 同一活動で異なるエージェントが矛盾した評価を出力
  - `efficiency-section-analyst`: "GCT 258msは優秀（★★★★☆）"
  - `summary-section-analyst`: "GCT 258msは改善必要（目標250ms未満）"
- **原因**:
  - 各エージェントが独自の評価基準を使用
  - プロンプト内の例文が固定値のまま誤用されている
  - データに基づかない主観的判断

#### 2. **ペース補正の欠如**
- **現象**: 全ペースで同じ基準値を適用
  - Fast Run (5:00/km) で GCT 216ms
  - Easy Run (7:11/km) で GCT 258ms
  - 両者が同じ効率と誤判定される
- **データ分析結果**: ペースによりGCTは45ms (21%) 変動
- **問題**: ペースの影響を考慮しない評価は科学的に不正確

#### 3. **トークン浪費**
- **現象**: エージェントが表データ（JSON）も生成
- **問題**:
  - `efficiency-section-analyst`が評価文と表データを両方生成
  - 表データはWorkerでも生成されるため重複
  - 評価文のみで十分なのにトークンを消費

### ユースケース

#### UC-1: 統一基準によるフォーム評価
**アクター**: ReportGeneratorWorker, SectionAnalysisAgents
**前提条件**: 個人データで訓練された基準値が存在
**フロー**:
1. WorkflowPlannerが活動データを収集
2. FormEvaluatorが基準値を用いて期待値を計算
3. 実測値と期待値の偏差を計算
4. スコアリング（0-100点）と★評価を生成
5. DuckDB `form_evaluations` テーブルに保存
6. エージェントが評価結果を読み取り、一貫した評価文を生成

**期待結果**: 全エージェントが同じ評価基準を使用し、矛盾がゼロになる

#### UC-2: ペース補正されたフォーム評価
**アクター**: FormEvaluator
**前提条件**: 冪乗回帰モデル（GCT）・線形モデル（VO/VR）が訓練済み
**フロー**:
1. 活動の平均ペースを取得
2. ペースから期待GCT/VO/VRを予測（統計モデル使用）
3. 実測値との偏差を計算
4. ±5%以内なら高評価、それ以上はペナルティ

**期待結果**: Fast Runで短いGCT、Easy Runで長いGCTが共に適正と評価される

#### UC-3: トークン最適化されたエージェント評価
**アクター**: efficiency-section-analyst, summary-section-analyst
**前提条件**: `form_evaluations` テーブルに評価済みデータが存在
**フロー**:
1. エージェントがMCPツール `get_form_evaluations()` を呼び出し
2. 評価結果JSON（期待値、実測値、スコア、needs_improvement）を取得
3. **評価文のみ**を生成（表データは生成しない）
4. `summary-section-analyst`は `needs_improvement=true` のみ改善提案

**期待結果**: トークン削減率70%、評価文の品質維持

#### UC-4: 基準値の定期更新
**アクター**: データ管理者
**前提条件**: 新規活動データが100件以上追加された
**フロー**:
1. `uv run python tools/scripts/train_form_baselines.py` 実行
2. DuckDB `splits` テーブルから全データ読込
3. 外れ値除去（IQR法）
4. ロバスト回帰（Huber, RANSAC）で係数訓練
5. `form_baselines` テーブルを更新

**期待結果**: 個人の成長・変化に対応した最新基準値

---

## 設計

### アーキテクチャ

#### システムパイプライン

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Training（一度だけ/定期更新）                    │
│   DuckDB splits (1800+ samples)                         │
│   → tools/form_baseline/trainer.py                      │
│   → form_baselines テーブル（係数保存）                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 2: Evaluation（活動ごと）                          │
│   workflow_planner.py                                   │
│   └→ tools/form_baseline/evaluator.py                   │
│      ├ form_baselines から係数読込                       │
│      ├ splits から実測値取得                             │
│      ├ 予測・スコアリング                                │
│      └ form_evaluations テーブルに保存                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 3: Section Analysis（並列実行）                     │
│   efficiency-section-analyst                            │
│   ├ mcp__garmin-db__get_form_evaluations() で評価取得   │
│   └ 評価文のみ生成（表データなし）← トークン削減          │
│                                                          │
│   summary-section-analyst                               │
│   ├ get_form_evaluations() で needs_improvement 確認    │
│   └ 改善提案のみ生成（達成済みは含まない）                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 4: Report Generation                              │
│   report_generator_worker.py                            │
│   ├ form_evaluations から表データ直接取得 ← NEW         │
│   ├ section_analyses から評価文取得                      │
│   └ テンプレートで表を生成（エージェントに依存しない）     │
└─────────────────────────────────────────────────────────┘
```

#### コンポーネント設計

**1. Form Baseline System** (新規)
- **Trainer**: 統計モデル訓練（冪乗回帰・線形回帰）
- **Predictor**: 期待値予測（ペース → GCT/VO/VR）
- **Scorer**: スコアリング・★評価生成
- **Evaluator**: 統合評価・DuckDB保存
- **TextGenerator**: 日本語評価文生成

**2. MCP Extension**
- **get_form_evaluations()**: 評価結果JSON取得

**3. Agent Integration**
- **efficiency-section-analyst**: 簡素化（表削除）
- **summary-section-analyst**: needs_improvement使用

**4. Report Generator**
- **report_generator_worker.py**: form_evaluations読込追加
- **detailed_report.j2**: 表生成ロジック追加

### データモデル

#### 1. form_baselines テーブル（係数保存）

```sql
CREATE TABLE form_baselines (
    baseline_id INTEGER PRIMARY KEY,
    user_id VARCHAR DEFAULT 'default',
    condition_group VARCHAR,  -- 'flat_road', 'uphill', 'trail' (Phase 1では'default'のみ)
    metric VARCHAR,           -- 'gct', 'vo', 'vr'
    model_type VARCHAR,       -- 'power' (GCT), 'linear' (VO/VR)

    -- 係数
    coef_alpha FLOAT,         -- GCT: log(c), VO/VR: intercept
    coef_d FLOAT,             -- GCT: slope (negative), VO/VR: NULL
    coef_a FLOAT,             -- VO/VR: intercept (duplicate), GCT: NULL
    coef_b FLOAT,             -- VO/VR: slope, GCT: NULL

    -- メタデータ
    n_samples INTEGER,        -- 訓練サンプル数
    rmse FLOAT,               -- モデル精度（Root Mean Squared Error）
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    speed_range_min FLOAT,    -- 適用可能速度範囲（m/s）
    speed_range_max FLOAT,

    UNIQUE(user_id, condition_group, metric)
);
```

**設計ノート**:
- Phase 1では `condition_group='default'` のみ実装
- 将来的に坂道・トレイルなど地形別に分層可能
- `coef_alpha` と `coef_a` は重複だが、モデルタイプにより意味が異なる

#### 2. form_evaluations テーブル（評価結果）

```sql
CREATE TABLE form_evaluations (
    eval_id INTEGER PRIMARY KEY,
    activity_id BIGINT UNIQUE,

    -- 期待値（Predicted from models）
    gct_ms_expected FLOAT,
    vo_cm_expected FLOAT,
    vr_pct_expected FLOAT,

    -- 実測値（Actual averages from splits）
    gct_ms_actual FLOAT,
    vo_cm_actual FLOAT,
    vr_pct_actual FLOAT,

    -- 偏差
    gct_delta_pct FLOAT,      -- (actual - expected) / expected * 100
    vo_delta_cm FLOAT,        -- actual - expected
    vr_delta_pct FLOAT,       -- (actual - expected) / expected * 100

    -- GCT評価
    gct_penalty FLOAT,        -- 0-100のペナルティスコア
    gct_star_rating VARCHAR,  -- '★★★★★' ~ '★☆☆☆☆'
    gct_score FLOAT,          -- 100 - penalty
    gct_needs_improvement BOOLEAN,
    gct_evaluation_text TEXT, -- 日本語評価文

    -- VO評価
    vo_penalty FLOAT,
    vo_star_rating VARCHAR,
    vo_score FLOAT,
    vo_needs_improvement BOOLEAN,
    vo_evaluation_text TEXT,

    -- VR評価
    vr_penalty FLOAT,
    vr_star_rating VARCHAR,
    vr_score FLOAT,
    vr_needs_improvement BOOLEAN,
    vr_evaluation_text TEXT,

    -- ケイデンス（既存splits集計）
    cadence_actual FLOAT,
    cadence_minimum INTEGER DEFAULT 180,
    cadence_achieved BOOLEAN,

    -- 総合評価
    overall_score FLOAT,      -- (gct_score + vo_score + vr_score) / 3
    overall_star_rating VARCHAR,

    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**設計ノート**:
- `activity_id` はUNIQUE制約（1活動1評価）
- スコア計算: `score = max(0, 100 - penalty)`
- `needs_improvement = (penalty > 10)` （スコア90未満）

### API/インターフェース設計

#### 1. Form Baseline Trainer

```python
# tools/form_baseline/trainer.py

from dataclasses import dataclass
from typing import Literal
import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, RANSACRegressor

@dataclass
class GCTPowerModel:
    """冪乗モデル: v = c * (GCT)^d"""
    alpha: float  # log(c)
    d: float      # slope (should be < 0)
    rmse: float
    n_samples: int
    speed_range: tuple[float, float]

    def predict(self, gct_ms: float) -> float:
        """GCTから速度を予測（内部使用）"""
        return np.exp(self.alpha + self.d * np.log(gct_ms))

    def predict_inverse(self, speed_mps: float) -> float:
        """速度からGCTを予測（評価で使用）"""
        return np.exp((np.log(speed_mps) - self.alpha) / self.d)

@dataclass
class LinearModel:
    """線形モデル: y = a + b * v"""
    a: float
    b: float
    rmse: float
    n_samples: int
    speed_range: tuple[float, float]

    def predict(self, speed_mps: float) -> float:
        """速度からVO/VRを予測"""
        return self.a + self.b * speed_mps

def fit_gct_power(
    df: pd.DataFrame,
    fallback_ransac: bool = True
) -> GCTPowerModel:
    """
    GCT冪乗モデルの訓練

    Args:
        df: columns=['gct_ms', 'speed_mps']
        fallback_ransac: 単調性チェック失敗時にRANSACを試す

    Returns:
        GCTPowerModel（d < 0を保証）

    Raises:
        ValueError: 単調性を満たすモデルが訓練できない場合
    """
    df_clean = drop_outliers(df, column='gct_ms')
    X = np.log(df_clean['gct_ms'].values).reshape(-1, 1)
    y = np.log(df_clean['speed_mps'].values)

    # Huber回帰（外れ値に強い）
    base = HuberRegressor().fit(X, y)
    alpha = base.intercept_
    d = base.coef_[0]

    # 単調性チェック（d < 0が期待値）
    if d >= 0:
        if not fallback_ransac:
            raise ValueError(f"Non-monotonic GCT model: d={d:.3f}")

        # RANSAC fallback
        ransac = RANSACRegressor(min_samples=0.8).fit(X, y)
        alpha = ransac.estimator_.intercept_
        d = ransac.estimator_.coef_[0]

        if d >= 0:
            raise ValueError(f"RANSAC failed: d={d:.3f}")

    # RMSE計算
    y_pred = alpha + d * X.flatten()
    rmse = np.sqrt(np.mean((y - y_pred) ** 2))

    return GCTPowerModel(
        alpha=alpha,
        d=d,
        rmse=rmse,
        n_samples=len(df_clean),
        speed_range=(df_clean['speed_mps'].min(), df_clean['speed_mps'].max())
    )

def fit_linear(
    df: pd.DataFrame,
    metric: Literal['vo', 'vr']
) -> LinearModel:
    """
    VO/VR線形モデルの訓練

    Args:
        df: columns=[f'{metric}_value', 'speed_mps']
        metric: 'vo' (cm) or 'vr' (%)

    Returns:
        LinearModel
    """
    column = f'{metric}_value'
    df_clean = drop_outliers(df, column=column)

    X = df_clean['speed_mps'].values.reshape(-1, 1)
    y = df_clean[column].values

    model = HuberRegressor().fit(X, y)
    a = model.intercept_
    b = model.coef_[0]

    # RMSE計算
    y_pred = model.predict(X)
    rmse = np.sqrt(np.mean((y - y_pred) ** 2))

    return LinearModel(
        a=a,
        b=b,
        rmse=rmse,
        n_samples=len(df_clean),
        speed_range=(df_clean['speed_mps'].min(), df_clean['speed_mps'].max())
    )
```

#### 2. Form Baseline Predictor

```python
# tools/form_baseline/predictor.py

from typing import NamedTuple
import duckdb

class FormExpectations(NamedTuple):
    """期待値のセット"""
    gct_ms: float
    vo_cm: float
    vr_pct: float

def predict_expectations(
    conn: duckdb.DuckDBPyConnection,
    avg_speed_mps: float,
    user_id: str = 'default',
    condition_group: str = 'default'
) -> FormExpectations:
    """
    速度から期待フォーム指標を予測

    Args:
        conn: DuckDB接続
        avg_speed_mps: 平均速度（m/s）
        user_id: ユーザーID
        condition_group: 地形グループ

    Returns:
        FormExpectations（期待GCT/VO/VR）

    Raises:
        ValueError: 基準値が存在しない場合
    """
    # GCT基準値取得
    gct_row = conn.execute("""
        SELECT coef_alpha, coef_d, speed_range_min, speed_range_max
        FROM form_baselines
        WHERE user_id = ? AND condition_group = ? AND metric = 'gct'
    """, [user_id, condition_group]).fetchone()

    if not gct_row:
        raise ValueError(f"GCT baseline not found for {user_id}/{condition_group}")

    alpha, d, speed_min, speed_max = gct_row

    # 速度範囲チェック（外挿警告）
    if not (speed_min <= avg_speed_mps <= speed_max):
        # ログ警告（実装時）
        pass

    # GCT予測: GCT = exp((log(v) - alpha) / d)
    gct_expected = np.exp((np.log(avg_speed_mps) - alpha) / d)

    # VO予測
    vo_row = conn.execute("""
        SELECT coef_a, coef_b
        FROM form_baselines
        WHERE user_id = ? AND condition_group = ? AND metric = 'vo'
    """, [user_id, condition_group]).fetchone()

    if not vo_row:
        raise ValueError(f"VO baseline not found")

    a_vo, b_vo = vo_row
    vo_expected = a_vo + b_vo * avg_speed_mps

    # VR予測
    vr_row = conn.execute("""
        SELECT coef_a, coef_b
        FROM form_baselines
        WHERE user_id = ? AND condition_group = ? AND metric = 'vr'
    """, [user_id, condition_group]).fetchone()

    if not vr_row:
        raise ValueError(f"VR baseline not found")

    a_vr, b_vr = vr_row
    vr_expected = a_vr + b_vr * avg_speed_mps

    return FormExpectations(
        gct_ms=gct_expected,
        vo_cm=vo_expected,
        vr_pct=vr_expected
    )
```

#### 3. Form Baseline Scorer

```python
# tools/form_baseline/scorer.py

from typing import NamedTuple

class MetricScore(NamedTuple):
    """個別指標のスコア"""
    penalty: float
    score: float  # 100 - penalty
    star_rating: str  # '★★★★★' ~ '★☆☆☆☆'
    needs_improvement: bool

def score_gct_observation(
    actual_ms: float,
    expected_ms: float,
    imbalance: float | None = None
) -> MetricScore:
    """
    GCT評価のスコアリング

    Args:
        actual_ms: 実測GCT（ms）
        expected_ms: 期待GCT（ms）
        imbalance: 左右差（0.0-1.0、Noneなら考慮しない）

    Returns:
        MetricScore
    """
    # 偏差率計算
    delta_pct = (actual_ms - expected_ms) / expected_ms

    penalty = 0.0

    # 偏差ペナルティ（±5%超で増加）
    if abs(delta_pct) > 0.05:
        # 1%超過ごとに2点ペナルティ（最大20点）
        penalty += min(20, (abs(delta_pct) - 0.05) * 200)

    # 左右差ペナルティ（6%超で10点）
    if imbalance is not None and imbalance > 0.06:
        penalty += 10

    score = max(0, 100 - penalty)
    star_rating = compute_star_rating(score)
    needs_improvement = (penalty > 10)  # スコア90未満

    return MetricScore(
        penalty=penalty,
        score=score,
        star_rating=star_rating,
        needs_improvement=needs_improvement
    )

def score_vo_observation(
    actual_cm: float,
    expected_cm: float
) -> MetricScore:
    """VO評価のスコアリング（GCTと同様のロジック）"""
    delta_cm = actual_cm - expected_cm
    delta_pct = delta_cm / expected_cm

    penalty = 0.0
    if abs(delta_pct) > 0.05:
        penalty += min(20, (abs(delta_pct) - 0.05) * 200)

    score = max(0, 100 - penalty)
    star_rating = compute_star_rating(score)
    needs_improvement = (penalty > 10)

    return MetricScore(penalty, score, star_rating, needs_improvement)

def score_vr_observation(
    actual_pct: float,
    expected_pct: float
) -> MetricScore:
    """VR評価のスコアリング（同上）"""
    delta_pct = (actual_pct - expected_pct) / expected_pct

    penalty = 0.0
    if abs(delta_pct) > 0.05:
        penalty += min(20, (abs(delta_pct) - 0.05) * 200)

    score = max(0, 100 - penalty)
    star_rating = compute_star_rating(score)
    needs_improvement = (penalty > 10)

    return MetricScore(penalty, score, star_rating, needs_improvement)

def compute_star_rating(score: float) -> str:
    """
    スコアから★評価を生成

    95-100: ★★★★★
    85-95:  ★★★★☆
    75-85:  ★★★☆☆
    65-75:  ★★☆☆☆
    <65:    ★☆☆☆☆
    """
    if score >= 95:
        return '★★★★★'
    elif score >= 85:
        return '★★★★☆'
    elif score >= 75:
        return '★★★☆☆'
    elif score >= 65:
        return '★★☆☆☆'
    else:
        return '★☆☆☆☆'
```

#### 4. Form Baseline Evaluator

```python
# tools/form_baseline/evaluator.py

import duckdb
from tools.form_baseline.predictor import predict_expectations
from tools.form_baseline.scorer import (
    score_gct_observation,
    score_vo_observation,
    score_vr_observation
)
from tools.form_baseline.text_generator import (
    generate_gct_evaluation_text,
    generate_vo_evaluation_text,
    generate_vr_evaluation_text
)

def evaluate_and_store(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    activity_date: str
) -> None:
    """
    単一活動のフォーム評価を実行し、DuckDBに保存

    Args:
        conn: DuckDB接続
        activity_id: 活動ID
        activity_date: 活動日（YYYY-MM-DD）

    Workflow:
        1. splitsから実測値（平均GCT/VO/VR、速度）を取得
        2. form_baselinesから基準値を読込
        3. 期待値を予測
        4. スコアリング
        5. 日本語評価文生成
        6. form_evaluationsに保存
    """
    # 1. 実測値取得
    actual = conn.execute("""
        SELECT
            AVG(ground_contact_time_ms) as gct_ms,
            AVG(vertical_oscillation_cm) as vo_cm,
            AVG(vertical_ratio_pct) as vr_pct,
            AVG(avg_running_cadence_spm) as cadence,
            AVG(1000.0 / pace_seconds_per_km) as speed_mps
        FROM splits
        WHERE activity_id = ?
    """, [activity_id]).fetchone()

    if not actual:
        raise ValueError(f"No splits data for activity {activity_id}")

    gct_actual, vo_actual, vr_actual, cadence_actual, avg_speed = actual

    # 2. 期待値予測
    expectations = predict_expectations(conn, avg_speed)

    # 3. スコアリング
    gct_score = score_gct_observation(gct_actual, expectations.gct_ms)
    vo_score = score_vo_observation(vo_actual, expectations.vo_cm)
    vr_score = score_vr_observation(vr_actual, expectations.vr_pct)

    # 4. 評価文生成
    gct_text = generate_gct_evaluation_text(
        actual=gct_actual,
        expected=expectations.gct_ms,
        score=gct_score,
        pace_minutes_per_km=1000.0 / avg_speed / 60.0
    )
    vo_text = generate_vo_evaluation_text(vo_actual, expectations.vo_cm, vo_score)
    vr_text = generate_vr_evaluation_text(vr_actual, expectations.vr_pct, vr_score)

    # 5. 総合スコア
    overall_score = (gct_score.score + vo_score.score + vr_score.score) / 3
    overall_star = compute_star_rating(overall_score)

    # 6. DuckDB保存
    conn.execute("""
        INSERT OR REPLACE INTO form_evaluations VALUES (
            NULL, ?, -- eval_id (AUTO), activity_id
            ?, ?, ?,  -- expected
            ?, ?, ?,  -- actual
            ?, ?, ?,  -- delta
            ?, ?, ?, ?, ?,  -- gct
            ?, ?, ?, ?, ?,  -- vo
            ?, ?, ?, ?, ?,  -- vr
            ?, ?, ?,  -- cadence
            ?, ?,     -- overall
            CURRENT_TIMESTAMP
        )
    """, [
        activity_id,
        expectations.gct_ms, expectations.vo_cm, expectations.vr_pct,
        gct_actual, vo_actual, vr_actual,
        (gct_actual - expectations.gct_ms) / expectations.gct_ms * 100,
        vo_actual - expectations.vo_cm,
        (vr_actual - expectations.vr_pct) / expectations.vr_pct * 100,
        gct_score.penalty, gct_score.star_rating, gct_score.score,
        gct_score.needs_improvement, gct_text,
        vo_score.penalty, vo_score.star_rating, vo_score.score,
        vo_score.needs_improvement, vo_text,
        vr_score.penalty, vr_score.star_rating, vr_score.score,
        vr_score.needs_improvement, vr_text,
        cadence_actual, 180, cadence_actual >= 180,
        overall_score, overall_star
    ])
```

#### 5. MCP Tool

```python
# mcp-server/garmin-db/server.py

@server.call_tool()
async def get_form_evaluations(activity_id: int) -> dict:
    """
    フォーム評価結果を取得

    Args:
        activity_id: 活動ID

    Returns:
        {
            "activity_id": 20790040925,
            "gct": {
                "actual": 258.0,
                "expected": 261.5,
                "delta_pct": -1.3,
                "star_rating": "★★★★★",
                "score": 95.0,
                "needs_improvement": false,
                "evaluation_text": "258msは期待値261msより1.3%優秀..."
            },
            "vo": {...},
            "vr": {...},
            "cadence": {
                "actual": 183,
                "minimum": 180,
                "achieved": true
            },
            "overall_score": 95.0,
            "overall_star_rating": "★★★★☆"
        }
    """
    conn = get_connection()
    row = conn.execute("""
        SELECT
            gct_ms_expected, gct_ms_actual, gct_delta_pct,
            gct_star_rating, gct_score, gct_needs_improvement, gct_evaluation_text,
            vo_cm_expected, vo_cm_actual, vo_delta_cm,
            vo_star_rating, vo_score, vo_needs_improvement, vo_evaluation_text,
            vr_pct_expected, vr_pct_actual, vr_delta_pct,
            vr_star_rating, vr_score, vr_needs_improvement, vr_evaluation_text,
            cadence_actual, cadence_minimum, cadence_achieved,
            overall_score, overall_star_rating
        FROM form_evaluations
        WHERE activity_id = ?
    """, [activity_id]).fetchone()

    if not row:
        raise ValueError(f"No form evaluation for activity {activity_id}")

    return {
        "activity_id": activity_id,
        "gct": {
            "actual": row[1],
            "expected": row[0],
            "delta_pct": row[2],
            "star_rating": row[3],
            "score": row[4],
            "needs_improvement": row[5],
            "evaluation_text": row[6]
        },
        "vo": {
            "actual": row[8],
            "expected": row[7],
            "delta_cm": row[9],
            "star_rating": row[10],
            "score": row[11],
            "needs_improvement": row[12],
            "evaluation_text": row[13]
        },
        "vr": {
            "actual": row[15],
            "expected": row[14],
            "delta_pct": row[16],
            "star_rating": row[17],
            "score": row[18],
            "needs_improvement": row[19],
            "evaluation_text": row[20]
        },
        "cadence": {
            "actual": row[21],
            "minimum": row[22],
            "achieved": row[23]
        },
        "overall_score": row[24],
        "overall_star_rating": row[25]
    }
```

---

## 実装フェーズ

### Phase 1: Form Baseline System Core (4-5時間)

**目標**: 統計モデル訓練・予測・スコアリング機能の実装

#### Tasks
- [ ] `tools/form_baseline/__init__.py` 作成
- [ ] `tools/form_baseline/utils.py` 実装
  - [ ] `drop_outliers(df, column)` - IQR法外れ値除去
  - [ ] `to_speed(pace_sec_per_km)` - ペース→速度変換
- [ ] `tools/form_baseline/trainer.py` 実装
  - [ ] `fit_gct_power()` - 冪乗モデル（Huber回帰）
  - [ ] 単調性チェック（d < 0 強制）
  - [ ] RANSAC fallback実装
  - [ ] `fit_linear()` - VO/VR線形モデル
- [ ] `tools/form_baseline/predictor.py` 実装
  - [ ] `predict_expectations()` - 期待値計算
  - [ ] 速度範囲外警告ロジック
- [ ] `tools/form_baseline/scorer.py` 実装
  - [ ] `score_gct_observation()` - GCTペナルティ計算
  - [ ] `score_vo_observation()` - VOペナルティ計算
  - [ ] `score_vr_observation()` - VRペナルティ計算
  - [ ] `compute_star_rating()` - ★評価マッピング
- [ ] `tools/scripts/train_form_baselines.py` 実装
  - [ ] CLI: 全データ訓練
  - [ ] DuckDBから splits 読込
  - [ ] 3モデル訓練（GCT/VO/VR）
  - [ ] `form_baselines` テーブルに保存
- [ ] `tools/database/db_writer.py` 修正
  - [ ] `_ensure_tables()` に `form_baselines`, `form_evaluations` 追加

#### Unit Tests
- [ ] `tests/form_baseline/test_utils.py`
  - [ ] 外れ値除去の正確性（IQR法）
  - [ ] 速度変換の正確性
- [ ] `tests/form_baseline/test_trainer.py`
  - [ ] GCT冪乗モデルの単調性（d < 0）
  - [ ] RANSAC fallbackの動作
  - [ ] 線形モデルの係数精度
- [ ] `tests/form_baseline/test_predictor.py`
  - [ ] 期待値計算の正確性（既知データで検証）
  - [ ] 速度範囲外警告の動作
- [ ] `tests/form_baseline/test_scorer.py`
  - [ ] スコアリングロジック（±5%境界値）
  - [ ] ★評価マッピング（境界値テスト）

### Phase 2: Evaluation Logic Integration (2-3時間)

**目標**: 評価実行・DuckDB保存・日本語評価文生成

#### Tasks
- [ ] `tools/form_baseline/text_generator.py` 実装
  - [ ] `generate_gct_evaluation_text()` - 日本語評価文
  - [ ] `generate_vo_evaluation_text()`
  - [ ] `generate_vr_evaluation_text()`
  - [ ] テンプレート: 偏差に応じた評価表現（優秀/良好/許容範囲/要改善）
- [ ] `tools/form_baseline/evaluator.py` 実装
  - [ ] `evaluate_and_store(conn, activity_id, activity_date)`
  - [ ] splits から実測値取得
  - [ ] form_baselines から係数読込
  - [ ] 予測・スコアリング実行
  - [ ] form_evaluations に保存
- [ ] `tools/planner/workflow_planner.py` 修正
  - [ ] データ収集後に `evaluate_and_store()` 呼び出し
  - [ ] エラーハンドリング（基準値未訓練時）

#### Integration Tests
- [ ] `tests/form_baseline/test_evaluator_integration.py`
  - [ ] 実データでの評価フロー（mock DuckDB使用）
  - [ ] form_evaluations への保存検証
  - [ ] 評価文の品質チェック（日本語自然性）

### Phase 3: MCP Extension (1-2時間)

**目標**: MCPツール `get_form_evaluations()` 実装

#### Tasks
- [ ] `mcp-server/garmin-db/server.py` 修正
  - [ ] `get_form_evaluations(activity_id)` 実装
  - [ ] form_evaluations テーブル読込
  - [ ] JSON整形（nested structure）
  - [ ] エラーハンドリング（評価未実行時）

#### Tests
- [ ] MCPツールの動作確認（実アクティビティ）
  - [ ] JSONスキーマ検証
  - [ ] 欠損値ハンドリング
  - [ ] パフォーマンス（<100ms）

### Phase 4: Agent Integration (2-3時間)

**目標**: エージェントプロンプト簡素化・トークン削減

#### Tasks
- [ ] `.claude/agents/efficiency-section-analyst.md` 修正
  - [ ] プロンプト簡素化（表データ削除）
  - [ ] `get_form_evaluations()` 使用指示追加
  - [ ] 評価文のみ生成（JSON出力禁止）
  - [ ] 例文更新（ペース補正評価の説明）
- [ ] `.claude/agents/summary-section-analyst.md` 修正
  - [ ] `get_form_evaluations()` 使用指示追加
  - [ ] `needs_improvement=true` のみ改善提案
  - [ ] 達成済み目標を絶対に含めないルール追加
  - [ ] 矛盾防止ガイドライン

#### Tests
- [ ] エージェント出力の検証（実活動で実行）
  - [ ] efficiency: 評価文のみ生成（表なし）
  - [ ] summary: needs_improvement判定の正確性
  - [ ] 矛盾チェック（GCT優秀 ≠ GCT改善必要）
  - [ ] トークン削減率測定（目標: 70%）

### Phase 5: Report Generation Extension (2-3時間)

**目標**: レポート生成Workerの拡張

#### Tasks
- [ ] `tools/reporting/report_generator_worker.py` 修正
  - [ ] `_generate_individual_report()` 修正
  - [ ] form_evaluations テーブル読込追加
  - [ ] section_analyses から評価文取得
  - [ ] テンプレートに両方渡す
- [ ] `tools/reporting/templates/detailed_report.j2` 修正
  - [ ] フォーム効率セクション修正
  - [ ] 表生成ロジック追加（Jinja2ループ）
  - [ ] 実測値・期待値・偏差・★評価を表示
  - [ ] 評価文セクション追加

#### Jinja2テンプレート例
```jinja2
## フォーム効率（ペース補正評価） ({{ form_evaluation.overall_star_rating }} {{ form_evaluation.overall_score|round(1) }}/100)

### 指標詳細

| 指標 | 実測値 | 期待値 | 偏差 | 評価 |
|------|--------|--------|------|------|
| **接地時間 (GCT)** | {{ form_evaluation.gct.actual|round(1) }}ms | {{ form_evaluation.gct.expected|round(1) }}ms | {{ form_evaluation.gct.delta_pct|round(1) }}% | {{ form_evaluation.gct.star_rating }} {{ form_evaluation.gct.score|round(1) }}/100 |
| **垂直振幅 (VO)** | {{ form_evaluation.vo.actual|round(2) }}cm | {{ form_evaluation.vo.expected|round(2) }}cm | {{ form_evaluation.vo.delta_cm|round(2) }}cm | {{ form_evaluation.vo.star_rating }} {{ form_evaluation.vo.score|round(1) }}/100 |
| **垂直比率 (VR)** | {{ form_evaluation.vr.actual|round(2) }}% | {{ form_evaluation.vr.expected|round(2) }}% | {{ form_evaluation.vr.delta_pct|round(1) }}% | {{ form_evaluation.vr.star_rating }} {{ form_evaluation.vr.score|round(1) }}/100 |
| **ケイデンス** | {{ form_evaluation.cadence.actual|round(0) }}spm | {{ form_evaluation.cadence.minimum }}spm以上 | - | {% if form_evaluation.cadence.achieved %}✓ 達成{% else %}要改善{% endif %} |

### 評価コメント

{{ efficiency_text }}
```

#### Tests
- [ ] レポート生成の検証（実活動）
  - [ ] 表が正しく生成されているか
  - [ ] 評価文セクションが含まれているか
  - [ ] 矛盾がないか（表と評価文の一致）

### Phase 6: Testing & Validation (2-3時間)

**目標**: システム全体の動作確認・性能検証

#### Tasks
- [ ] 訓練実行: `uv run python tools/scripts/train_form_baselines.py`
  - [ ] 100+活動から係数生成
  - [ ] 単調性確認（d < 0）
  - [ ] RMSE確認（GCT: <10ms, VO: <1cm, VR: <1%）
  - [ ] form_baselines テーブル確認
- [ ] 評価実行: `uv run python -m tools.planner.workflow_planner 2025-10-25`
  - [ ] form_evaluations 生成確認
  - [ ] 評価文の自然さ確認
  - [ ] 期待値の妥当性確認
- [ ] エージェント実行: 5エージェント並列
  - [ ] efficiency: 評価文のみ生成（表なし）
  - [ ] summary: needs_improvement=true のみ改善提案
  - [ ] 矛盾チェック
- [ ] レポート生成: `report_generator_worker`
  - [ ] 表が正しく生成
  - [ ] 評価文が含まれる
  - [ ] 全体の一貫性

#### Performance Tests
- [ ] 訓練時間: <5分（1800+ samples）
- [ ] 評価時間: <1秒/活動
- [ ] エージェント: トークン削減率 70%
- [ ] MCP: レスポンス <100ms

#### Validation Criteria
- [ ] 2025-10-25活動で矛盾ゼロ
  - GCT 258ms → "優秀" (efficiency) = "達成済み" (summary)
- [ ] ペース補正の正確性
  - Fast (5:00/km) GCT 216ms → 優秀
  - Easy (7:11/km) GCT 258ms → 優秀
- [ ] トークン削減: efficiency-section-analyst ~800 → ~300

---

## テスト計画

### Unit Tests

#### `tests/form_baseline/test_utils.py`
- [ ] `test_drop_outliers_iqr()` - IQR法外れ値除去の正確性
- [ ] `test_to_speed_conversion()` - ペース→速度変換の正確性
- [ ] `test_edge_cases()` - ゼロ値・負値ハンドリング

#### `tests/form_baseline/test_trainer.py`
- [ ] `test_fit_gct_power_monotonicity()` - d < 0保証
- [ ] `test_fit_gct_power_ransac_fallback()` - RANSAC動作確認
- [ ] `test_fit_linear_vo()` - VO線形モデル係数精度
- [ ] `test_fit_linear_vr()` - VR線形モデル係数精度
- [ ] `test_insufficient_data()` - 少数サンプル時のエラー

#### `tests/form_baseline/test_predictor.py`
- [ ] `test_predict_expectations_accuracy()` - 既知データで期待値検証
- [ ] `test_predict_out_of_range_warning()` - 速度範囲外警告
- [ ] `test_missing_baselines_error()` - 基準値未訓練時のエラー

#### `tests/form_baseline/test_scorer.py`
- [ ] `test_score_gct_within_tolerance()` - ±5%以内で高評価
- [ ] `test_score_gct_penalty_calculation()` - ペナルティ計算正確性
- [ ] `test_star_rating_boundaries()` - ★評価境界値（95, 85, 75, 65）
- [ ] `test_needs_improvement_threshold()` - penalty > 10判定

#### `tests/form_baseline/test_text_generator.py`
- [ ] `test_generate_gct_text_excellent()` - 優秀時の評価文
- [ ] `test_generate_gct_text_needs_improvement()` - 要改善時の評価文
- [ ] `test_japanese_natural_language()` - 日本語自然性チェック

### Integration Tests

#### `tests/form_baseline/test_evaluator_integration.py`
- [ ] `test_evaluate_and_store_full_flow()` - 実データでの評価フロー
- [ ] `test_form_evaluations_saved()` - DuckDB保存検証
- [ ] `test_evaluation_consistency()` - 再評価時の一貫性

#### `tests/integration/test_workflow_planner_form_evaluation.py`
- [ ] `test_workflow_includes_form_evaluation()` - workflow_planner統合
- [ ] `test_error_handling_no_baselines()` - 基準値未訓練時のエラー

#### `tests/integration/test_mcp_form_evaluations.py`
- [ ] `test_get_form_evaluations_json_schema()` - JSONスキーマ検証
- [ ] `test_get_form_evaluations_performance()` - レスポンス<100ms

### Performance Tests

#### `tests/performance/test_training_performance.py`
- [ ] `test_training_time_1800_samples()` - 訓練時間 <5分
- [ ] `test_model_accuracy_rmse()` - RMSE閾値（GCT<10ms, VO<1cm, VR<1%）

#### `tests/performance/test_evaluation_performance.py`
- [ ] `test_evaluation_time_single_activity()` - 評価時間 <1秒
- [ ] `test_batch_evaluation_100_activities()` - 100活動評価 <2分

### Agent Tests

#### `tests/agents/test_efficiency_section_analyst.py`
- [ ] `test_output_format_no_table()` - 表データ含まない検証
- [ ] `test_token_reduction()` - トークン削減率 70%測定
- [ ] `test_evaluation_consistency()` - summary-section-analystとの一貫性

#### `tests/agents/test_summary_section_analyst.py`
- [ ] `test_needs_improvement_filtering()` - needs_improvement=trueのみ提案
- [ ] `test_no_achieved_goals()` - 達成済み目標を含まない
- [ ] `test_no_contradiction()` - efficiency-section-analystとの矛盾ゼロ

### Validation Tests

#### `tests/validation/test_2025_10_25_activity.py`
- [ ] `test_gct_258ms_evaluation_consistency()` - GCT 258ms矛盾ゼロ検証
- [ ] `test_pace_correction_fast_run()` - Fast Run GCT 216ms優秀
- [ ] `test_pace_correction_easy_run()` - Easy Run GCT 258ms優秀

---

## 受け入れ基準

### 機能要件
- [ ] **統一基準**: 全エージェント・Workerが同じ基準値使用（form_baselines読込）
- [ ] **ペース補正**: 速度に応じた期待値計算が正確（冪乗回帰・線形回帰）
- [ ] **一貫性**: 同一活動で矛盾した評価がゼロ（efficiency ⇔ summary）
- [ ] **評価保存**: form_evaluations テーブルに評価結果が保存される
- [ ] **MCP拡張**: `get_form_evaluations()` が正しいJSONを返す
- [ ] **日本語評価文**: 自然で読みやすい評価文が生成される

### 品質要件
- [ ] **単調性**: GCT冪乗モデルで d < 0 保証
- [ ] **精度**: RMSE（GCT<10ms, VO<1cm, VR<1%）
- [ ] **カバレッジ**: ユニットテスト80%以上
- [ ] **コード品質**: Black, Ruff, Mypy合格
- [ ] **Pre-commit**: 全フックパス

### パフォーマンス要件
- [ ] **訓練時間**: 1800+ samples を <5分で処理
- [ ] **評価時間**: 単一活動を <1秒で評価
- [ ] **MCP応答**: <100ms
- [ ] **トークン削減**: efficiency-section-analyst ~70%削減

### ドキュメント要件
- [ ] **CLAUDE.md**: Form Baseline System使用方法追記
- [ ] **completion_report.md**: 実装詳細・成果・制約事項記載
- [ ] **コメント**: 全公開API関数にdocstring

### 検証要件
- [ ] **実活動検証**: 2025-10-25活動で矛盾ゼロ
  - GCT 258ms → efficiency: "優秀" = summary: "達成済み"
- [ ] **ペース補正検証**: Fast/Easy Runで異なる期待値
  - Fast (5:00/km): GCT期待 ~215ms
  - Easy (7:11/km): GCT期待 ~260ms
- [ ] **レポート検証**: 表と評価文が一致

---

## 技術的制約

### DuckDB
- 新テーブル追加: `form_baselines`, `form_evaluations`
- 既存データに影響なし（読取専用）
- スキーマ変更は `db_writer.py` の `_ensure_tables()` のみ

### Python
- Python 3.12+
- 新依存パッケージ: scikit-learn, pandas, numpy（既存環境に含まれる）
- 型ヒント必須（Mypy検証）

### MCP
- サーバー再起動が必要（ツール追加時）
- JSONスキーマ安定性重視（後方互換性）

### エージェント
- プロンプト変更は慎重に（安定性重視）
- 既存動作を破壊しない（後方互換性）
- トークン削減と品質のバランス

### Git Worktree
- Main branchで計画（このドキュメント）
- 実装はworktree (`feature/unified-form-evaluation`)
- 完了後にmainへマージ

---

## リスクと対策

### Risk 1: 単調性チェック失敗
**リスク**: GCT冪乗モデルで d ≥ 0 になる可能性
**影響**: 期待値計算が物理的に不正確
**対策**:
- Huber回帰失敗時にRANSAC fallback
- 訓練データの外れ値除去（IQR法）
- 最悪時は固定基準値にフォールバック

### Risk 2: 速度範囲外での予測
**リスク**: 訓練データ外の速度で期待値を予測
**影響**: 外挿により不正確な期待値
**対策**:
- 速度範囲を `form_baselines` に保存
- 範囲外時に警告ログ出力
- Phase 2以降で分層（速度帯別モデル）検討

### Risk 3: エージェントプロンプト変更の影響
**リスク**: プロンプト修正により既存動作が破壊
**影響**: 他セクションの品質低下
**対策**:
- 最小限の変更（表削除のみ）
- 複数活動での動作検証
- ロールバック可能な設計（MCP切替可能）

### Risk 4: DuckDBテーブル作成タイミング
**リスク**: 既存環境で新テーブルが作成されない
**影響**: 評価実行時にエラー
**対策**:
- `db_writer.py` の `_ensure_tables()` で自動作成
- 初回実行時の手動確認手順をドキュメント化
- テストで新テーブル作成を検証

### Risk 5: トークン削減率未達成
**リスク**: 70%削減目標に届かない
**影響**: パフォーマンス改善が限定的
**対策**:
- 評価文テンプレート最適化
- 不要な説明文削除
- 実測トークン数で継続測定

---

## 成果物

### コード
- `tools/form_baseline/` (7ファイル)
  - `__init__.py`, `trainer.py`, `predictor.py`, `scorer.py`
  - `evaluator.py`, `text_generator.py`, `utils.py`
- `tools/scripts/train_form_baselines.py`
- `mcp-server/garmin-db/server.py` (get_form_evaluations追加)
- `tools/planner/workflow_planner.py` (評価呼び出し追加)
- `tools/reporting/report_generator_worker.py` (form_evaluations読込追加)
- `tools/reporting/templates/detailed_report.j2` (表生成ロジック追加)
- `.claude/agents/efficiency-section-analyst.md` (簡素化)
- `.claude/agents/summary-section-analyst.md` (needs_improvement使用)

### テスト
- `tests/form_baseline/` (5ファイル)
- `tests/integration/` (3ファイル)
- `tests/performance/` (2ファイル)
- `tests/agents/` (2ファイル)
- `tests/validation/` (1ファイル)

### ドキュメント
- `docs/project/2025-10-27_unified_form_evaluation_system/planning.md` (本ドキュメント)
- `docs/project/2025-10-27_unified_form_evaluation_system/completion_report.md` (完了後)
- `CLAUDE.md` 更新（Form Baseline System使用方法）

### データ
- DuckDB `form_baselines` テーブル（訓練済み係数）
- DuckDB `form_evaluations` テーブル（活動ごとの評価結果）

---

## 実装後の運用

### 初回訓練
```bash
# 基準値訓練（初回のみ/定期実行）
uv run python tools/scripts/train_form_baselines.py

# 確認
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb', read_only=True)
print(conn.execute('SELECT * FROM form_baselines').df())
"
```

### 日常利用
```bash
# 通常通りworkflow_planner実行（自動的に評価実行）
uv run python -m tools.planner.workflow_planner 2025-10-25

# 確認
uv run python -c "
import duckdb
conn = duckdb.connect('data/database/garmin_performance.duckdb', read_only=True)
print(conn.execute('SELECT activity_id, overall_score, overall_star_rating FROM form_evaluations ORDER BY activity_id DESC LIMIT 5').df())
"
```

### 定期更新（月次推奨）
```bash
# 新規活動データが100件以上追加されたら再訓練
uv run python tools/scripts/train_form_baselines.py

# 過去評価の再実行（オプション）
# → 基準値更新後、過去活動を再評価する場合
uv run python tools/scripts/reevaluate_all_activities.py
```

### MCPツール使用例（エージェント内）
```python
# efficiency-section-analyst.md
form_eval = mcp__garmin-db__get_form_evaluations(activity_id=20790040925)

# 評価文生成（表データなし）
評価文: {form_eval['gct']['evaluation_text']}
```

---

## 拡張性

### Phase 2（将来拡張）
- **地形別分層**: 平坦/坂道/トレイルで異なる基準値
- **速度帯別モデル**: Fast/Tempo/Easy/Recoveryで個別訓練
- **左右差分析**: GCT左右差の詳細評価
- **時系列分析**: 月次でのフォーム進化トラッキング

### Phase 3（高度な機能）
- **異常検知**: 急激なフォーム悪化の自動アラート
- **推奨トレーニング**: フォーム改善のためのドリル提案
- **レース予測**: フォーム効率からゴールタイム予測

---

## 参考資料

### 既存プロジェクト
- `2025-10-17_intensity_aware_phase_evaluation`: Training type導入の先例
- `2025-10-13_form_anomaly_api_refactoring`: Form metrics API設計の参考
- `2025-10-12_mcp_tool_refactoring`: MCP拡張のベストプラクティス

### 技術文献
- scikit-learn HuberRegressor: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.HuberRegressor.html
- 冪乗則回帰: Power law fitting in Python

### データソース
- DuckDB `splits` テーブル: 1800+ samples
- 既存 `form_efficiency` テーブル: 参考用（廃止予定なし）

---

## 完了判定

### Phase 1完了条件
- [ ] 全Unit Tests合格
- [ ] 訓練スクリプトが実行可能（係数保存確認）
- [ ] 単調性チェック動作確認

### Phase 2完了条件
- [ ] Integration Tests合格
- [ ] workflow_planner統合動作確認
- [ ] form_evaluationsテーブル生成確認

### Phase 3完了条件
- [ ] MCPツール動作確認
- [ ] JSONスキーマ検証合格

### Phase 4完了条件
- [ ] エージェント出力検証（矛盾ゼロ）
- [ ] トークン削減率測定（70%達成）

### Phase 5完了条件
- [ ] レポート生成動作確認
- [ ] 表と評価文の一貫性確認

### Phase 6完了条件
- [ ] 全Performance Tests合格
- [ ] 実活動検証（2025-10-25）合格
- [ ] Pre-commit hooks合格

### プロジェクト完了条件
- [ ] 全受け入れ基準達成
- [ ] completion_report.md作成
- [ ] GitHub Issue解決
- [ ] Main branchへマージ
- [ ] プロジェクトディレクトリをアーカイブ移動
