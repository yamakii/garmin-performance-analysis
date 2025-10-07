# Phase 3: Multivariate Correlation Analysis - Specifications

**Document Version**: 1.0
**Last Updated**: 2025-10-07
**Status**: Planned (Not Yet Implemented)
**Estimated Duration**: 9-13 days

## Executive Summary

Phase 3 implements multivariate correlation analysis to answer "why" questions about performance variations. By integrating wellness metrics (sleep, stress, Body Battery) with existing performance data, the system will provide causal insights and actionable recommendations for training optimization.

### Key Objectives
1. Integrate wellness data from Garmin API
2. Implement statistical correlation analysis
3. Generate natural language insights
4. Enable "why" question queries
5. Provide training load impact analysis

### Success Criteria
- ✅ Wellness data collection pipeline functional
- ✅ Statistical correlations calculated with p-values
- ✅ Natural language insights generated automatically
- ✅ "Why" questions answerable via MCP tools
- ✅ All tests passing with >80% coverage

---

## Motivation: From "What" to "Why"

### Current Capabilities (Phase 0-2)
Phase 0-2 answers **"what"** questions:
- What was my pace trend last month? (get_performance_trends)
- What activities are similar to today's workout? (compare_similar_workouts)
- What improvements did I make? (extract_insights)

### Phase 3 Capabilities
Phase 3 answers **"why"** questions:
- **Why was today's pace slow?** → Correlation: Poor sleep (65 score) + high stress (71) → -8.3% pace
- **Why do I fatigue quickly on hot days?** → Correlation: Temp >27°C + inadequate hydration → +15.2% HR drift
- **Why is my cadence unstable?** → Correlation: Body Battery <30 + 2 days without recovery → -12% cadence stability
- **Why did I perform well despite fatigue?** → Positive correlation: Good sleep (88 score) offset low Body Battery

### Example User Scenarios

**Scenario 1: Post-Run Analysis**
```
User: "今日のペースが遅かったのはなぜですか？" (Why was today's pace slow?)

System Query:
1. Get today's performance (pace 15s slower than average)
2. Get today's wellness data (sleep: 62, stress: 68, Body Battery: 42)
3. Calculate correlations
4. Generate insight

Response:
"今日のペース低下（-5.8%）の主な要因:
1. 睡眠スコア62（平均より-18ポイント）→ ペース-3.2%の相関（p<0.05）
2. ストレスレベル68（高）→ ペース-2.1%の相関（p<0.05）
3. Body Battery 42（低）→ HR Drift +8.9%の相関（p<0.01）

推奨: 今日は回復ランにする、明日は休息日を検討"
```

**Scenario 2: Training Planning**
```
User: "最近疲労が溜まっているが、練習を続けて大丈夫か？"
      (I've been accumulating fatigue, is it safe to continue training?)

System Query:
1. Get last 7 days training load (TSS累積)
2. Get last 7 days wellness trends (sleep, stress, Body Battery)
3. Calculate fatigue accumulation pattern
4. Compare to historical recovery patterns

Response:
"過去7日間の分析:
- トレーニング負荷: 累積TSS 580（通常より+23%高い）
- 睡眠スコア平均: 68（通常より-12ポイント低い）
- Body Battery回復率: 72%（通常より-15%低い）
- HR Drift傾向: +6.3%/日（疲労蓄積の兆候）

⚠️ 警告: 現在の状態は過去のオーバートレーニングパターンに類似
推奨: 2-3日の完全休養、またはEasy Run（60分以下）のみ"
```

**Scenario 3: Performance Optimization**
```
User: "来週の10kmレースで最高のパフォーマンスを出すには？"
      (How can I achieve best performance in next week's 10km race?)

System Query:
1. Find best past 10km performances
2. Analyze wellness conditions on those days
3. Identify optimal condition patterns
4. Compare to current trajectory

Response:
"過去のベストパフォーマンス時の共通条件:
1. 睡眠スコア: 85-92（現在: 78 → +7-14ポイント必要）
2. ストレスレベル: 25-35（現在: 48 → -13-23ポイント必要）
3. Body Battery: 85-95（現在: 68 → +17-27ポイント必要）
4. 前日の運動: 完全休養 or 30分以下のEasy Run

推奨7日間プラン:
- Day 1-3: Easy Run 30-40分（疲労抜き）
- Day 4-5: 完全休養（Body Battery回復）
- Day 6: 20分軽めのジョグ（動作確認）
- Day 7: レース当日（Target条件達成見込み: 85%）"
```

---

## Data Sources

### 3.1: Wellness Metrics (New Data Collection)

#### Garmin MCP API Endpoints
```python
# Sleep data
mcp__garmin__get_sleep_data(date="2025-10-07")
# Returns: {
#   "dailySleepDTO": {
#     "sleepScores": {
#       "overall": {"value": 82},  # 0-100
#       "rem": {"value": 15},
#       "deep": {"value": 18},
#       "light": {"value": 55}
#     },
#     "sleepTimeSeconds": 28800,  # 8 hours
#     "sleepStartTimestampGMT": "2025-10-06T22:30:00",
#     "sleepEndTimestampGMT": "2025-10-07T06:30:00"
#   }
# }

# Stress data
mcp__garmin__get_stress_data(date="2025-10-07")
# Returns: {
#   "avgStressLevel": 35,  # 0-100 (lower is better)
#   "maxStressLevel": 62,
#   "stressValuesArray": [...],  # Hourly stress values
#   "restStressDuration": 18000  # Seconds in rest state
# }

# Body Battery data
mcp__garmin__get_body_battery(
    start_date="2025-10-07",
    end_date="2025-10-07"
)
# Returns: [{
#   "date": "2025-10-07",
#   "charged": 45,  # Energy gained
#   "drained": 60,  # Energy spent
#   "bodyBatteryValuesArray": [...]  # Hourly BB values (0-100)
# }]

# Training readiness
mcp__garmin__get_training_readiness(date="2025-10-07")
# Returns: {
#   "trainingReadinessLevel": "BALANCED",  # LOW/BALANCED/HIGH
#   "trainingReadinessScore": 72,  # 0-100
#   "recoveryTimeHours": 24,
#   "hrv7DayAverage": 45.2
# }
```

#### Data Fields to Collect
| Field | Source | Type | Description |
|-------|--------|------|-------------|
| sleep_score | get_sleep_data | int (0-100) | Overall sleep quality |
| sleep_duration_hours | get_sleep_data | float | Total sleep time |
| rem_percentage | get_sleep_data | int (0-100) | REM sleep % |
| deep_percentage | get_sleep_data | int (0-100) | Deep sleep % |
| stress_level | get_stress_data | int (0-100) | Daily average stress |
| max_stress | get_stress_data | int (0-100) | Peak stress level |
| rest_stress_duration_hours | get_stress_data | float | Time in rest state |
| body_battery_start | get_body_battery | int (0-100) | BB at day start |
| body_battery_end | get_body_battery | int (0-100) | BB at day end |
| body_battery_charged | get_body_battery | int | Energy gained |
| body_battery_drained | get_body_battery | int | Energy spent |
| training_readiness_score | get_training_readiness | int (0-100) | Readiness score |
| training_readiness_level | get_training_readiness | str | LOW/BALANCED/HIGH |
| recovery_time_hours | get_training_readiness | int | Recommended recovery |
| hrv_7day_avg | get_training_readiness | float | Heart rate variability |

### 3.2: Training Load Metrics (From Existing Data)

#### Already Available in activities table
- aerobic_te (Aerobic Training Effect)
- anaerobic_te (Anaerobic Training Effect)
- duration_seconds
- distance_km

#### Need to Calculate
- **TSS (Training Stress Score)**: Estimated from duration × intensity
  - Formula: `TSS = duration_hours × (aerobic_te + anaerobic_te) × 50`
  - Example: 1 hour × (3.5 + 1.2) × 50 = 235 TSS

- **Cumulative Training Load**: Rolling 7-day TSS sum
  - Track training load accumulation
  - Identify overtraining risk periods

- **Recovery Time Deficit**: Actual recovery vs recommended
  - Compare time between workouts vs recovery_time_hours
  - Identify insufficient recovery patterns

---

## DuckDB Schema Extensions

### 3.1: New Table: wellness_metrics

```sql
CREATE TABLE wellness_metrics (
    date DATE PRIMARY KEY,
    sleep_score INTEGER,                    -- 0-100
    sleep_duration_hours FLOAT,
    rem_percentage INTEGER,                 -- 0-100
    deep_percentage INTEGER,                -- 0-100
    stress_level INTEGER,                   -- 0-100 (lower is better)
    max_stress INTEGER,                     -- 0-100
    rest_stress_duration_hours FLOAT,
    body_battery_start INTEGER,             -- 0-100
    body_battery_end INTEGER,               -- 0-100
    body_battery_charged INTEGER,           -- Energy gained
    body_battery_drained INTEGER,           -- Energy spent
    training_readiness_score INTEGER,       -- 0-100
    training_readiness_level VARCHAR,       -- LOW/BALANCED/HIGH
    recovery_time_hours INTEGER,            -- Recommended recovery
    hrv_7day_avg FLOAT,                     -- Heart rate variability
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast date lookups
CREATE INDEX idx_wellness_date ON wellness_metrics(date);
```

### 3.2: New Table: training_load_history

```sql
CREATE TABLE training_load_history (
    date DATE PRIMARY KEY,
    daily_tss FLOAT,                        -- Training Stress Score
    cumulative_7day_tss FLOAT,              -- Rolling 7-day sum
    cumulative_14day_tss FLOAT,             -- Rolling 14-day sum
    cumulative_30day_tss FLOAT,             -- Rolling 30-day sum
    recovery_time_deficit_hours INTEGER,    -- Actual vs recommended
    training_load_status VARCHAR,           -- LIGHT/MODERATE/HIGH/EXTREME
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (date) REFERENCES activities(activity_date)
);

-- Index for fast date lookups
CREATE INDEX idx_training_load_date ON training_load_history(date);
```

### 3.3: Updated Table: activities (add foreign key support)

```sql
-- Add wellness metrics foreign key (conceptual, dates align)
-- No schema change needed, but correlation queries will join on date
```

---

## Implementation Architecture

### 3.1: Data Collection Layer

#### Class: WellnessDataCollector

**File**: `tools/rag/collectors/wellness_collector.py`

**Purpose**: Collect wellness data from Garmin API and store in DuckDB

**Methods**:
```python
class WellnessDataCollector:
    def __init__(self, db_path: str = "data/database/garmin_performance.duckdb"):
        self.db_path = db_path
        self.garmin_client = GarminMCPClient()  # MCP client wrapper

    def collect_date(self, date: str) -> Dict[str, Any]:
        """Collect all wellness data for a specific date."""
        sleep = self._collect_sleep(date)
        stress = self._collect_stress(date)
        body_battery = self._collect_body_battery(date)
        readiness = self._collect_training_readiness(date)

        return self._merge_wellness_data(sleep, stress, body_battery, readiness)

    def collect_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Collect wellness data for a date range."""
        dates = self._generate_date_range(start_date, end_date)
        results = []
        for date in dates:
            try:
                data = self.collect_date(date)
                results.append(data)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                logger.error(f"Failed to collect {date}: {e}")
        return results

    def save_to_duckdb(self, wellness_data: List[Dict]) -> None:
        """Insert wellness data into DuckDB."""
        conn = duckdb.connect(self.db_path)

        for record in wellness_data:
            conn.execute("""
                INSERT OR REPLACE INTO wellness_metrics (
                    date, sleep_score, sleep_duration_hours, ...
                ) VALUES (?, ?, ?, ...)
            """, [record["date"], record["sleep_score"], ...])

        conn.close()

    def backfill_historical_data(self, days: int = 90) -> None:
        """Backfill wellness data for past N days."""
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        wellness_data = self.collect_date_range(
            str(start_date), str(end_date)
        )
        self.save_to_duckdb(wellness_data)
```

**Testing Strategy**:
```python
# tools/rag/test_wellness_collector.py
def test_collect_single_date():
    collector = WellnessDataCollector()
    data = collector.collect_date("2025-10-07")

    assert "sleep_score" in data
    assert 0 <= data["sleep_score"] <= 100
    assert "stress_level" in data
    assert "body_battery_start" in data

def test_backfill_saves_to_duckdb():
    collector = WellnessDataCollector()
    collector.backfill_historical_data(days=7)

    conn = duckdb.connect(collector.db_path)
    result = conn.execute(
        "SELECT COUNT(*) FROM wellness_metrics WHERE date >= DATE_SUB(CURRENT_DATE, 7)"
    ).fetchone()

    assert result[0] == 7
```

#### Class: TrainingLoadCalculator

**File**: `tools/rag/calculators/training_load.py`

**Purpose**: Calculate TSS and training load metrics

**Methods**:
```python
class TrainingLoadCalculator:
    def __init__(self, db_path: str = "data/database/garmin_performance.duckdb"):
        self.db_path = db_path

    def calculate_tss(self, activity_id: int) -> float:
        """Calculate TSS for a single activity."""
        conn = duckdb.connect(self.db_path)

        result = conn.execute("""
            SELECT duration_seconds, aerobic_te, anaerobic_te
            FROM activities WHERE activity_id = ?
        """, [activity_id]).fetchone()

        duration_hours = result[0] / 3600
        aerobic_te = result[1] or 0
        anaerobic_te = result[2] or 0

        tss = duration_hours * (aerobic_te + anaerobic_te) * 50
        return round(tss, 1)

    def calculate_cumulative_load(self, date: str, window_days: int = 7) -> float:
        """Calculate cumulative TSS for N-day window."""
        conn = duckdb.connect(self.db_path)

        result = conn.execute("""
            SELECT SUM(daily_tss)
            FROM training_load_history
            WHERE date BETWEEN DATE_SUB(?, INTERVAL ? DAY) AND ?
        """, [date, window_days, date]).fetchone()

        return result[0] or 0.0

    def calculate_recovery_deficit(self, date: str) -> int:
        """Calculate recovery time deficit."""
        conn = duckdb.connect(self.db_path)

        # Get recommended recovery time from wellness data
        result = conn.execute("""
            SELECT recovery_time_hours FROM wellness_metrics
            WHERE date = ?
        """, [date]).fetchone()

        recommended_hours = result[0] if result else 24

        # Get actual time since last workout
        last_activity = conn.execute("""
            SELECT activity_date FROM activities
            WHERE activity_date < ?
            ORDER BY activity_date DESC LIMIT 1
        """, [date]).fetchone()

        if not last_activity:
            return 0

        actual_hours = (
            datetime.fromisoformat(date) -
            datetime.fromisoformat(last_activity[0])
        ).total_seconds() / 3600

        deficit = max(0, recommended_hours - actual_hours)
        return int(deficit)

    def update_training_load_history(self) -> None:
        """Recalculate training load for all activities."""
        conn = duckdb.connect(self.db_path)

        activities = conn.execute("""
            SELECT activity_id, activity_date FROM activities
            ORDER BY activity_date
        """).fetchall()

        for activity_id, date in activities:
            tss = self.calculate_tss(activity_id)
            cum_7day = self.calculate_cumulative_load(date, 7)
            cum_14day = self.calculate_cumulative_load(date, 14)
            cum_30day = self.calculate_cumulative_load(date, 30)
            recovery_deficit = self.calculate_recovery_deficit(date)

            # Determine training load status
            if cum_7day < 300:
                status = "LIGHT"
            elif cum_7day < 500:
                status = "MODERATE"
            elif cum_7day < 700:
                status = "HIGH"
            else:
                status = "EXTREME"

            conn.execute("""
                INSERT OR REPLACE INTO training_load_history (
                    date, daily_tss, cumulative_7day_tss, cumulative_14day_tss,
                    cumulative_30day_tss, recovery_time_deficit_hours,
                    training_load_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [date, tss, cum_7day, cum_14day, cum_30day, recovery_deficit, status])
```

### 3.2: Statistical Analysis Layer

#### Class: CorrelationAnalyzer

**File**: `tools/rag/analytics/correlation_analyzer.py`

**Purpose**: Calculate statistical correlations between wellness and performance metrics

**Methods**:
```python
import numpy as np
from scipy import stats
from typing import Dict, List, Tuple

class CorrelationAnalyzer:
    def __init__(self, db_path: str = "data/database/garmin_performance.duckdb"):
        self.db_path = db_path

    def analyze_wellness_performance_correlation(
        self,
        performance_metric: str,  # e.g., "avg_pace", "hr_drift"
        wellness_metric: str,     # e.g., "sleep_score", "body_battery_start"
        period: str = "1M",
        min_samples: int = 10
    ) -> Dict[str, Any]:
        """
        Analyze correlation between wellness and performance metrics.

        Returns:
        {
            "correlation_coefficient": float,  # -1 to 1
            "p_value": float,                  # Statistical significance
            "is_significant": bool,            # p < 0.05
            "direction": str,                  # "positive", "negative", "none"
            "strength": str,                   # "strong", "moderate", "weak"
            "interpretation": str,             # Natural language insight
            "data_points": int,                # Sample size
            "scatter_data": List[Tuple]        # For visualization
        }
        """
        # Get data from DuckDB
        conn = duckdb.connect(self.db_path)

        query = f"""
            SELECT
                a.activity_date,
                a.{performance_metric},
                w.{wellness_metric}
            FROM activities a
            JOIN wellness_metrics w ON a.activity_date = w.date
            WHERE a.activity_date >= DATE_SUB(CURRENT_DATE, INTERVAL '{period}')
              AND a.{performance_metric} IS NOT NULL
              AND w.{wellness_metric} IS NOT NULL
            ORDER BY a.activity_date
        """

        result = conn.execute(query).fetchall()
        conn.close()

        if len(result) < min_samples:
            return {
                "error": f"Insufficient data: {len(result)} samples (minimum {min_samples})"
            }

        # Extract arrays
        performance_values = np.array([r[1] for r in result])
        wellness_values = np.array([r[2] for r in result])

        # Calculate Pearson correlation
        corr_coef, p_value = stats.pearsonr(performance_values, wellness_values)

        # Determine significance and strength
        is_significant = p_value < 0.05

        if abs(corr_coef) >= 0.7:
            strength = "strong"
        elif abs(corr_coef) >= 0.4:
            strength = "moderate"
        elif abs(corr_coef) >= 0.2:
            strength = "weak"
        else:
            strength = "negligible"

        if corr_coef > 0:
            direction = "positive"
        elif corr_coef < 0:
            direction = "negative"
        else:
            direction = "none"

        # Generate interpretation
        interpretation = self._generate_correlation_interpretation(
            performance_metric, wellness_metric,
            corr_coef, p_value, direction, strength
        )

        return {
            "correlation_coefficient": round(corr_coef, 3),
            "p_value": round(p_value, 4),
            "is_significant": is_significant,
            "direction": direction,
            "strength": strength,
            "interpretation": interpretation,
            "data_points": len(result),
            "scatter_data": [(r[2], r[1]) for r in result]  # (wellness, performance)
        }

    def find_top_correlations(
        self,
        performance_metric: str,
        period: str = "1M",
        top_n: int = 5
    ) -> List[Dict]:
        """
        Find top N wellness factors correlating with a performance metric.
        """
        wellness_metrics = [
            "sleep_score", "sleep_duration_hours", "rem_percentage",
            "stress_level", "body_battery_start", "body_battery_drained",
            "training_readiness_score", "hrv_7day_avg"
        ]

        correlations = []
        for wellness_metric in wellness_metrics:
            result = self.analyze_wellness_performance_correlation(
                performance_metric, wellness_metric, period
            )

            if "error" not in result and result["is_significant"]:
                correlations.append({
                    "wellness_metric": wellness_metric,
                    **result
                })

        # Sort by absolute correlation coefficient
        correlations.sort(
            key=lambda x: abs(x["correlation_coefficient"]),
            reverse=True
        )

        return correlations[:top_n]

    def analyze_multivariate_impact(
        self,
        performance_metric: str,
        date: str
    ) -> Dict[str, Any]:
        """
        Analyze multiple wellness factors' combined impact on a specific day's performance.

        This is the core "why" question answerer.
        """
        # Get today's values
        conn = duckdb.connect(self.db_path)

        today_data = conn.execute(f"""
            SELECT
                a.{performance_metric},
                w.sleep_score,
                w.stress_level,
                w.body_battery_start,
                w.training_readiness_score,
                tl.cumulative_7day_tss,
                tl.recovery_time_deficit_hours
            FROM activities a
            JOIN wellness_metrics w ON a.activity_date = w.date
            JOIN training_load_history tl ON a.activity_date = tl.date
            WHERE a.activity_date = ?
        """, [date]).fetchone()

        if not today_data:
            return {"error": f"No data found for {date}"}

        # Get baseline averages (past 30 days)
        baseline_data = conn.execute(f"""
            SELECT
                AVG(a.{performance_metric}),
                AVG(w.sleep_score),
                AVG(w.stress_level),
                AVG(w.body_battery_start),
                AVG(w.training_readiness_score),
                AVG(tl.cumulative_7day_tss)
            FROM activities a
            JOIN wellness_metrics w ON a.activity_date = w.date
            JOIN training_load_history tl ON a.activity_date = tl.date
            WHERE a.activity_date BETWEEN DATE_SUB(?, INTERVAL 30 DAY) AND ?
        """, [date, date]).fetchone()

        conn.close()

        # Calculate deviations
        perf_value, sleep, stress, bb, readiness, tss, recovery_def = today_data
        perf_avg, sleep_avg, stress_avg, bb_avg, readiness_avg, tss_avg = baseline_data

        deviations = {
            "sleep_score": sleep - sleep_avg,
            "stress_level": stress - stress_avg,
            "body_battery_start": bb - bb_avg,
            "training_readiness_score": readiness - readiness_avg,
            "cumulative_7day_tss": tss - tss_avg,
            "recovery_deficit": recovery_def
        }

        # Get correlations for each factor
        factors = []
        for metric, deviation in deviations.items():
            if abs(deviation) > 5:  # Only significant deviations
                corr_result = self.analyze_wellness_performance_correlation(
                    performance_metric, metric, period="2M"
                )

                if corr_result.get("is_significant"):
                    # Estimate impact
                    estimated_impact = (
                        deviation * corr_result["correlation_coefficient"] * 0.01
                    )

                    factors.append({
                        "factor": metric,
                        "deviation": round(deviation, 1),
                        "correlation": corr_result["correlation_coefficient"],
                        "estimated_impact_percent": round(estimated_impact, 2),
                        "interpretation": corr_result["interpretation"]
                    })

        # Sort by absolute impact
        factors.sort(key=lambda x: abs(x["estimated_impact_percent"]), reverse=True)

        # Generate overall insight
        total_impact = sum(f["estimated_impact_percent"] for f in factors)
        performance_change = ((perf_value - perf_avg) / perf_avg) * 100

        insight = self._generate_multivariate_insight(
            performance_metric, performance_change, factors, date
        )

        return {
            "date": date,
            "performance_metric": performance_metric,
            "actual_value": round(perf_value, 2),
            "baseline_avg": round(perf_avg, 2),
            "change_percent": round(performance_change, 2),
            "contributing_factors": factors,
            "total_estimated_impact_percent": round(total_impact, 2),
            "insight": insight
        }

    def _generate_correlation_interpretation(
        self, perf_metric: str, wellness_metric: str,
        corr_coef: float, p_value: float, direction: str, strength: str
    ) -> str:
        """Generate Japanese interpretation of correlation."""
        # Metric name translations
        perf_names = {
            "avg_pace": "ペース",
            "avg_heart_rate": "平均心拍数",
            "hr_drift": "HR Drift",
            "cadence_stability": "ピッチ安定性"
        }

        wellness_names = {
            "sleep_score": "睡眠スコア",
            "stress_level": "ストレスレベル",
            "body_battery_start": "Body Battery",
            "training_readiness_score": "トレーニング準備スコア"
        }

        perf_name = perf_names.get(perf_metric, perf_metric)
        wellness_name = wellness_names.get(wellness_metric, wellness_metric)

        if not p_value < 0.05:
            return f"{wellness_name}と{perf_name}の相関は統計的に有意ではありません"

        strength_text = {
            "strong": "強い",
            "moderate": "中程度の",
            "weak": "弱い"
        }[strength]

        direction_text = {
            "positive": "正の",
            "negative": "負の"
        }[direction]

        return f"{wellness_name}と{perf_name}の間に{strength_text}{direction_text}相関があります（r={corr_coef:.2f}, p={p_value:.3f}）"

    def _generate_multivariate_insight(
        self, perf_metric: str, change_percent: float,
        factors: List[Dict], date: str
    ) -> str:
        """Generate natural language insight for multivariate analysis."""
        if not factors:
            return f"{date}のパフォーマンス変化に明確な要因は見つかりませんでした"

        perf_names = {"avg_pace": "ペース", "hr_drift": "HR Drift"}
        perf_name = perf_names.get(perf_metric, perf_metric)

        change_text = "向上" if change_percent < 0 else "低下"

        insight_parts = [f"{date}の{perf_name}{change_text}（{abs(change_percent):.1f}%）の主な要因:"]

        for i, factor in enumerate(factors[:3], 1):  # Top 3 factors
            factor_name = {
                "sleep_score": "睡眠スコア",
                "stress_level": "ストレスレベル",
                "body_battery_start": "Body Battery",
                "cumulative_7day_tss": "トレーニング負荷"
            }.get(factor["factor"], factor["factor"])

            deviation = factor["deviation"]
            impact = factor["estimated_impact_percent"]

            deviation_text = f"+{deviation:.0f}" if deviation > 0 else f"{deviation:.0f}"
            impact_text = f"{abs(impact):.1f}%の影響"

            insight_parts.append(
                f"{i}. {factor_name} {deviation_text} → {impact_text}"
            )

        return "\n".join(insight_parts)
```

### 3.3: Query Interface Layer

#### MCP Tool: analyze_performance_why

**File**: `servers/garmin_db_server.py` (add to existing tools)

**Tool Definition**:
```python
Tool(
    name="analyze_performance_why",
    description="Answer 'why' questions about performance variations using multivariate correlation analysis",
    inputSchema={
        "type": "object",
        "properties": {
            "performance_metric": {
                "type": "string",
                "description": "Performance metric to analyze: avg_pace, hr_drift, cadence_stability, etc."
            },
            "date": {
                "type": "string",
                "description": "Date to analyze in YYYY-MM-DD format"
            },
            "analysis_type": {
                "type": "string",
                "enum": ["single_factor", "multivariate", "top_correlations"],
                "description": "Type of analysis to perform"
            },
            "wellness_metric": {
                "type": "string",
                "description": "Wellness metric for single_factor analysis (optional)"
            }
        },
        "required": ["performance_metric", "date"]
    }
)
```

**Handler Implementation**:
```python
elif name == "analyze_performance_why":
    metric = arguments["performance_metric"]
    date = arguments["date"]
    analysis_type = arguments.get("analysis_type", "multivariate")

    analyzer = CorrelationAnalyzer()

    if analysis_type == "single_factor":
        wellness_metric = arguments["wellness_metric"]
        result = analyzer.analyze_wellness_performance_correlation(
            metric, wellness_metric, period="1M"
        )
    elif analysis_type == "top_correlations":
        result = analyzer.find_top_correlations(metric, period="1M")
    else:  # multivariate
        result = analyzer.analyze_multivariate_impact(metric, date)

    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
```

---

## Implementation Phases

### Phase 3.1: Data Collection Foundation (Days 1-3)

**Objectives**:
- Implement WellnessDataCollector
- Create DuckDB schema extensions
- Backfill historical data (60-90 days)

**Tasks**:
1. ✅ Create `wellness_metrics` table schema
2. ✅ Create `training_load_history` table schema
3. ✅ Implement WellnessDataCollector class
4. ✅ Test Garmin MCP endpoints (sleep, stress, BB, readiness)
5. ✅ Implement backfill script
6. ✅ Validate data quality (completeness, accuracy)

**Deliverables**:
- `tools/rag/collectors/wellness_collector.py`
- `tools/rag/test_wellness_collector.py`
- `tools/rag/scripts/backfill_wellness_data.py`
- DuckDB tables populated with 60-90 days data

**Success Criteria**:
- All 4 wellness data sources accessible
- Data completeness >95% for past 60 days
- Tests passing

### Phase 3.2: Training Load Calculation (Days 4-5)

**Objectives**:
- Implement TrainingLoadCalculator
- Calculate TSS for all activities
- Generate training load metrics

**Tasks**:
1. ✅ Implement TSS calculation formula
2. ✅ Calculate cumulative loads (7/14/30 day)
3. ✅ Implement recovery deficit calculation
4. ✅ Populate training_load_history table
5. ✅ Validate calculations against known values

**Deliverables**:
- `tools/rag/calculators/training_load.py`
- `tools/rag/test_training_load.py`
- training_load_history table populated

**Success Criteria**:
- TSS calculations reasonable (50-400 range for typical runs)
- Cumulative loads track expected patterns
- Recovery deficit calculation accurate

### Phase 3.3: Correlation Analysis Engine (Days 6-8)

**Objectives**:
- Implement CorrelationAnalyzer
- Calculate wellness-performance correlations
- Generate statistical insights

**Tasks**:
1. ✅ Implement Pearson correlation calculation
2. ✅ Add statistical significance testing (p-values)
3. ✅ Implement multivariate analysis
4. ✅ Create natural language interpretation generator
5. ✅ Validate with known correlations (e.g., sleep → pace)

**Deliverables**:
- `tools/rag/analytics/correlation_analyzer.py`
- `tools/rag/test_correlation_analyzer.py`

**Success Criteria**:
- Correlations detect expected patterns (e.g., good sleep → better pace)
- P-values correctly identify significant vs random correlations
- Multivariate analysis combines factors reasonably
- Japanese interpretations are accurate and natural

### Phase 3.4: MCP Integration (Days 9-10)

**Objectives**:
- Add new MCP tool: analyze_performance_why
- Integrate with CorrelationAnalyzer
- Test end-to-end query flow

**Tasks**:
1. ✅ Add tool definition to garmin_db_server.py
2. ✅ Implement tool handler
3. ✅ Test with Claude Code
4. ✅ Validate "why" question answers
5. ✅ Document usage examples

**Deliverables**:
- Updated `servers/garmin_db_server.py`
- `tools/rag/test_mcp_why_queries.py`
- Usage documentation in CLAUDE.md

**Success Criteria**:
- MCP tool callable from Claude
- Answers match expected insights
- Response time <5 seconds
- Error handling graceful

### Phase 3.5: Validation & Documentation (Days 11-13)

**Objectives**:
- Comprehensive testing
- User feedback validation
- Documentation completion

**Tasks**:
1. ✅ Create test scenarios for all "why" question types
2. ✅ Get user feedback on real queries
3. ✅ Refine interpretations based on feedback
4. ✅ Write comprehensive documentation
5. ✅ Create example queries and expected outputs
6. ✅ Git commit and phase completion report

**Deliverables**:
- `tools/rag/test_phase3_integration.py`
- `data/rag/phase3_completion_report.md`
- Updated CLAUDE.md with Phase 3 usage
- Git commit

**Success Criteria**:
- All tests passing
- User confirms accuracy of insights
- Documentation complete and clear
- Ready for production use

---

## Expected Insights Examples

### Example 1: Sleep Impact on Pace

**Query**:
```python
analyze_performance_why(
    performance_metric="avg_pace",
    date="2025-10-07",
    analysis_type="multivariate"
)
```

**Expected Output**:
```json
{
  "date": "2025-10-07",
  "performance_metric": "avg_pace",
  "actual_value": 278.5,
  "baseline_avg": 262.3,
  "change_percent": 6.2,
  "contributing_factors": [
    {
      "factor": "sleep_score",
      "deviation": -18.0,
      "correlation": -0.62,
      "estimated_impact_percent": 3.2,
      "interpretation": "睡眠スコアとペースの間に中程度の負の相関があります"
    },
    {
      "factor": "stress_level",
      "deviation": 15.0,
      "correlation": 0.45,
      "estimated_impact_percent": 2.1,
      "interpretation": "ストレスレベルとペースの間に中程度の正の相関があります"
    }
  ],
  "total_estimated_impact_percent": 5.3,
  "insight": "2025-10-07のペース低下（6.2%）の主な要因:\n1. 睡眠スコア -18 → 3.2%の影響\n2. ストレスレベル +15 → 2.1%の影響"
}
```

### Example 2: Fatigue Detection

**Query**:
```python
analyze_performance_why(
    performance_metric="hr_drift",
    date="2025-10-02",
    analysis_type="multivariate"
)
```

**Expected Output**:
```json
{
  "date": "2025-10-02",
  "performance_metric": "hr_drift",
  "actual_value": 16.3,
  "baseline_avg": 8.2,
  "change_percent": 98.8,
  "contributing_factors": [
    {
      "factor": "cumulative_7day_tss",
      "deviation": 120.0,
      "correlation": 0.58,
      "estimated_impact_percent": 45.2,
      "interpretation": "トレーニング負荷とHR Driftの間に中程度の正の相関があります"
    },
    {
      "factor": "body_battery_start",
      "deviation": -23.0,
      "correlation": -0.51,
      "estimated_impact_percent": 35.8,
      "interpretation": "Body BatteryとHR Driftの間に中程度の負の相関があります"
    },
    {
      "factor": "recovery_deficit",
      "deviation": 18.0,
      "correlation": 0.42,
      "estimated_impact_percent": 18.6,
      "interpretation": "回復不足とHR Driftの間に弱い正の相関があります"
    }
  ],
  "total_estimated_impact_percent": 99.6,
  "insight": "2025-10-02のHR Drift増加（98.8%）の主な要因:\n1. トレーニング負荷 +120 → 45.2%の影響\n2. Body Battery -23 → 35.8%の影響\n3. 回復不足 +18時間 → 18.6%の影響\n\n⚠️ 警告: 顕著な疲労蓄積が検出されました。休息日を推奨します。"
}
```

### Example 3: Top Correlations Discovery

**Query**:
```python
analyze_performance_why(
    performance_metric="avg_pace",
    date="2025-10-07",
    analysis_type="top_correlations"
)
```

**Expected Output**:
```json
[
  {
    "wellness_metric": "sleep_score",
    "correlation_coefficient": -0.62,
    "p_value": 0.0012,
    "is_significant": true,
    "strength": "moderate",
    "interpretation": "睡眠スコアとペースの間に中程度の負の相関があります"
  },
  {
    "wellness_metric": "body_battery_start",
    "correlation_coefficient": -0.54,
    "p_value": 0.0045,
    "is_significant": true,
    "strength": "moderate",
    "interpretation": "Body Batteryとペースの間に中程度の負の相関があります"
  },
  {
    "wellness_metric": "stress_level",
    "correlation_coefficient": 0.48,
    "p_value": 0.0089,
    "is_significant": true,
    "strength": "moderate",
    "interpretation": "ストレスレベルとペースの間に中程度の正の相関があります"
  }
]
```

---

## Testing Strategy

### 3.1: Unit Tests

**Test Files**:
- `tools/rag/test_wellness_collector.py` (WellnessDataCollector)
- `tools/rag/test_training_load.py` (TrainingLoadCalculator)
- `tools/rag/test_correlation_analyzer.py` (CorrelationAnalyzer)

**Coverage Goals**:
- >80% code coverage
- All public methods tested
- Edge cases handled (missing data, insufficient samples, etc.)

### 3.2: Integration Tests

**Test File**: `tools/rag/test_phase3_integration.py`

**Test Scenarios**:
1. End-to-end wellness data collection → correlation analysis
2. MCP tool query → natural language insight
3. Multivariate analysis with real data
4. Historical data backfill → training load calculation → correlation discovery

### 3.3: User Validation Tests

**Test File**: `tools/rag/test_phase3_user_scenarios.py`

**Scenarios**:
1. Reproduce user's fatigue detection scenario (10/2, 10/4, 10/5)
2. Test "why was pace slow" query
3. Test training load warnings
4. Validate correlation interpretations with user feedback

---

## Risk Analysis

### 3.1: Data Availability Risks

**Risk**: Garmin API may not provide all wellness data for past dates

**Mitigation**:
- Test data availability before implementation
- Implement graceful handling of missing data
- Use imputation for critical missing values (if appropriate)
- Document data limitations

**Contingency**:
- If <60% data availability, reduce analysis window to available dates
- Implement "data confidence" score in insights

### 3.2: Statistical Validity Risks

**Risk**: Insufficient sample size for reliable correlations

**Mitigation**:
- Require minimum 10-15 data points per correlation
- Report p-values to indicate confidence
- Warn users when sample size is low

**Contingency**:
- If insufficient data, recommend longer data collection period
- Provide qualitative insights instead of quantitative correlations

### 3.3: Interpretation Accuracy Risks

**Risk**: Natural language interpretations may be misleading

**Mitigation**:
- User feedback validation during Phase 3.5
- Include statistical details (r, p-value) in output
- Conservative interpretation language

**Contingency**:
- Iterative refinement based on user feedback
- Option to show "raw" correlation data without interpretation

### 3.4: Performance Risks

**Risk**: Complex queries may be slow

**Mitigation**:
- Optimize SQL queries with indexes
- Cache correlation results
- Limit analysis windows to reasonable periods (1-3 months)

**Contingency**:
- Implement query timeouts
- Provide progress indicators for long-running analyses

---

## Success Metrics

### 3.1: Technical Metrics

- ✅ Data collection pipeline: >95% success rate
- ✅ Correlation calculations: <5 seconds per query
- ✅ Test coverage: >80%
- ✅ MCP tool response time: <5 seconds
- ✅ Statistical significance: >70% of detected correlations have p<0.05

### 3.2: User Experience Metrics

- ✅ Insight accuracy: User confirms >80% of insights are correct
- ✅ Usefulness: User reports insights are actionable
- ✅ Clarity: Natural language interpretations are understandable
- ✅ Discovery: System identifies correlations user wasn't aware of

### 3.3: Business Value Metrics

- ✅ Training optimization: User makes data-driven training adjustments
- ✅ Injury prevention: Early fatigue detection prevents overtraining
- ✅ Performance improvement: User achieves performance goals faster

---

## Future Extensions (Post-Phase 3)

### Phase 4: Predictive Analytics (Future)

- Train machine learning models to predict performance
- "What if" scenario analysis ("If I sleep 8 hours tonight, what pace can I expect?")
- Optimal training schedule recommendations

### Phase 5: Advanced Wellness Integration (Future)

- Nutrition data integration (calories, macros, hydration)
- Environment data (temperature, humidity, altitude)
- Injury history and recovery patterns

### Phase 6: Multi-Sport Analysis (Future)

- Extend to cycling, swimming, strength training
- Cross-sport correlation analysis
- Training periodization optimization

---

## Conclusion

Phase 3 represents a transformative step in the RAG system, moving from descriptive "what" questions to explanatory "why" questions. By integrating wellness metrics and applying statistical correlation analysis, the system will provide actionable insights for training optimization, fatigue management, and performance improvement.

The 9-13 day implementation plan is designed to be incremental and testable, with clear deliverables and success criteria at each sub-phase. User feedback validation ensures the insights are accurate, useful, and aligned with real-world training needs.

Upon completion, Phase 3 will establish a solid foundation for future predictive analytics and advanced optimization features.

**Next Step**: Begin Phase 3.1 implementation (Data Collection Foundation) upon user approval.
