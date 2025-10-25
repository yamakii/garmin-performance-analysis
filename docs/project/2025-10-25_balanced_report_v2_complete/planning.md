# 計画: BALANCED Report V2 Complete Rewrite

## プロジェクト情報
- **プロジェクト名**: `balanced_report_v2_complete`
- **作成日**: `2025-10-25`
- **ステータス**: 計画中
- **GitHub Issue**: TBD (計画承認後に作成)

---

## Executive Summary

### Problem Statement
Current template (`detailed_report.j2`, 330 lines) doesn't match sample BALANCED reports. Structure discrepancies include:
- Section order differs from samples (Base: 324 lines, Interval: 464 lines)
- Missing training_type-specific conditional sections
- Lacks physiological indicators table for tempo/interval runs
- No folding sections for split details, technical info, glossary

### Solution
Complete template rewrite based on actual sample structure with:
1. **Training_type-specific branching** (recovery/base/tempo/interval)
2. **Exact section order** matching samples
3. **Conditional physiological indicators** (show_physiological flag)
4. **Folding sections** (`<details>` for split details, technical info, glossary)
5. **Worker modifications** for additional data sources

### Expected Outcomes
- Base run reports: 300-324 lines (no physiological indicators)
- Tempo/Interval reports: 400-464 lines (with physiological indicators table + details section)
- Section order matches samples exactly
- All conditionals working correctly for 4 training types

---

## Current State Analysis

### Template vs Sample Comparison

#### Current Template Structure (detailed_report.j2, 330 lines)

```
## 基本情報
## 📊 パフォーマンスサマリー
  - 生理学的指標サマリー (if show_physiological)
  - 類似ワークアウト比較
## 1. フォーム効率
## 2. 環境条件の影響
## 3. 改善ポイント
## 4. フェーズ別評価
  - ウォームアップ/メイン/クールダウン (or リカバリー)
## 4.5. 生理学的指標との関連 (if show_physiological)
## 5. スプリット分析
## 6. 総合評価
```

**Issues:**
- Section numbering (1-6) inconsistent
- "改善ポイント" at position 3 (should be near end)
- Split analysis before 総合評価 (should be after or folded)
- No folding for split details
- No glossary section

#### Sample Base Run Structure (2025-10-08_BALANCED.md, 324 lines)

```
## 基本情報
## 📊 パフォーマンスサマリー
  ### 類似ワークアウトとの比較
  > **参考**: VO2 Max データ
## 総合評価
  ### アクティビティタイプ
  ### 総合所見
  ### ペース・心拍推移 (mermaid graph)
## パフォーマンス指標
  ### スプリット概要
  <details>スプリット詳細</details>
  ### フォーム効率
## フェーズ評価
  ### ウォームアップ/メイン/クールダウン
## 環境要因
## 💡 改善ポイント
## 技術的詳細 (<details>)
## 📚 用語解説 (<details>)
```

**Key Differences:**
- No section numbers
- 総合評価 includes mermaid graph
- パフォーマンス指標 includes スプリット概要 + folded details
- フォーム効率 inside パフォーマンス指標
- 改善ポイント near end (not position 3)
- Folding sections for details/glossary

#### Sample Interval Run Structure (2025-10-15_interval_BALANCED.md, 464 lines)

```
## 基本情報
## 📊 パフォーマンスサマリー
  ### 生理学的指標サマリー ← Present
  ### 類似ワークアウトとの比較
## 総合評価
  ### アクティビティタイプ
  ### 総合所見
  ### ペース・心拍・パワー推移 (mermaid graph)
## パフォーマンス指標
  ### スプリット概要
  <details>Work/Recovery詳細</details>
  ### フォーム効率（Workセグメント）
## 生理学的指標との関連 ← Present (simple version)
  ### VO2 Max活用度
  ### 閾値超過度
## フェーズ評価
  ### ウォームアップ/Work/Recovery/クールダウン (4-phase)
## 環境要因
## 💡 改善ポイント
  ### 1-5 (numbered subsections)
  ### 長期目標 (4-8週間後)
## 技術的詳細 (<details>)
## 📚 用語解説 (<details>)
```

**Key Differences from Base:**
- 生理学的指標サマリー present in パフォーマンスサマリー
- 生理学的指標との関連 section (simple, not verbose)
- 4-phase evaluation (not 3-phase)
- Numbered improvement points (1-5 + 長期目標)

### Section Mapping Table

| Section | Current Template | Base Sample | Interval Sample | Notes |
|---------|-----------------|-------------|----------------|-------|
| 基本情報 | ✅ | ✅ | ✅ | Same |
| パフォーマンスサマリー | ✅ | ✅ | ✅ | Conditional physiological |
| 総合評価 | Position 6 | Position 3 | Position 3 | **MOVE UP** |
| Mermaid graph | ❌ | Inside 総合評価 | Inside 総合評価 | **ADD** |
| パフォーマンス指標 | Position 1 (as フォーム効率) | Position 4 | Position 4 | **RESTRUCTURE** |
| スプリット概要 | Position 5 (as スプリット分析) | Inside パフォーマンス指標 | Inside パフォーマンス指標 | **MOVE** |
| Split details | Inline | `<details>` folded | `<details>` folded | **FOLD** |
| フォーム効率 | Position 1 | Inside パフォーマンス指標 | Inside パフォーマンス指標 | **NEST** |
| 生理学的指標との関連 | Position 4.5 | ❌ (Note only) | Position 5 (simple) | **CONDITIONAL** |
| フェーズ評価 | Position 4 | Position 5 | Position 6 | **REORDER** |
| 環境要因 | Position 2 (as 環境条件の影響) | Position 6 | Position 7 | **REORDER** |
| 改善ポイント | Position 3 | Position 7 | Position 8 | **MOVE DOWN** |
| 技術的詳細 | ❌ | `<details>` | `<details>` | **ADD** |
| 用語解説 | ❌ | `<details>` | `<details>` | **ADD** |

### Critical Structural Changes Needed

1. **Section Order**: Complete reorder to match samples
2. **Nesting**: フォーム効率 must be inside パフォーマンス指標
3. **Folding**: Add `<details>` for split details, technical info, glossary
4. **Mermaid Graphs**: Add inside 総合評価
5. **Conditional Logic**: Physiological indicators based on training_type
6. **Numbering**: Remove all section numbers (samples don't use them)

---

## Architecture Design

### Complete Template Structure (Pseudocode)

```jinja2
{# Phase 1: Training type category mapping #}
{% set show_physiological = training_type_category in ["tempo_threshold", "interval_sprint"] %}
{% set phase_count = get_phase_count(training_type_category) %}  {# 1, 3, or 4 #}

{# =================================================================== #}
{# SECTION 1: 基本情報 #}
{# =================================================================== #}
## 基本情報
| 項目 | 値 |
|------|-----|
| アクティビティID | {{ activity_id }} |
| 実施日 | {{ date }} |
| 活動名 | {{ activity_name }} |
| 場所 | {{ location_name }} |
| トレーニングタイプ | {{ training_type }} |
| 総距離 | {{ distance_km }} km |
| 総時間 | {{ duration_formatted }} |
| 平均ペース | {{ avg_pace_formatted }}/km |
| 平均心拍数 | {{ avg_heart_rate }} bpm |
| 平均ケイデンス | {{ avg_cadence }} spm |

---

{# =================================================================== #}
{# SECTION 2: 📊 パフォーマンスサマリー #}
{# =================================================================== #}
## 📊 パフォーマンスサマリー

{% if show_physiological %}
### 生理学的指標サマリー

| 指標 | 現在値 | 評価 |
|------|--------|------|
| **VO2 Max** | {{ vo2_max_value }} ml/kg/min | カテゴリ: {{ vo2_max_category }} |
| **VO2 Max利用率** | {{ vo2_max_utilization }}% | {{ vo2_max_utilization_eval }} |
| **閾値ペース** | {{ threshold_pace_formatted }}/km | {{ threshold_pace_comparison }} |
| **FTP（パワー）** | {{ ftp_value }} W | Work平均{{ work_avg_power }}W = FTPの{{ ftp_percentage }}% |

{% endif %}

### 類似ワークアウトとの比較

過去の同条件ワークアウト（{{ similar_conditions }}）との比較：

| 指標 | 今回 | 類似{{ similar_count }}回平均 | 変化 | トレンド |
|------|------|------------|------|----------|
| {{ metric_comparisons | render_table }}

**💡 インサイト**: {{ insight_text }}

{% if not show_physiological %}
> **参考**: VO2 Max {{ vo2_max_value }} ml/kg/min（{{ vo2_max_category }}）、閾値ペース {{ threshold_pace_formatted }}/km
{% endif %}

---

{# =================================================================== #}
{# SECTION 3: 総合評価 #}
{# =================================================================== #}
## 総合評価

### アクティビティタイプ
**{{ activity_type_name }}** ({{ activity_type_english }})

{{ activity_type_description }}

### 総合所見 ({{ overall_rating_stars }} {{ overall_rating_score }}/5.0)

{{ overall_summary_paragraph }}

**✅ 優れている点:**
{% for strength in key_strengths %}
- {{ strength }}
{% endfor %}

**⚠️ 改善可能な点:**
{% for area in improvement_areas %}
- {{ area }}
{% endfor %}

{{ overall_conclusion_paragraph }}

### ペース・心拍{% if show_physiological %}・パワー{% endif %}推移{% if is_interval %}（Work/Recoveryハイライト）{% endif %}

```mermaid
xychart-beta
    title "{{ graph_title }}"
    x-axis {{ x_axis_labels }}
    y-axis "{{ y_axis_label }}" {{ y_min }} --> {{ y_max }}
    line {{ pace_data }}
    line {{ heart_rate_data }}
    {% if show_physiological %}
    line {{ power_data }}
    {% endif %}
```

{% if is_interval %}
**凡例**: 青=ペース（秒/km）、橙=心拍（bpm）、緑=パワー（W）

**分析**:
{{ interval_graph_analysis }}
{% endif %}

---

{# =================================================================== #}
{# SECTION 4: パフォーマンス指標 #}
{# =================================================================== #}
## パフォーマンス指標

{% if is_interval %}
> **評価対象**: {{ target_segments_description }}（インターバル走は高強度区間のパフォーマンスを重視）
{% endif %}

### スプリット概要{% if is_interval %}（全区間）{% endif %}

| # | {% if is_interval %}タイプ | {% endif %}ペース | 心拍 | ケイデンス | パワー | ストライド | GCT | VO | VR | 標高 |
|---|{% if is_interval %}-------|{% endif %}--------|------|------------|--------|------------|-----|----|----|------|
{{ splits_table | render_rows }}

**📈 {% if is_interval %}Workセグメント {% endif %}ハイライト:**
{{ highlights_list }}

<details>
<summary>📋 {% if is_interval %}Work/Recovery{% else %}スプリット{% endif %}詳細分析（クリックで展開）</summary>

{{ split_details_content }}

</details>

---

### フォーム効率（{% if is_interval %}Workセグメント {% endif %}ペース補正評価） ({{ form_efficiency_rating_stars }} {{ form_efficiency_rating_score }}/5.0)

{% if is_interval %}
```mermaid
pie title "心拍ゾーン分布（全体）"
{{ heart_rate_zone_pie_data }}
```
{% else %}
```mermaid
pie title "心拍ゾーン分布"
{{ heart_rate_zone_pie_data }}
```
{% endif %}

**{% if is_interval %}Workセグメント（{{ work_segment_count }}本）の平均値（{% endif %}ペース{{ avg_pace_formatted }} = {{ avg_pace_seconds }}秒/km 基準{% if is_interval %}）{% endif %}:**

| 指標 | 実測値 | ペース基準値 | 補正スコア | 評価 |
|------|--------|------------|-----------|------|
| **接地時間** | {{ gct_actual }}ms | {{ gct_baseline }}ms | **{{ gct_score }}%** {{ gct_label }} | {{ gct_rating_stars }} {{ gct_rating_score }} |
| **垂直振幅** | {{ vo_actual }}cm | {{ vo_baseline }}cm | **{{ vo_score }}%** {{ vo_label }} | {{ vo_rating_stars }} {{ vo_rating_score }} |
| **垂直比率** | {{ vr_actual }}% | 8.0-9.5% | {{ vr_label }} | {{ vr_rating_stars }} {{ vr_rating_score }} |
| **パワー** | {{ power_actual }}W | {{ power_baseline }}W（類似平均） | **{{ power_score }}%** {{ power_label }} | {{ power_rating_stars }} {{ power_rating_score }} |
| **ストライド長** | {{ stride_actual }}m | {{ stride_baseline }}m（類似平均） | **{{ stride_score }}%** {{ stride_label }} | {{ stride_rating_stars }} {{ stride_rating_score }} |

**総合フォーム効率: {{ form_efficiency_rating_stars }} {{ form_efficiency_rating_score }}/5.0**

{{ form_efficiency_summary_paragraph }}

**パワー効率詳細:**
{{ power_efficiency_details }}

**ストライド長詳細:**
{{ stride_length_details }}

**心拍効率:**
{{ heart_rate_efficiency_details }}

**パフォーマンストレンド:**
{{ performance_trend_details }}

---

{% if show_physiological %}
{# =================================================================== #}
{# SECTION 5: 生理学的指標との関連 (Tempo/Interval only) #}
{# =================================================================== #}
## 生理学的指標との関連

### VO2 Max活用度 ({{ vo2_max_usage_rating_stars }} {{ vo2_max_usage_rating_score }}/5.0)

{{ vo2_max_usage_paragraph }}

- **現在のVO2 Max**: {{ vo2_max_value }} ml/kg/min（{{ vo2_max_category }}）
- **{% if is_interval %}Work{% else %}メイン区間{% endif %}平均心拍**: {{ target_avg_hr }} bpm（最大心拍の{{ max_hr_percentage }}%）
- **VO2 Max利用率**: 約{{ vo2_max_utilization }}%（{{ vo2_max_utilization_eval }}）

**期待効果**: {{ vo2_max_expected_effect }}

### 閾値超過度 ({{ threshold_usage_rating_stars }} {{ threshold_usage_rating_score }}/5.0)

{{ threshold_usage_paragraph }}

- **閾値心拍**: {{ threshold_hr }} bpm（最大心拍の{{ threshold_hr_percentage }}%）
- **{% if is_interval %}Work{% else %}メイン区間{% endif %}平均心拍**: {{ target_avg_hr }} bpm（閾値{{ threshold_hr_diff }}bpm）
- **閾値パワー（FTP）**: {{ ftp_value }} W
- **{% if is_interval %}Work{% else %}メイン区間{% endif %}平均パワー**: {{ target_avg_power }} W（FTPの{{ ftp_percentage }}%）→ {{ power_zone_name }} ✅

**期待効果**: {{ threshold_expected_effect }}

---

{% endif %}

{# =================================================================== #}
{# SECTION 6 (or 5): フェーズ評価 #}
{# =================================================================== #}
## フェーズ評価

{% if phase_count >= 1 %}
### ウォームアップフェーズ ({{ warmup_rating_stars }} {{ warmup_rating_score }}/5.0)
**実際**: {{ warmup_actual_description }}

**{% if phase_count == 1 %}評価{% else %}推奨{% endif %}**: {{ warmup_recommendation }}

{{ warmup_evaluation_content }}

{% if phase_count == 1 %}
{# Recovery run - only 1 phase, no more sections #}
---
{% endif %}
{% endif %}

{% if phase_count >= 3 %}
### {% if is_interval %}Workフェーズ{% else %}メイン走行フェーズ{% endif %} ({{ main_rating_stars }} {{ main_rating_score }}/5.0)
**実際**: {{ main_actual_description }}

**評価**: {{ main_evaluation_content }}

{% if is_interval %}
**目標達成度:**
{{ interval_achievement_details }}
{% endif %}

---

{% if phase_count == 4 %}
### Recoveryフェーズ ({{ recovery_rating_stars }} {{ recovery_rating_score }}/5.0)
**実際**: {{ recovery_actual_description }}

**評価**: {{ recovery_evaluation_content }}

**改善点:**
{{ recovery_improvement_points }}

---
{% endif %}

### クールダウンフェーズ ({{ cooldown_rating_stars }} {{ cooldown_rating_score }}/5.0)
**実際**: {{ cooldown_actual_description }}

**推奨**: {{ cooldown_recommendation }}

**影響**: {{ cooldown_impact_description }}

---
{% endif %}

{# =================================================================== #}
{# SECTION 7 (or 6 or 5): 環境要因 #}
{# =================================================================== #}
## 環境要因

### 気象条件・環境インパクト ({{ environment_rating_stars }} {{ environment_rating_score }}/5.0)

- **気温**: {{ temperature }}°C（{{ temperature_eval }}）{% if temperature_ideal_flag %}✅{% else %}⚠️{% endif %}
- **湿度**: {{ humidity }}%（{{ humidity_eval }}）{% if humidity_ideal_flag %}✅{% else %}⚠️{% endif %}
- **風速**: {{ wind_speed }} m/s（{{ wind_eval }}）
- **地形**: {{ terrain_classification }}（獲得標高{{ elevation_gain }}m、損失{{ elevation_loss }}m）

**評価**: {{ environment_evaluation_paragraph }}

{% if environment_impact_paragraph %}
**環境によるパフォーマンス影響**: {{ environment_impact_paragraph }}
{% endif %}

---

{# =================================================================== #}
{# SECTION 8 (or 7 or 6): 💡 改善ポイント #}
{# =================================================================== #}
## 💡 改善ポイント

{% if is_interval %}
次回の{{ interval_description }}を実施する際の改善点：
{% else %}
今回の{{ run_description }}を次回実施する際の改善点：
{% endif %}

{% for improvement in improvements %}
### {{ improvement.number }}. {{ improvement.title }} ⭐ 重要度: {{ improvement.priority }}
**現状**: {{ improvement.current_state }}

**推奨アクション:**
{{ improvement.recommended_actions }}

**期待効果**: {{ improvement.expected_effect }}

---

{% endfor %}

{% if show_physiological and is_interval %}
### 長期目標（4-8週間後）

**VO2 Max向上:**
- 現在: {{ vo2_max_current }} ml/kg/min
- 目標: {{ vo2_max_target }} ml/kg/min（{{ vo2_max_improvement }}）

**閾値ペース改善:**
- 現在: {{ threshold_pace_current }}/km
- 目標: {{ threshold_pace_target }}/km（{{ threshold_pace_improvement }}）

**FTP向上:**
- 現在: {{ ftp_current }} W
- 目標: {{ ftp_target }} W（{{ ftp_improvement }}）

---
{% endif %}

{# =================================================================== #}
{# SECTION 9 (or 8 or 7): 技術的詳細 #}
{# =================================================================== #}
## 技術的詳細

<details>
<summary>クリックで展開</summary>

### データソース
- スプリットデータ: DuckDB (splits table - power, stride_length含む)
{% if is_interval %}
- インターバル区間: DuckDB (splits.intensity_type = 'active'/'rest')
{% endif %}
- フォーム指標: DuckDB (form_efficiency table)
- 心拍データ: DuckDB (hr_efficiency, heart_rate_zones tables)
{% if show_physiological %}
- 生理学的指標: DuckDB (vo2_max, lactate_threshold tables)
{% endif %}
- 環境データ: DuckDB (weather table)
- 類似ワークアウト: `mcp__garmin-db__compare_similar_workouts()`

### 分析バージョン
- 生成日時: {{ generation_timestamp }}
- システムバージョン: v4.0 (BALANCED - 情報最適化版)
- 改善項目: 構成最適化/セクション統合/アドバイス形式への変更

</details>

---

{# =================================================================== #}
{# SECTION 10 (or 9 or 8): 📚 用語解説 #}
{# =================================================================== #}
## 📚 用語解説

<details>
<summary>クリックで展開</summary>

{% if is_interval %}
- **Work**: インターバル走の高強度区間（{{ work_distance }}km×{{ work_count }}本の「{{ work_distance }}km」部分）
- **Recovery**: Work間の回復区間（{{ recovery_distance }}m）
{% endif %}
- **GCT (Ground Contact Time)**: 接地時間。ペースが速いほど短くなる（目標: ペース基準値{% if is_interval %}±1%{% else %}-5%{% endif %}以内）
- **VO (Vertical Oscillation)**: 垂直振幅。走行中の上下動（目標: 6-8cm）
- **VR (Vertical Ratio)**: 垂直比率。VO÷ストライド長（目標: 8-10%、ペース依存なし）
- **パワー**: ランニングパワー（W）。{% if is_interval %}高強度ほど高い{% else %}効率向上で同じペースでも低下する{% endif %}
{% if show_physiological %}
- **FTP (Functional Threshold Power)**: 機能的閾値パワー。1時間維持可能な最大パワー
{% endif %}
- **ストライド長**: 1歩あたりの距離（m）。スピード = ケイデンス × ストライド長
{% if is_interval %}
- **Zone 5**: VO2 Maxゾーン。非常に高強度（FTPの105%以上）
{% else %}
- **Zone 2**: 有酸素ゾーン。長時間維持可能（会話余裕あり）
- **Zone 3**: テンポゾーン。「やや速い」と感じる強度
{% endif %}
{% if show_physiological %}
- **VO2 Max**: 最大酸素摂取量。有酸素能力の指標
- **VO2 Max利用率**: VO2 Maxペースに対する実際のペースの比率
- **閾値ペース**: 乳酸閾値ペース。約60分維持可能な最速ペース
{% endif %}
{% if training_type_category == "low_moderate" %}
- **有酸素ベース走**: Zone 2-3中心の中強度走。有酸素基盤構築が目的
{% endif %}
- **ペース補正評価**: そのペースに対する相対評価（同じペースのランナーと比較）
{% if is_interval %}
- **回復率**: Recovery終了時の心拍低下率（例: 170bpm→145bpm = 85%回復）
{% endif %}

</details>

---

*このレポートは、Garmin Performance Analysis System により自動生成されました。*
```

### Key Structural Decisions

1. **Section Numbers Removed**: Samples don't use numbered sections (1-6)
2. **Nested フォーム効率**: Inside パフォーマンス指標 (not separate section 1)
3. **総合評価 Early**: Position 3 (not position 6)
4. **Mermaid Graphs**: Inside 総合評価 section
5. **Folding**: `<details>` for split details, technical info, glossary
6. **Conditional Physiological**: Based on `show_physiological` flag
7. **改善ポイント**: Near end (position 8/7/6 depending on phase count)
8. **Phase Count**: 1 (recovery), 3 (base/tempo), 4 (interval)

---

## Data Model

### Training Type Category Mapping

```python
# Worker: report_generator_worker.py, load_performance_data()
training_type = hr_eff[0]  # From hr_efficiency.training_type
if training_type in ["recovery"]:
    training_type_category = "recovery"
elif training_type in ["aerobic_base", "low_moderate"]:
    training_type_category = "low_moderate"
elif training_type in ["tempo", "lactate_threshold"]:
    training_type_category = "tempo_threshold"
elif training_type in ["vo2max", "anaerobic_capacity", "speed"]:
    training_type_category = "interval_sprint"
else:
    training_type_category = "low_moderate"  # Default fallback
```

### Template Variables (Context Dict)

#### Existing Variables (No Changes)
```python
context = {
    "activity_id": str(activity_id),
    "date": date,
    "activity_name": str,
    "location_name": str,
    "basic_metrics": {
        "distance_km": float,
        "duration_seconds": int,
        "avg_pace_seconds_per_km": float,
        "avg_heart_rate": float,
        "avg_cadence": float,
        # ... (existing fields)
    },
    "weather_data": {
        "temp_celsius": float,
        "relative_humidity_percent": float,
        "wind_speed_kmh": float,
    },
    "training_type": str,
    "training_type_category": str,  # ← EXISTING (already mapped in Phase 1)
    "vo2_max_data": {
        "precise_value": float,
        "value": float,
        "date": str,
        "category": str,
    },
    "lactate_threshold_data": {
        "heart_rate": float,
        "speed_mps": float,
        "date_hr": str,
        "functional_threshold_power": float,
        "date_power": str,
    },
    "splits": [
        {
            "index": int,
            "distance": float,
            "pace_seconds_per_km": float,
            "pace_formatted": str,
            "heart_rate": float,
            "cadence": float,
            "power": float,
            "stride_length": float,
            "ground_contact_time": float,
            "vertical_oscillation": float,
            "vertical_ratio": float,
            "elevation_gain": float,
            "elevation_loss": float,
        }
    ],
    "efficiency": str | dict,  # From efficiency-section-analyst
    "environment_analysis": str | dict,  # From environment-section-analyst
    "phase_evaluation": dict,  # From phase-section-analyst
    "split_analysis": str | dict,  # From split-section-analyst
    "summary": dict,  # From summary-section-analyst
}
```

#### New Variables Needed (Worker Modifications)

**For Mermaid Graphs:**
```python
context["mermaid_data"] = {
    "x_axis_labels": ["1", "2", "3", "4", "5", "6", "7"],  # Split indexes or Work/Recovery
    "pace_data": [398, 403, 403, 419, 402, 406, 404],  # seconds/km
    "heart_rate_data": [128, 145, 148, 148, 149, 150, 151],  # bpm
    "power_data": [215, 225, 227, 220, 228, 226, 227] if show_physiological else None,  # W
}
```

**For Similar Workout Comparison:**
```python
context["similar_workouts"] = {
    "conditions": "距離5-6km、ペース6:30-7:00/km、平坦コース",
    "count": 3,
    "comparisons": [
        {
            "metric": "平均ペース",
            "current": "6:45/km",
            "average": "6:48/km",
            "change": "+3秒速い",
            "trend": "↗️ 改善",
        },
        # ... more metrics
    ],
    "insight": "ペース+3秒速いのにパワー-5W低下＝効率が2.2%向上 ✅",
}
```
**Data Source**: `mcp__garmin-db__compare_similar_workouts(activity_id, ...)`

**For Form Efficiency Pace Correction:**
```python
context["form_efficiency_pace_corrected"] = {
    "avg_pace_seconds": 405,  # seconds/km
    "gct": {
        "actual": 253.0,  # ms
        "baseline": 266.3,  # ms (from pace)
        "score": -5.0,  # %
        "label": "優秀",
        "rating_stars": "★★★★★",
        "rating_score": 5.0,
    },
    "vo": {
        "actual": 7.13,  # cm
        "baseline": 7.46,  # cm (from pace)
        "score": -4.4,  # %
        "label": "優秀",
        "rating_stars": "★★★★☆",
        "rating_score": 4.5,
    },
    # ... vr, power, stride
}
```
**Data Source**: Calculate from `form_efficiency` + `basic_metrics.avg_pace_seconds_per_km`

**For Improvement Points:**
```python
context["improvements"] = [
    {
        "number": 1,
        "title": "ウォームアップの導入",
        "priority": "高",
        "current_state": "なし（最初から心拍145bpmでスタート）",
        "recommended_actions": "- 最初の1-1.5kmをゆっくり開始（7:30-8:00/km）\n- 心拍120-135bpm、パワー180-200Wを目安に",
        "expected_effect": "怪我リスク低減、メイン走行での効率向上",
    },
    # ... more improvements (2-5)
]
```
**Data Source**: Extract from `summary.recommendations` or generate from `phase_evaluation`

### Missing Data Sources (Future Work)

**Similar Workouts Comparison** (Phase 3):
- Currently: Not available in Worker
- Required: Call `mcp__garmin-db__compare_similar_workouts(activity_id, ...)`
- Return: List of similar activities with comparison metrics

**Mermaid Graph Data** (Phase 3):
- Currently: Not available in Worker
- Required: Aggregate splits data into graph format
- Return: x_axis_labels, pace_data, heart_rate_data, power_data (optional)

**Pace Correction Baseline** (Phase 2):
- Currently: Not calculated
- Required: Implement `get_baseline_gct(pace_seconds_per_km)`, `get_baseline_vo(pace_seconds_per_km)` functions
- Return: Baseline values for GCT, VO based on pace

---

## Implementation Phases

### Phase 1: Template Structure Rewrite (Section Order)
**Goal**: Match sample section order exactly

**Implementation:**
1. **Reorder sections** in `detailed_report.j2`:
   - 基本情報
   - 📊 パフォーマンスサマリー
   - **総合評価** (MOVE UP from position 6)
   - **パフォーマンス指標** (new container section)
     - スプリット概要 (MOVE from position 5)
     - フォーム効率 (NEST inside, was position 1)
   - 生理学的指標との関連 (CONDITIONAL, was position 4.5)
   - フェーズ評価 (keep relative position)
   - 環境要因 (keep relative position, rename from "環境条件の影響")
   - 💡 改善ポイント (MOVE DOWN from position 3)
   - 技術的詳細 (NEW, folded)
   - 📚 用語解説 (NEW, folded)

2. **Remove section numbers** (1-6):
   - Change `## 1. 🎯 フォーム効率` → `### フォーム効率`
   - Change `## 2. 🌍 環境条件の影響` → `## 環境要因`
   - etc.

3. **Add folding sections**:
   ```jinja2
   <details>
   <summary>📋 スプリット詳細分析（クリックで展開）</summary>
   {{ split_details_content }}
   </details>
   ```

**Test:**
- [ ] Section order matches base sample (2025-10-08_BALANCED.md)
- [ ] Section order matches interval sample (2025-10-15_interval_BALANCED.md)
- [ ] No section numbers (1-6) present
- [ ] Folding sections work (`<details>` expands/collapses)
- [ ] Generate report for `training_type_category="low_moderate"` (base run)

---

### Phase 2: Mermaid Graphs + 総合評価 Content
**Goal**: Add mermaid graphs inside 総合評価 section

**Implementation:**
1. **Worker modifications** (report_generator_worker.py):
   ```python
   def generate_mermaid_data(self, activity_id: int, splits: list) -> dict:
       """Generate mermaid graph data from splits."""
       x_labels = [str(s["index"]) for s in splits]
       pace_data = [int(s["pace_seconds_per_km"]) for s in splits]
       hr_data = [int(s["heart_rate"]) for s in splits]
       power_data = [int(s["power"]) for s in splits if s.get("power")]
       return {
           "x_axis_labels": json.dumps(x_labels),
           "pace_data": json.dumps(pace_data),
           "heart_rate_data": json.dumps(hr_data),
           "power_data": json.dumps(power_data) if power_data else None,
       }
   ```

2. **Template additions** (detailed_report.j2):
   ```jinja2
   ## 総合評価

   ### アクティビティタイプ
   **{{ summary.activity_type }}**

   {{ summary.activity_type_description }}

   ### 総合所見 ({{ summary.overall_rating }})

   {{ summary.summary }}

   **✅ 優れている点:**
   {{ summary.key_strengths | bullet_list }}

   **⚠️ 改善可能な点:**
   {{ summary.improvement_areas | bullet_list }}

   ### ペース・心拍{% if show_physiological %}・パワー{% endif %}推移

   ```mermaid
   xychart-beta
       title "スプリット別 ペース・心拍数推移"
       x-axis {{ mermaid_data.x_axis_labels }}
       y-axis "ペース(秒/km)" 380 --> 440
       y-axis "心拍(bpm)" 120 --> 160
       line {{ mermaid_data.pace_data }}
       line {{ mermaid_data.heart_rate_data }}
       {% if show_physiological and mermaid_data.power_data %}
       line {{ mermaid_data.power_data }}
       {% endif %}
   ```
   ```

3. **Interval-specific graph** (Work/Recovery highlights):
   ```jinja2
   {% if is_interval %}
   **凡例**: 青=ペース（秒/km）、橙=心拍（bpm）、緑=パワー（W）

   **分析**:
   - Work 1-4は優秀な一貫性（4:26-4:30/km、310-315W）
   - Work 5で心拍175bpm、パワー305Wと疲労の兆候も、ペース4:30/kmを維持
   - Recovery後半（R3-4）の心拍回復がやや不十分（150-152bpm）
   {% endif %}
   ```

**Test:**
- [ ] Mermaid graph renders correctly for base run
- [ ] Mermaid graph includes power for interval run
- [ ] Graph title changes for interval run ("Work/Recoveryハイライト")
- [ ] Graph analysis paragraph appears for interval run
- [ ] No template errors when power data is None

---

### Phase 3: Similar Workouts Comparison + Data Integration
**Goal**: Add 類似ワークアウトとの比較 table with actual data

**Implementation:**
1. **Worker modifications** (report_generator_worker.py):
   ```python
   def load_similar_workouts(self, activity_id: int, training_type: str) -> dict:
       """Load similar workouts comparison using MCP tool."""
       # Call MCP tool
       from tools.mcp.garmin_db_mcp import compare_similar_workouts

       similar = compare_similar_workouts(
           activity_id=activity_id,
           distance_tolerance=0.10,
           pace_tolerance=0.10,
           terrain_match=True,
           limit=10
       )

       if not similar or len(similar) < 3:
           return None

       # Calculate averages from top 3 similar workouts
       # ...

       return {
           "conditions": f"距離{min_dist}-{max_dist}km、ペース{min_pace}-{max_pace}/km、{terrain}",
           "count": len(similar[:3]),
           "comparisons": [
               {
                   "metric": "平均ペース",
                   "current": format_pace(current_pace),
                   "average": format_pace(similar_avg_pace),
                   "change": f"+{pace_diff}秒速い" if pace_diff > 0 else f"-{abs(pace_diff)}秒遅い",
                   "trend": "↗️ 改善" if pace_diff > 0 else "↘️ 悪化",
               },
               # ... more metrics (heart_rate, power, stride, gct, vo)
           ],
           "insight": "ペース+3秒速いのにパワー-5W低下＝効率が2.2%向上 ✅",
       }
   ```

2. **Template modifications** (detailed_report.j2):
   ```jinja2
   ### 類似ワークアウトとの比較

   {% if similar_workouts %}
   過去の同条件ワークアウト（{{ similar_workouts.conditions }}）との比較：

   | 指標 | 今回 | 類似{{ similar_workouts.count }}回平均 | 変化 | トレンド |
   |------|------|------------|------|----------|
   {% for comp in similar_workouts.comparisons %}
   | {{ comp.metric }} | {{ comp.current }} | {{ comp.average }} | {{ comp.change }} | {{ comp.trend }} |
   {% endfor %}

   **💡 インサイト**: {{ similar_workouts.insight }}
   {% else %}
   類似ワークアウトが見つかりませんでした。
   {% endif %}
   ```

**Test:**
- [ ] Similar workouts table renders with real data
- [ ] Comparison metrics include pace, HR, power, stride, GCT, VO
- [ ] Insight text is meaningful (e.g., "効率が2.2%向上")
- [ ] Handles case when no similar workouts found
- [ ] MCP tool call succeeds

**Note**: This phase requires MCP tool integration. If `compare_similar_workouts()` doesn't exist or returns insufficient data, can use placeholder data for Phase 3 and mark as "Future Work".

---

### Phase 4: Pace-Corrected Form Efficiency
**Goal**: Implement ペース補正評価 for GCT, VO

**Implementation:**
1. **Worker modifications** (report_generator_worker.py):
   ```python
   def calculate_pace_corrected_form_efficiency(
       self, avg_pace_seconds_per_km: float, form_eff: dict
   ) -> dict:
       """Calculate pace-corrected form efficiency scores."""

       # Baseline GCT from pace (linear approximation)
       # 4:00/km → 230ms, 7:00/km → 270ms
       # y = 230 + (pace - 240) * 0.22
       baseline_gct = 230 + (avg_pace_seconds_per_km - 240) * 0.22

       # Baseline VO from pace (gentle increase)
       # 4:00/km → 6.8cm, 7:00/km → 7.5cm
       # y = 6.8 + (pace - 240) * 0.004
       baseline_vo = 6.8 + (avg_pace_seconds_per_km - 240) * 0.004

       # GCT efficiency score
       gct_actual = form_eff["gct_average"]
       gct_score = ((gct_actual - baseline_gct) / baseline_gct) * 100
       gct_label = "優秀" if gct_score < -5 else ("良好" if abs(gct_score) <= 5 else "要改善")
       gct_rating = 5.0 if gct_score < -5 else (4.5 if gct_score < -2 else 4.0)

       # VO efficiency score
       vo_actual = form_eff["vo_average"]
       vo_score = ((vo_actual - baseline_vo) / baseline_vo) * 100
       vo_label = "優秀" if vo_score < -5 else ("良好" if abs(vo_score) <= 5 else "要改善")
       vo_rating = 5.0 if vo_score < -5 else (4.5 if vo_score < -2 else 4.0)

       # VR (no pace correction)
       vr_actual = form_eff["vr_average"]
       vr_label = "理想範囲内" if 8.0 <= vr_actual <= 9.5 else "要改善"
       vr_rating = 5.0 if 8.0 <= vr_actual <= 9.5 else 3.5

       return {
           "avg_pace_seconds": int(avg_pace_seconds_per_km),
           "gct": {
               "actual": round(gct_actual, 1),
               "baseline": round(baseline_gct, 1),
               "score": round(gct_score, 1),
               "label": gct_label,
               "rating_stars": "★" * int(gct_rating) + "☆" * (5 - int(gct_rating)),
               "rating_score": gct_rating,
           },
           "vo": {
               "actual": round(vo_actual, 2),
               "baseline": round(baseline_vo, 2),
               "score": round(vo_score, 1),
               "label": vo_label,
               "rating_stars": "★" * int(vo_rating) + "☆" * (5 - int(vo_rating)),
               "rating_score": vo_rating,
           },
           "vr": {
               "actual": round(vr_actual, 2),
               "label": vr_label,
               "rating_stars": "★" * int(vr_rating) + "☆" * (5 - int(vr_rating)),
               "rating_score": vr_rating,
           },
       }
   ```

2. **Template modifications** (detailed_report.j2):
   ```jinja2
   ### フォーム効率（ペース補正評価） ({{ form_efficiency_rating }})

   **主要指標（ペース{{ avg_pace_formatted }} = {{ form_efficiency_pace_corrected.avg_pace_seconds }}秒/km 基準）:**

   | 指標 | 実測値 | ペース基準値 | 補正スコア | 評価 |
   |------|--------|------------|-----------|------|
   | **接地時間** | {{ form_efficiency_pace_corrected.gct.actual }}ms | {{ form_efficiency_pace_corrected.gct.baseline }}ms | **{{ form_efficiency_pace_corrected.gct.score }}%** {{ form_efficiency_pace_corrected.gct.label }} | {{ form_efficiency_pace_corrected.gct.rating_stars }} {{ form_efficiency_pace_corrected.gct.rating_score }} |
   | **垂直振幅** | {{ form_efficiency_pace_corrected.vo.actual }}cm | {{ form_efficiency_pace_corrected.vo.baseline }}cm | **{{ form_efficiency_pace_corrected.vo.score }}%** {{ form_efficiency_pace_corrected.vo.label }} | {{ form_efficiency_pace_corrected.vo.rating_stars }} {{ form_efficiency_pace_corrected.vo.rating_score }} |
   | **垂直比率** | {{ form_efficiency_pace_corrected.vr.actual }}% | 8.0-9.5% | {{ form_efficiency_pace_corrected.vr.label }} | {{ form_efficiency_pace_corrected.vr.rating_stars }} {{ form_efficiency_pace_corrected.vr.rating_score }} |
   | **パワー** | {{ power_actual }}W | {{ power_baseline }}W（類似平均） | **{{ power_score }}%** {{ power_label }} | {{ power_rating }} |
   | **ストライド長** | {{ stride_actual }}m | {{ stride_baseline }}m（類似平均） | **{{ stride_score }}%** {{ stride_label }} | {{ stride_rating }} |

   **総合フォーム効率: {{ form_efficiency_rating }}**

   {{ avg_pace_formatted }}という{{ pace_intensity }}ペースに対して、全指標が基準以上の効率を示しています。
   ```

**Test:**
- [ ] GCT baseline calculated correctly from pace
- [ ] VO baseline calculated correctly from pace
- [ ] GCT/VO scores calculated (% deviation from baseline)
- [ ] Labels ("優秀", "良好", "要改善") assigned correctly
- [ ] Star ratings (★★★★★, ★★★★☆, etc.) displayed correctly
- [ ] Summary paragraph mentions pace and intensity level

---

## Testing Strategy

### Unit Tests

#### test_template_structure.py
```python
def test_section_order_base_run():
    """Base run section order matches sample."""
    sections = extract_sections(render_report(training_type_category="low_moderate"))
    expected_order = [
        "基本情報",
        "📊 パフォーマンスサマリー",
        "総合評価",
        "パフォーマンス指標",
        "フェーズ評価",
        "環境要因",
        "💡 改善ポイント",
        "技術的詳細",
        "📚 用語解説",
    ]
    assert sections == expected_order

def test_section_order_interval_run():
    """Interval run includes 生理学的指標との関連."""
    sections = extract_sections(render_report(training_type_category="interval_sprint"))
    assert "生理学的指標との関連" in sections
    assert sections.index("生理学的指標との関連") < sections.index("フェーズ評価")

def test_no_section_numbers():
    """No section numbers (1-6) in report."""
    report = render_report()
    assert "## 1." not in report
    assert "## 2." not in report
    assert "## 3." not in report

def test_folding_sections_present():
    """Folding sections (<details>) present."""
    report = render_report()
    assert "<details>" in report
    assert "<summary>📋 スプリット詳細分析（クリックで展開）</summary>" in report
    assert "<summary>クリックで展開</summary>" in report  # Technical details
    assert "</details>" in report
```

#### test_mermaid_graphs.py
```python
def test_mermaid_graph_base_run():
    """Mermaid graph present in base run."""
    report = render_report(training_type_category="low_moderate")
    assert "```mermaid" in report
    assert "xychart-beta" in report
    assert "スプリット別 ペース・心拍数推移" in report

def test_mermaid_graph_interval_run_includes_power():
    """Mermaid graph includes power for interval run."""
    report = render_report(training_type_category="interval_sprint")
    assert "line {{ mermaid_data.power_data }}" in report or "line [" in report  # Check for power line

def test_mermaid_graph_analysis_interval_only():
    """Mermaid graph analysis only present for interval run."""
    base_report = render_report(training_type_category="low_moderate")
    interval_report = render_report(training_type_category="interval_sprint")

    assert "**凡例**: 青=ペース" not in base_report
    assert "**凡例**: 青=ペース" in interval_report
    assert "**分析**:" in interval_report
```

#### test_form_efficiency_pace_correction.py
```python
def test_gct_baseline_calculation():
    """GCT baseline calculated correctly from pace."""
    # 6:45/km (405 seconds) → baseline 266.3ms
    baseline = get_baseline_gct(405)
    assert abs(baseline - 266.3) < 0.1

def test_vo_baseline_calculation():
    """VO baseline calculated correctly from pace."""
    # 6:45/km (405 seconds) → baseline 7.46cm
    baseline = get_baseline_vo(405)
    assert abs(baseline - 7.46) < 0.01

def test_gct_score_calculation():
    """GCT score (% deviation) calculated correctly."""
    # actual 253ms, baseline 266.3ms → -5.0%
    score = calculate_gct_score(253, 266.3)
    assert abs(score - (-5.0)) < 0.1

def test_form_efficiency_rating():
    """Form efficiency rating stars calculated correctly."""
    rating = calculate_form_efficiency_rating(gct_score=-5.0, vo_score=-4.4, vr_score=1.6)
    assert rating["stars"] == "★★★★☆"
    assert abs(rating["score"] - 4.5) < 0.1
```

### Integration Tests

#### test_report_generation_full.py
```python
@pytest.mark.parametrize("training_type_category,min_lines,max_lines", [
    ("recovery", 200, 250),
    ("low_moderate", 280, 324),
    ("tempo_threshold", 400, 450),
    ("interval_sprint", 400, 464),
])
def test_full_report_generation(training_type_category, min_lines, max_lines):
    """Generate full report and check line count."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=TEST_ACTIVITY_IDS[training_type_category])

    report_path = result["report_path"]
    with open(report_path) as f:
        lines = f.readlines()

    line_count = len(lines)
    assert min_lines <= line_count <= max_lines, f"{training_type_category}: {line_count} lines (expected {min_lines}-{max_lines})"

def test_base_run_no_physiological_indicators():
    """Base run does not include physiological indicators section."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)  # Base run sample

    with open(result["report_path"]) as f:
        report = f.read()

    assert "生理学的指標サマリー" not in report
    assert "生理学的指標との関連" not in report
    assert "> **参考**: VO2 Max" in report  # Should have note instead

def test_interval_run_has_physiological_indicators():
    """Interval run includes physiological indicators section."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=TEST_INTERVAL_ID)

    with open(result["report_path"]) as f:
        report = f.read()

    assert "生理学的指標サマリー" in report
    assert "生理学的指標との関連" in report
    assert "VO2 Max活用度" in report
    assert "閾値超過度" in report

def test_interval_run_4_phase_evaluation():
    """Interval run has 4-phase evaluation."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=TEST_INTERVAL_ID)

    with open(result["report_path"]) as f:
        report = f.read()

    assert "ウォームアップフェーズ" in report
    assert "Workフェーズ" in report
    assert "Recoveryフェーズ" in report
    assert "クールダウンフェーズ" in report
```

### Manual Testing

#### Test Data
- **Recovery**: TBD (need to identify recovery run activity_id)
- **Base Run**: 20625808856 (2025-10-08, sample exists)
- **Threshold**: 20744768051 (2025-10-20)
- **Interval**: TBD (架空データ, create test fixture)

#### Verification Checklist
- [ ] Base run (20625808856):
  - [ ] 300-324 lines
  - [ ] No "生理学的指標サマリー" section
  - [ ] 3-phase evaluation (Warmup/Run/Cooldown)
  - [ ] "> **参考**: VO2 Max" note present
  - [ ] Section order matches 2025-10-08_BALANCED.md
  - [ ] Mermaid graph renders in GitHub Preview
  - [ ] `<details>` sections fold/unfold correctly
- [ ] Interval run (TBD):
  - [ ] 400-464 lines
  - [ ] "生理学的指標サマリー" section present
  - [ ] "生理学的指標との関連" section present (simple version)
  - [ ] 4-phase evaluation (Warmup/Work/Recovery/Cooldown)
  - [ ] Section order matches 2025-10-15_interval_BALANCED.md
  - [ ] Mermaid graph includes power line
  - [ ] "長期目標（4-8週間後）" section present
- [ ] Markdown syntax validation:
  - [ ] No broken tables (missing pipes, misaligned columns)
  - [ ] No broken mermaid graphs (syntax errors)
  - [ ] No broken `<details>` tags (unclosed tags)
- [ ] Content completeness:
  - [ ] No "データがありません" messages (unless intentional)
  - [ ] All agent outputs (efficiency, environment, phase, split, summary) integrated
  - [ ] Similar workouts table populated (or gracefully handles no data)

---

## Acceptance Criteria

### Functional Requirements
- [ ] **4 Training Types**: Generate reports for recovery/base/tempo/interval with different structures
- [ ] **Line Count Targets**:
  - [ ] Recovery: 200-250 lines (1-phase, no physiological)
  - [ ] Base: 280-324 lines (3-phase, no physiological)
  - [ ] Tempo/Threshold: 400-450 lines (3-phase, physiological)
  - [ ] Interval/Sprint: 400-464 lines (4-phase, physiological)
- [ ] **Section Order**: Matches sample reports exactly
- [ ] **Conditional Sections**:
  - [ ] 生理学的指標サマリー: Only for tempo/interval
  - [ ] 生理学的指標との関連: Only for tempo/interval (simple version)
  - [ ] Phase count: 1/3/4 depending on training type
- [ ] **Folding Sections**: `<details>` for split details, technical info, glossary
- [ ] **Mermaid Graphs**: Present in 総合評価 section
- [ ] **Pace-Corrected Form Efficiency**: GCT/VO baselines calculated from pace

### Quality Requirements
- [ ] **Unit Tests**: All tests pass (80%+ coverage for new code)
- [ ] **Integration Tests**: All 4 training types generate successfully
- [ ] **Pre-commit Hooks**: Black, Ruff, Mypy pass
- [ ] **Code Review**: At least 1 reviewer approval

### Documentation Requirements
- [ ] **Planning.md**: This document completed
- [ ] **Completion_report.md**: Generated after implementation
- [ ] **Sample Reports**: All 4 training types regenerated with new template
- [ ] **CHANGELOG.md**: Entry added for v4.0 (BALANCED v2)

### Backward Compatibility
- [ ] **No Worker API Changes**: `generate_report()` signature unchanged
- [ ] **No DuckDB Schema Changes**: All data from existing tables
- [ ] **No Agent Output Changes**: Agents output same format, template handles differences
- [ ] **Graceful Degradation**: If `training_type_category` is None, defaults to `low_moderate`

---

## Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Template becomes too complex** | High (maintenance burden) | Medium | - Use Jinja2 macros/filters for reusable logic<br>- Add inline comments<br>- Keep conditions simple (no deep nesting) |
| **Missing data for similar workouts** | Medium (incomplete table) | High | - Graceful handling: Show "類似ワークアウトが見つかりませんでした"<br>- Provide placeholder data for Phase 3 tests<br>- Mark as "Future Work" if MCP tool unavailable |
| **Mermaid graph syntax errors** | Medium (graph doesn't render) | Low | - Validate graph data before rendering<br>- Test with GitHub Preview<br>- Add fallback: Skip graph if data invalid |
| **Agent output format changes** | High (template breaks) | Low | - Defensive checks: `if field exists then render`<br>- Test with real agent outputs<br>- Add logging for missing fields |
| **Pace correction formulas inaccurate** | Medium (misleading scores) | Medium | - Validate against sample report values<br>- Document formula sources (training-type-evaluation-criteria.md)<br>- Add unit tests for edge cases (very slow/fast paces) |
| **Section order differs from samples** | Low (aesthetic) | Low | - Strict adherence to sample structure<br>- Manual review against samples<br>- Automated tests for section order |

---

## Future Work (Out of Scope for V2)

### Phase 5+: Additional Enhancements (Not Required for V2 Completion)

1. **Interactive Mermaid Graphs** (if Garmin Connect supports):
   - Tooltip on hover (split details)
   - Click to expand split

2. **Similar Workouts Deep Dive**:
   - Link to past workout reports
   - Trend graphs (pace over time)

3. **Improvement Points AI Personalization**:
   - Use Claude to generate personalized advice based on user's training history
   - Incorporate user goals (e.g., "目標: sub-3時間マラソン")

4. **Report Variants**:
   - `compact.j2`: 100-150 lines (ultra-minimal for quick review)
   - `verbose.j2`: 600-800 lines (all details unfolded)

5. **Multi-language Support**:
   - English template (`detailed_report_en.j2`)
   - Language parameter in Worker

---

## Implementation Schedule (Estimated)

| Phase | Tasks | Estimated Time | Dependencies |
|-------|-------|----------------|--------------|
| **Phase 1** | Template structure rewrite<br>- Section reordering<br>- Folding sections<br>- Remove numbering | 6-8 hours | None |
| **Phase 2** | Mermaid graphs<br>- Worker modifications<br>- Template integration<br>- Testing | 4-6 hours | Phase 1 complete |
| **Phase 3** | Similar workouts<br>- MCP tool integration<br>- Worker modifications<br>- Template table | 6-8 hours | Phase 1 complete<br>MCP tool available |
| **Phase 4** | Pace-corrected form efficiency<br>- Worker calculations<br>- Template integration<br>- Formula validation | 4-6 hours | Phase 1 complete |
| **Testing** | Unit tests<br>Integration tests<br>Manual testing | 4-6 hours | All phases complete |
| **Documentation** | Completion report<br>Sample regeneration<br>CHANGELOG | 2-3 hours | All phases complete |
| **Total** | | **26-37 hours** | |

**Note**: Phases 2-4 can be partially parallelized after Phase 1 completion.

---

## References

### Design Documents
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/docs/report-balance-analysis.md` - BALANCED principle, line reduction targets
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/docs/training-type-evaluation-criteria.md` - Training type-specific evaluation, pace correction formulas

### Sample Reports (IDEAL STRUCTURE)
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/result/individual/2025/10/2025-10-08_20625808856_SAMPLE_BALANCED.md` - Base run (324 lines)
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/result/individual/2025/10/2025-10-15_interval_SAMPLE_BALANCED.md` - Interval run (464 lines)

### Current Implementation
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/tools/reporting/templates/detailed_report.j2` - Current template (330 lines)
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/tools/reporting/report_generator_worker.py` - Worker (634 lines)
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/tools/reporting/report_template_renderer.py` - Renderer

### Related Projects
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/docs/project/2025-10-25_balanced_report_templates/planning.md` - Previous iteration-based planning (archived)
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/docs/project/2025-10-25_balanced_report_templates/completion_report.md` - Phase 1 completion (iteration approach, not v2 complete rewrite)

---

## Appendix A: Sample Comparison Matrix

| Feature | Current Template | Base Sample | Interval Sample | V2 Target |
|---------|-----------------|-------------|----------------|-----------|
| Line count | 330 (template) | 324 (output) | 464 (output) | 200-464 (type-dependent) |
| Section numbering | 1-6 | None | None | None |
| 総合評価 position | 6 | 3 | 3 | 3 |
| Mermaid graphs | ❌ | ✅ (in 総合評価) | ✅ (in 総合評価) | ✅ |
| Folding split details | ❌ | ✅ `<details>` | ✅ `<details>` | ✅ |
| 生理学的指標サマリー | Conditional | ❌ (note only) | ✅ | Conditional (tempo+) |
| 生理学的指標との関連 | Position 4.5 | ❌ | ✅ (simple) | Conditional (tempo+) |
| フォーム効率 location | Section 1 (独立) | Inside パフォーマンス指標 | Inside パフォーマンス指標 | Nested |
| Pace correction | ❌ | ✅ (GCT/VO) | ✅ (GCT/VO) | ✅ |
| Similar workouts table | ❌ | ✅ | ✅ | ✅ |
| 改善ポイント position | 3 | 7 | 8 | Near end (7/8) |
| Technical details folding | ❌ | ✅ `<details>` | ✅ `<details>` | ✅ |
| Glossary folding | ❌ | ✅ `<details>` | ✅ `<details>` | ✅ |
| Phase count | 3 (or 4) | 3 | 4 | 1/3/4 (type-dependent) |

---

## Appendix B: Training Type Category Decision Tree

```
hr_efficiency.training_type
├── "recovery"
│   └→ training_type_category = "recovery"
│       - phase_count = 1
│       - show_physiological = False
│       - target_lines = 200-250
├── "aerobic_base" or "low_moderate"
│   └→ training_type_category = "low_moderate"
│       - phase_count = 3
│       - show_physiological = False
│       - target_lines = 280-324
├── "tempo" or "lactate_threshold"
│   └→ training_type_category = "tempo_threshold"
│       - phase_count = 3
│       - show_physiological = True
│       - target_lines = 400-450
├── "vo2max" or "anaerobic_capacity" or "speed"
│   └→ training_type_category = "interval_sprint"
│       - phase_count = 4
│       - show_physiological = True
│       - target_lines = 400-464
└── NULL or unknown
    └→ training_type_category = "low_moderate" (default fallback)
```

---

*End of Planning Document*
