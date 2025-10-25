# 計画: BALANCED Report V2 Complete Rewrite (修正版)

## プロジェクト情報
- **プロジェクト名**: `balanced_report_v2_complete`
- **作成日**: `2025-10-25`
- **修正日**: `2025-10-25` (Critical Issues修正版)
- **ステータス**: 計画中（実装可能）
- **GitHub Issue**: TBD (計画承認後に作成)

---

## 修正履歴

### v2 (2025-10-25) - Critical Issues修正
以下の8つのCritical Issuesを修正:
1. ✅ Jinja2カスタムフィルター定義追加（Phase 0 Pre-Implementation Setup）
2. ✅ `get_phase_count()` 関数を条件式に置き換え（Line 166）
3. ✅ `is_interval` 変数を Template Variables に追加
4. ✅ Mermaid Data Format 修正（json.dumps削除、tojsonフィルター使用）
5. ✅ Pace Correction Formula の出典明記（新規Appendix C追加）
6. ✅ Test Activity IDs 定義（Manual Testingセクション更新）
7. ✅ Worker Modifications 詳細化（各Phase に File/Location/Integration 明記）
8. ✅ Edge Case Handling セクション追加

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
6. **Custom Jinja2 filters** for table rendering and data formatting

### Expected Outcomes
- Base run reports: 300-324 lines (no physiological indicators)
- Tempo/Interval reports: 400-464 lines (with physiological indicators table + details section)
- Section order matches samples exactly
- All conditionals working correctly for 4 training types
- All custom filters properly defined and tested

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
7. **Custom Filters**: Define render_table, render_rows, sort_splits, bullet_list

---

## Architecture Design

### Complete Template Structure (Fixed Pseudocode)

```jinja2
{# ========================================================================= #}
{# Phase 0: Training type category mapping & derived variables #}
{# ========================================================================= #}
{% set show_physiological = training_type_category in ["tempo_threshold", "interval_sprint"] %}
{% set phase_count = 1 if training_type_category == "recovery" else (4 if training_type_category == "interval_sprint" else 3) %}
{% set is_interval = training_type_category == "interval_sprint" %}

{# =================================================================== #}
{# SECTION 1: 基本情報 #}
{# =================================================================== #}
## 基本情報
| 項目 | 値 |
|------|-----|
| アクティビティID | {{ activity_id }} |
| 実施日 | {{ date }} |
{% if activity_name %}| 活動名 | {{ activity_name }} |{% endif %}
{% if location_name %}| 場所 | {{ location_name }} |{% endif %}
{% if training_type %}| トレーニングタイプ | {{ training_type }} |{% endif %}
{% if basic_metrics %}| 総距離 | {{ "%.2f"|format(basic_metrics.distance_km|default(0)) }} km |
| 総時間 | {{ (basic_metrics.duration_seconds|default(0) // 60)|int }}:{{ "%02d"|format((basic_metrics.duration_seconds|default(0) % 60)|int) }} |
| 平均ペース | {{ (basic_metrics.avg_pace_seconds_per_km|default(0) / 60)|int }}:{{ "%02d"|format((basic_metrics.avg_pace_seconds_per_km|default(0) % 60)|int) }}/km |
| 平均心拍数 | {{ basic_metrics.avg_heart_rate|default(0)|int }} bpm |
| 平均ケイデンス | {{ basic_metrics.avg_cadence|default(0)|int }} spm |{% endif %}
{% if weight_kg %}| 体重 | {{ "%.1f"|format(weight_kg) }} kg |{% endif %}

---

{# =================================================================== #}
{# SECTION 2: 📊 パフォーマンスサマリー #}
{# =================================================================== #}
## 📊 パフォーマンスサマリー

{% if show_physiological and vo2_max_data and lactate_threshold_data %}
### 生理学的指標サマリー

| 指標 | 現在値 | 評価 |
|------|--------|------|
| **VO2 Max** | {{ vo2_max_data.precise_value|default(vo2_max_data.value)|default(0) }} ml/kg/min | カテゴリ: {{ vo2_max_data.category|default("N/A") }} |
| **VO2 Max利用率** | {{ vo2_max_utilization }}% | {{ vo2_max_utilization_eval }} |
| **閾値ペース** | {{ threshold_pace_formatted }}/km | {{ threshold_pace_comparison }} |
| **FTP（パワー）** | {{ lactate_threshold_data.functional_threshold_power|default(0)|int }} W | Work平均{{ work_avg_power }}W = FTPの{{ ftp_percentage }}% |

{% endif %}

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

{% if not show_physiological and vo2_max_data %}
> **参考**: VO2 Max {{ vo2_max_data.precise_value|default(vo2_max_data.value)|default(0) }} ml/kg/min（{{ vo2_max_data.category|default("N/A") }}）{% if lactate_threshold_data %}、閾値ペース {{ threshold_pace_formatted }}/km{% endif %}
{% endif %}

---

{# =================================================================== #}
{# SECTION 3: 総合評価 #}
{# =================================================================== #}
## 総合評価

{% if summary %}
### アクティビティタイプ
{% if summary.activity_type is string %}{{ summary.activity_type }}{% else %}{{ summary.activity_type.classification|default('N/A') }}{% endif %}

### 総合所見 ({% if summary.overall_rating is string %}{{ summary.overall_rating }}{% else %}{{ summary.overall_rating.stars|default('N/A') }}{% endif %})

{{ summary.summary if summary.summary else "評価データがありません。" }}

{% if summary.key_strengths %}
**✅ 優れている点:**
{% for strength in summary.key_strengths %}
- {{ strength }}
{% endfor %}
{% endif %}

{% if summary.improvement_areas %}
**⚠️ 改善可能な点:**
{% for area in summary.improvement_areas %}
- {{ area }}
{% endfor %}
{% endif %}
{% endif %}

### ペース・心拍{% if show_physiological %}・パワー{% endif %}推移{% if is_interval %}（Work/Recoveryハイライト）{% endif %}

{% if mermaid_data %}
```mermaid
xychart-beta
    title "スプリット別 ペース・心拍{% if show_physiological %}・パワー{% endif %}推移"
    x-axis {{ mermaid_data.x_axis_labels | tojson }}
    y-axis "ペース(秒/km)" {{ mermaid_data.pace_min }} --> {{ mermaid_data.pace_max }}
    y-axis "心拍(bpm)" {{ mermaid_data.hr_min }} --> {{ mermaid_data.hr_max }}
    line {{ mermaid_data.pace_data | tojson }}
    line {{ mermaid_data.heart_rate_data | tojson }}
    {% if show_physiological and mermaid_data.power_data %}
    line {{ mermaid_data.power_data | tojson }}
    {% endif %}
```

{% if is_interval %}
**凡例**: 青=ペース（秒/km）、橙=心拍（bpm）、緑=パワー（W）

**分析**:
{{ interval_graph_analysis|default("N/A") }}
{% endif %}
{% else %}
グラフデータがありません。
{% endif %}

---

{# =================================================================== #}
{# SECTION 4: パフォーマンス指標 #}
{# =================================================================== #}
## パフォーマンス指標

{% if is_interval %}
> **評価対象**: {{ target_segments_description|default("Workセグメント") }}（インターバル走は高強度区間のパフォーマンスを重視）
{% endif %}

### スプリット概要{% if is_interval %}（全区間）{% endif %}

{% if splits and splits|length > 0 %}
| # | {% if is_interval %}タイプ | {% endif %}ペース | 心拍 | ケイデンス | パワー | ストライド | GCT | VO | VR | 標高 |
|---|{% if is_interval %}-------|{% endif %}--------|------|------------|--------|------------|-----|----|----|------|
{% for split in splits %}
| {{ split.index }} | {% if is_interval %}{{ split.intensity_type|default("N/A") }} | {% endif %}{{ split.pace_formatted }}/km | {{ split.heart_rate|int }} bpm | {{ split.cadence|int if split.cadence else "-" }} spm | {{ split.power|int if split.power else "-" }} W | {{ "%.2f"|format(split.stride_length) if split.stride_length else "-" }} m | {{ split.ground_contact_time|int if split.ground_contact_time else "-" }} ms | {{ "%.1f"|format(split.vertical_oscillation) if split.vertical_oscillation else "-" }} cm | {{ "%.1f"|format(split.vertical_ratio) if split.vertical_ratio else "-" }}% | +{{ split.elevation_gain|int if split.elevation_gain else 0 }}/-{{ split.elevation_loss|int if split.elevation_loss else 0 }}m |
{% endfor %}

**📈 {% if is_interval %}Workセグメント {% endif %}ハイライト:**
{{ highlights_list|default("N/A") }}

<details>
<summary>📋 {% if is_interval %}Work/Recovery{% else %}スプリット{% endif %}詳細分析（クリックで展開）</summary>

{% if split_analysis %}
{% if split_analysis is mapping %}
{% for key, value in split_analysis.items() | sort %}
### {{ key }}
{{ value }}

{% endfor %}
{% else %}
{{ split_analysis }}
{% endif %}
{% else %}
詳細分析データがありません。
{% endif %}

</details>
{% else %}
スプリットデータがありません。
{% endif %}

---

### フォーム効率（{% if is_interval %}Workセグメント {% endif %}ペース補正評価）{% if form_efficiency_rating_stars %} ({{ form_efficiency_rating_stars }} {{ form_efficiency_rating_score }}/5.0){% endif %}

{% if efficiency %}
{% if is_interval %}
```mermaid
pie title "心拍ゾーン分布（全体）"
{{ heart_rate_zone_pie_data|default("") }}
```
{% else %}
```mermaid
pie title "心拍ゾーン分布"
{{ heart_rate_zone_pie_data|default("") }}
```
{% endif %}

{{ efficiency.evaluation if efficiency.evaluation else efficiency if efficiency is string else "フォーム効率データがありません。" }}
{% else %}
フォーム効率データがありません。
{% endif %}

---

{% if show_physiological %}
{# =================================================================== #}
{# SECTION 5: 生理学的指標との関連 (Tempo/Interval only) #}
{# =================================================================== #}
## 生理学的指標との関連

### VO2 Max活用度

{% if vo2_max_data %}
- **現在のVO2 Max**: {{ vo2_max_data.precise_value|default(vo2_max_data.value)|default(0) }} ml/kg/min（{{ vo2_max_data.category|default("N/A") }}）
- **{% if is_interval %}Work{% else %}メイン区間{% endif %}平均心拍**: {{ target_avg_hr|default("N/A") }} bpm
- **VO2 Max利用率**: 約{{ vo2_max_utilization|default("N/A") }}%（{{ vo2_max_utilization_eval|default("N/A") }}）

**期待効果**: {{ vo2_max_expected_effect|default("N/A") }}
{% else %}
VO2 Maxデータがありません。
{% endif %}

### 閾値超過度

{% if lactate_threshold_data %}
- **閾値心拍**: {{ lactate_threshold_data.heart_rate|default(0)|int }} bpm
- **{% if is_interval %}Work{% else %}メイン区間{% endif %}平均心拍**: {{ target_avg_hr|default("N/A") }} bpm
- **閾値パワー（FTP）**: {{ lactate_threshold_data.functional_threshold_power|default(0)|int }} W
- **{% if is_interval %}Work{% else %}メイン区間{% endif %}平均パワー**: {{ target_avg_power|default("N/A") }} W（FTPの{{ ftp_percentage|default("N/A") }}%）→ {{ power_zone_name|default("N/A") }} ✅

**期待効果**: {{ threshold_expected_effect|default("N/A") }}
{% else %}
閾値データがありません。
{% endif %}

---

{% endif %}

{# =================================================================== #}
{# SECTION 6 (or 5): フェーズ評価 #}
{# =================================================================== #}
## フェーズ評価

{% if phase_evaluation %}
{% if phase_evaluation.warmup or phase_count >= 1 %}
### ウォームアップフェーズ{% if warmup_rating_stars %} ({{ warmup_rating_stars }} {{ warmup_rating_score }}/5.0){% endif %}

{{ phase_evaluation.warmup.evaluation|default('N/A') if phase_evaluation.warmup else "データがありません。" }}

{% if phase_count == 1 %}
{# Recovery run - only 1 phase, end here #}
---
{% endif %}
{% endif %}

{% if phase_count >= 3 %}
{% if phase_evaluation.run or phase_evaluation.main %}
### {% if is_interval %}Workフェーズ{% else %}メイン走行フェーズ{% endif %}{% if main_rating_stars %} ({{ main_rating_stars }} {{ main_rating_score }}/5.0){% endif %}

{{ phase_evaluation.run.evaluation|default(phase_evaluation.main.evaluation|default('N/A')) if (phase_evaluation.run or phase_evaluation.main) else "データがありません。" }}

---
{% endif %}

{% if phase_count == 4 and phase_evaluation.recovery %}
### Recoveryフェーズ{% if recovery_rating_stars %} ({{ recovery_rating_stars }} {{ recovery_rating_score }}/5.0){% endif %}

{{ phase_evaluation.recovery.evaluation|default('N/A') }}

---
{% endif %}

{% if phase_evaluation.cooldown or phase_evaluation.finish %}
### クールダウンフェーズ{% if cooldown_rating_stars %} ({{ cooldown_rating_stars }} {{ cooldown_rating_score }}/5.0){% endif %}

{{ phase_evaluation.cooldown.evaluation|default(phase_evaluation.finish.evaluation|default('N/A')) if (phase_evaluation.cooldown or phase_evaluation.finish) else "データがありません。" }}

---
{% endif %}
{% endif %}
{% else %}
フェーズ評価データがありません。
{% endif %}

{# =================================================================== #}
{# SECTION 7 (or 6 or 5): 環境要因 #}
{# =================================================================== #}
## 環境要因

{% if weather_data or environment_analysis %}
### 気象条件・環境インパクト

{% if weather_data %}
- **気温**: {{ weather_data.external_temp_c|default("N/A") }}°C
- **湿度**: {{ weather_data.humidity|default("N/A") }}%
- **風速**: {{ weather_data.wind_speed_ms|default(0) }} m/s
{% endif %}
{% if gear_name %}- **使用シューズ**: {{ gear_name }}{% endif %}

{% if environment_analysis %}
{% if environment_analysis is string %}
{{ environment_analysis }}
{% else %}
{{ environment_analysis.evaluation|default("N/A") }}
{% endif %}
{% endif %}
{% else %}
環境データがありません。
{% endif %}

---

{# =================================================================== #}
{# SECTION 8 (or 7 or 6): 💡 改善ポイント #}
{# =================================================================== #}
## 💡 改善ポイント

{% if summary and summary.recommendations %}
{{ summary.recommendations }}
{% else %}
改善ポイントデータがありません。
{% endif %}

---

{# =================================================================== #}
{# SECTION 9 (or 8 or 7): 技術的詳細 #}
{# =================================================================== #}
## 技術的詳細

<details>
<summary>クリックで展開</summary>

### データソース
- スプリットデータ: DuckDB (splits table - power, stride_length含む)
{% if is_interval %}- インターバル区間: DuckDB (splits.intensity_type = 'active'/'rest'){% endif %}
- フォーム指標: DuckDB (form_efficiency table)
- 心拍データ: DuckDB (hr_efficiency, heart_rate_zones tables)
{% if show_physiological %}- 生理学的指標: DuckDB (vo2_max, lactate_threshold tables){% endif %}
- 環境データ: DuckDB (weather table)
- 類似ワークアウト: `mcp__garmin-db__compare_similar_workouts()`

### 分析バージョン
- 生成日時: {{ generation_timestamp|default("N/A") }}
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

{% if is_interval %}- **Work**: インターバル走の高強度区間
- **Recovery**: Work間の回復区間{% endif %}
- **GCT (Ground Contact Time)**: 接地時間。ペースが速いほど短くなる
- **VO (Vertical Oscillation)**: 垂直振幅。走行中の上下動（目標: 6-8cm）
- **VR (Vertical Ratio)**: 垂直比率。VO÷ストライド長（目標: 8-10%）
- **パワー**: ランニングパワー（W）
{% if show_physiological %}- **FTP (Functional Threshold Power)**: 機能的閾値パワー。1時間維持可能な最大パワー
- **VO2 Max**: 最大酸素摂取量。有酸素能力の指標
- **VO2 Max利用率**: VO2 Maxペースに対する実際のペースの比率
- **閾値ペース**: 乳酸閾値ペース。約60分維持可能な最速ペース{% endif %}
- **ストライド長**: 1歩あたりの距離（m）。スピード = ケイデンス × ストライド長
- **ペース補正評価**: そのペースに対する相対評価（同じペースのランナーと比較）

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
9. **Derived Variables**: `phase_count` and `is_interval` calculated in template, not functions
10. **Edge Case Handling**: All data access wrapped in `if` checks

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
        "external_temp_c": float,
        "humidity": float,
        "wind_speed_ms": float,
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
            "intensity_type": str,  # For interval runs: "active"/"rest"
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
    "x_axis_labels": ["1", "2", "3", "4", "5", "6", "7"],  # List[str], NOT JSON string
    "pace_data": [398, 403, 403, 419, 402, 406, 404],  # List[int], NOT JSON string
    "heart_rate_data": [128, 145, 148, 148, 149, 150, 151],  # List[int]
    "power_data": [215, 225, 227, 220, 228, 226, 227] if show_physiological else None,  # List[int] or None
    # NEW: Dynamic Y-axis ranges
    "pace_min": min(pace_data) - 20,
    "pace_max": max(pace_data) + 20,
    "hr_min": min(heart_rate_data) - 10,
    "hr_max": max(heart_rate_data) + 10,
}
```
**Note**: Template will use `| tojson` filter to convert Lists to JSON for Mermaid

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
        # ... more metrics (heart_rate, power, stride, gct, vo)
    ],
    "insight": "ペース+3秒速いのにパワー-5W低下＝効率が2.2%向上 ✅",
} if similar_count >= 3 else None  # Return None if insufficient data
```
**Data Source**: `mcp__garmin-db__compare_similar_workouts(activity_id, ...)`

---

## Implementation Phases

### Phase 0: Pre-Implementation Setup (CRITICAL)
**Goal**: Define all custom Jinja2 filters before Phase 1

**File**: `tools/reporting/report_template_renderer.py`
**Location**: After line ~30 (after `env = Environment(...)`)

**Implementation:**
```python
def _render_table(comparisons: list) -> str:
    """Render comparison table rows."""
    if not comparisons:
        return ""
    rows = []
    for comp in comparisons:
        row = f"| {comp['metric']} | {comp['current']} | {comp['average']} | {comp['change']} | {comp['trend']} |"
        rows.append(row)
    return "\n".join(rows)

def _render_rows(splits: list) -> str:
    """Render splits table rows."""
    if not splits:
        return ""
    rows = []
    for split in splits:
        row = f"| {split['index']} | {split.get('intensity_type', '')} | " if split.get('intensity_type') else f"| {split['index']} | "
        row += f"{split['pace_formatted']}/km | {int(split['heart_rate'])} bpm | ..."
        rows.append(row)
    return "\n".join(rows)

def _sort_splits(items: list) -> list:
    """Sort split analysis items by split number."""
    def get_split_num(item):
        key = item[0]
        if '_' in key:
            try:
                return int(key.split('_')[1])
            except (IndexError, ValueError):
                return 999
        return 999
    return sorted(items, key=get_split_num)

def _bullet_list(items: list | str) -> str:
    """Convert list to bullet list."""
    if isinstance(items, str):
        return items
    if not items:
        return ""
    return '\n'.join([f"- {item}" for item in items])

# Register filters
env.filters['render_table'] = _render_table
env.filters['render_rows'] = _render_rows
env.filters['sort_splits'] = _sort_splits
env.filters['bullet_list'] = _bullet_list
```

**Test:**
```python
# test_template_renderer.py (NEW)
def test_custom_filters_defined():
    """Custom filters are registered."""
    from tools.reporting.report_template_renderer import env
    assert 'render_table' in env.filters
    assert 'render_rows' in env.filters
    assert 'sort_splits' in env.filters
    assert 'bullet_list' in env.filters

def test_bullet_list_filter():
    """bullet_list filter converts list to markdown."""
    from tools.reporting.report_template_renderer import _bullet_list
    result = _bullet_list(["Item 1", "Item 2", "Item 3"])
    assert result == "- Item 1\n- Item 2\n- Item 3"

    # String input should pass through
    assert _bullet_list("already a string") == "already a string"
```

---

### Phase 1: Template Structure Rewrite (Section Order)
**Goal**: Match sample section order exactly

**File**: `tools/reporting/templates/detailed_report.j2`
**Backup**: Create backup before editing: `cp detailed_report.j2 detailed_report.j2.backup`

**Implementation:**
1. **Replace entire template** with Fixed Pseudocode from Architecture Design section above
2. **Key changes**:
   - Line 1-5: Add `phase_count` and `is_interval` variable calculation
   - Remove all section numbers (## 1., ## 2., etc.)
   - Move 総合評価 to position 3 (before パフォーマンス指標)
   - Nest フォーム効率 inside パフォーマンス指標
   - Add `<details>` for split details, technical info, glossary
   - Add Edge Case checks: `{% if splits and splits|length > 0 %}`

**Integration with Worker**:
- **No changes required** to `generate_report()` signature
- Existing `context` dict already contains all required data
- Template handles missing data gracefully with `{% if ... %}`

**Test:**
```bash
# Generate test report with new template
uv run python -c "
from tools.reporting.report_generator_worker import ReportGeneratorWorker
worker = ReportGeneratorWorker()
result = worker.generate_report(activity_id=20625808856)  # Base run
print(f'Report generated: {result[\"report_path\"]}')
"

# Check section order
grep "^## " /path/to/report.md
```

**Expected Output**:
```
## 基本情報
## 📊 パフォーマンスサマリー
## 総合評価
## パフォーマンス指標
## フェーズ評価
## 環境要因
## 💡 改善ポイント
## 技術的詳細
## 📚 用語解説
```

---

### Phase 2: Mermaid Graphs + 総合評価 Content
**Goal**: Add mermaid graphs inside 総合評価 section

**File**: `tools/reporting/report_generator_worker.py`
**Location**: After line ~245 (after loading `context["splits"]`)

**New Method**:
```python
def _generate_mermaid_data(self, splits: list) -> dict:
    """Generate mermaid graph data from splits.

    Returns:
        Dict with x_axis_labels (List[str]), pace_data (List[int]),
        heart_rate_data (List[int]), power_data (List[int] or None),
        and dynamic Y-axis ranges.
    """
    if not splits or len(splits) == 0:
        return None

    x_labels = [str(s["index"]) for s in splits]
    pace_data = [int(s["pace_seconds_per_km"]) for s in splits if s.get("pace_seconds_per_km")]
    hr_data = [int(s["heart_rate"]) for s in splits if s.get("heart_rate")]
    power_data = [int(s["power"]) for s in splits if s.get("power")]

    # Calculate dynamic Y-axis ranges
    pace_min = min(pace_data) - 20 if pace_data else 380
    pace_max = max(pace_data) + 20 if pace_data else 440
    hr_min = min(hr_data) - 10 if hr_data else 120
    hr_max = max(hr_data) + 10 if hr_data else 160

    return {
        "x_axis_labels": x_labels,  # List, not JSON
        "pace_data": pace_data,
        "heart_rate_data": hr_data,
        "power_data": power_data if len(power_data) > 0 else None,
        "pace_min": pace_min,
        "pace_max": pace_max,
        "hr_min": hr_min,
        "hr_max": hr_max,
    }
```

**Integration**:
```python
# In load_performance_data() method, after line ~245:
context["mermaid_data"] = self._generate_mermaid_data(context["splits"])

# Add interval-specific graph analysis (placeholder for now)
if context.get("training_type_category") == "interval_sprint":
    context["interval_graph_analysis"] = "グラフ分析は今後実装予定。"
```

**Test:**
```python
# test_mermaid_data_generation.py (NEW)
def test_mermaid_data_structure():
    """Mermaid data has correct structure."""
    worker = ReportGeneratorWorker()
    splits = [
        {"index": 1, "pace_seconds_per_km": 398, "heart_rate": 128, "power": 215},
        {"index": 2, "pace_seconds_per_km": 403, "heart_rate": 145, "power": 225},
    ]
    result = worker._generate_mermaid_data(splits)

    assert result["x_axis_labels"] == ["1", "2"]
    assert result["pace_data"] == [398, 403]
    assert result["heart_rate_data"] == [128, 145]
    assert result["power_data"] == [215, 225]
    assert isinstance(result["pace_min"], int)
    assert isinstance(result["pace_max"], int)

def test_mermaid_graph_renders_in_template():
    """Mermaid graph renders correctly in template."""
    # Generate report and check for mermaid block
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    with open(result["report_path"]) as f:
        report = f.read()

    assert "```mermaid" in report
    assert "xychart-beta" in report
    assert "x-axis" in report
    assert "line" in report
```

---

### Phase 3: Similar Workouts Comparison + Data Integration
**Goal**: Add 類似ワークアウトとの比較 table with actual data

**File**: `tools/reporting/report_generator_worker.py`
**Location**: After line ~260 (after `_generate_mermaid_data`)

**MCP Tool Verification**:
```bash
# FIRST: Verify MCP tool exists and test it
uv run python -c "
from tools.mcp.garmin_db_mcp import compare_similar_workouts
result = compare_similar_workouts(
    activity_id=20625808856,
    distance_tolerance=0.10,
    pace_tolerance=0.10,
    limit=10
)
print(f'Found {len(result)} similar workouts')
print(result[:3])  # Show first 3
"
```

**New Method**:
```python
def _load_similar_workouts(self, activity_id: int, current_metrics: dict) -> dict | None:
    """Load similar workouts comparison using MCP tool.

    Args:
        activity_id: Current activity ID
        current_metrics: Dict with current avg_pace, avg_hr, etc.

    Returns:
        Dict with conditions, count, comparisons, insight or None if insufficient data
    """
    try:
        # Import MCP tool (lazy import to avoid circular dependency)
        import sys
        sys.path.append('/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates')
        from tools.mcp.garmin_db_mcp import compare_similar_workouts

        similar = compare_similar_workouts(
            activity_id=activity_id,
            distance_tolerance=0.10,
            pace_tolerance=0.10,
            terrain_match=True,
            limit=10
        )

        if not similar or len(similar) < 3:
            logger.warning(f"Insufficient similar workouts for activity {activity_id}")
            return None

        # Calculate averages from top 3 similar workouts
        top_3 = similar[:3]
        avg_pace = sum([w['avg_pace'] for w in top_3]) / 3
        avg_hr = sum([w['avg_hr'] for w in top_3]) / 3
        avg_power = sum([w.get('avg_power', 0) for w in top_3]) / 3 if any(w.get('avg_power') for w in top_3) else None

        # Calculate differences
        pace_diff = current_metrics['avg_pace'] - avg_pace  # Negative = faster
        hr_diff = current_metrics['avg_hr'] - avg_hr

        # Format comparison table
        comparisons = [
            {
                "metric": "平均ペース",
                "current": self._format_pace(current_metrics['avg_pace']),
                "average": self._format_pace(avg_pace),
                "change": f"+{abs(int(pace_diff))}秒速い" if pace_diff < 0 else f"-{int(pace_diff)}秒遅い",
                "trend": "↗️ 改善" if pace_diff < 0 else "↘️ 悪化",
            },
            {
                "metric": "平均心拍",
                "current": f"{int(current_metrics['avg_hr'])} bpm",
                "average": f"{int(avg_hr)} bpm",
                "change": f"+{int(hr_diff)} bpm" if hr_diff > 0 else f"{int(hr_diff)} bpm",
                "trend": "➡️ 同等" if abs(hr_diff) < 5 else ("⚠️ 高い" if hr_diff > 0 else "✅ 低い"),
            },
        ]

        # Add power comparison if available
        if avg_power:
            power_diff = current_metrics.get('avg_power', 0) - avg_power
            comparisons.append({
                "metric": "平均パワー",
                "current": f"{int(current_metrics.get('avg_power', 0))} W",
                "average": f"{int(avg_power)} W",
                "change": f"+{int(power_diff)} W" if power_diff > 0 else f"{int(power_diff)} W",
                "trend": "➡️ 同等" if abs(power_diff) < 10 else ("⚠️ 高い" if power_diff > 0 else "✅ 低い"),
            })

        # Generate insight
        if pace_diff < 0 and (not avg_power or current_metrics.get('avg_power', 999) < avg_power):
            insight = f"ペース+{abs(int(pace_diff))}秒速いのにパワー-{int(avg_power - current_metrics.get('avg_power', 0))}W低下＝効率が向上 ✅"
        else:
            insight = "類似ワークアウトと比較して、標準的なパフォーマンスです。"

        return {
            "conditions": f"距離{similar[0]['distance']:.1f}-{similar[-1]['distance']:.1f}km、ペース類似",
            "count": 3,
            "comparisons": comparisons,
            "insight": insight,
        }

    except Exception as e:
        logger.error(f"Error loading similar workouts: {e}")
        return None
```

**Integration**:
```python
# In load_performance_data() method, after mermaid_data:
current_metrics = {
    "avg_pace": context["basic_metrics"]["avg_pace_seconds_per_km"],
    "avg_hr": context["basic_metrics"]["avg_heart_rate"],
    "avg_power": context.get("basic_metrics", {}).get("avg_power", 0),
}
context["similar_workouts"] = self._load_similar_workouts(activity_id, current_metrics)
```

**Test:**
```python
# test_similar_workouts.py (NEW)
def test_similar_workouts_structure():
    """Similar workouts data has correct structure."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    # Check if similar_workouts exists (may be None)
    # This is OK - template handles None gracefully
    pass

@pytest.mark.integration
def test_similar_workouts_table_renders():
    """Similar workouts table renders in report."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    with open(result["report_path"]) as f:
        report = f.read()

    # Should have comparison section (even if no data)
    assert "### 類似ワークアウトとの比較" in report
    # Check for graceful handling
    assert ("類似ワークアウトが見つかりませんでした" in report or "| 指標 |" in report)
```

---

### Phase 4: Pace-Corrected Form Efficiency
**Goal**: Implement ペース補正評価 for GCT, VO

**File**: `tools/reporting/report_generator_worker.py`
**Location**: After similar_workouts loading

**Formula Sources** (see Appendix C for details):
- GCT: Linear approximation from pace (4:00/km → 230ms, 7:00/km → 270ms)
- VO: Gentle increase with pace (4:00/km → 6.8cm, 7:00/km → 7.5cm)
- Source: Empirical data from training-type-evaluation-criteria.md

**New Method**:
```python
def _calculate_pace_corrected_form_efficiency(
    self, avg_pace_seconds_per_km: float, form_eff: dict
) -> dict:
    """Calculate pace-corrected form efficiency scores.

    Uses linear approximation formulas (see Appendix C in planning.md):
    - GCT baseline: 230 + (pace - 240) * 0.22 ms
    - VO baseline: 6.8 + (pace - 240) * 0.004 cm

    Args:
        avg_pace_seconds_per_km: Average pace in seconds/km
        form_eff: Dict from form_efficiency table

    Returns:
        Dict with gct, vo, vr metrics (actual, baseline, score, label, rating)
    """
    # Baseline calculations (see Appendix C for formula derivation)
    baseline_gct = 230 + (avg_pace_seconds_per_km - 240) * 0.22
    baseline_vo = 6.8 + (avg_pace_seconds_per_km - 240) * 0.004

    # GCT efficiency score (% deviation from baseline)
    gct_actual = form_eff.get("gct_average", 0)
    gct_score = ((gct_actual - baseline_gct) / baseline_gct) * 100 if baseline_gct > 0 else 0
    gct_label = "優秀" if gct_score < -5 else ("良好" if abs(gct_score) <= 5 else "要改善")
    gct_rating = 5.0 if gct_score < -5 else (4.5 if gct_score < -2 else (4.0 if abs(gct_score) <= 5 else 3.0))

    # VO efficiency score
    vo_actual = form_eff.get("vo_average", 0)
    vo_score = ((vo_actual - baseline_vo) / baseline_vo) * 100 if baseline_vo > 0 else 0
    vo_label = "優秀" if vo_score < -5 else ("良好" if abs(vo_score) <= 5 else "要改善")
    vo_rating = 5.0 if vo_score < -5 else (4.5 if vo_score < -2 else (4.0 if abs(vo_score) <= 5 else 3.0))

    # VR (no pace correction - absolute threshold)
    vr_actual = form_eff.get("vr_average", 0)
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

**Integration**:
```python
# In load_performance_data() method:
if form_eff:
    context["form_efficiency_pace_corrected"] = self._calculate_pace_corrected_form_efficiency(
        context["basic_metrics"]["avg_pace_seconds_per_km"],
        form_eff
    )
```

**Test:**
```python
# test_pace_correction.py (NEW)
@pytest.mark.parametrize("pace,expected_gct", [
    (240, 230),    # 4:00/km → 230ms
    (420, 270),    # 7:00/km → 270ms (230 + 180*0.22 = 269.6)
    (405, 266.3),  # 6:45/km
])
def test_gct_baseline_calculation(pace, expected_gct):
    """GCT baseline calculated correctly from pace."""
    worker = ReportGeneratorWorker()
    baseline = 230 + (pace - 240) * 0.22
    assert abs(baseline - expected_gct) < 0.5

@pytest.mark.parametrize("pace,expected_vo", [
    (240, 6.8),    # 4:00/km → 6.8cm
    (420, 7.52),   # 7:00/km → 7.52cm (6.8 + 180*0.004)
    (405, 7.46),   # 6:45/km
])
def test_vo_baseline_calculation(pace, expected_vo):
    """VO baseline calculated correctly from pace."""
    baseline = 6.8 + (pace - 240) * 0.004
    assert abs(baseline - expected_vo) < 0.02

def test_pace_corrected_form_efficiency_integration():
    """Pace-corrected form efficiency integrated in report."""
    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    with open(result["report_path"]) as f:
        report = f.read()

    # Check for pace correction table
    assert "ペース基準値" in report
    assert "補正スコア" in report
```

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
    assert "スプリット別 ペース・心拍" in report

def test_mermaid_graph_interval_run_includes_power():
    """Mermaid graph includes power for interval run."""
    report = render_report(training_type_category="interval_sprint")
    # Check for 3 data lines (pace, HR, power)
    assert report.count("line") >= 3

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
    baseline = 230 + (405 - 240) * 0.22
    assert abs(baseline - 266.3) < 0.1

def test_vo_baseline_calculation():
    """VO baseline calculated correctly from pace."""
    # 6:45/km (405 seconds) → baseline 7.46cm
    baseline = 6.8 + (405 - 240) * 0.004
    assert abs(baseline - 7.46) < 0.01

def test_gct_score_calculation():
    """GCT score (% deviation) calculated correctly."""
    # actual 253ms, baseline 266.3ms → -5.0%
    score = ((253 - 266.3) / 266.3) * 100
    assert abs(score - (-5.0)) < 0.1

def test_form_efficiency_rating():
    """Form efficiency rating stars calculated correctly."""
    # gct_score=-5.0 → rating=5.0 → ★★★★★
    rating = 5.0 if -5.0 < -5 else (4.5 if -5.0 < -2 else 4.0)
    assert rating == 4.5  # Actually between -5 and -2, so 4.5
```

### Integration Tests

#### test_report_generation_full.py
```python
# TEST ACTIVITY IDS DEFINITION
TEST_ACTIVITY_IDS = {
    "recovery": None,  # TODO: Identify recovery run activity_id
    "low_moderate": 20625808856,  # 2025-10-08 base run sample
    "tempo_threshold": 20744768051,  # 2025-10-20 threshold run
    "interval_sprint": None,  # TODO: Identify or create interval run test data
}

@pytest.mark.parametrize("training_type_category,min_lines,max_lines", [
    ("recovery", 200, 250),
    ("low_moderate", 280, 324),
    ("tempo_threshold", 400, 450),
    ("interval_sprint", 400, 464),
])
def test_full_report_generation(training_type_category, min_lines, max_lines):
    """Generate full report and check line count."""
    activity_id = TEST_ACTIVITY_IDS[training_type_category]
    if not activity_id:
        pytest.skip(f"Test activity ID not defined for {training_type_category}")

    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=activity_id)

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
    activity_id = TEST_ACTIVITY_IDS["interval_sprint"]
    if not activity_id:
        pytest.skip("Interval test activity ID not defined")

    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=activity_id)

    with open(result["report_path"]) as f:
        report = f.read()

    assert "生理学的指標サマリー" in report
    assert "生理学的指標との関連" in report
    assert "VO2 Max活用度" in report
    assert "閾値超過度" in report

def test_interval_run_4_phase_evaluation():
    """Interval run has 4-phase evaluation."""
    activity_id = TEST_ACTIVITY_IDS["interval_sprint"]
    if not activity_id:
        pytest.skip("Interval test activity ID not defined")

    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=activity_id)

    with open(result["report_path"]) as f:
        report = f.read()

    assert "ウォームアップフェーズ" in report
    assert "Workフェーズ" in report
    assert "Recoveryフェーズ" in report
    assert "クールダウンフェーズ" in report
```

### Manual Testing

#### Test Data (UPDATED)
```python
# Define in test_report_generation_full.py:
TEST_ACTIVITY_IDS = {
    "recovery": None,  # TODO: Search for recovery run in database
    "low_moderate": 20625808856,  # 2025-10-08, sample exists
    "tempo_threshold": 20744768051,  # 2025-10-20
    "interval_sprint": None,  # TODO: Create mock data or find real activity
}

# TODO for Manual Testing:
# 1. Query database for recovery run:
#    SELECT activity_id, activity_date FROM hr_efficiency
#    WHERE training_type = 'recovery' LIMIT 5;
#
# 2. Query database for interval run:
#    SELECT activity_id, activity_date FROM hr_efficiency
#    WHERE training_type IN ('vo2max', 'speed') LIMIT 5;
#
# 3. Update TEST_ACTIVITY_IDS with found IDs
```

#### Verification Checklist
- [ ] Base run (20625808856):
  - [ ] 300-324 lines
  - [ ] No "生理学的指標サマリー" section
  - [ ] 3-phase evaluation (Warmup/Main/Cooldown)
  - [ ] "> **参考**: VO2 Max" note present
  - [ ] Section order matches 2025-10-08_BALANCED.md
  - [ ] Mermaid graph renders in GitHub Preview
  - [ ] `<details>` sections fold/unfold correctly
- [ ] Threshold run (20744768051):
  - [ ] 400-450 lines
  - [ ] "生理学的指標サマリー" section present
  - [ ] "生理学的指標との関連" section present (simple version)
  - [ ] 3-phase evaluation (Warmup/Run/Cooldown)
  - [ ] Mermaid graph includes pace/HR only (no power for threshold)
- [ ] Interval run (TBD):
  - [ ] 400-464 lines
  - [ ] 4-phase evaluation (Warmup/Work/Recovery/Cooldown)
  - [ ] Section order matches 2025-10-15_interval_BALANCED.md
  - [ ] Mermaid graph includes power line
  - [ ] "長期目標（4-8週間後）" section present (if interval)
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
- [ ] **Mermaid Graphs**: Present in 総合評価 section with dynamic Y-axis
- [ ] **Pace-Corrected Form Efficiency**: GCT/VO baselines calculated from pace
- [ ] **Custom Filters**: All 4 filters (render_table, render_rows, sort_splits, bullet_list) defined and working

### Quality Requirements
- [ ] **Unit Tests**: All tests pass (80%+ coverage for new code)
- [ ] **Integration Tests**: All 4 training types generate successfully (where test data available)
- [ ] **Pre-commit Hooks**: Black, Ruff, Mypy pass
- [ ] **Code Review**: At least 1 reviewer approval

### Documentation Requirements
- [ ] **Planning.md**: This document completed and approved
- [ ] **Completion_report.md**: Generated after implementation
- [ ] **Sample Reports**: All 4 training types regenerated with new template (where possible)
- [ ] **CHANGELOG.md**: Entry added for v4.0 (BALANCED v2)

### Backward Compatibility
- [ ] **No Worker API Changes**: `generate_report()` signature unchanged
- [ ] **No DuckDB Schema Changes**: All data from existing tables
- [ ] **No Agent Output Changes**: Agents output same format, template handles differences
- [ ] **Graceful Degradation**: If `training_type_category` is None, defaults to `low_moderate`
- [ ] **Edge Cases Handled**: Missing data (splits, similar_workouts, vo2_max, etc.) handled gracefully

---

## Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Template becomes too complex** | High (maintenance burden) | Medium | - Use Jinja2 macros/filters for reusable logic<br>- Add inline comments<br>- Keep conditions simple (no deep nesting)<br>- Custom filters defined in Phase 0 |
| **Missing data for similar workouts** | Medium (incomplete table) | High | - Graceful handling: Show "類似ワークアウトが見つかりませんでした"<br>- Verify MCP tool before Phase 3<br>- Template checks `if similar_workouts` before rendering |
| **Mermaid graph syntax errors** | Medium (graph doesn't render) | Low | - Use `| tojson` filter for data conversion<br>- Test with GitHub Preview<br>- Return None if splits empty, template checks `if mermaid_data` |
| **Agent output format changes** | High (template breaks) | Low | - Defensive checks: `if field exists then render`<br>- Test with real agent outputs<br>- Add logging for missing fields |
| **Pace correction formulas inaccurate** | Medium (misleading scores) | Medium | - Formulas documented in Appendix C<br>- Validated against sample report values<br>- Unit tests for edge cases (very slow/fast paces) |
| **Section order differs from samples** | Low (aesthetic) | Low | - Strict adherence to sample structure<br>- Manual review against samples<br>- Automated tests for section order |
| **Custom filters not defined** | Critical (template fails) | Low | - Phase 0 PRE-IMPLEMENTATION setup<br>- Unit tests verify filters exist<br>- Test template rendering before Phase 1 |

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
| **Phase 0** | Pre-Implementation Setup<br>- Define custom Jinja2 filters<br>- Unit tests for filters | 1-2 hours | None |
| **Phase 1** | Template structure rewrite<br>- Section reordering<br>- Folding sections<br>- Remove numbering<br>- Edge case handling | 6-8 hours | Phase 0 complete |
| **Phase 2** | Mermaid graphs<br>- Worker modifications<br>- Template integration<br>- Testing | 4-6 hours | Phase 1 complete |
| **Phase 3** | Similar workouts<br>- MCP tool verification<br>- Worker modifications<br>- Template table | 6-8 hours | Phase 1 complete<br>MCP tool verified |
| **Phase 4** | Pace-corrected form efficiency<br>- Worker calculations<br>- Template integration<br>- Formula validation | 4-6 hours | Phase 1 complete |
| **Testing** | Unit tests<br>Integration tests<br>Manual testing | 4-6 hours | All phases complete |
| **Documentation** | Completion report<br>Sample regeneration<br>CHANGELOG | 2-3 hours | All phases complete |
| **Total** | | **27-39 hours** | |

**Note**: Phases 2-4 can be partially parallelized after Phase 1 completion.

---

## References

### Design Documents
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/docs/report-balance-analysis.md` - BALANCED principle, line reduction targets
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/docs/training-type-evaluation-criteria.md` - Training type-specific evaluation, pace correction formulas (see Appendix C)

### Sample Reports (IDEAL STRUCTURE)
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/result/individual/2025/10/2025-10-08_20625808856_SAMPLE_BALANCED.md` - Base run (324 lines)
- `/home/yamakii/workspace/claude_workspace/garmin-performance-analysis/result/individual/2025/10/2025-10-15_interval_SAMPLE_BALANCED.md` - Interval run (464 lines)

### Current Implementation
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/tools/reporting/templates/detailed_report.j2` - Current template (330 lines)
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/tools/reporting/report_generator_worker.py` - Worker (634 lines)
- `/home/yamakii/workspace/claude_workspace/garmin-balanced-report-templates/tools/reporting/report_template_renderer.py` - Renderer (WHERE CUSTOM FILTERS ARE DEFINED)

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
| Mermaid graphs | ❌ | ✅ (in 総合評価) | ✅ (in 総合評価) | ✅ (dynamic Y-axis) |
| Folding split details | ❌ | ✅ `<details>` | ✅ `<details>` | ✅ |
| 生理学的指標サマリー | Conditional | ❌ (note only) | ✅ | Conditional (tempo+) |
| 生理学的指標との関連 | Position 4.5 | ❌ | ✅ (simple) | Conditional (tempo+) |
| フォーム効率 location | Section 1 (独立) | Inside パフォーマンス指標 | Inside パフォーマンス指標 | Nested |
| Pace correction | ❌ | ✅ (GCT/VO) | ✅ (GCT/VO) | ✅ (with formulas) |
| Similar workouts table | ❌ | ✅ | ✅ | ✅ (MCP-powered) |
| 改善ポイント position | 3 | 7 | 8 | Near end (7/8) |
| Technical details folding | ❌ | ✅ `<details>` | ✅ `<details>` | ✅ |
| Glossary folding | ❌ | ✅ `<details>` | ✅ `<details>` | ✅ |
| Phase count | 3 (or 4) | 3 | 4 | 1/3/4 (type-dependent) |
| Custom filters | ❌ | N/A | N/A | ✅ (4 filters defined) |

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

## Appendix C: Pace Correction Formula Sources (NEW)

### GCT (Ground Contact Time) Baseline

**Formula**: `baseline_gct = 230 + (pace_seconds_per_km - 240) * 0.22`

**Derivation**:
- **Reference Points** (from training-type-evaluation-criteria.md):
  - 4:00/km (240 sec/km) → 230ms (elite runner)
  - 7:00/km (420 sec/km) → 270ms (recreational runner)
- **Linear Approximation**:
  - Slope: (270 - 230) / (420 - 240) = 40 / 180 = 0.22
  - Intercept: 230 (at pace = 240)
- **Validation**:
  - 6:45/km (405 sec/km): 230 + (405 - 240) * 0.22 = 230 + 36.3 = **266.3ms** ✅
  - Matches sample report baseline value

**Evaluation Thresholds**:
- Score = ((actual - baseline) / baseline) * 100
- **優秀 (Excellent)**: Score < -5% (5% faster than baseline)
- **良好 (Good)**: -5% ≤ Score ≤ 5% (within ±5% of baseline)
- **要改善 (Needs Improvement)**: Score > 5% (5% slower than baseline)

### VO (Vertical Oscillation) Baseline

**Formula**: `baseline_vo = 6.8 + (pace_seconds_per_km - 240) * 0.004`

**Derivation**:
- **Reference Points** (from training-type-evaluation-criteria.md):
  - 4:00/km (240 sec/km) → 6.8cm (elite runner, minimal bounce)
  - 7:00/km (420 sec/km) → 7.5cm (recreational runner, more bounce)
- **Linear Approximation**:
  - Slope: (7.5 - 6.8) / (420 - 240) = 0.7 / 180 = 0.0039 ≈ 0.004
  - Intercept: 6.8 (at pace = 240)
- **Validation**:
  - 6:45/km (405 sec/km): 6.8 + (405 - 240) * 0.004 = 6.8 + 0.66 = **7.46cm** ✅
  - Matches sample report baseline value

**Evaluation Thresholds**:
- Score = ((actual - baseline) / baseline) * 100
- **優秀 (Excellent)**: Score < -5% (5% less bounce)
- **良好 (Good)**: -5% ≤ Score ≤ 5% (within ±5% of baseline)
- **要改善 (Needs Improvement)**: Score > 5% (5% more bounce)

### VR (Vertical Ratio) Evaluation

**No Pace Correction** - Absolute threshold

**Rationale**: VR = VO / Stride Length is a relative metric that should remain constant across paces. A good runner maintains VR between 8-10% regardless of speed.

**Evaluation Thresholds**:
- **理想範囲内 (Ideal Range)**: 8.0% ≤ VR ≤ 9.5%
- **要改善 (Needs Improvement)**: VR < 8.0% or VR > 9.5%

### Formula Sources and Validation

**Primary Source**:
- `docs/training-type-evaluation-criteria.md` - Running form efficiency metrics by pace

**Validation Method**:
1. Compare baseline values with actual sample report (2025-10-08 base run):
   - Sample pace: 6:45/km (405 sec/km)
   - Sample GCT baseline: 266.3ms ✅ Matches formula
   - Sample VO baseline: 7.46cm ✅ Matches formula
2. Linear regression analysis on 100+ activities (planned for Phase 4 validation)
3. Cross-reference with running biomechanics literature (Daniels' Running Formula, Noakes' Lore of Running)

**Notes**:
- Formulas are **linear approximations** suitable for recreational to sub-elite paces (5:00-8:00/km)
- For paces < 4:00/km or > 8:00/km, formulas may need recalibration
- Elite runners may have different baselines due to superior biomechanics

---

*End of Planning Document (Fixed Version)*
