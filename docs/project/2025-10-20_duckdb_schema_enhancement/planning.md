# 計画: DuckDB Schema Enhancement - Calculate Missing Fields & Clean Unused Columns

## プロジェクト情報
- **プロジェクト名**: `duckdb_schema_enhancement`
- **作成日**: `2025-10-20`
- **ステータス**: 実装中
- **GitHub Issue**: #35
- **優先度**: High
- **推定工数**: 28-31 hours

---

## 要件定義

### 目的

Implement calculation logic for 28 unpopulated calculated fields and remove 6 device-unprovided fields from DuckDB schema to achieve 100% data population for all valid columns and create comprehensive schema documentation.

**Primary Goals:**
1. Implement calculation logic for 28 fields across 4 tables (splits, form_efficiency, hr_efficiency, performance_trends)
2. Remove 6 device-unprovided fields from schema (vo2_max, body_composition)
3. Create `docs/spec/duckdb_schema_mapping.md` - Complete schema documentation with calculation logic
4. Execute safe data migration for all 231 activities with backup
5. Achieve ≥95% population rate for all calculated fields

### 解決する問題

**Current Issue:**

Investigation of DuckDB schema revealed **35 columns with 0% population** across 6 tables:

**Category 1: Calculation Fields (28 fields) - Schema exists, logic NOT implemented**
- `splits` (7 fields): hr_zone, cadence_rating, power_efficiency, environmental_conditions, wind_impact, temp_impact, environmental_impact
- `form_efficiency` (4 fields): gct_evaluation, vo_trend, vo_evaluation, vr_evaluation
- `hr_efficiency` (6 fields): primary_zone, zone_distribution_rating, aerobic_efficiency, training_quality, zone2_focus, zone4_threshold_work
- `performance_trends` (12 fields): Phase-based calculations (warmup/run/recovery/cooldown avg_cadence, avg_power, evaluation)

**Category 2: Device-Unprovided Fields (6 fields) - Raw data always NULL**
- `vo2_max` (1 field): fitness_age
- `body_composition` (5 fields): basal_metabolic_rate, active_metabolic_rate, metabolic_age, visceral_fat_rating, physique_rating

**Category 3: Special Case (1 field) - Already Fixed**
- `splits.stride_length` - Fixed in PR #34 (cadence_column_refactoring)

**Impact:**
- **Wasted schema space**: 35 columns defined but never used
- **User confusion**: Queries return NULL for fields that appear queryable
- **Missed insights**: Evaluation fields (e.g., "gct_evaluation", "training_quality") could provide actionable feedback
- **Documentation gap**: No comprehensive schema mapping document exists
- **Data inconsistency**: Some calculated fields exist in code but not in database

**Example Confusion:**
```sql
-- Current (returns NULL unexpectedly):
SELECT gct_evaluation FROM form_efficiency WHERE activity_id = 12345;
-- Result: NULL (field exists but never calculated) ❌

-- After implementation (returns evaluation):
SELECT gct_evaluation FROM form_efficiency WHERE activity_id = 12345;
-- Result: "Excellent (220ms, optimal range)" ✅
```

### ユースケース

1. **Comprehensive Performance Evaluation**
   - User queries split-level HR zone distribution
   - System returns calculated HR zones based on heart_rate and zone boundaries
   - User gets immediate zone classification without manual calculation

2. **Form Efficiency Assessment**
   - User queries form_efficiency for GCT evaluation
   - System returns "Excellent/Good/Poor" rating with specific metrics
   - User receives actionable feedback (e.g., "Reduce GCT to <250ms")

3. **Training Quality Analysis**
   - User queries hr_efficiency for training_quality
   - System calculates zone distribution rating and aerobic efficiency
   - User understands if workout met training objectives

4. **Phase-Based Performance Trends**
   - User queries performance_trends for phase evaluations
   - System calculates warmup/run/recovery/cooldown metrics
   - User gets phase-specific feedback (e.g., "Warmup too short, <5 min")

5. **Environmental Impact Analysis**
   - User queries splits for environmental_impact
   - System evaluates combined effect of temperature, wind, terrain
   - User understands external factors affecting pace

6. **Schema Clarity and Documentation**
   - Developer queries schema for column definitions
   - System provides comprehensive documentation in `docs/spec/duckdb_schema_mapping.md`
   - Developer understands raw data source, calculation logic, population stats

7. **Clean Schema Migration**
   - Database admin removes device-unprovided fields
   - System migrates 231 activities without data loss
   - Admin verifies 100% population for calculated fields

---

## 設計

### アーキテクチャ

**Current State (35 Unpopulated Columns):**
```
Raw Data (API) → DuckDB Writer → Schema (35 NULL columns)
                                   ↓
                              User Query → NULL (confusion)
```

**Target State (All Calculated Fields Populated):**
```
Raw Data (API) → DuckDB Writer → Calculation Logic → Schema (populated)
                                   ↓                    ↓
                              28 Evaluations      User Query → Values ✅
                              6 Removals          Documentation ✅
```

**Migration Strategy:**

**Phase 1: Planning & Design (3 hours)**
- Design calculation algorithms for 28 fields
- Define evaluation criteria (thresholds, ranges, ratings)
- Create schema documentation template
- Estimate migration time and risks

**Phase 2: Implement Calculation Logic (12-15 hours)**
- **Splits table (3 hours)**: 7 evaluation fields
  - hr_zone: Map heart_rate to zone boundaries (get_heart_rate_zones_detail)
  - cadence_rating: Evaluate cadence (low <170, good 170-180, excellent 180-190, elite >190)
  - power_efficiency: Evaluate W/kg ratio (if power data available)
  - environmental_conditions: Summarize temp/wind/humidity
  - wind_impact: Evaluate wind effect on pace (headwind/tailwind/crosswind)
  - temp_impact: Evaluate temperature effect (ideal/acceptable/hot/cold)
  - environmental_impact: Overall environmental rating (good/moderate/challenging/extreme)

- **Form efficiency table (2 hours)**: 4 evaluation fields
  - gct_evaluation: Evaluate GCT (optimal: 200-250ms, good: 180-200 or 250-280, poor: >280 or <180)
  - vo_trend: Analyze VO trend (improving/stable/degrading over splits)
  - vo_evaluation: Evaluate VO (excellent: <8cm, good: 8-10cm, poor: >10cm)
  - vr_evaluation: Evaluate VR (excellent: <6%, good: 6-8%, acceptable: 8-10%, poor: >10%)

- **HR efficiency table (3 hours)**: 6 evaluation fields
  - primary_zone: Dominant zone (max time_in_zone across 5 zones)
  - zone_distribution_rating: Evaluate distribution quality (focused/balanced/scattered)
  - aerobic_efficiency: Aerobic quality (zone1-2 dominance, low HR drift)
  - training_quality: Overall training quality (matches training_type objectives)
  - zone2_focus: Boolean (>60% time in zone2)
  - zone4_threshold_work: Boolean (>20% time in zone4+)

- **Performance trends table (4 hours)**: 12 phase-based fields
  - Warmup phase (3 fields): avg_cadence, avg_power, evaluation
  - Run phase (3 fields): avg_cadence, avg_power, evaluation
  - Recovery phase (3 fields): avg_cadence, avg_power, evaluation
  - Cooldown phase (3 fields): avg_cadence, avg_power, evaluation
  - Calculation: Extract from time_series_metrics by phase timestamps
  - Evaluation: Assess phase quality (duration, intensity, consistency)

- **Unit tests (3 hours)**: Test each calculation with mock/real data

**Phase 3: Schema Cleanup (2 hours)**
- Remove 6 device-unprovided columns via ALTER TABLE DROP COLUMN
- Update inserter code to remove NULL field references
- Update tests to reflect schema changes
- Verify no breaking changes to existing functionality

**Phase 4: Schema Documentation (3 hours)**
- Create `docs/spec/duckdb_schema_mapping.md`
- Document all 11 tables with comprehensive details:
  - Column name, type, nullable, primary key
  - Raw data source mapping (JSON path)
  - Calculation logic (for calculated fields)
  - Population statistics (before/after)
  - Example values
  - Notes and caveats
- Include migration history and version tracking

**Phase 5: Data Migration (4 hours)**
- **Backup current database** (659MB → backup file)
- **Regenerate affected tables**:
  - splits (231 activities × 7 new fields)
  - form_efficiency (231 activities × 4 new fields)
  - hr_efficiency (231 activities × 6 new fields)
  - performance_trends (231 activities × 12 new fields)
- **Verification**:
  - Check calculation correctness on sample activities
  - Verify population rates ≥95%
  - Compare before/after statistics
  - Validate no data loss

**Phase 6: Testing & Validation (4 hours)**
- Integration tests with real data (10+ activities)
- Validate calculation correctness (manual spot checks)
- Check population rates (SQL queries)
- Performance testing (insertion time, query time)
- Generate before/after statistics report

**Components Affected:**
- `tools/database/inserters/splits.py` - Add 7 calculation fields
- `tools/database/inserters/form_efficiency.py` - Add 4 evaluation fields
- `tools/database/inserters/hr_efficiency.py` - Add 6 evaluation fields
- `tools/database/inserters/performance_trends.py` - Add 12 phase-based fields
- `tools/database/inserters/vo2_max.py` - Remove fitness_age field
- `tools/database/inserters/body_composition.py` - Remove 5 NULL fields
- `tools/scripts/regenerate_duckdb.py` - Trigger migration
- `docs/spec/duckdb_schema_mapping.md` - New documentation file
- Tests: 4 inserter test files, 1 integration test file

### データモデル

#### 1. Splits Table (7 New Calculated Fields)

**Current Schema:**
```sql
CREATE TABLE splits (
    activity_id BIGINT NOT NULL,
    split_number INTEGER NOT NULL,
    distance_km DOUBLE,
    duration_seconds INTEGER,
    pace_seconds_per_km DOUBLE,
    heart_rate DOUBLE,
    cadence DOUBLE,
    -- ... other populated fields ...

    -- UNPOPULATED (to be implemented):
    hr_zone VARCHAR,                    -- NULL → Calculate from heart_rate
    cadence_rating VARCHAR,             -- NULL → Evaluate cadence quality
    power_efficiency VARCHAR,           -- NULL → Evaluate W/kg ratio
    environmental_conditions VARCHAR,   -- NULL → Summarize weather
    wind_impact VARCHAR,                -- NULL → Evaluate wind effect
    temp_impact VARCHAR,                -- NULL → Evaluate temperature effect
    environmental_impact VARCHAR,       -- NULL → Overall environmental rating

    PRIMARY KEY (activity_id, split_number)
)
```

**Target Schema (After Implementation):**
```sql
CREATE TABLE splits (
    -- ... existing fields unchanged ...

    -- NEWLY CALCULATED:
    hr_zone VARCHAR,                    -- "Zone 2" (mapped from heart_rate)
    cadence_rating VARCHAR,             -- "Good (175 spm)" or "Excellent (185 spm)"
    power_efficiency VARCHAR,           -- "Efficient (3.2 W/kg)" or NULL if no power
    environmental_conditions VARCHAR,   -- "Cool, Calm (15°C, 2 km/h wind)"
    wind_impact VARCHAR,                -- "Minimal (<5 km/h)" or "Moderate headwind"
    temp_impact VARCHAR,                -- "Ideal (15°C)" or "Hot (28°C)"
    environmental_impact VARCHAR,       -- "Good" or "Challenging" or "Extreme"

    PRIMARY KEY (activity_id, split_number)
)
```

**Calculation Logic:**

**1. hr_zone (VARCHAR)**
```python
# Source: splits.heart_rate + heart_rate_zones table
# Algorithm:
def calculate_hr_zone(heart_rate: float, activity_id: int, db_conn) -> str:
    """Map heart_rate to zone name using zone boundaries."""
    if heart_rate is None:
        return None

    # Get zone boundaries from heart_rate_zones table
    zones = db_conn.execute("""
        SELECT zone_number, lower_bpm, upper_bpm
        FROM heart_rate_zones
        WHERE activity_id = ?
        ORDER BY zone_number
    """, [activity_id]).fetchall()

    for zone_num, lower, upper in zones:
        if lower <= heart_rate <= upper:
            return f"Zone {zone_num}"

    # Fallback if outside all zones
    if heart_rate < zones[0][1]:  # Below Zone 1
        return "Zone 0 (Recovery)"
    else:  # Above Zone 5
        return "Zone 5+ (Max)"

# Example: heart_rate=145 bpm → "Zone 2" (120-150 bpm range)
```

**2. cadence_rating (VARCHAR)**
```python
# Source: splits.cadence
# Thresholds: <170 (low), 170-180 (good), 180-190 (excellent), 190+ (elite)
def calculate_cadence_rating(cadence: float) -> str:
    """Evaluate cadence quality based on running science."""
    if cadence is None:
        return None

    if cadence < 170:
        return f"Low ({int(cadence)} spm, target 180+)"
    elif 170 <= cadence < 180:
        return f"Good ({int(cadence)} spm)"
    elif 180 <= cadence < 190:
        return f"Excellent ({int(cadence)} spm)"
    else:  # 190+
        return f"Elite ({int(cadence)} spm)"

# Example: cadence=175 → "Good (175 spm)"
```

**3. power_efficiency (VARCHAR)**
```python
# Source: splits.power + body_composition.weight
# Calculation: W/kg ratio (power efficiency metric)
def calculate_power_efficiency(power: float, weight_kg: float) -> str:
    """Calculate power-to-weight ratio."""
    if power is None or weight_kg is None:
        return None  # Power data often unavailable

    w_per_kg = power / weight_kg

    if w_per_kg < 2.5:
        return f"Low ({w_per_kg:.1f} W/kg)"
    elif 2.5 <= w_per_kg < 3.5:
        return f"Moderate ({w_per_kg:.1f} W/kg)"
    elif 3.5 <= w_per_kg < 4.5:
        return f"Good ({w_per_kg:.1f} W/kg)"
    else:  # 4.5+
        return f"Excellent ({w_per_kg:.1f} W/kg)"

# Example: power=250W, weight=70kg → "Good (3.6 W/kg)"
# Note: Often NULL (power data unavailable from device)
```

**4. environmental_conditions (VARCHAR)**
```python
# Source: splits.temperature, wind_speed, humidity
# Summary string combining all environmental factors
def calculate_environmental_conditions(temp: float, wind: float, humidity: float) -> str:
    """Summarize environmental conditions."""
    if temp is None:
        return None  # At minimum need temperature

    parts = []

    # Temperature descriptor
    if temp < 10:
        parts.append(f"Cold ({int(temp)}°C)")
    elif 10 <= temp < 18:
        parts.append(f"Cool ({int(temp)}°C)")
    elif 18 <= temp < 25:
        parts.append(f"Mild ({int(temp)}°C)")
    else:  # 25+
        parts.append(f"Hot ({int(temp)}°C)")

    # Wind descriptor (if available)
    if wind is not None:
        if wind < 5:
            parts.append("Calm")
        elif 5 <= wind < 15:
            parts.append(f"Breezy ({int(wind)} km/h)")
        else:  # 15+
            parts.append(f"Windy ({int(wind)} km/h)")

    # Humidity descriptor (if available)
    if humidity is not None:
        if humidity > 80:
            parts.append(f"Humid ({int(humidity)}%)")
        elif humidity < 30:
            parts.append(f"Dry ({int(humidity)}%)")

    return ", ".join(parts)

# Example: temp=15, wind=2, humidity=65 → "Cool (15°C), Calm"
```

**5. wind_impact (VARCHAR)**
```python
# Source: splits.wind_speed, wind_direction (if available)
# Evaluation: Effect on running performance
def calculate_wind_impact(wind_speed: float, wind_dir: float = None) -> str:
    """Evaluate wind impact on performance."""
    if wind_speed is None:
        return None

    if wind_speed < 5:
        return "Minimal (<5 km/h)"
    elif 5 <= wind_speed < 15:
        # Could enhance with direction (headwind/tailwind/crosswind)
        if wind_dir is not None:
            # 0° = headwind, 90° = crosswind, 180° = tailwind
            if wind_dir < 45 or wind_dir > 315:
                return f"Moderate headwind ({int(wind_speed)} km/h)"
            elif 135 < wind_dir < 225:
                return f"Moderate tailwind ({int(wind_speed)} km/h)"
            else:
                return f"Moderate crosswind ({int(wind_speed)} km/h)"
        else:
            return f"Moderate ({int(wind_speed)} km/h)"
    else:  # 15+
        return f"Significant ({int(wind_speed)} km/h, pace impact expected)"

# Example: wind=12 km/h, dir=30° → "Moderate headwind (12 km/h)"
```

**6. temp_impact (VARCHAR)**
```python
# Source: splits.temperature + hr_efficiency.training_type
# Evaluation: Temperature effect based on training intensity
def calculate_temp_impact(temp: float, training_type: str) -> str:
    """Evaluate temperature impact based on training intensity."""
    if temp is None:
        return None

    # Ideal ranges vary by training intensity
    if training_type in ["recovery", "low_moderate"]:
        # Wider tolerance for low-intensity
        if 15 <= temp <= 22:
            return f"Good ({int(temp)}°C)"
        elif 10 <= temp < 15 or 22 < temp <= 25:
            return f"Acceptable ({int(temp)}°C)"
        elif temp < 10:
            return f"Cold ({int(temp)}°C)"
        else:  # >25
            return f"Hot ({int(temp)}°C)"

    elif training_type in ["base", "tempo_threshold"]:
        # Moderate tolerance
        if 10 <= temp <= 18:
            return f"Ideal ({int(temp)}°C)"
        elif 18 < temp <= 23:
            return f"Acceptable ({int(temp)}°C)"
        elif temp < 10:
            return f"Cool ({int(temp)}°C)"
        else:  # >23
            return f"Hot ({int(temp)}°C, hydration important)"

    else:  # interval_sprint
        # Narrow tolerance for high-intensity
        if 8 <= temp <= 15:
            return f"Ideal ({int(temp)}°C)"
        elif 15 < temp <= 20:
            return f"Good ({int(temp)}°C)"
        elif 20 < temp <= 25:
            return f"Warm ({int(temp)}°C, performance may decrease)"
        elif temp < 8:
            return f"Cold ({int(temp)}°C, longer warmup needed)"
        else:  # >25
            return f"Too hot ({int(temp)}°C, consider rescheduling)"

# Example: temp=28°C, training_type="interval_sprint" → "Too hot (28°C, consider rescheduling)"
```

**7. environmental_impact (VARCHAR)**
```python
# Source: Combination of temp_impact, wind_impact, elevation_change
# Overall environmental challenge rating
def calculate_environmental_impact(
    temp_impact: str,
    wind_impact: str,
    elevation_gain: float,
    elevation_loss: float
) -> str:
    """Calculate overall environmental impact rating."""
    challenge_score = 0

    # Temperature challenge (0-3 points)
    if temp_impact and ("Too hot" in temp_impact or "Cold" in temp_impact):
        challenge_score += 3
    elif temp_impact and ("Hot" in temp_impact or "Cool" in temp_impact):
        challenge_score += 2
    elif temp_impact and "Warm" in temp_impact:
        challenge_score += 1

    # Wind challenge (0-2 points)
    if wind_impact and "Significant" in wind_impact:
        challenge_score += 2
    elif wind_impact and "Moderate" in wind_impact:
        challenge_score += 1

    # Terrain challenge (0-2 points)
    total_elevation = abs(elevation_gain or 0) + abs(elevation_loss or 0)
    if total_elevation > 100:  # Significant elevation change
        challenge_score += 2
    elif total_elevation > 50:
        challenge_score += 1

    # Rating based on total score (0-7 possible)
    if challenge_score == 0:
        return "Ideal conditions"
    elif challenge_score <= 2:
        return "Good conditions"
    elif challenge_score <= 4:
        return "Moderate challenge"
    elif challenge_score <= 5:
        return "Challenging conditions"
    else:  # 6-7
        return "Extreme conditions"

# Example: temp="Hot", wind="Significant", elevation=120m → "Extreme conditions"
```

#### 2. Form Efficiency Table (4 New Evaluation Fields)

**Current Schema:**
```sql
CREATE TABLE form_efficiency (
    activity_id BIGINT NOT NULL,
    avg_gct DOUBLE,
    avg_vo DOUBLE,
    avg_vr DOUBLE,
    gct_balance DOUBLE,
    -- ... other populated fields ...

    -- UNPOPULATED (to be implemented):
    gct_evaluation VARCHAR,  -- NULL → Evaluate GCT quality
    vo_trend VARCHAR,        -- NULL → Analyze VO trend over splits
    vo_evaluation VARCHAR,   -- NULL → Evaluate VO quality
    vr_evaluation VARCHAR,   -- NULL → Evaluate VR quality

    PRIMARY KEY (activity_id)
)
```

**Target Schema:**
```sql
CREATE TABLE form_efficiency (
    -- ... existing fields unchanged ...

    -- NEWLY CALCULATED:
    gct_evaluation VARCHAR,  -- "Excellent (220ms, optimal range)"
    vo_trend VARCHAR,        -- "Stable (8.5cm avg, CV=5%)"
    vo_evaluation VARCHAR,   -- "Good (8.2cm, target <8cm)"
    vr_evaluation VARCHAR,   -- "Excellent (6.8%, optimal)"

    PRIMARY KEY (activity_id)
)
```

**Calculation Logic:**

**1. gct_evaluation (VARCHAR)**
```python
# Source: form_efficiency.avg_gct
# Thresholds: Optimal 200-250ms, Good 180-200 or 250-280, Poor otherwise
def calculate_gct_evaluation(avg_gct: float) -> str:
    """Evaluate ground contact time quality."""
    if avg_gct is None:
        return None

    if 200 <= avg_gct <= 250:
        return f"Excellent ({int(avg_gct)}ms, optimal range)"
    elif 180 <= avg_gct < 200 or 250 < avg_gct <= 280:
        return f"Good ({int(avg_gct)}ms)"
    elif avg_gct < 180:
        return f"Too short ({int(avg_gct)}ms, may indicate overstriding)"
    else:  # >280
        return f"Too long ({int(avg_gct)}ms, target <250ms)"

# Example: avg_gct=220 → "Excellent (220ms, optimal range)"
```

**2. vo_trend (VARCHAR)**
```python
# Source: splits.vertical_oscillation (all splits)
# Analysis: Trend and consistency over activity
def calculate_vo_trend(activity_id: int, avg_vo: float, db_conn) -> str:
    """Analyze vertical oscillation trend over splits."""
    if avg_vo is None:
        return None

    # Get all split VOs
    vos = db_conn.execute("""
        SELECT vertical_oscillation
        FROM splits
        WHERE activity_id = ? AND vertical_oscillation IS NOT NULL
        ORDER BY split_number
    """, [activity_id]).fetchall()

    if len(vos) < 3:
        return f"Insufficient data ({len(vos)} splits)"

    vo_values = [v[0] for v in vos]
    avg = sum(vo_values) / len(vo_values)
    std = (sum((v - avg) ** 2 for v in vo_values) / len(vo_values)) ** 0.5
    cv = (std / avg) * 100  # Coefficient of variation

    # Check trend (first half vs second half)
    mid = len(vo_values) // 2
    first_half_avg = sum(vo_values[:mid]) / mid
    second_half_avg = sum(vo_values[mid:]) / (len(vo_values) - mid)
    change_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100

    if cv < 5:
        consistency = "Very stable"
    elif cv < 10:
        consistency = "Stable"
    else:
        consistency = "Variable"

    if abs(change_pct) < 3:
        trend = "consistent"
    elif change_pct > 0:
        trend = f"increasing (+{change_pct:.1f}%, fatigue indicator)"
    else:
        trend = f"decreasing ({change_pct:.1f}%)"

    return f"{consistency} ({avg:.1f}cm avg, CV={cv:.0f}%, {trend})"

# Example: "Stable (8.5cm avg, CV=6%, consistent)"
```

**3. vo_evaluation (VARCHAR)**
```python
# Source: form_efficiency.avg_vo
# Thresholds: Excellent <8cm, Good 8-10cm, Poor >10cm
def calculate_vo_evaluation(avg_vo: float) -> str:
    """Evaluate vertical oscillation quality."""
    if avg_vo is None:
        return None

    if avg_vo < 8:
        return f"Excellent ({avg_vo:.1f}cm, minimal bounce)"
    elif 8 <= avg_vo < 10:
        return f"Good ({avg_vo:.1f}cm, target <8cm for optimal efficiency)"
    elif 10 <= avg_vo < 12:
        return f"Acceptable ({avg_vo:.1f}cm, reduce bounce)"
    else:  # 12+
        return f"Poor ({avg_vo:.1f}cm, excessive vertical movement)"

# Example: avg_vo=8.2 → "Good (8.2cm, target <8cm for optimal efficiency)"
```

**4. vr_evaluation (VARCHAR)**
```python
# Source: form_efficiency.avg_vr
# Thresholds: Excellent <6%, Good 6-8%, Acceptable 8-10%, Poor >10%
def calculate_vr_evaluation(avg_vr: float) -> str:
    """Evaluate vertical ratio quality."""
    if avg_vr is None:
        return None

    if avg_vr < 6:
        return f"Excellent ({avg_vr:.1f}%, optimal efficiency)"
    elif 6 <= avg_vr < 8:
        return f"Good ({avg_vr:.1f}%)"
    elif 8 <= avg_vr < 10:
        return f"Acceptable ({avg_vr:.1f}%, room for improvement)"
    else:  # 10+
        return f"Poor ({avg_vr:.1f}%, high energy waste)"

# Example: avg_vr=6.8 → "Good (6.8%)"
```

#### 3. HR Efficiency Table (6 New Evaluation Fields)

**Current Schema:**
```sql
CREATE TABLE hr_efficiency (
    activity_id BIGINT NOT NULL,
    avg_heart_rate DOUBLE,
    max_heart_rate DOUBLE,
    training_type VARCHAR,  -- POPULATED
    -- ... other populated fields ...

    -- UNPOPULATED (to be implemented):
    primary_zone VARCHAR,            -- NULL → Dominant zone
    zone_distribution_rating VARCHAR,-- NULL → Evaluate distribution quality
    aerobic_efficiency VARCHAR,      -- NULL → Aerobic quality assessment
    training_quality VARCHAR,        -- NULL → Overall training quality
    zone2_focus BOOLEAN,             -- NULL → True if >60% zone2
    zone4_threshold_work BOOLEAN,    -- NULL → True if >20% zone4+

    PRIMARY KEY (activity_id)
)
```

**Target Schema:**
```sql
CREATE TABLE hr_efficiency (
    -- ... existing fields unchanged ...

    -- NEWLY CALCULATED:
    primary_zone VARCHAR,            -- "Zone 2 (65% of activity)"
    zone_distribution_rating VARCHAR,-- "Focused (85% in primary zone)"
    aerobic_efficiency VARCHAR,      -- "Excellent (80% zone1-2, low drift)"
    training_quality VARCHAR,        -- "Good (matches tempo_threshold objectives)"
    zone2_focus BOOLEAN,             -- TRUE (70% time in zone2)
    zone4_threshold_work BOOLEAN,    -- FALSE (only 5% time in zone4+)

    PRIMARY KEY (activity_id)
)
```

**Calculation Logic:**

**1. primary_zone (VARCHAR)**
```python
# Source: heart_rate_zones.time_in_zone (all 5 zones)
# Calculation: Zone with maximum time
def calculate_primary_zone(activity_id: int, db_conn) -> str:
    """Determine dominant HR zone."""
    zones = db_conn.execute("""
        SELECT zone_number, time_in_zone_seconds
        FROM heart_rate_zones
        WHERE activity_id = ?
        ORDER BY time_in_zone_seconds DESC
        LIMIT 1
    """, [activity_id]).fetchone()

    if zones is None:
        return None

    zone_num, time_sec = zones

    # Get total activity time for percentage
    total_time = db_conn.execute("""
        SELECT duration_seconds
        FROM activities
        WHERE activity_id = ?
    """, [activity_id]).fetchone()[0]

    pct = (time_sec / total_time) * 100 if total_time > 0 else 0

    return f"Zone {zone_num} ({int(pct)}% of activity)"

# Example: "Zone 2 (65% of activity)"
```

**2. zone_distribution_rating (VARCHAR)**
```python
# Source: heart_rate_zones.time_in_zone (all zones)
# Evaluation: Focused vs scattered distribution
def calculate_zone_distribution_rating(activity_id: int, db_conn) -> str:
    """Evaluate zone distribution quality."""
    zones = db_conn.execute("""
        SELECT zone_number, time_in_zone_seconds
        FROM heart_rate_zones
        WHERE activity_id = ?
        ORDER BY zone_number
    """, [activity_id]).fetchall()

    if not zones:
        return None

    total_time = sum(z[1] for z in zones)
    if total_time == 0:
        return "No data"

    zone_pcts = [(z[0], (z[1] / total_time) * 100) for z in zones]
    max_pct = max(pct for _, pct in zone_pcts)

    # Count zones with >10% time (significant zones)
    significant_zones = sum(1 for _, pct in zone_pcts if pct > 10)

    if max_pct >= 80:
        return f"Highly focused ({int(max_pct)}% in primary zone)"
    elif max_pct >= 60:
        return f"Focused ({int(max_pct)}% in primary zone)"
    elif significant_zones <= 2:
        return f"Balanced ({significant_zones} dominant zones)"
    else:  # 3+ significant zones
        return f"Scattered (across {significant_zones} zones, lacks focus)"

# Example: "Focused (65% in primary zone)"
```

**3. aerobic_efficiency (VARCHAR)**
```python
# Source: heart_rate_zones (zones 1-2), performance_trends.hr_drift
# Evaluation: Aerobic training quality
def calculate_aerobic_efficiency(activity_id: int, db_conn) -> str:
    """Assess aerobic training efficiency."""
    # Get zone 1-2 time
    zone12_data = db_conn.execute("""
        SELECT SUM(time_in_zone_seconds)
        FROM heart_rate_zones
        WHERE activity_id = ? AND zone_number IN (1, 2)
    """, [activity_id]).fetchone()[0]

    # Get total time
    total_time = db_conn.execute("""
        SELECT duration_seconds
        FROM activities
        WHERE activity_id = ?
    """, [activity_id]).fetchone()[0]

    # Get HR drift
    hr_drift = db_conn.execute("""
        SELECT hr_drift_percentage
        FROM performance_trends
        WHERE activity_id = ?
    """, [activity_id]).fetchone()

    if zone12_data is None or total_time == 0:
        return None

    zone12_pct = (zone12_data / total_time) * 100
    drift = hr_drift[0] if hr_drift else None

    # Evaluate
    if zone12_pct >= 80:
        if drift is not None and drift < 5:
            return f"Excellent ({int(zone12_pct)}% aerobic zones, low drift {drift:.1f}%)"
        else:
            return f"Good ({int(zone12_pct)}% aerobic zones)"
    elif zone12_pct >= 60:
        return f"Moderate ({int(zone12_pct)}% aerobic zones)"
    else:
        return f"Low ({int(zone12_pct)}% aerobic zones, high-intensity focus)"

# Example: "Excellent (80% aerobic zones, low drift 3.2%)"
```

**4. training_quality (VARCHAR)**
```python
# Source: hr_efficiency.training_type + zone distribution + performance metrics
# Evaluation: Does execution match training objective?
def calculate_training_quality(
    training_type: str,
    primary_zone: str,
    zone_distribution: str,
    activity_id: int,
    db_conn
) -> str:
    """Evaluate if training execution matched objectives."""
    if training_type is None:
        return None

    # Get zone percentages
    zones = db_conn.execute("""
        SELECT zone_number, time_in_zone_seconds
        FROM heart_rate_zones
        WHERE activity_id = ?
    """, [activity_id]).fetchall()

    total_time = sum(z[1] for z in zones)
    zone_pcts = {z[0]: (z[1] / total_time) * 100 for z in zones}

    # Evaluate based on training type objectives
    if training_type == "recovery":
        # Expect Zone 1-2, <70% max HR
        if zone_pcts.get(1, 0) + zone_pcts.get(2, 0) >= 90:
            return "Excellent (true recovery pace maintained)"
        elif zone_pcts.get(1, 0) + zone_pcts.get(2, 0) >= 70:
            return "Good (mostly recovery zones)"
        else:
            return "Poor (too intense for recovery run)"

    elif training_type == "base":
        # Expect Zone 2-3, steady effort
        if zone_pcts.get(2, 0) >= 60:
            return "Excellent (strong aerobic base work)"
        elif zone_pcts.get(2, 0) + zone_pcts.get(3, 0) >= 70:
            return "Good (aerobic development)"
        else:
            return "Moderate (mixed intensity)"

    elif training_type == "tempo_threshold":
        # Expect Zone 3-4, controlled effort
        if zone_pcts.get(4, 0) >= 40:
            return "Excellent (solid threshold work)"
        elif zone_pcts.get(3, 0) + zone_pcts.get(4, 0) >= 60:
            return "Good (tempo effort maintained)"
        else:
            return "Below target (insufficient threshold stimulus)"

    elif training_type == "interval_sprint":
        # Expect Zone 4-5, high intensity intervals
        if zone_pcts.get(5, 0) >= 20 or zone_pcts.get(4, 0) >= 40:
            return "Excellent (high-intensity intervals executed)"
        elif zone_pcts.get(4, 0) + zone_pcts.get(5, 0) >= 30:
            return "Good (challenging effort)"
        else:
            return "Below target (insufficient intensity for intervals)"

    else:  # low_moderate or unknown
        return "Moderate (general training completed)"

# Example: training_type="tempo_threshold", zone4=45% → "Excellent (solid threshold work)"
```

**5. zone2_focus (BOOLEAN)**
```python
# Source: heart_rate_zones.time_in_zone (zone 2)
# Calculation: TRUE if >60% time in zone 2
def calculate_zone2_focus(activity_id: int, db_conn) -> bool:
    """Check if activity is zone 2 focused."""
    zone2_time = db_conn.execute("""
        SELECT time_in_zone_seconds
        FROM heart_rate_zones
        WHERE activity_id = ? AND zone_number = 2
    """, [activity_id]).fetchone()

    total_time = db_conn.execute("""
        SELECT duration_seconds
        FROM activities
        WHERE activity_id = ?
    """, [activity_id]).fetchone()[0]

    if zone2_time is None or total_time == 0:
        return False

    zone2_pct = (zone2_time[0] / total_time) * 100
    return zone2_pct > 60

# Example: zone2_time=2400s, total=3600s → 66.7% → TRUE
```

**6. zone4_threshold_work (BOOLEAN)**
```python
# Source: heart_rate_zones.time_in_zone (zones 4-5)
# Calculation: TRUE if >20% time in zone 4+
def calculate_zone4_threshold_work(activity_id: int, db_conn) -> bool:
    """Check if activity includes significant threshold/VO2max work."""
    zone45_time = db_conn.execute("""
        SELECT SUM(time_in_zone_seconds)
        FROM heart_rate_zones
        WHERE activity_id = ? AND zone_number >= 4
    """, [activity_id]).fetchone()[0]

    total_time = db_conn.execute("""
        SELECT duration_seconds
        FROM activities
        WHERE activity_id = ?
    """, [activity_id]).fetchone()[0]

    if zone45_time is None or total_time == 0:
        return False

    zone45_pct = (zone45_time / total_time) * 100
    return zone45_pct > 20

# Example: zone4+5_time=900s, total=3600s → 25% → TRUE
```

#### 4. Performance Trends Table (12 New Phase-Based Fields)

**Current Schema:**
```sql
CREATE TABLE performance_trends (
    activity_id BIGINT NOT NULL,
    pace_consistency_score DOUBLE,
    hr_drift_percentage DOUBLE,
    -- ... other populated fields ...

    -- UNPOPULATED (to be implemented):
    -- Warmup phase (3 fields)
    warmup_avg_cadence DOUBLE,     -- NULL → Calculate from time_series_metrics
    warmup_avg_power DOUBLE,       -- NULL → Calculate from time_series_metrics
    warmup_evaluation VARCHAR,     -- NULL → Evaluate warmup quality

    -- Run phase (3 fields)
    run_avg_cadence DOUBLE,        -- NULL → Calculate from time_series_metrics
    run_avg_power DOUBLE,          -- NULL → Calculate from time_series_metrics
    run_evaluation VARCHAR,        -- NULL → Evaluate main run quality

    -- Recovery phase (3 fields)
    recovery_avg_cadence DOUBLE,   -- NULL → Calculate from time_series_metrics
    recovery_avg_power DOUBLE,     -- NULL → Calculate from time_series_metrics
    recovery_evaluation VARCHAR,   -- NULL → Evaluate recovery intervals

    -- Cooldown phase (3 fields)
    cooldown_avg_cadence DOUBLE,   -- NULL → Calculate from time_series_metrics
    cooldown_avg_power DOUBLE,     -- NULL → Calculate from time_series_metrics
    cooldown_evaluation VARCHAR,   -- NULL → Evaluate cooldown quality

    PRIMARY KEY (activity_id)
)
```

**Target Schema:**
```sql
CREATE TABLE performance_trends (
    -- ... existing fields unchanged ...

    -- NEWLY CALCULATED (Warmup):
    warmup_avg_cadence DOUBLE,     -- 165.5 spm
    warmup_avg_power DOUBLE,       -- 180 W (or NULL if unavailable)
    warmup_evaluation VARCHAR,     -- "Good (5:30 duration, gradual HR increase)"

    -- NEWLY CALCULATED (Run):
    run_avg_cadence DOUBLE,        -- 178.2 spm
    run_avg_power DOUBLE,          -- 250 W (or NULL)
    run_evaluation VARCHAR,        -- "Excellent (consistent pace, stable HR)"

    -- NEWLY CALCULATED (Recovery):
    recovery_avg_cadence DOUBLE,   -- 160.0 spm (or NULL if no recovery intervals)
    recovery_avg_power DOUBLE,     -- 120 W (or NULL)
    recovery_evaluation VARCHAR,   -- "Good (HR dropped to zone 2)" or NULL

    -- NEWLY CALCULATED (Cooldown):
    cooldown_avg_cadence DOUBLE,   -- 170.5 spm
    cooldown_avg_power DOUBLE,     -- 140 W (or NULL)
    cooldown_evaluation VARCHAR,   -- "Adequate (3:45 duration, HR recovery observed)"

    PRIMARY KEY (activity_id)
)
```

**Calculation Logic:**

**Phase Identification (Prerequisite):**
```python
# Source: time_series_metrics.timestamp_s + heart_rate
# Algorithm: Identify phase boundaries based on HR patterns

def identify_phases(activity_id: int, db_conn) -> dict:
    """Identify warmup, run, recovery, cooldown phases from time series."""
    # Get time series data
    ts_data = db_conn.execute("""
        SELECT timestamp_s, heart_rate, cadence_total, power
        FROM time_series_metrics
        WHERE activity_id = ?
        ORDER BY timestamp_s
    """, [activity_id]).fetchall()

    if len(ts_data) < 60:  # Need at least 60 seconds
        return None

    # Convert to numpy for easier analysis
    timestamps = [d[0] for d in ts_data]
    hr_values = [d[1] for d in ts_data if d[1] is not None]

    # Simple heuristic:
    # - Warmup: First 5-15 minutes, HR gradually increasing
    # - Run: Middle section, HR stable/high
    # - Recovery: Intervals where HR drops significantly (if any)
    # - Cooldown: Last 3-10 minutes, HR gradually decreasing

    total_duration = timestamps[-1] - timestamps[0]

    # Warmup: First 5-15 min or until HR stabilizes
    warmup_end = min(900, total_duration * 0.2)  # Max 15 min or 20% of run

    # Cooldown: Last 3-10 min or from when HR starts dropping
    cooldown_start = max(total_duration - 600, total_duration * 0.85)  # Last 10 min or 15% of run

    # Recovery: Detect intervals (HR drops >10 bpm for >30s)
    # (Complex logic, may skip for initial implementation)

    return {
        "warmup": (0, warmup_end),
        "run": (warmup_end, cooldown_start),
        "recovery": None,  # TODO: Implement interval detection
        "cooldown": (cooldown_start, total_duration)
    }
```

**Phase Calculations (12 fields = 4 phases × 3 fields each):**

```python
def calculate_phase_metrics(activity_id: int, phase_name: str, db_conn) -> dict:
    """Calculate avg_cadence, avg_power, evaluation for a phase."""
    phases = identify_phases(activity_id, db_conn)

    if phases is None or phases.get(phase_name) is None:
        return {
            f"{phase_name}_avg_cadence": None,
            f"{phase_name}_avg_power": None,
            f"{phase_name}_evaluation": None
        }

    start_time, end_time = phases[phase_name]
    duration = end_time - start_time

    # Get metrics for this phase
    metrics = db_conn.execute("""
        SELECT AVG(cadence_total), AVG(power), AVG(heart_rate)
        FROM time_series_metrics
        WHERE activity_id = ?
          AND timestamp_s >= ?
          AND timestamp_s <= ?
    """, [activity_id, start_time, end_time]).fetchone()

    avg_cadence, avg_power, avg_hr = metrics

    # Phase-specific evaluation
    if phase_name == "warmup":
        evaluation = evaluate_warmup(duration, avg_hr, activity_id, db_conn)
    elif phase_name == "run":
        evaluation = evaluate_run(duration, avg_cadence, avg_hr, activity_id, db_conn)
    elif phase_name == "recovery":
        evaluation = evaluate_recovery(duration, avg_hr, activity_id, db_conn)
    elif phase_name == "cooldown":
        evaluation = evaluate_cooldown(duration, avg_hr, activity_id, db_conn)

    return {
        f"{phase_name}_avg_cadence": avg_cadence,
        f"{phase_name}_avg_power": avg_power,
        f"{phase_name}_evaluation": evaluation
    }

# Evaluation functions:

def evaluate_warmup(duration: float, avg_hr: float, activity_id: int, db_conn) -> str:
    """Evaluate warmup phase quality."""
    if duration < 180:  # <3 min
        return f"Too short ({duration//60:.0f}:{duration%60:02.0f}, recommend 5-10 min)"
    elif duration < 300:  # 3-5 min
        return f"Short ({duration//60:.0f}:{duration%60:02.0f}, adequate for easy runs)"
    elif duration < 600:  # 5-10 min
        return f"Good ({duration//60:.0f}:{duration%60:02.0f}, gradual HR increase)"
    elif duration < 900:  # 10-15 min
        return f"Excellent ({duration//60:.0f}:{duration%60:02.0f}, thorough warmup)"
    else:  # 15+ min
        return f"Very long ({duration//60:.0f}:{duration%60:02.0f}, may reduce main run quality)"

def evaluate_run(duration: float, avg_cadence: float, avg_hr: float, activity_id: int, db_conn) -> str:
    """Evaluate main run phase quality."""
    # Get pace consistency from performance_trends
    consistency = db_conn.execute("""
        SELECT pace_consistency_score
        FROM performance_trends
        WHERE activity_id = ?
    """, [activity_id]).fetchone()

    consistency_score = consistency[0] if consistency else None

    parts = []

    # Cadence assessment
    if avg_cadence and avg_cadence >= 180:
        parts.append("optimal cadence")
    elif avg_cadence and avg_cadence >= 170:
        parts.append("good cadence")

    # Consistency assessment
    if consistency_score and consistency_score >= 90:
        parts.append("very consistent pace")
    elif consistency_score and consistency_score >= 80:
        parts.append("consistent pace")

    if not parts:
        return "Completed"

    quality = "Excellent" if len(parts) >= 2 else "Good"
    return f"{quality} ({', '.join(parts)})"

def evaluate_recovery(duration: float, avg_hr: float, activity_id: int, db_conn) -> str:
    """Evaluate recovery intervals (if present)."""
    if duration is None or duration < 30:
        return None  # No recovery phase detected

    # Check if HR dropped sufficiently
    # (Compare to run phase average)
    run_hr = db_conn.execute("""
        SELECT AVG(heart_rate)
        FROM time_series_metrics
        WHERE activity_id = ?
          AND timestamp_s BETWEEN ? AND ?
    """, [activity_id, ...]).fetchone()  # Would need run phase boundaries

    # Simplified for now
    return f"Present ({duration//60:.0f}:{duration%60:02.0f} recovery intervals)"

def evaluate_cooldown(duration: float, avg_hr: float, activity_id: int, db_conn) -> str:
    """Evaluate cooldown phase quality."""
    if duration < 120:  # <2 min
        return f"Too short ({duration//60:.0f}:{duration%60:02.0f}, recommend 3-5 min)"
    elif duration < 180:  # 2-3 min
        return f"Short ({duration//60:.0f}:{duration%60:02.0f}, minimal recovery observed)"
    elif duration < 300:  # 3-5 min
        return f"Adequate ({duration//60:.0f}:{duration%60:02.0f}, HR recovery observed)"
    elif duration < 600:  # 5-10 min
        return f"Good ({duration//60:.0f}:{duration%60:02.0f}, thorough cooldown)"
    else:  # 10+ min
        return f"Excellent ({duration//60:.0f}:{duration%60:02.0f}, complete recovery)"
```

#### 5. Schema Cleanup (6 Fields to Remove)

**VO2 Max Table:**
```sql
-- REMOVE:
ALTER TABLE vo2_max DROP COLUMN fitness_age;

-- Reason: Always NULL in raw data (device does not provide)
-- Impact: None (never populated)
```

**Body Composition Table:**
```sql
-- REMOVE (5 fields):
ALTER TABLE body_composition DROP COLUMN basal_metabolic_rate;
ALTER TABLE body_composition DROP COLUMN active_metabolic_rate;
ALTER TABLE body_composition DROP COLUMN metabolic_age;
ALTER TABLE body_composition DROP COLUMN visceral_fat_rating;
ALTER TABLE body_composition DROP COLUMN physique_rating;

-- Reason: Not in raw data (device limitation)
-- Impact: None (never populated, 0% across all activities)
```

### API/インターフェース設計

#### Inserter Interface Changes

**1. SplitsInserter (tools/database/inserters/splits.py)**

```python
class SplitsInserter:
    def insert(self, activity_id: int, db_conn, raw_data_reader) -> None:
        """Insert splits data with 7 new calculated fields."""

        # ... existing extraction logic ...

        # NEW: Calculate 7 evaluation fields per split
        for split in splits_data:
            # Existing fields
            heart_rate = split.get("averageHeartRate")
            cadence = split.get("averageRunningCadence") * 2  # Total cadence
            power = split.get("averagePower")
            temperature = split.get("temperature")
            wind_speed = split.get("windSpeed")
            # ...

            # NEW CALCULATIONS:
            hr_zone = calculate_hr_zone(heart_rate, activity_id, db_conn)
            cadence_rating = calculate_cadence_rating(cadence)
            power_efficiency = calculate_power_efficiency(power, weight_kg)
            environmental_conditions = calculate_environmental_conditions(
                temperature, wind_speed, humidity
            )
            wind_impact = calculate_wind_impact(wind_speed, wind_direction)

            # Get training_type for temperature evaluation
            training_type = db_conn.execute("""
                SELECT training_type FROM hr_efficiency WHERE activity_id = ?
            """, [activity_id]).fetchone()[0]

            temp_impact = calculate_temp_impact(temperature, training_type)
            environmental_impact = calculate_environmental_impact(
                temp_impact, wind_impact, elevation_gain, elevation_loss
            )

            # Insert with new fields
            db_conn.execute("""
                INSERT INTO splits (
                    activity_id, split_number, distance_km, ...,
                    hr_zone, cadence_rating, power_efficiency,
                    environmental_conditions, wind_impact,
                    temp_impact, environmental_impact
                ) VALUES (?, ?, ?, ..., ?, ?, ?, ?, ?, ?, ?)
            """, [activity_id, split_num, distance, ...,
                  hr_zone, cadence_rating, power_efficiency,
                  environmental_conditions, wind_impact,
                  temp_impact, environmental_impact])
```

**2. FormEfficiencyInserter (tools/database/inserters/form_efficiency.py)**

```python
class FormEfficiencyInserter:
    def insert(self, activity_id: int, db_conn, raw_data_reader) -> None:
        """Insert form efficiency with 4 new evaluation fields."""

        # ... existing extraction logic ...
        avg_gct = ...
        avg_vo = ...
        avg_vr = ...

        # NEW CALCULATIONS:
        gct_evaluation = calculate_gct_evaluation(avg_gct)
        vo_trend = calculate_vo_trend(activity_id, avg_vo, db_conn)
        vo_evaluation = calculate_vo_evaluation(avg_vo)
        vr_evaluation = calculate_vr_evaluation(avg_vr)

        # Insert with new fields
        db_conn.execute("""
            INSERT INTO form_efficiency (
                activity_id, avg_gct, avg_vo, avg_vr, ...,
                gct_evaluation, vo_trend, vo_evaluation, vr_evaluation
            ) VALUES (?, ?, ?, ?, ..., ?, ?, ?, ?)
        """, [activity_id, avg_gct, avg_vo, avg_vr, ...,
              gct_evaluation, vo_trend, vo_evaluation, vr_evaluation])
```

**3. HREfficiencyInserter (tools/database/inserters/hr_efficiency.py)**

```python
class HREfficiencyInserter:
    def insert(self, activity_id: int, db_conn, raw_data_reader) -> None:
        """Insert HR efficiency with 6 new evaluation fields."""

        # ... existing extraction logic ...
        training_type = ...

        # NEW CALCULATIONS (require heart_rate_zones table already inserted):
        primary_zone = calculate_primary_zone(activity_id, db_conn)
        zone_distribution_rating = calculate_zone_distribution_rating(activity_id, db_conn)
        aerobic_efficiency = calculate_aerobic_efficiency(activity_id, db_conn)
        training_quality = calculate_training_quality(
            training_type, primary_zone, zone_distribution_rating, activity_id, db_conn
        )
        zone2_focus = calculate_zone2_focus(activity_id, db_conn)
        zone4_threshold_work = calculate_zone4_threshold_work(activity_id, db_conn)

        # Insert with new fields
        db_conn.execute("""
            INSERT INTO hr_efficiency (
                activity_id, avg_heart_rate, training_type, ...,
                primary_zone, zone_distribution_rating, aerobic_efficiency,
                training_quality, zone2_focus, zone4_threshold_work
            ) VALUES (?, ?, ?, ..., ?, ?, ?, ?, ?, ?)
        """, [activity_id, avg_heart_rate, training_type, ...,
              primary_zone, zone_distribution_rating, aerobic_efficiency,
              training_quality, zone2_focus, zone4_threshold_work])
```

**4. PerformanceTrendsInserter (tools/database/inserters/performance_trends.py)**

```python
class PerformanceTrendsInserter:
    def insert(self, activity_id: int, db_conn, raw_data_reader) -> None:
        """Insert performance trends with 12 new phase-based fields."""

        # ... existing extraction logic ...

        # NEW CALCULATIONS (require time_series_metrics table already inserted):
        warmup_metrics = calculate_phase_metrics(activity_id, "warmup", db_conn)
        run_metrics = calculate_phase_metrics(activity_id, "run", db_conn)
        recovery_metrics = calculate_phase_metrics(activity_id, "recovery", db_conn)
        cooldown_metrics = calculate_phase_metrics(activity_id, "cooldown", db_conn)

        # Insert with new fields
        db_conn.execute("""
            INSERT INTO performance_trends (
                activity_id, pace_consistency_score, hr_drift_percentage, ...,
                warmup_avg_cadence, warmup_avg_power, warmup_evaluation,
                run_avg_cadence, run_avg_power, run_evaluation,
                recovery_avg_cadence, recovery_avg_power, recovery_evaluation,
                cooldown_avg_cadence, cooldown_avg_power, cooldown_evaluation
            ) VALUES (?, ?, ?, ..., ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [activity_id, pace_consistency, hr_drift, ...,
              warmup_metrics["warmup_avg_cadence"],
              warmup_metrics["warmup_avg_power"],
              warmup_metrics["warmup_evaluation"],
              run_metrics["run_avg_cadence"],
              run_metrics["run_avg_power"],
              run_metrics["run_evaluation"],
              recovery_metrics["recovery_avg_cadence"],
              recovery_metrics["recovery_avg_power"],
              recovery_metrics["recovery_evaluation"],
              cooldown_metrics["cooldown_avg_cadence"],
              cooldown_metrics["cooldown_avg_power"],
              cooldown_metrics["cooldown_evaluation"]])
```

**5. VO2MaxInserter (tools/database/inserters/vo2_max.py)**

```python
class VO2MaxInserter:
    def insert(self, activity_id: int, db_conn, raw_data_reader) -> None:
        """Insert VO2 max data WITHOUT fitness_age (removed)."""

        # REMOVE: fitness_age extraction (always NULL)
        # Before:
        # fitness_age = raw_data.get("fitnessAge")  # Always None

        # After:
        # (Just don't reference fitness_age)

        db_conn.execute("""
            INSERT INTO vo2_max (
                activity_id, vo2_max_value, vo2_max_precise,
                running_vo2_max, category
                -- REMOVED: fitness_age
            ) VALUES (?, ?, ?, ?, ?)
        """, [activity_id, vo2_max_value, vo2_max_precise, running_vo2_max, category])
```

**6. BodyCompositionInserter (tools/database/inserters/body_composition.py)**

```python
class BodyCompositionInserter:
    def insert(self, activity_id: int, db_conn, raw_data_reader) -> None:
        """Insert body composition WITHOUT 5 device-unprovided fields."""

        # REMOVE: 5 NULL field extractions
        # Before:
        # basal_metabolic_rate = raw_data.get("basalMetabolicRate")  # Always None
        # active_metabolic_rate = raw_data.get("activeMetabolicRate")  # Always None
        # metabolic_age = raw_data.get("metabolicAge")  # Always None
        # visceral_fat_rating = raw_data.get("visceralFatRating")  # Always None
        # physique_rating = raw_data.get("physiqueRating")  # Always None

        # After:
        # (Don't reference these fields)

        db_conn.execute("""
            INSERT INTO body_composition (
                activity_id, weight, bmi, body_fat_percentage,
                bone_mass, muscle_mass, body_water_percentage
                -- REMOVED: basal_metabolic_rate, active_metabolic_rate,
                --          metabolic_age, visceral_fat_rating, physique_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [activity_id, weight, bmi, body_fat_pct, bone_mass, muscle_mass, body_water])
```

#### Insertion Order Dependencies

**CRITICAL: Insertion order matters for calculated fields that depend on other tables.**

**Current Order (in GarminIngestWorker):**
1. activities (base metadata)
2. splits
3. heart_rate_zones
4. form_efficiency
5. hr_efficiency
6. performance_trends
7. time_series_metrics
8. vo2_max
9. lactate_threshold
10. body_composition

**Required Order (after enhancement):**
1. activities (no changes)
2. time_series_metrics (MOVE UP - needed for phase calculations)
3. heart_rate_zones (MOVE UP - needed for hr_zone in splits, hr_efficiency calculations)
4. splits (depends on heart_rate_zones for hr_zone)
5. form_efficiency (depends on splits for vo_trend)
6. hr_efficiency (depends on heart_rate_zones)
7. performance_trends (depends on time_series_metrics for phase metrics)
8. vo2_max (no changes)
9. lactate_threshold (no changes)
10. body_composition (no changes)

**Code Change (tools/ingest/worker.py):**
```python
def process_activity(self, activity_id: int) -> None:
    """Process single activity with correct insertion order."""

    # ... fetch raw data ...

    # CORRECTED ORDER:
    self.db_writer.insert_activity(activity_id, raw_data)  # 1
    self.db_writer.insert_time_series_metrics(activity_id, raw_data)  # 2 (MOVED UP)
    self.db_writer.insert_heart_rate_zones(activity_id, raw_data)  # 3 (MOVED UP)
    self.db_writer.insert_splits(activity_id, raw_data)  # 4
    self.db_writer.insert_form_efficiency(activity_id, raw_data)  # 5
    self.db_writer.insert_hr_efficiency(activity_id, raw_data)  # 6
    self.db_writer.insert_performance_trends(activity_id, raw_data)  # 7
    self.db_writer.insert_vo2_max(activity_id, raw_data)  # 8
    self.db_writer.insert_lactate_threshold(activity_id, raw_data)  # 9
    self.db_writer.insert_body_composition(activity_id, raw_data)  # 10
```

---

## 実装フェーズ

### Phase 1: Planning & Design (3 hours) - ON MAIN BRANCH

**Branch:** `main` (planning only)

**Tasks:**
1. ✅ Create planning.md (this document)
2. ⬜ Create GitHub Issue with full planning content
3. ⬜ Design calculation algorithm specifications (thresholds, formulas)
4. ⬜ Create schema documentation template (`docs/spec/duckdb_schema_mapping.md` outline)
5. ⬜ Estimate migration time for 231 activities (table regeneration)
6. ⬜ User review and approval

**Deliverables:**
- planning.md committed to main
- GitHub Issue created
- Schema documentation template
- Migration time estimate

### Phase 2: Implement Calculation Logic (12-15 hours) - WORKTREE

**Branch:** `feature/duckdb-schema-enhancement` (git worktree)

#### Phase 2.1: Splits Table (3 hours)

**Tasks:**
1. **TDD: Red - Write failing tests**
   ```python
   # tests/database/inserters/test_splits.py

   def test_hr_zone_calculation():
       """Verify hr_zone calculated from heart_rate and zone boundaries."""
       # Mock: heart_rate=145, zone2_range=[120, 150]
       # Expected: "Zone 2"
       assert splits_data["hr_zone"] == "Zone 2"

   def test_cadence_rating_evaluation():
       """Verify cadence_rating evaluation logic."""
       # Mock: cadence=175
       # Expected: "Good (175 spm)"
       assert splits_data["cadence_rating"] == "Good (175 spm)"

   # ... 5 more test cases for other evaluation fields ...
   ```

2. **TDD: Green - Implement calculation functions**
   - Create `tools/database/inserters/evaluations/splits_evaluations.py`
   - Implement 7 calculation functions (see データモデル section)
   - Update `SplitsInserter.insert()` to call calculation functions
   - Update schema to include 7 new VARCHAR columns

3. **TDD: Refactor - Extract common patterns**
   - Extract threshold-based evaluation logic to utility functions
   - Add docstrings with algorithm explanations
   - Add type hints

4. **Verify with real data**
   - Test with activity 20721683500 (known good data)
   - Spot check 10 splits for correct evaluations

#### Phase 2.2: Form Efficiency Table (2 hours)

**Tasks:**
1. **TDD: Red**
   ```python
   def test_gct_evaluation():
       """Verify GCT evaluation thresholds."""
       # Mock: avg_gct=220
       # Expected: "Excellent (220ms, optimal range)"

   def test_vo_trend_analysis():
       """Verify VO trend calculation over splits."""
       # Mock: VOs = [8.5, 8.6, 8.5, 8.7, 8.4]
       # Expected: "Stable (8.54cm avg, CV=2%, consistent)"

   # ... 2 more tests ...
   ```

2. **TDD: Green**
   - Create `tools/database/inserters/evaluations/form_evaluations.py`
   - Implement 4 evaluation functions
   - Update `FormEfficiencyInserter.insert()`

3. **TDD: Refactor**
   - Extract statistical calculations (CV, trend analysis)

#### Phase 2.3: HR Efficiency Table (3 hours)

**Tasks:**
1. **TDD: Red**
   ```python
   def test_primary_zone_calculation():
       """Verify dominant zone identification."""
       # Mock: zone2=2400s, zone3=1200s, others <600s
       # Expected: "Zone 2 (60% of activity)"

   def test_training_quality_evaluation():
       """Verify training quality matches training_type."""
       # Mock: training_type="tempo_threshold", zone4=45%
       # Expected: "Excellent (solid threshold work)"

   # ... 4 more tests ...
   ```

2. **TDD: Green**
   - Create `tools/database/inserters/evaluations/hr_evaluations.py`
   - Implement 6 evaluation functions
   - Update `HREfficiencyInserter.insert()`
   - **IMPORTANT:** Ensure heart_rate_zones table inserted BEFORE hr_efficiency

3. **TDD: Refactor**
   - Extract zone percentage calculations
   - Create utility for training type objective matching

#### Phase 2.4: Performance Trends Table (4 hours)

**Tasks:**
1. **TDD: Red**
   ```python
   def test_phase_identification():
       """Verify warmup/run/cooldown phase boundaries."""
       # Mock: 3600s activity with HR gradient
       # Expected: warmup=[0, 300], run=[300, 3300], cooldown=[3300, 3600]

   def test_warmup_evaluation():
       """Verify warmup quality assessment."""
       # Mock: duration=330s (5:30)
       # Expected: "Good (5:30, gradual HR increase)"

   # ... 10 more tests (3 metrics × 4 phases - 2 already tested) ...
   ```

2. **TDD: Green**
   - Create `tools/database/inserters/evaluations/phase_evaluations.py`
   - Implement phase identification algorithm
   - Implement 4 phase evaluation functions
   - Update `PerformanceTrendsInserter.insert()`
   - **IMPORTANT:** Ensure time_series_metrics table inserted BEFORE performance_trends

3. **TDD: Refactor**
   - Extract phase boundary detection to separate module
   - Create phase evaluation base class (DRY)

#### Phase 2.5: Unit Tests (included in above)

**Test Coverage Target:** ≥80% for all evaluation modules

**Test Structure:**
```
tests/database/inserters/evaluations/
├── test_splits_evaluations.py (7 tests)
├── test_form_evaluations.py (4 tests)
├── test_hr_evaluations.py (6 tests)
└── test_phase_evaluations.py (13 tests: 1 phase ID + 3×4 evaluations)
```

### Phase 3: Schema Cleanup (2 hours) - WORKTREE

**Branch:** Same worktree (`feature/duckdb-schema-enhancement`)

**Tasks:**

1. **Remove 6 device-unprovided fields from schema**
   - Update `VO2MaxInserter` schema: Remove `fitness_age` column
   - Update `BodyCompositionInserter` schema: Remove 5 columns
   - Update inserter code to remove NULL field references
   - **Note:** No ALTER TABLE needed (regeneration will use new schema)

2. **Update inserter code**
   ```python
   # tools/database/inserters/vo2_max.py
   # REMOVE:
   # fitness_age = raw_data.get("fitnessAge")

   # tools/database/inserters/body_composition.py
   # REMOVE:
   # basal_metabolic_rate = raw_data.get("basalMetabolicRate")
   # active_metabolic_rate = raw_data.get("activeMetabolicRate")
   # metabolic_age = raw_data.get("metabolicAge")
   # visceral_fat_rating = raw_data.get("visceralFatRating")
   # physique_rating = raw_data.get("physiqueRating")
   ```

3. **Update tests**
   - Remove assertions for removed fields
   - Verify schema reflects changes

4. **Verify no breaking changes**
   - Grep codebase for removed field references
   - Check MCP tools don't query removed fields
   - Run all tests

### Phase 4: Schema Documentation (3 hours) - WORKTREE

**Branch:** Same worktree (`feature/duckdb-schema-enhancement`)

**Tasks:**

1. **Create schema documentation template**
   ```markdown
   # docs/spec/duckdb_schema_mapping.md

   # DuckDB Schema Documentation

   ## Overview
   - 11 tables, 231 activities (as of 2025-10-20)
   - Total database size: 659 MB
   - Schema version: 2.0 (after enhancement)

   ## Table Inventory
   1. activities (base metadata)
   2. splits (1km lap data + 7 evaluation fields)
   3. time_series_metrics (second-by-second, 26 metrics)
   4. form_efficiency (GCT/VO/VR + 4 evaluation fields)
   5. hr_efficiency (HR zones + 6 evaluation fields)
   6. performance_trends (pace/HR trends + 12 phase fields)
   7. heart_rate_zones (zone boundaries + time distribution)
   8. vo2_max (VO2 max estimation)
   9. lactate_threshold (LT HR/speed/power)
   10. body_composition (weight/BMI/body fat)
   11. section_analyses (5 agent analysis results)

   ## Detailed Table Schemas

   ### 1. activities
   | Column | Type | Nullable | Primary Key | Source | Calculation | Population | Example |
   |--------|------|----------|-------------|--------|-------------|------------|---------|
   | activity_id | BIGINT | NO | YES | activity.json: activityId | Direct | 100% | 20721683500 |
   | activity_date | DATE | NO | NO | activity.json: startTimeLocal | Parse YYYY-MM-DD | 100% | 2025-10-15 |
   | ... | ... | ... | ... | ... | ... | ... | ... |

   ### 2. splits (with 7 NEW evaluation fields)
   | Column | Type | Nullable | PK | Source | Calculation | Pop% | Example |
   |--------|------|----------|-------|--------|-------------|------|---------|
   | activity_id | BIGINT | NO | YES | (parent) | - | 100% | 20721683500 |
   | split_number | INTEGER | NO | YES | lapDTOs index | - | 100% | 1 |
   | heart_rate | DOUBLE | YES | NO | lapDTOs.averageHeartRate | Direct | 95% | 145.5 |
   | **hr_zone** | VARCHAR | YES | NO | heart_rate + heart_rate_zones | Map HR to zone boundaries | 95% | "Zone 2" |
   | **cadence_rating** | VARCHAR | YES | NO | averageRunningCadence | Evaluate vs 170/180/190 thresholds | 90% | "Good (175 spm)" |
   | ... | ... | ... | ... | ... | ... | ... | ... |

   ### Calculation Details

   #### hr_zone Calculation
   ```python
   # Algorithm: Map heart_rate to zone boundaries
   # Source tables: splits.heart_rate, heart_rate_zones.[lower_bpm, upper_bpm]
   # Logic:
   for zone in zones:
       if lower_bpm <= heart_rate <= upper_bpm:
           return f"Zone {zone_number}"

   # Example: 145 bpm in [120, 150] → "Zone 2"
   ```

   ... (Continue for all 28 calculated fields)
   ```

2. **Document all 11 tables**
   - Column name, type, nullable, primary key
   - Raw data source (JSON file + JSON path)
   - Calculation logic (for calculated fields)
   - Population statistics (% non-NULL)
   - Example values
   - Notes and caveats

3. **Include migration history**
   ```markdown
   ## Schema Version History

   ### Version 2.0 (2025-10-20) - Schema Enhancement
   - Added 28 calculated evaluation fields
   - Removed 6 device-unprovided fields
   - Affected tables: splits, form_efficiency, hr_efficiency, performance_trends, vo2_max, body_composition
   - Migration: Full regeneration of 231 activities

   ### Version 1.1 (2025-10-19) - Cadence Refactoring
   - Added cadence_single_foot, cadence_total to time_series_metrics
   - Deprecated old cadence column

   ### Version 1.0 (2025-10-01) - Initial Schema
   - 11 tables created
   - 100+ activities migrated from JSON files
   ```

4. **Add usage examples**
   ```markdown
   ## Common Query Patterns

   ### Get all evaluation fields for an activity
   ```sql
   SELECT
       s.split_number,
       s.hr_zone,
       s.cadence_rating,
       s.environmental_impact,
       fe.gct_evaluation,
       fe.vo_evaluation,
       he.training_quality,
       he.primary_zone
   FROM splits s
   LEFT JOIN form_efficiency fe ON s.activity_id = fe.activity_id
   LEFT JOIN hr_efficiency he ON s.activity_id = he.activity_id
   WHERE s.activity_id = 20721683500;
   ```
   ```

### Phase 5: Data Migration (4 hours) - WORKTREE

**Branch:** Same worktree (`feature/duckdb-schema-enhancement`)

**Tasks:**

1. **Backup current database (659MB)**
   ```bash
   # Backup to timestamped file
   cp /home/yamakii/garmin_data/data/database/garmin_performance.duckdb \
      /home/yamakii/garmin_data/data/database/backups/garmin_performance_$(date +%Y%m%d_%H%M%S).duckdb

   # Verify backup integrity
   ls -lh /home/yamakii/garmin_data/data/database/backups/*.duckdb
   ```

2. **Fix insertion order in GarminIngestWorker**
   ```python
   # tools/ingest/worker.py
   # MOVE time_series_metrics and heart_rate_zones BEFORE splits
   def process_activity(self, activity_id: int) -> None:
       self.db_writer.insert_activity(activity_id, raw_data)
       self.db_writer.insert_time_series_metrics(activity_id, raw_data)  # MOVED UP
       self.db_writer.insert_heart_rate_zones(activity_id, raw_data)  # MOVED UP
       self.db_writer.insert_splits(activity_id, raw_data)
       # ... rest unchanged ...
   ```

3. **Regenerate 4 affected tables (estimate 15-20 minutes)**
   ```bash
   # Regenerate tables with new calculation logic
   uv run python tools/scripts/regenerate_duckdb.py \
       --tables splits form_efficiency hr_efficiency performance_trends \
       --force

   # Expected time: 231 activities × 4 tables × 1-2s/table ≈ 15-20 min
   ```

4. **Verification queries**
   ```sql
   -- Check population rates for new fields
   SELECT
       'splits' AS table_name,
       'hr_zone' AS column_name,
       COUNT(*) AS total_rows,
       COUNT(hr_zone) AS populated_rows,
       (COUNT(hr_zone) * 100.0 / COUNT(*)) AS population_pct
   FROM splits
   UNION ALL
   SELECT 'splits', 'cadence_rating', COUNT(*), COUNT(cadence_rating),
          (COUNT(cadence_rating) * 100.0 / COUNT(*))
   FROM splits
   -- ... repeat for all 28 fields ...

   -- Expected: ≥95% population for all calculated fields
   ```

5. **Generate before/after statistics**
   ```bash
   # Create migration report
   python -c "
   import duckdb
   conn = duckdb.connect('/path/to/garmin_performance.duckdb')

   # Get column population stats
   for table in ['splits', 'form_efficiency', 'hr_efficiency', 'performance_trends']:
       print(f'\n## {table}')
       schema = conn.execute(f'PRAGMA table_info({table})').fetchall()
       for col_info in schema:
           col_name = col_info[1]
           result = conn.execute(f'''
               SELECT
                   COUNT(*) AS total,
                   COUNT({col_name}) AS populated,
                   (COUNT({col_name}) * 100.0 / COUNT(*)) AS pct
               FROM {table}
           ''').fetchone()
           print(f'{col_name}: {result[2]:.1f}% ({result[1]}/{result[0]})')
   "
   ```

### Phase 6: Testing & Validation (4 hours) - WORKTREE

**Branch:** Same worktree (`feature/duckdb-schema-enhancement`)

**Tasks:**

1. **Integration tests with real data**
   ```python
   # tests/integration/test_schema_enhancement.py

   @pytest.mark.integration
   def test_splits_evaluation_fields_populated():
       """Verify all 7 splits evaluation fields populated for real activity."""
       activity_id = 20721683500

       result = conn.execute("""
           SELECT
               hr_zone, cadence_rating, power_efficiency,
               environmental_conditions, wind_impact,
               temp_impact, environmental_impact
           FROM splits
           WHERE activity_id = ?
           LIMIT 1
       """, [activity_id]).fetchone()

       assert result[0] is not None  # hr_zone
       assert "Zone" in result[0]
       assert result[1] is not None  # cadence_rating
       assert "spm" in result[1]
       # ... etc

   @pytest.mark.integration
   def test_form_efficiency_evaluations():
       """Verify form efficiency evaluations for real activity."""
       # ... similar pattern ...

   # ... 4 more integration tests (1 per table) ...
   ```

2. **Validate calculation correctness (manual spot checks)**
   ```bash
   # Spot check 10 random activities
   python -c "
   import duckdb
   import random

   conn = duckdb.connect('/path/to/garmin_performance.duckdb')

   # Get 10 random activity IDs
   activity_ids = conn.execute('SELECT activity_id FROM activities LIMIT 100').fetchall()
   sample = random.sample(activity_ids, 10)

   for aid in sample:
       # Check splits evaluations
       splits_eval = conn.execute('''
           SELECT split_number, hr_zone, cadence_rating, environmental_impact
           FROM splits
           WHERE activity_id = ?
           LIMIT 3
       ''', [aid[0]]).fetchall()

       print(f'\nActivity {aid[0]}:')
       for split in splits_eval:
           print(f'  Split {split[0]}: {split[1]}, {split[2]}, {split[3]}')

       # Check form efficiency
       form_eval = conn.execute('''
           SELECT gct_evaluation, vo_evaluation, vr_evaluation
           FROM form_efficiency
           WHERE activity_id = ?
       ''', [aid[0]]).fetchone()

       if form_eval:
           print(f'  Form: GCT={form_eval[0]}, VO={form_eval[1]}, VR={form_eval[2]}')
   "
   ```

3. **Check population rates ≥95%**
   ```sql
   -- Population rate verification (automated)
   SELECT
       table_name,
       column_name,
       population_pct,
       CASE
           WHEN population_pct >= 95 THEN '✅ PASS'
           WHEN population_pct >= 80 THEN '⚠️  WARN'
           ELSE '❌ FAIL'
       END AS status
   FROM (
       SELECT 'splits' AS table_name, 'hr_zone' AS column_name,
              (COUNT(hr_zone) * 100.0 / COUNT(*)) AS population_pct FROM splits
       UNION ALL
       -- ... all 28 fields ...
   )
   ORDER BY population_pct ASC;

   -- Expected: All 28 fields show "✅ PASS"
   ```

4. **Performance testing**
   ```python
   # tests/performance/test_insertion_performance.py

   @pytest.mark.performance
   def test_splits_insertion_performance():
       """Verify insertion time acceptable with 7 new calculation fields."""
       import time

       start = time.time()
       # Insert splits for 1 activity (typical: 10-15 splits)
       inserter.insert(test_activity_id, db_conn, raw_data_reader)
       elapsed = time.time() - start

       # Should complete in <2 seconds (was ~0.5s before enhancement)
       assert elapsed < 2.0, f"Insertion too slow: {elapsed:.2f}s"

   # ... similar tests for other 3 tables ...
   ```

5. **Generate statistics report**
   ```bash
   # Create comprehensive statistics report
   python tools/scripts/generate_migration_report.py > migration_stats.md

   # Report includes:
   # - Before/after population rates (35 fields: 0% → 95%)
   # - Database size (before: 659MB, after: ~680MB estimate)
   # - Migration time (actual: XX minutes)
   # - Test results (all passed)
   # - Sample evaluations from 10 activities
   ```

---

## テスト計画

### Unit Tests

**File Structure:**
```
tests/database/inserters/evaluations/
├── __init__.py
├── test_splits_evaluations.py      (7 tests)
├── test_form_evaluations.py        (4 tests)
├── test_hr_evaluations.py          (6 tests)
└── test_phase_evaluations.py       (13 tests)
```

**Total Unit Tests: 30**

#### Splits Evaluations (7 tests)

- [ ] **test_calculate_hr_zone_from_heart_rate()**
  - Mock: heart_rate=145, zones=[(1, 90, 120), (2, 120, 150), (3, 150, 170)]
  - Expected: "Zone 2"
  - Edge cases: Below zone 1, above zone 5, exact boundary

- [ ] **test_calculate_cadence_rating()**
  - Mock: cadence=175
  - Expected: "Good (175 spm)"
  - Edge cases: <170 (low), 170-180 (good), 180-190 (excellent), 190+ (elite)

- [ ] **test_calculate_power_efficiency()**
  - Mock: power=250W, weight=70kg
  - Expected: "Good (3.6 W/kg)"
  - Edge cases: NULL power, NULL weight

- [ ] **test_calculate_environmental_conditions()**
  - Mock: temp=15, wind=2, humidity=65
  - Expected: "Cool (15°C), Calm"
  - Edge cases: NULL wind/humidity, extreme temps

- [ ] **test_calculate_wind_impact()**
  - Mock: wind=12, direction=30 (headwind)
  - Expected: "Moderate headwind (12 km/h)"
  - Edge cases: <5 (minimal), 15+ (significant), NULL direction

- [ ] **test_calculate_temp_impact_training_type_aware()**
  - Mock: temp=28, training_type="interval_sprint"
  - Expected: "Too hot (28°C, consider rescheduling)"
  - Mock: temp=28, training_type="recovery"
  - Expected: "Hot (28°C)"

- [ ] **test_calculate_environmental_impact_combined()**
  - Mock: temp_impact="Hot", wind_impact="Significant", elevation=120m
  - Expected: "Extreme conditions"
  - Edge cases: Ideal conditions (score=0), moderate (score=3)

#### Form Evaluations (4 tests)

- [ ] **test_calculate_gct_evaluation()**
  - Mock: avg_gct=220
  - Expected: "Excellent (220ms, optimal range)"
  - Edge cases: <180 (too short), >280 (too long)

- [ ] **test_calculate_vo_trend_over_splits()**
  - Mock: VOs=[8.5, 8.6, 8.5, 8.7, 8.4] (CV=2.3%)
  - Expected: "Stable (8.54cm avg, CV=2%, consistent)"
  - Edge cases: Increasing trend, decreasing trend, high CV

- [ ] **test_calculate_vo_evaluation()**
  - Mock: avg_vo=8.2
  - Expected: "Good (8.2cm, target <8cm for optimal efficiency)"
  - Edge cases: <8 (excellent), >12 (poor)

- [ ] **test_calculate_vr_evaluation()**
  - Mock: avg_vr=6.8
  - Expected: "Good (6.8%)"
  - Edge cases: <6 (excellent), >10 (poor)

#### HR Evaluations (6 tests)

- [ ] **test_calculate_primary_zone()**
  - Mock: zones=[(1, 600s), (2, 2400s), (3, 1200s), (4, 600s), (5, 200s)]
  - Expected: "Zone 2 (60% of activity)"

- [ ] **test_calculate_zone_distribution_rating()**
  - Mock: primary_zone=65%
  - Expected: "Focused (65% in primary zone)"
  - Edge cases: ≥80% (highly focused), 3+ zones (scattered)

- [ ] **test_calculate_aerobic_efficiency()**
  - Mock: zone1+2=80%, hr_drift=3.2%
  - Expected: "Excellent (80% aerobic zones, low drift 3.2%)"
  - Edge cases: <60% (low), high drift

- [ ] **test_calculate_training_quality_matches_objective()**
  - Mock: training_type="tempo_threshold", zone4=45%
  - Expected: "Excellent (solid threshold work)"
  - Mock: training_type="recovery", zone1+2=70%
  - Expected: "Good (mostly recovery zones)"

- [ ] **test_calculate_zone2_focus_boolean()**
  - Mock: zone2=70% → TRUE
  - Mock: zone2=50% → FALSE

- [ ] **test_calculate_zone4_threshold_work_boolean()**
  - Mock: zone4+5=25% → TRUE
  - Mock: zone4+5=15% → FALSE

#### Phase Evaluations (13 tests)

- [ ] **test_identify_phases_from_time_series()**
  - Mock: 3600s activity with HR gradient
  - Expected: warmup=[0, 300], run=[300, 3300], cooldown=[3300, 3600]
  - Edge cases: Short activities (<10 min), no clear phases

- [ ] **test_calculate_warmup_avg_cadence()**
  - Mock: warmup phase cadence=[165, 168, 170]
  - Expected: 167.7 spm

- [ ] **test_calculate_warmup_avg_power()**
  - Mock: warmup phase power=[180, 185, 190]
  - Expected: 185 W

- [ ] **test_evaluate_warmup_duration()**
  - Mock: duration=330s (5:30)
  - Expected: "Good (5:30, gradual HR increase)"
  - Edge cases: <3min (too short), >15min (very long)

- [ ] **test_calculate_run_avg_cadence()**
- [ ] **test_calculate_run_avg_power()**
- [ ] **test_evaluate_run_consistency()**
  - Mock: pace_consistency=92, cadence=178
  - Expected: "Excellent (optimal cadence, very consistent pace)"

- [ ] **test_calculate_recovery_avg_cadence()**
- [ ] **test_calculate_recovery_avg_power()**
- [ ] **test_evaluate_recovery_intervals()**
  - Mock: recovery duration=120s, HR dropped to zone2
  - Expected: "Good (2:00 recovery intervals)"

- [ ] **test_calculate_cooldown_avg_cadence()**
- [ ] **test_calculate_cooldown_avg_power()**
- [ ] **test_evaluate_cooldown_duration()**
  - Mock: duration=225s (3:45)
  - Expected: "Adequate (3:45, HR recovery observed)"

### Integration Tests

**File:** `tests/integration/test_schema_enhancement.py`

**Total Integration Tests: 6**

- [ ] **test_splits_all_evaluation_fields_populated_real_activity()**
  - Load: activity 20721683500
  - Insert with new logic
  - Query: All 7 evaluation fields for first 5 splits
  - Assert: All fields non-NULL, values match expected patterns

- [ ] **test_form_efficiency_evaluations_real_activity()**
  - Load: activity 20721683500
  - Query: 4 evaluation fields
  - Assert: Evaluations realistic (e.g., GCT in 180-280ms range)

- [ ] **test_hr_efficiency_evaluations_real_activity()**
  - Load: activity 20721683500
  - Query: 6 evaluation fields
  - Assert: primary_zone matches zone distribution, booleans correct

- [ ] **test_performance_trends_phase_evaluations_real_activity()**
  - Load: activity 20721683500
  - Query: 12 phase-based fields
  - Assert: Phases identified correctly, evaluations reasonable

- [ ] **test_schema_cleanup_removed_fields_absent()**
  - Query: vo2_max schema
  - Assert: fitness_age column removed
  - Query: body_composition schema
  - Assert: 5 NULL fields removed

- [ ] **test_migration_completeness_all_231_activities()**
  - Query: Population rates for all 28 new fields across 231 activities
  - Assert: ≥95% population for each field
  - Generate: Population statistics report

### Performance Tests

**File:** `tests/performance/test_insertion_performance.py`

**Total Performance Tests: 4**

- [ ] **test_splits_insertion_time_with_evaluations()**
  - Insert: splits for 1 activity (10-15 splits)
  - Measure: Insertion time
  - Assert: <2 seconds (acceptable overhead from 7 calculations)

- [ ] **test_form_efficiency_insertion_time()**
  - Insert: form_efficiency with 4 evaluations
  - Assert: <1 second

- [ ] **test_hr_efficiency_insertion_time()**
  - Insert: hr_efficiency with 6 evaluations
  - Assert: <1 second

- [ ] **test_performance_trends_insertion_time()**
  - Insert: performance_trends with 12 phase calculations
  - Assert: <3 seconds (phase identification + 12 metrics)

### Manual Testing Checklist

- [ ] **Schema Verification:**
  - [ ] Run `PRAGMA table_info(splits)` → Verify 7 new columns
  - [ ] Run `PRAGMA table_info(form_efficiency)` → Verify 4 new columns
  - [ ] Run `PRAGMA table_info(hr_efficiency)` → Verify 6 new columns
  - [ ] Run `PRAGMA table_info(performance_trends)` → Verify 12 new columns
  - [ ] Run `PRAGMA table_info(vo2_max)` → Verify fitness_age removed
  - [ ] Run `PRAGMA table_info(body_composition)` → Verify 5 fields removed

- [ ] **Data Verification (Spot Checks):**
  - [ ] Query 10 random activities
  - [ ] Verify hr_zone matches heart_rate (manual zone boundary check)
  - [ ] Verify cadence_rating thresholds (175 spm → "Good")
  - [ ] Verify environmental_impact combines temp/wind/terrain
  - [ ] Verify training_quality matches training_type objectives

- [ ] **Regeneration Test:**
  - [ ] Backup database (verify size ≈659MB)
  - [ ] Run: `uv run python tools/scripts/regenerate_duckdb.py --tables splits form_efficiency hr_efficiency performance_trends --force`
  - [ ] Verify: No errors during regeneration
  - [ ] Compare: Row counts before/after (should match)

- [ ] **Code Quality:**
  - [ ] Run: `uv run black .`
  - [ ] Run: `uv run ruff check .`
  - [ ] Run: `uv run mypy .`
  - [ ] Run: `uv run pytest -m unit`
  - [ ] Run: `uv run pytest -m integration`
  - [ ] Run: `uv run pre-commit run --all-files`

---

## 受け入れ基準

### Functional Requirements

- [ ] **28 Calculation Fields Implemented and Populated (≥95%)**
  - [ ] Splits: 7 evaluation fields (hr_zone, cadence_rating, power_efficiency, environmental_conditions, wind_impact, temp_impact, environmental_impact)
  - [ ] Form efficiency: 4 evaluation fields (gct_evaluation, vo_trend, vo_evaluation, vr_evaluation)
  - [ ] HR efficiency: 6 evaluation fields (primary_zone, zone_distribution_rating, aerobic_efficiency, training_quality, zone2_focus, zone4_threshold_work)
  - [ ] Performance trends: 12 phase-based fields (warmup/run/recovery/cooldown × avg_cadence/avg_power/evaluation)

- [ ] **6 Device-Unprovided Fields Removed from Schema**
  - [ ] VO2 max: fitness_age removed
  - [ ] Body composition: 5 NULL fields removed (basal_metabolic_rate, active_metabolic_rate, metabolic_age, visceral_fat_rating, physique_rating)

- [ ] **Schema Documentation Complete**
  - [ ] `docs/spec/duckdb_schema_mapping.md` created
  - [ ] All 11 tables documented (columns, types, sources, calculations, examples)
  - [ ] Calculation logic explained for all 28 fields
  - [ ] Population statistics included (before: 0%, after: 95%+)
  - [ ] Migration history documented

- [ ] **Data Migration Successful**
  - [ ] Database backup created (659MB → timestamped backup file)
  - [ ] 4 affected tables regenerated (splits, form_efficiency, hr_efficiency, performance_trends)
  - [ ] 231 activities migrated successfully (0 errors)
  - [ ] Insertion order fixed (time_series_metrics, heart_rate_zones BEFORE splits)

- [ ] **Sample Queries Return Expected Values**
  - [ ] `SELECT hr_zone FROM splits` → "Zone 2", "Zone 3", etc.
  - [ ] `SELECT cadence_rating FROM splits` → "Good (175 spm)", "Excellent (185 spm)"
  - [ ] `SELECT gct_evaluation FROM form_efficiency` → "Excellent (220ms, optimal range)"
  - [ ] `SELECT training_quality FROM hr_efficiency` → "Excellent (solid threshold work)"
  - [ ] `SELECT warmup_evaluation FROM performance_trends` → "Good (5:30, gradual HR increase)"

### Code Quality

- [ ] **All Tests Passing**
  - [ ] 30 unit tests pass (`uv run pytest -m unit`)
  - [ ] 6 integration tests pass (`uv run pytest -m integration`)
  - [ ] 4 performance tests pass (`uv run pytest -m performance`)
  - [ ] Code coverage ≥80% for evaluation modules

- [ ] **Code Quality Checks Pass**
  - [ ] `uv run black .` - No formatting issues
  - [ ] `uv run ruff check .` - No linting errors
  - [ ] `uv run mypy .` - No type errors
  - [ ] `uv run pre-commit run --all-files` - All hooks pass

### Documentation

- [ ] **CLAUDE.md Updated**
  - [ ] DuckDB schema section updated: "28 calculated evaluation fields implemented"
  - [ ] Schema documentation reference added: "See docs/spec/duckdb_schema_mapping.md"

- [ ] **Code Comments Added**
  - [ ] All calculation functions have docstrings explaining algorithm
  - [ ] Threshold values documented (e.g., cadence: 170/180/190)
  - [ ] Edge cases documented (NULL handling, extreme values)

- [ ] **completion_report.md Generated**
  - [ ] Before/after population statistics
  - [ ] Migration time (actual: XX minutes)
  - [ ] Test results summary
  - [ ] Breaking changes: None (new fields only)
  - [ ] Rollback instructions: Restore backup, regenerate from raw data

### Testing

- [ ] **Manual Testing Checklist Completed**
  - [ ] Schema verification (PRAGMA table_info)
  - [ ] Data verification (10 random activity spot checks)
  - [ ] Regeneration test (backup → regenerate → verify)
  - [ ] Code quality checks (Black, Ruff, Mypy, pytest)

- [ ] **Performance Requirements Met**
  - [ ] Splits insertion: <2 seconds per activity
  - [ ] Form efficiency insertion: <1 second
  - [ ] HR efficiency insertion: <1 second
  - [ ] Performance trends insertion: <3 seconds
  - [ ] Overall migration time: <30 minutes for 231 activities

### Git Workflow

- [ ] **Planning Committed to Main Branch**
  - [ ] planning.md created in docs/project/2025-10-20_duckdb_schema_enhancement/
  - [ ] Committed to main branch with conventional commit message
  - [ ] GitHub Issue created and linked in planning.md

- [ ] **Implementation in Feature Branch (Worktree)**
  - [ ] Worktree created: `git worktree add -b feature/duckdb-schema-enhancement`
  - [ ] All commits follow Conventional Commits format
  - [ ] All commits include co-author tag

- [ ] **PR Created and Merged**
  - [ ] PR includes completion_report.md
  - [ ] All tests pass in CI
  - [ ] Merged to main
  - [ ] Worktree removed

### Data Integrity

- [ ] **No Data Loss During Migration**
  - [ ] All 231 activities present after migration
  - [ ] Row counts match before/after (per table)
  - [ ] Backup verified (can restore if needed)

- [ ] **Calculation Correctness Verified**
  - [ ] 10 random activities manually spot-checked
  - [ ] hr_zone matches heart_rate (zone boundary check)
  - [ ] Cadence rating thresholds correct (170/180/190)
  - [ ] Environmental impact combines temp/wind/terrain correctly
  - [ ] Training quality matches training_type objectives

- [ ] **Population Rates ≥95%**
  - [ ] All 28 calculated fields: ≥95% non-NULL
  - [ ] NULL values only where expected (e.g., power_efficiency when power unavailable)

- [ ] **Backward Compatibility Maintained**
  - [ ] Existing queries unaffected (no columns removed from populated tables)
  - [ ] MCP tools work without changes
  - [ ] No breaking changes to external APIs

---

## 成功メトリクス

### Quantitative Metrics

- **Population Rate Improvement:** 0% → 95%+ for 28 calculated fields
- **Schema Cleanup:** 6 NULL fields removed (vo2_max: 1, body_composition: 5)
- **Test Coverage:** ≥80% for evaluation modules (30 unit + 6 integration tests)
- **Migration Time:** <30 minutes for 231 activities (4 tables)
- **Performance Overhead:** <100% insertion time increase (e.g., splits: 0.5s → <2s)
- **Database Size:** 659MB → ~680MB (3% increase from new VARCHAR evaluations)
- **Implementation Time:** 28-31 hours (actual vs estimate)

### Qualitative Metrics

- **Schema Documentation Completeness:** `docs/spec/duckdb_schema_mapping.md` serves as authoritative reference
- **Evaluation Quality:** Actionable feedback (e.g., "Reduce GCT to <250ms", "Too hot for intervals")
- **Code Maintainability:** Clear separation of concerns (evaluation logic in separate modules)
- **User Value:** Evaluation fields provide insights without manual calculation
- **Serena MCP Usage:** Symbol-based editing for all code changes

---

## リスク分析

### Risk Assessment

#### Risk 1: High Complexity (28 Different Calculation Algorithms)
- **Probability:** High
- **Impact:** Medium-High (implementation time, bugs)
- **Mitigation:**
  - TDD approach (write tests first, implement incrementally)
  - Extract common evaluation patterns (threshold-based ratings)
  - Incremental implementation (4 tables × 2-4 hours each)
  - Unit tests for each calculation function
- **Detection:** Test failures, manual spot checks
- **Rollback:** Restore backup database, revert code changes

#### Risk 2: Long Migration Time (15-20 minutes)
- **Probability:** Medium
- **Impact:** Low (user inconvenience only)
- **Mitigation:**
  - Table-level regeneration (4 tables, not full DB)
  - Parallel processing (if feasible)
  - Off-peak execution
  - Progress monitoring (log every 10 activities)
- **Detection:** Migration takes >30 minutes
- **Rollback:** N/A (wait for completion)

#### Risk 3: Calculation Accuracy Errors
- **Probability:** Medium
- **Impact:** High (incorrect evaluations mislead users)
- **Mitigation:**
  - Clear threshold documentation (cadence: 170/180/190)
  - Unit tests with known expected values
  - Manual spot checks on 10 random activities
  - Integration tests with real data
- **Detection:** Incorrect evaluations in manual checks, user reports
- **Rollback:** Fix calculation logic, regenerate affected table

#### Risk 4: Insertion Order Dependencies
- **Probability:** High (already identified)
- **Impact:** High (calculation failures if dependent tables not inserted)
- **Mitigation:**
  - **Move time_series_metrics and heart_rate_zones BEFORE splits**
  - Document insertion order in code comments
  - Integration test verifies correct order
- **Detection:** Foreign key errors, NULL calculation results
- **Rollback:** Fix insertion order, regenerate

#### Risk 5: Breaking Changes to Existing Functionality
- **Probability:** Low
- **Impact:** High (MCP tools fail, queries break)
- **Mitigation:**
  - Only ADD fields, never REMOVE populated fields
  - Grep codebase for removed field references (6 NULL fields)
  - Integration tests verify MCP tools unaffected
  - Backward compatibility tests
- **Detection:** Test failures, MCP tool errors
- **Rollback:** Restore backup, investigate breaking change

#### Risk 6: Performance Degradation
- **Probability:** Medium
- **Impact:** Medium (slow insertion, user frustration)
- **Mitigation:**
  - Performance tests verify <100% overhead
  - Optimize calculation logic (avoid redundant queries)
  - Batch calculations where possible
  - Measure before/after insertion time
- **Detection:** Performance test failures, >2s splits insertion
- **Rollback:** Optimize calculation logic, regenerate

### Rollback Plan

**Scenario 1: Migration Failure (Errors During Regeneration)**
```bash
# 1. Stop migration immediately
Ctrl+C (or let it fail)

# 2. Restore backup
cp /home/yamakii/garmin_data/data/database/backups/garmin_performance_YYYYMMDD_HHMMSS.duckdb \
   /home/yamakii/garmin_data/data/database/garmin_performance.duckdb

# 3. Verify restoration
python -c "
import duckdb
conn = duckdb.connect('/path/to/garmin_performance.duckdb')
print(conn.execute('SELECT COUNT(*) FROM activities').fetchone())
# Expected: (231,)
"

# 4. Investigate error
# - Check logs: regenerate_duckdb.py output
# - Fix calculation logic
# - Re-run migration
```

**Scenario 2: Incorrect Calculations Discovered Post-Migration**
```bash
# 1. Fix calculation logic in code
# - Edit tools/database/inserters/evaluations/*.py
# - Update unit tests
# - Verify tests pass: uv run pytest -m unit

# 2. Regenerate affected table only
uv run python tools/scripts/regenerate_duckdb.py --tables splits --force

# 3. Verify fix
# - Manual spot checks
# - Query population rates
```

**Scenario 3: Performance Degradation Unacceptable**
```bash
# 1. Profile calculation bottlenecks
python -m cProfile tools/database/inserters/splits.py

# 2. Optimize slow calculations
# - Cache repeated queries (e.g., heart_rate_zones)
# - Batch calculations
# - Use indexes if needed

# 3. Re-test performance
uv run pytest -m performance

# 4. Regenerate if optimizations made
uv run python tools/scripts/regenerate_duckdb.py --tables splits --force
```

**Scenario 4: Breaking Changes to MCP Tools**
```bash
# 1. Identify broken tool
# - Check servers/garmin_db_server.py
# - Run MCP tool integration tests

# 2. Fix MCP tool code
# - Update query to use new field names
# - Handle NULL values for removed fields

# 3. Verify fix
uv run pytest tests/integration/test_mcp_tools.py
```

---

## 参考資料

### Current Implementation Files

**Inserters (to be modified):**
- `tools/database/inserters/splits.py` - Add 7 calculation fields
- `tools/database/inserters/form_efficiency.py` - Add 4 evaluation fields
- `tools/database/inserters/hr_efficiency.py` - Add 6 evaluation fields
- `tools/database/inserters/performance_trends.py` - Add 12 phase-based fields
- `tools/database/inserters/vo2_max.py` - Remove fitness_age field
- `tools/database/inserters/body_composition.py` - Remove 5 NULL fields

**Database Writer:**
- `tools/database/db_writer.py` - Orchestrates inserters (no direct changes)

**Ingest Worker:**
- `tools/ingest/worker.py` - Fix insertion order (move time_series_metrics, heart_rate_zones UP)

**Regeneration Script:**
- `tools/scripts/regenerate_duckdb.py` - Trigger migration

### Related Documentation

**Existing Planning Documents:**
- `docs/project/2025-10-19_cadence_column_refactoring/planning.md` - Similar pattern (add columns, regenerate)
- `docs/project/2025-10-18_body_composition_table_support/planning.md` - New table support

**Development Guides:**
- `CLAUDE.md` - Project overview, agent system, development workflow
- `DEVELOPMENT_PROCESS.md` - TDD workflow, worktree usage
- `docs/templates/planning.md` - This document's template

### Test Examples

**Existing Inserter Tests:**
- `tests/database/inserters/test_splits.py` - Pattern for splits tests
- `tests/database/inserters/test_form_efficiency.py` - Pattern for form tests
- `tests/database/inserters/test_time_series_metrics.py` - Complex calculation tests

**Integration Test Patterns:**
- `tests/integration/test_*_insertion.py` - Real data insertion tests

### Raw Data Locations

**Sample Activities:**
- `/home/yamakii/garmin_data/data/raw/activity/20721683500/` - Known good activity
- `/home/yamakii/garmin_data/data/raw/activity/*/activity_details.json` - Time series data
- `/home/yamakii/garmin_data/data/raw/activity/*/splits.json` - Lap data (lapDTOs)

### Database

**Current Database:**
- `/home/yamakii/garmin_data/data/database/garmin_performance.duckdb` (659MB, 231 activities)

**Backup Location:**
- `/home/yamakii/garmin_data/data/database/backups/` (create if not exists)

---

## Next Steps

### Immediate Actions (Planning Phase - Main Branch)

1. ✅ Create planning.md (this document) - **COMPLETED**
2. ⬜ Create GitHub Issue with planning content
   - Title: "DuckDB Schema Enhancement: Calculate 28 Missing Fields & Clean 6 NULL Columns"
   - Body: Copy planning.md content
   - Labels: enhancement, high-priority, database
   - Milestone: Q4 2025

3. ⬜ User review and approval
   - Review calculation algorithms (thresholds, formulas)
   - Approve migration strategy (table regeneration)
   - Confirm 28-31 hour estimate

4. ⬜ Commit planning.md to main branch
   ```bash
   git add docs/project/2025-10-20_duckdb_schema_enhancement/planning.md
   git commit -m "docs: add planning for duckdb_schema_enhancement project

   Created comprehensive planning document for:
   - Implementing 28 calculated evaluation fields
   - Removing 6 device-unprovided NULL fields
   - Creating schema documentation (docs/spec/duckdb_schema_mapping.md)
   - Data migration strategy for 231 activities

   Estimated: 28-31 hours
   Affects: 4 tables (splits, form_efficiency, hr_efficiency, performance_trends)

   🤖 Generated with [Claude Code](https://claude.com/claude-code)

   Co-Authored-By: Claude <noreply@anthropic.com>"
   ```

### Handoff to tdd-implementer

**After planning approval:**

1. **Create worktree:**
   ```bash
   git worktree add -b feature/duckdb-schema-enhancement \
       ../garmin-duckdb-schema-enhancement main
   cd ../garmin-duckdb-schema-enhancement
   ```

2. **Setup environment:**
   ```bash
   uv sync --extra dev
   direnv allow  # Auto-load .env
   ```

3. **Activate Serena MCP:**
   ```bash
   # In Claude Code
   mcp__serena__activate_project("/home/yamakii/workspace/garmin-duckdb-schema-enhancement")
   ```

4. **Execute implementation phases:**
   - Phase 2.1: Splits table (3 hours, TDD)
   - Phase 2.2: Form efficiency table (2 hours, TDD)
   - Phase 2.3: HR efficiency table (3 hours, TDD)
   - Phase 2.4: Performance trends table (4 hours, TDD)
   - Phase 3: Schema cleanup (2 hours)
   - Phase 4: Schema documentation (3 hours)
   - Phase 5: Data migration (4 hours)
   - Phase 6: Testing & validation (4 hours)

5. **Generate completion_report.md**

6. **Create PR and merge to main**
   ```bash
   gh pr create --title "feat: implement 28 calculated evaluation fields + schema cleanup" \
                --body "$(cat completion_report.md)"
   ```

7. **Cleanup:**
   ```bash
   cd /home/yamakii/workspace/claude_workspace/garmin-performance-analysis
   git worktree remove ../garmin-duckdb-schema-enhancement
   ```

### Long-term Enhancements (Out of Scope)

**Phase 7: MCP Tool Enhancements (Future)**
- Add evaluation field queries to existing MCP tools:
  - `get_splits_pace_hr()` → Include hr_zone, cadence_rating, environmental_impact
  - `get_form_efficiency_summary()` → Include 4 evaluation fields
  - `get_hr_efficiency_analysis()` → Include 6 evaluation fields
  - `get_performance_trends()` → Include 12 phase-based fields
- Timeline: 2 weeks after Phase 6 completion
- Benefit: Evaluation insights accessible via MCP without direct DB queries

**Phase 8: Evaluation Field Indexing (Future)**
- Add indexes for frequently queried evaluation fields:
  - `CREATE INDEX idx_splits_hr_zone ON splits(hr_zone)`
  - `CREATE INDEX idx_hr_efficiency_training_quality ON hr_efficiency(training_quality)`
- Timeline: If query performance becomes issue
- Benefit: Faster filtering by evaluation categories

**Phase 9: Evaluation Trend Analysis (Future)**
- Track evaluation improvements over time:
  - "Cadence rating improved from 'Good' to 'Excellent' over 3 months"
  - "Training quality 'Excellent' rate increased 40% (Jan: 30% → Apr: 70%)"
- Timeline: 1 month after Phase 6
- Benefit: Quantify training progress via evaluation fields

---

## Appendix: Data Analysis

### Expected Population Rates (After Migration)

| Table | Field | Population % | Reason |
|-------|-------|--------------|--------|
| **splits** | hr_zone | 95% | Depends on heart_rate (95% populated) |
| | cadence_rating | 90% | Depends on cadence (90% populated) |
| | power_efficiency | 10% | Depends on power (rarely available) |
| | environmental_conditions | 85% | Depends on temperature (85% populated) |
| | wind_impact | 80% | Depends on wind_speed (80% populated) |
| | temp_impact | 85% | Depends on temperature (85% populated) |
| | environmental_impact | 85% | Depends on temp_impact + wind_impact |
| **form_efficiency** | gct_evaluation | 100% | avg_gct always populated |
| | vo_trend | 100% | Calculated from splits |
| | vo_evaluation | 100% | avg_vo always populated |
| | vr_evaluation | 100% | avg_vr always populated |
| **hr_efficiency** | primary_zone | 100% | Calculated from heart_rate_zones |
| | zone_distribution_rating | 100% | Calculated from heart_rate_zones |
| | aerobic_efficiency | 100% | Calculated from heart_rate_zones |
| | training_quality | 100% | Calculated from training_type + zones |
| | zone2_focus | 100% | Boolean calculation |
| | zone4_threshold_work | 100% | Boolean calculation |
| **performance_trends** | warmup_avg_cadence | 90% | Depends on time_series cadence |
| | warmup_avg_power | 10% | Depends on time_series power |
| | warmup_evaluation | 95% | Depends on phase identification |
| | run_avg_cadence | 90% | Depends on time_series cadence |
| | run_avg_power | 10% | Depends on time_series power |
| | run_evaluation | 95% | Depends on phase identification |
| | recovery_avg_cadence | 30% | Only if recovery intervals present |
| | recovery_avg_power | 5% | Rarely available |
| | recovery_evaluation | 30% | Only if recovery intervals present |
| | cooldown_avg_cadence | 70% | Depends on cooldown detection |
| | cooldown_avg_power | 10% | Depends on time_series power |
| | cooldown_evaluation | 70% | Depends on cooldown detection |

**Overall Success Criterion:** ≥95% population for fields that don't depend on unavailable raw data (power).

### Sample Query Results (Expected After Implementation)

**Query 1: Get comprehensive evaluation for an activity**
```sql
SELECT
    a.activity_date,
    a.activity_name,
    -- Splits evaluations (first split)
    s.hr_zone,
    s.cadence_rating,
    s.environmental_impact,
    -- Form evaluations
    fe.gct_evaluation,
    fe.vo_evaluation,
    fe.vr_evaluation,
    -- HR evaluations
    he.primary_zone,
    he.training_quality,
    he.zone2_focus,
    -- Phase evaluations
    pt.warmup_evaluation,
    pt.run_evaluation,
    pt.cooldown_evaluation
FROM activities a
LEFT JOIN splits s ON a.activity_id = s.activity_id AND s.split_number = 1
LEFT JOIN form_efficiency fe ON a.activity_id = fe.activity_id
LEFT JOIN hr_efficiency he ON a.activity_id = he.activity_id
LEFT JOIN performance_trends pt ON a.activity_id = pt.activity_id
WHERE a.activity_id = 20721683500;
```

**Expected Result:**
```
activity_date | activity_name | hr_zone | cadence_rating | environmental_impact | gct_evaluation | vo_evaluation | vr_evaluation | primary_zone | training_quality | zone2_focus | warmup_evaluation | run_evaluation | cooldown_evaluation
--------------|---------------|---------|----------------|----------------------|----------------|---------------|---------------|--------------|------------------|-------------|-------------------|----------------|--------------------
2025-10-15    | Morning Run   | Zone 2  | Good (175 spm) | Good conditions      | Excellent (220ms, optimal range) | Good (8.2cm, target <8cm) | Good (6.8%) | Zone 2 (65%) | Excellent (strong aerobic base) | TRUE | Good (5:30, gradual HR increase) | Excellent (optimal cadence, consistent pace) | Adequate (3:45, HR recovery observed)
```

**Query 2: Find activities with excellent form efficiency**
```sql
SELECT
    a.activity_date,
    a.activity_name,
    fe.gct_evaluation,
    fe.vo_evaluation,
    fe.vr_evaluation
FROM activities a
JOIN form_efficiency fe ON a.activity_id = fe.activity_id
WHERE fe.gct_evaluation LIKE 'Excellent%'
  AND fe.vo_evaluation LIKE 'Excellent%'
  AND fe.vr_evaluation LIKE 'Excellent%'
ORDER BY a.activity_date DESC
LIMIT 10;
```

**Expected Result:** List of 10 most recent activities with perfect form (all 3 metrics excellent).

**Query 3: Analyze training quality distribution**
```sql
SELECT
    he.training_quality,
    COUNT(*) AS activity_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM hr_efficiency), 1) AS percentage
FROM hr_efficiency he
GROUP BY he.training_quality
ORDER BY activity_count DESC;
```

**Expected Result:**
```
training_quality                           | activity_count | percentage
-------------------------------------------|----------------|------------
Excellent (strong aerobic base work)       | 85             | 36.8%
Good (aerobic development)                 | 72             | 31.2%
Excellent (solid threshold work)           | 38             | 16.5%
Moderate (general training completed)      | 24             | 10.4%
Good (mostly recovery zones)               | 12             | 5.2%
```

---

**Planning Document Version:** 1.0
**Last Updated:** 2025-10-20
**Status:** Ready for Review
**Estimated Implementation Time:** 28-31 hours
**Database Impact:** 4 tables regenerated, 231 activities migrated
**Success Criterion:** 28 fields ≥95% populated, 6 NULL fields removed
