# 計画: BALANCED Sample Report Reproduction

## プロジェクト情報
- **プロジェクト名**: `balanced_sample_reproduction`
- **作成日**: `2025-10-25`
- **ステータス**: 計画中
- **目的**: 3つのBALANCEDサンプルレポート（Base/Interval/Threshold）の形式を可能な限り忠実に再現する

## 要件定義

### 目的
現在のBALANCED Report V2システムがサンプルレポートと異なる出力を生成している。サンプルレポートの形式・構造・内容を分析し、training type別に適切なレポートフォーマットを実装することで、一貫性のある高品質なレポート生成を実現する。

### 解決する問題
1. **構造の不一致**: セクション順序、サブセクション、詳細度の相違
2. **内容の不均一**: Training type間での情報過多/過少
3. **フォーマットの相違**: 表形式/箇条書き/自由記述の使い分けが不統一
4. **Training type対応不足**: Base/Interval/Thresholdで異なるべき表現が統一されている

### ユースケース
1. **ベースラン分析**: Zone 2-3中心の中強度走の適切な評価と改善提案
2. **インターバル分析**: Work/Recovery区間の明確な分離とVO2 Max活用度評価
3. **閾値トレーニング分析**: 閾値ペース維持時間とZone 4比率の重点評価
4. **自動レポート生成**: Training type検出から適切なフォーマット選択まで自動化

## ギャップ分析

### 分析対象サンプル
1. **Base run**: `result/individual/2025/10/2025-10-08_20625808856_SAMPLE_BALANCED.md`
   - Training type: `aerobic_base`
   - 距離: 5.43km
   - 特徴: Zone 3中心、パフォーマンスサマリー充実、類似ワークアウト比較

2. **Interval**: `result/individual/2025/10/2025-10-15_interval_SAMPLE_BALANCED.md`
   - Training type: `interval_training`
   - 距離: 10.6km (1km×5本)
   - 特徴: Work/Recovery明示、生理学的指標サマリー、VO2 Max活用度

3. **Threshold**: `result/individual/2025/10/2025-10-24_threshold_SAMPLE_BALANCED.md`
   - Training type: `lactate_threshold`
   - 距離: 6.13km (メイン3.35km)
   - 特徴: メイン区間重視、Zone 4時間比率、閾値超過度

### 主要な差異

#### 1. 構造上の差異

**サンプルレポート共通構造:**
```
1. 基本情報 (簡潔な箇条書き)
2. 📊 パフォーマンスサマリー
   - 生理学的指標サマリー (Tempo/Interval only)
   - 類似ワークアウトとの比較
   - 参考値 (VO2 Max, 閾値ペース)
3. 総合評価
   - アクティビティタイプ
   - 総合所見 (★★★★☆ X.X/5.0)
   - ペース・心拍推移 (Mermaidグラフ + 分析)
4. パフォーマンス指標
   - スプリット概要 (表形式)
   - ハイライト
   - 詳細分析 (折りたたみ)
   - フォーム効率 (ペース補正評価)
5. 生理学的指標との関連 (Tempo/Interval only)
   - VO2 Max活用度
   - 閾値超過度
6. フェーズ評価
   - ウォームアップ (★評価付き)
   - メイン/Work (★評価付き)
   - Recovery (Interval only, ★評価付き)
   - クールダウン (★評価付き)
7. 環境要因
   - 気象条件・環境インパクト (★評価付き)
8. 💡 改善ポイント
   - 優先度・重要度付き構造化提案
9. 技術的詳細 (折りたたみ)
10. 📚 用語解説 (折りたたみ)
```

**現在のテンプレート問題点:**
- ✅ 基本構造は一致
- ❌ 生理学的指標サマリーの配置・内容が不統一
- ❌ 総合所見の★評価が欠落
- ❌ フェーズ評価の★評価が欠落
- ❌ 改善ポイントの構造化（⭐重要度表示）が不完全
- ❌ Mermaidグラフの分析文が欠落（Interval/Thresholdで必須）

#### 2. Training Type別内容差異

**Base Run (aerobic_base):**
| 要素 | サンプル | 現状 | 差異 |
|------|---------|------|------|
| 生理学的サマリー | なし | なし | ✅ 一致 |
| 類似比較 | 全体ペース比較 | 全体ペース比較 | ✅ 一致 |
| 総合所見 | ★4.2/5.0表示 | 欠落 | ❌ 追加必要 |
| ペース補正評価 | 詳細な表形式 | 簡易版 | ❌ 改善必要 |
| フェーズ評価 | 3段階(W/R/C) | 3段階 | ✅ 一致 |
| 改善ポイント | ⭐重要度3段階 | 箇条書きのみ | ❌ 構造化必要 |

**Interval (interval_training):**
| 要素 | サンプル | 現状 | 差異 |
|------|---------|------|------|
| 生理学的サマリー | あり（VO2 Max利用率、FTP%） | なし | ❌ 追加必要 |
| 類似比較 | Work区間ペース比較 | 全体ペース | ❌ 変更必要 |
| 総合所見 | ★4.8/5.0表示 | 欠落 | ❌ 追加必要 |
| スプリット表 | タイプ列（W-up/W1/R1） | なし | ❌ 追加必要 |
| グラフ分析 | Work/Recovery推移分析 | なし | ❌ 追加必要 |
| フェーズ評価 | 4段階(W/Work/Rec/C) | 3段階 | ❌ 変更必要 |
| 改善ポイント | Recoveryペース管理優先 | 一般的提案 | ❌ 特化必要 |

**Threshold (lactate_threshold):**
| 要素 | サンプル | 現状 | 差異 |
|------|---------|------|------|
| 生理学的サマリー | あり（閾値ペース一致確認） | なし | ❌ 追加必要 |
| 類似比較 | メイン区間ペース比較 | 全体ペース | ❌ 変更必要 |
| 総合所見 | ★4.3/5.0表示 | 欠落 | ❌ 追加必要 |
| 評価対象明示 | "メイン区間のみ評価" | 全体評価 | ❌ 明示必要 |
| フォーム評価 | メイン区間のみ | 全体統計 | ❌ 変更必要 |
| フェーズ評価 | 3段階(W/Run/C) | 3段階(W/Main/Finish) | ⚠️ 命名変更 |
| 改善ポイント | Zone 4時間延長提案 | 一般的提案 | ❌ 特化必要 |

#### 3. フォーマット上の差異

**総合所見 (サンプル vs 現状):**
```
[サンプル]
### 総合所見 (★★★★☆ 4.2/5.0)

今日のランは質の高い有酸素ベース走でした。平均心拍数146bpm、
平均ペース6:45/km、平均パワー225Wという適切な中強度で、
ペース変動係数0.017と非常に高い安定性を発揮しています。

**✅ 優れている点:**
- ペース安定性: 変動係数0.017（目標<0.05を大幅クリア）
- **パワー効率向上**: 前回比-5W（2.2%効率アップ）✅
- フォーム効率: 全指標でペース補正後に優秀評価

**⚠️ 改善可能な点:**
- ウォームアップ不足: 最初から心拍145bpmでスタート
- クールダウン欠如: 運動後の急激な負荷低下
```

```
[現状テンプレート]
## 総合評価

{% if summary %}
### 総合所見

{{ summary.summary if summary.summary else "評価データがありません。" }}

{% if summary.key_strengths %}
**✅ 優れている点:**
{% for strength in summary.key_strengths %}
- {{ strength }}
{% endfor %}
{% endif %}
```

**差異:**
- ❌ ★評価が欠落
- ❌ 評価スコア(X.X/5.0)が欠落
- ✅ 優れている点/改善点の構造は一致

**改善ポイント (サンプル vs 現状):**
```
[サンプル]
## 💡 改善ポイント

今回のベース走（有酸素ゾーン中心）を次回実施する際の改善点：

### 1. ウォームアップの導入 ⭐ 重要度: 高
**現状**: なし（最初から心拍145bpmでスタート）

**推奨アクション:**
- 最初の1-1.5kmをゆっくり開始（7:30-8:00/km）
- 心拍120-135bpm、パワー180-200Wを目安に

**期待効果**: 怪我リスク低減、メイン走行での効率向上
```

```
[現状テンプレート]
## 💡 改善ポイント

{% if summary and summary.recommendations %}
{{ summary.recommendations }}
{% else %}
改善ポイントデータがありません。
{% endif %}
```

**差異:**
- ❌ 構造化されていない（テキストのみ）
- ❌ ⭐重要度表示なし
- ❌ 現状/推奨/期待効果の3段階構成なし

#### 4. データ表示の差異

**フォーム効率表 (サンプル vs 期待される表示):**
```
[サンプル - 非常に詳細]
| 指標 | 実測値 | ペース基準値 | 補正スコア | 評価 |
|------|--------|------------|-----------|------|
| **接地時間** | 253.0ms | 266.3ms | **-5.0%** 優秀 | ★★★★★ 5.0 |
| **垂直振幅** | 7.13cm | 7.46cm | **-4.4%** 優秀 | ★★★★☆ 4.5 |
| **垂直比率** | 8.89% | 8.0-9.5% | 理想範囲内 | ★★★★★ 5.0 |
```

**現状の実装状況:**
- ✅ ペース基準値計算ロジックは実装済み（`_calculate_pace_corrected_form_efficiency`）
- ❌ テンプレートでの表示が簡易化されている
- ❌ ★評価表示が欠落

**スプリット表 (Interval時のタイプ列):**
```
[サンプル]
| Split | タイプ | 距離 | ペース | 心拍 | ... |
|-------|-------|------|--------|------|-----|
| 1 | W-up | 1.00km | 7:00 | 135 | ... |
| 3 | **W1** | 1.00km | **4:28** | **170** | ... |
| 4 | R1 | 0.40km | 6:30 | 145 | ... |
```

**現状:**
- ✅ `intensity_type` 列はテンプレートで条件付き表示
- ✅ DuckDB splits table に `intensity_type` 存在
- ⚠️ タイプ表示が "W-up/W1/R1" 形式ではなく "warmup/active/rest"

#### 5. Agent出力形式の差異

**summary-section-analyst の出力:**
```python
# サンプルレポートで期待される形式
{
    "summary": "今日のランは質の高い...",  # ★評価含む
    "key_strengths": ["...", "..."],         # 箇条書きリスト
    "improvement_areas": ["...", "..."],     # 箇条書きリスト
    "recommendations": """
### 1. ウォームアップの導入 ⭐ 重要度: 高
**現状**: なし
**推奨アクション:**
- 最初の1-1.5kmをゆっくり開始
**期待効果**: 怪我リスク低減
"""
}
```

**現状の実装:**
- ✅ `summary`, `key_strengths`, `improvement_areas` は実装済み
- ❌ `summary` に★評価が含まれていない
- ❌ `recommendations` が構造化されていない（マークダウン形式でない）

## 設計

### アーキテクチャ設計

#### 1. Training Type Detection & Category Mapping

**データフロー:**
```
DuckDB (hr_efficiency.training_type)
    ↓
ReportGeneratorWorker.load_performance_data()
    ↓ training_type string
ReportTemplateRenderer.render_report()
    ↓ training_type_category
Jinja2 Template
    ↓ セクション表示制御
Final Report
```

**Training Type Categorization:**
```python
def get_training_type_category(training_type: str) -> str:
    """
    Map training_type to template category.

    Returns:
        - "low_moderate": recovery, aerobic_base, aerobic_endurance
        - "tempo_threshold": tempo, lactate_threshold
        - "interval_sprint": vo2max, anaerobic_capacity, speed
    """
    interval_sprint = {"vo2max", "anaerobic_capacity", "speed"}
    tempo_threshold = {"tempo", "lactate_threshold"}

    if training_type in interval_sprint:
        return "interval_sprint"
    elif training_type in tempo_threshold:
        return "tempo_threshold"
    else:
        return "low_moderate"
```

**テンプレート内での使用:**
```jinja2
{% set training_type_category = training_type_category|default("low_moderate") %}
{% set show_physiological = training_type_category in ["tempo_threshold", "interval_sprint"] %}
{% set is_interval = training_type_category == "interval_sprint" %}
```

#### 2. Star Rating System

**実装箇所:**
- **summary-section-analyst**: 総合所見に★評価を含める
- **phase-section-analyst**: 各フェーズ評価に★評価を含める
- **efficiency-section-analyst**: フォーム効率に★評価を含める
- **environment-section-analyst**: 環境インパクトに★評価を含める

**出力形式:**
```python
# Agent output example
{
    "summary": "...(★★★★☆ 4.2/5.0)",
    "rating": 4.2  # Optional: for template extraction
}
```

**テンプレート処理:**
```jinja2
{# Extract rating from summary text #}
{% set rating_match = summary.summary | regex_search(r'\(★+☆* (\d+\.\d+)/5\.0\)') %}
{% if rating_match %}
### 総合所見 ({{ rating_match.group(0) }})
{% else %}
### 総合所見
{% endif %}
```

#### 3. Comparison Pace Selection Logic

**現在の実装 (`_get_comparison_pace`):**
```python
def _get_comparison_pace(self, performance_data: dict) -> tuple[float, str]:
    training_type = performance_data.get("training_type", "unknown")
    structured_types = {"tempo", "lactate_threshold", "vo2max", "anaerobic_capacity", "speed"}

    if training_type in structured_types:
        run_metrics = performance_data.get("run_metrics")
        if run_metrics and run_metrics.get("avg_pace_seconds_per_km"):
            return (run_metrics["avg_pace_seconds_per_km"], "main_set")

    return (performance_data["basic_metrics"]["avg_pace_seconds_per_km"], "overall")
```

**サンプル検証:**
- ✅ Base run: 全体ペース使用（正しい）
- ✅ Interval: Work区間ペース使用（正しい）
- ✅ Threshold: メイン区間ペース使用（正しい）

**問題点:**
- ❌ テンプレートで `pace_source` 表示がない
- ❌ "メインセットペース比較" という注釈がない

#### 4. Physiological Indicators Display

**表示条件:**
```jinja2
{% if show_physiological and vo2_max_data and lactate_threshold_data %}
### 生理学的指標サマリー

| 指標 | 現在値 | 評価 |
|------|--------|------|
| **VO2 Max** | {{ vo2_max_data.precise_value }} ml/kg/min | ... |
| **VO2 Max利用率** | {{ vo2_max_utilization }}% | ... |
| **閾値ペース** | {{ threshold_pace_formatted }}/km | ... |
| **FTP(パワー)** | {{ lactate_threshold_data.functional_threshold_power }} W | ... |
{% endif %}
```

**必要な計算:**
```python
# In ReportGeneratorWorker.generate_report()
if training_type_category in ["tempo_threshold", "interval_sprint"]:
    # Calculate VO2 Max utilization
    vo2_max_pace = estimate_vo2_max_pace(vo2_max_data["precise_value"])
    target_pace = run_metrics["avg_pace_seconds_per_km"]
    vo2_max_utilization = (vo2_max_pace / target_pace) * 100

    # FTP percentage
    ftp = lactate_threshold_data["functional_threshold_power"]
    work_avg_power = run_metrics.get("avg_power", 0)
    ftp_percentage = (work_avg_power / ftp) * 100 if ftp > 0 else 0
```

#### 5. Structured Recommendations Format

**Agent出力要件 (summary-section-analyst):**
```python
{
    "recommendations": """
今回のベース走（有酸素ゾーン中心）を次回実施する際の改善点：

### 1. ウォームアップの導入 ⭐ 重要度: 高
**現状**: なし（最初から心拍145bpmでスタート）

**推奨アクション:**
- 最初の1-1.5kmをゆっくり開始（7:30-8:00/km）
- 心拍120-135bpm、パワー180-200Wを目安に
- 筋肉・腱の準備、特に高湿度環境では発汗機能の準備も重要

**期待効果**: 怪我リスク低減、メイン走行での効率向上

---

### 2. クールダウンの追加 ⭐ 重要度: 高
**現状**: なし（心拍151bpmから急停止）
...
"""
}
```

**構造化ルール:**
1. 見出しに番号と⭐重要度を含める
2. 各改善点を `---` で区切る
3. 必須セクション: **現状**, **推奨アクション**, **期待効果**

### データモデル設計

#### 1. Agent Output Schema Updates

**summary-section-analyst:**
```python
{
    "summary": str,              # ★評価含む
    "key_strengths": list[str],  # 箇条書き
    "improvement_areas": list[str],
    "recommendations": str       # 構造化マークダウン
}
```

**phase-section-analyst:**
```python
{
    "warmup_evaluation": str,    # ★評価含む
    "run_evaluation": str,       # ★評価含む (or main_evaluation)
    "recovery_evaluation": str,  # ★評価含む (interval only)
    "cooldown_evaluation": str   # ★評価含む (or finish_evaluation)
}
```

**efficiency-section-analyst:**
```python
{
    "efficiency": str,           # ★評価含む
    "pace_corrected_table": str  # 表形式（オプション）
}
```

**environment-section-analyst:**
```python
{
    "environmental": str         # ★評価含む
}
```

#### 2. Template Context Enhancements

**新規追加項目:**
```python
context = {
    # ... existing ...

    # Training type category
    "training_type_category": str,  # "low_moderate" | "tempo_threshold" | "interval_sprint"

    # Physiological indicators (tempo/interval only)
    "vo2_max_utilization": float,
    "vo2_max_utilization_eval": str,
    "threshold_pace_formatted": str,
    "threshold_pace_comparison": str,
    "ftp_percentage": float,
    "work_avg_power": float,

    # Star ratings extracted from agent text
    "summary_rating_stars": str,    # "★★★★☆"
    "summary_rating_score": float,  # 4.2
    "warmup_rating_stars": str,
    "warmup_rating_score": float,
    "main_rating_stars": str,
    "main_rating_score": float,
    "recovery_rating_stars": str,
    "recovery_rating_score": float,
    "cooldown_rating_stars": str,
    "cooldown_rating_score": float,
    "form_efficiency_rating_stars": str,
    "form_efficiency_rating_score": float,
    "environment_rating_stars": str,
    "environment_rating_score": float,

    # Interval-specific
    "interval_graph_analysis": str,  # Mermaidグラフ下の分析文
    "target_segments_description": str,  # "Workセグメント5本のみ"
}
```

### API/インターフェース設計

#### 1. ReportGeneratorWorker Enhancements

**新規メソッド:**
```python
def _get_training_type_category(self, training_type: str) -> str:
    """Map training_type to template category."""
    pass

def _calculate_physiological_indicators(
    self,
    training_type_category: str,
    vo2_max_data: dict,
    lactate_threshold_data: dict,
    run_metrics: dict
) -> dict:
    """Calculate VO2 Max utilization, FTP%, etc."""
    pass

def _extract_star_rating(self, text: str) -> tuple[str, float] | None:
    """Extract star rating from agent text using regex."""
    # Pattern: (★★★★☆ 4.2/5.0)
    pass

def _generate_interval_graph_analysis(
    self,
    splits: list[dict],
    run_metrics: dict,
    recovery_metrics: dict
) -> str:
    """Generate Work/Recovery analysis text for interval reports."""
    pass
```

#### 2. Agent Prompt Updates

**summary-section-analyst.md:**
```markdown
## 出力形式

**section_type**: `"summary"`

### 総合所見に★評価を含めること

必ず以下の形式で★評価を含める:

```python
{
    "summary": """
今日のランは質の高い有酸素ベース走でした。...(★★★★☆ 4.2/5.0)
""",
    "key_strengths": [...],
    "improvement_areas": [...],
    "recommendations": """
### 1. タイトル ⭐ 重要度: 高
**現状**: ...
**推奨アクション:**
- ...
**期待効果**: ...
---
### 2. タイトル ⭐ 重要度: 中
...
"""
}
```

### 評価基準
- 5.0: 完璧（全指標優秀、改善点なし）
- 4.5-4.9: 非常に良好（一部軽微な改善点）
- 4.0-4.4: 良好（明確な強みあり、改善余地あり）
- 3.5-3.9: 標準的（強みと課題が混在）
- 3.0-3.4: 要改善（課題が目立つ）
```

**phase-section-analyst.md:**
```markdown
## 出力形式

各フェーズ評価に★評価を含めること:

```python
{
    "warmup_evaluation": """
**実際**: 2km @ 7:00→6:50/km、心拍135→142bpm

**評価**: 段階的にペース・心拍を上昇させ、理想的な準備ができています。(★★★★★ 5.0/5.0)

**改善点**: なし
""",
    "run_evaluation": "...(★★★★☆ 4.8/5.0)",
    "cooldown_evaluation": "...(★★★☆☆ 3.5/5.0)"
}
```
```

#### 3. Template Filter/Function Additions

**新規Jinja2フィルター:**
```python
@app.template_filter('extract_star_rating')
def extract_star_rating(text: str) -> dict:
    """
    Extract star rating from text.

    Returns:
        {"stars": "★★★★☆", "score": 4.2, "text_without_rating": "..."}
    """
    import re
    pattern = r'\(([★☆]+) (\d+\.\d+)/5\.0\)'
    match = re.search(pattern, text)
    if match:
        return {
            "stars": match.group(1),
            "score": float(match.group(2)),
            "text_without_rating": re.sub(pattern, "", text).strip()
        }
    return {"stars": "", "score": 0.0, "text_without_rating": text}

@app.template_filter('format_intensity_type')
def format_intensity_type(intensity_type: str, index: int) -> str:
    """
    Format intensity_type for interval display.

    Args:
        intensity_type: "warmup" | "active" | "rest" | "cooldown"
        index: Split index

    Returns:
        "W-up" | "W1" | "R1" | "C-down"
    """
    if intensity_type == "warmup":
        return "W-up"
    elif intensity_type == "cooldown":
        return "C-down"
    elif intensity_type == "active":
        # Count active splits up to this index
        work_count = count_active_splits_before(index)
        return f"W{work_count}"
    elif intensity_type == "rest":
        recovery_count = count_rest_splits_before(index)
        return f"R{recovery_count}"
    return intensity_type
```

## 実装フェーズ

### Phase 1: Template Structure & Star Ratings (優先度: 最高)

**目的**: サンプルと同じセクション構造を実現し、★評価を全セクションに追加

**タスク:**
1. **テンプレート構造修正**
   - [ ] 生理学的指標サマリーの配置確認（Tempo/Interval only）
   - [ ] 類似ワークアウト比較の注釈追加（pace_source表示）
   - [ ] 総合所見の★評価表示
   - [ ] フェーズ評価の★評価表示（各フェーズ）
   - [ ] 環境インパクトの★評価表示
   - [ ] フォーム効率の★評価表示

2. **Agent Prompt更新 (summary-section-analyst)**
   - [ ] 総合所見に★評価を含める指示追加
   - [ ] 評価基準明示（5段階）
   - [ ] recommendationsの構造化ルール追加（⭐重要度）
   - [ ] 改善ポイントテンプレート提供

3. **Agent Prompt更新 (phase-section-analyst)**
   - [ ] 各フェーズ評価に★評価を含める指示追加
   - [ ] Training type別評価基準の明確化
   - [ ] フェーズ別評価基準（5段階）

4. **Agent Prompt更新 (efficiency/environment)**
   - [ ] ★評価を含める指示追加
   - [ ] 評価基準明示

**テスト:**
- [ ] Base run: 総合所見★4.2、フェーズ評価★表示確認
- [ ] Interval: 総合所見★4.8、Work/Recovery/Cooldown評価確認
- [ ] Threshold: 総合所見★4.3、メイン区間評価重視確認

**受け入れ基準:**
- 全レポートタイプで★評価が適切に表示される
- 改善ポイントが構造化される（⭐重要度付き）
- サンプルと同じセクション順序

### Phase 2: Training Type-Specific Content (優先度: 高)

**目的**: Training type別の内容差を実装

**タスク:**
1. **Training Type Category Mapping**
   - [ ] `ReportGeneratorWorker._get_training_type_category()` 実装
   - [ ] テンプレートで `training_type_category` 変数設定
   - [ ] `show_physiological`, `is_interval` フラグ設定

2. **Physiological Indicators Calculation**
   - [ ] VO2 Max utilization計算ロジック
   - [ ] FTP percentage計算
   - [ ] Threshold pace comparison text生成
   - [ ] Work average power/HR計算（Interval/Threshold用）

3. **Comparison Pace Annotation**
   - [ ] テンプレートで `pace_source` 表示
   - [ ] "過去の同条件ワークアウト（**メインセットペース比較**）" 注釈

4. **Interval-Specific Elements**
   - [ ] スプリット表にタイプ列追加（W-up/W1/R1/C-down）
   - [ ] Mermaidグラフ分析文生成（Work/Recovery推移）
   - [ ] 評価対象明示テキスト（"Workセグメント5本のみ"）
   - [ ] 4フェーズ評価（warmup/run/recovery/cooldown）

5. **Threshold-Specific Elements**
   - [ ] 評価対象明示（"メイン区間のみ評価"）
   - [ ] フォーム効率をメイン区間のみ計算
   - [ ] Zone 4時間比率の表示・評価

**テスト:**
- [ ] Base run: 生理学的サマリーなし、全体ペース比較
- [ ] Interval: 生理学的サマリーあり、Work区間比較、4フェーズ評価
- [ ] Threshold: 生理学的サマリーあり、メイン区間比較、Zone 4評価

**受け入れ基準:**
- Training type検出が正しく動作
- 各typeで適切な内容が表示される
- 不要なセクションが非表示になる

### Phase 3: Data Display Formatting (優先度: 中)

**目的**: 表形式・グラフ・詳細表示をサンプルと一致させる

**タスク:**
1. **フォーム効率表の拡張**
   - [ ] ペース基準値列追加
   - [ ] 補正スコア列追加（-X.X%形式）
   - [ ] ★評価列追加
   - [ ] 表ヘッダーの統一

2. **スプリット表のフォーマット改善**
   - [ ] タイプ列のフォーマット（W-up/W1/R1形式）
   - [ ] Work区間の**太字**強調
   - [ ] 列幅・配置の最適化

3. **Mermaidグラフ分析の追加**
   - [ ] Interval: Work/Recovery推移分析
   - [ ] Threshold: メイン区間の安定性分析
   - [ ] Base: ペース・心拍推移の簡潔な分析

4. **折りたたみ詳細の充実**
   - [ ] スプリット詳細分析の強化
   - [ ] 技術的詳細の拡充
   - [ ] 用語解説のTraining type別カスタマイズ

**テスト:**
- [ ] フォーム効率表がサンプルと一致
- [ ] スプリット表の可読性向上
- [ ] グラフ分析が有益

**受け入れ基準:**
- 表形式がサンプルと視覚的に一致
- グラフ分析が的確
- 折りたたみ要素が適切に機能

### Phase 4: Agent Output Quality Improvement (優先度: 中)

**目的**: Agent出力の質を向上させ、サンプルの文章品質に近づける

**タスク:**
1. **summary-section-analyst強化**
   - [ ] 総合所見の文章構造改善（導入→詳細→まとめ）
   - [ ] 優れている点の具体性向上（数値引用）
   - [ ] 改善可能な点の建設的表現
   - [ ] recommendations構造化の徹底

2. **phase-section-analyst強化**
   - [ ] Training type別評価基準の適用徹底
   - [ ] フェーズ別の具体的フィードバック
   - [ ] 次回への改善提案の追加

3. **split-section-analyst強化**
   - [ ] ハイライトの選定基準明確化
   - [ ] 詳細分析の深度向上
   - [ ] 区間比較の有益性向上

4. **efficiency-section-analyst強化**
   - [ ] ペース補正評価の説明改善
   - [ ] Training type別フォーム評価基準
   - [ ] パフォーマンストレンドの分析

**テスト:**
- [ ] 3つのサンプルタイプで文章品質を比較
- [ ] 具体性・有益性・読みやすさの評価

**受け入れ基準:**
- Agent出力がサンプルと同等の品質
- データドリブンな分析
- 建設的で実行可能な提案

### Phase 5: Edge Cases & Refinement (優先度: 低)

**目的**: エッジケース対応と細部の調整

**タスク:**
1. **データ欠損対応**
   - [ ] VO2 Max/閾値データなし時のフォールバック
   - [ ] 類似ワークアウトなし時の表示
   - [ ] セクション分析欠落時のエラーハンドリング

2. **Training type未知時の対応**
   - [ ] デフォルトフォーマット決定
   - [ ] 警告メッセージ表示

3. **パフォーマンス最適化**
   - [ ] テンプレートレンダリングの高速化
   - [ ] 不要なデータ取得の削減

4. **日本語文章の自然さ向上**
   - [ ] 体言止めの削減
   - [ ] 接続詞の適切な使用
   - [ ] 敬体/常体の統一

**テスト:**
- [ ] データ欠損ケースでエラーなし
- [ ] 未知training typeで適切な表示
- [ ] レンダリング時間が許容範囲

**受け入れ基準:**
- すべてのエッジケースで適切な表示
- エラーなくレポート生成
- パフォーマンス劣化なし

## テスト計画

### Unit Tests

**対象ファイル: `tools/reporting/report_generator_worker.py`**

1. **Training Type Category Mapping**
   ```python
   def test_get_training_type_category():
       worker = ReportGeneratorWorker()
       assert worker._get_training_type_category("aerobic_base") == "low_moderate"
       assert worker._get_training_type_category("lactate_threshold") == "tempo_threshold"
       assert worker._get_training_type_category("vo2max") == "interval_sprint"
       assert worker._get_training_type_category("unknown") == "low_moderate"
   ```

2. **Star Rating Extraction**
   ```python
   def test_extract_star_rating():
       worker = ReportGeneratorWorker()
       text = "今日のランは素晴らしい...(★★★★☆ 4.2/5.0)"
       stars, score = worker._extract_star_rating(text)
       assert stars == "★★★★☆"
       assert score == 4.2
   ```

3. **Physiological Indicators Calculation**
   ```python
   def test_calculate_physiological_indicators():
       worker = ReportGeneratorWorker()
       result = worker._calculate_physiological_indicators(
           training_type_category="tempo_threshold",
           vo2_max_data={"precise_value": 52.3},
           lactate_threshold_data={"functional_threshold_power": 285},
           run_metrics={"avg_pace_seconds_per_km": 304, "avg_power": 342}
       )
       assert "vo2_max_utilization" in result
       assert "ftp_percentage" in result
       assert result["ftp_percentage"] == pytest.approx(120.0, rel=0.1)
   ```

**対象ファイル: `tools/reporting/report_template_renderer.py`**

1. **Intensity Type Formatting**
   ```python
   def test_format_intensity_type():
       assert format_intensity_type("warmup", 1) == "W-up"
       assert format_intensity_type("active", 3) == "W1"  # assuming 1st active
       assert format_intensity_type("rest", 4) == "R1"
       assert format_intensity_type("cooldown", 12) == "C-down"
   ```

### Integration Tests

**テストケース: 3つのサンプルワークアウト**

1. **Base Run Test (Activity 20625808856)**
   ```python
   def test_base_run_report_generation():
       worker = ReportGeneratorWorker()
       result = worker.generate_report(20625808856, "2025-10-08")

       report_content = Path(result["report_path"]).read_text()

       # Structure checks
       assert "## 📊 パフォーマンスサマリー" in report_content
       assert "### 類似ワークアウトとの比較" in report_content
       assert "生理学的指標サマリー" not in report_content  # Should NOT appear

       # Star rating checks
       assert re.search(r'### 総合所見 \(★+☆* \d+\.\d+/5\.0\)', report_content)
       assert re.search(r'### ウォームアップフェーズ \(★+☆* \d+\.\d+/5\.0\)', report_content)

       # Content checks
       assert "過去の同条件ワークアウト" in report_content
       assert "全体ペース" in report_content or "overall" in report_content
   ```

2. **Interval Test**
   ```python
   def test_interval_report_generation():
       # Assume we have interval data in test DB
       worker = ReportGeneratorWorker()
       result = worker.generate_report(test_interval_activity_id, test_date)

       report_content = Path(result["report_path"]).read_text()

       # Structure checks
       assert "### 生理学的指標サマリー" in report_content
       assert "VO2 Max利用率" in report_content
       assert "FTP(パワー)" in report_content

       # Interval-specific checks
       assert "Work" in report_content
       assert "Recovery" in report_content
       assert "W1" in report_content or "W-up" in report_content

       # Phase evaluation (4 phases)
       assert "### Workフェーズ" in report_content
       assert "### Recoveryフェーズ" in report_content
   ```

3. **Threshold Test**
   ```python
   def test_threshold_report_generation():
       worker = ReportGeneratorWorker()
       result = worker.generate_report(20783281578, "2025-10-24")

       report_content = Path(result["report_path"]).read_text()

       # Structure checks
       assert "### 生理学的指標サマリー" in report_content
       assert "閾値ペース" in report_content

       # Threshold-specific checks
       assert "メイン区間" in report_content
       assert "Zone 4" in report_content

       # Comparison annotation
       assert "メインセットペース比較" in report_content
   ```

### Performance Tests

1. **Report Generation Time**
   ```python
   def test_report_generation_performance():
       worker = ReportGeneratorWorker()
       start = time.time()
       worker.generate_report(20625808856, "2025-10-08")
       duration = time.time() - start

       assert duration < 5.0  # Should complete within 5 seconds
   ```

2. **Template Rendering Time**
   ```python
   def test_template_rendering_performance():
       renderer = ReportTemplateRenderer()
       context = load_test_context()

       start = time.time()
       renderer.render_report(**context)
       duration = time.time() - start

       assert duration < 1.0  # Template rendering should be fast
   ```

### Acceptance Tests

**比較テスト: サンプル vs 生成レポート**

```python
def test_sample_reproduction_similarity():
    """
    生成レポートがサンプルとどの程度一致するかを検証
    """
    worker = ReportGeneratorWorker()

    # Base run
    result = worker.generate_report(20625808856, "2025-10-08")
    generated = Path(result["report_path"]).read_text()
    sample = Path("result/individual/2025/10/2025-10-08_20625808856_SAMPLE_BALANCED.md").read_text()

    # Structure similarity
    assert count_sections(generated) == count_sections(sample)

    # Star rating presence
    assert count_star_ratings(generated) >= count_star_ratings(sample) * 0.8

    # Key phrases
    assert "パフォーマンスサマリー" in generated
    assert "類似ワークアウトとの比較" in generated
    assert "改善ポイント" in generated

    # Training type-specific
    assert ("生理学的指標サマリー" in generated) == ("生理学的指標サマリー" in sample)
```

## リスク評価

### リスク1: Agent出力形式の変更による後方互換性喪失

**重大度**: 高

**影響範囲:**
- 既存のsection_analyses dataに★評価が含まれていない
- recommendations構造が旧形式

**緩和策:**
1. **段階的移行**
   - 新形式をデフォルトとするが、旧形式もサポート
   - テンプレートで両形式を処理可能にする

2. **テンプレート側での柔軟な処理**
   ```jinja2
   {# Extract star rating if present, else show plain text #}
   {% set rating = summary.summary | extract_star_rating %}
   {% if rating.score > 0 %}
   ### 総合所見 ({{ rating.stars }} {{ rating.score }}/5.0)
   {{ rating.text_without_rating }}
   {% else %}
   ### 総合所見
   {{ summary.summary }}
   {% endif %}
   ```

3. **段階的Agent更新**
   - Phase 1でテンプレート対応
   - Phase 4でAgent prompt更新
   - 古いデータでもエラーにならない

**対応期限**: Phase 1完了時

### リスク2: Training Type Detection失敗

**重大度**: 中

**影響範囲:**
- `hr_efficiency.training_type` が NULL または未知の値
- 適切なフォーマットが選択されない

**緩和策:**
1. **フォールバックロジック**
   ```python
   training_type = performance_data.get("training_type", "unknown")
   if not training_type or training_type == "unknown":
       # Heuristic detection based on pace variability
       if pace_consistency < 0.05:
           training_type_category = "low_moderate"
       elif has_recovery_phase:
           training_type_category = "interval_sprint"
       else:
           training_type_category = "low_moderate"
   ```

2. **警告ログ**
   - Training type未検出時にログ出力
   - ユーザーに手動確認を促す

3. **デフォルトフォーマット**
   - 不明時は `low_moderate` として扱う
   - 最小限の情報を表示

**対応期限**: Phase 2実装時

### リスク3: DuckDB Schema変更による互換性問題

**重大度**: 低

**影響範囲:**
- `performance_trends` のスキーマ変更（run/main, cooldown/finish）
- 新旧データの混在

**緩和策:**
1. **Schema Check Logic**
   - 現在の実装と同様、カラム存在チェックを継続
   ```python
   schema_check = conn.execute("PRAGMA table_info('performance_trends')").fetchall()
   column_names = [row[1] for row in schema_check]
   has_new_schema = "run_avg_pace_seconds_per_km" in column_names
   ```

2. **Legacy Support**
   - 旧スキーマでも正しくマッピング
   - テンプレートで両命名規則をサポート

**対応期限**: 継続的に維持

### リスク4: Jinja2テンプレートの複雑化

**重大度**: 中

**影響範囲:**
- 条件分岐の増加による可読性低下
- デバッグ困難
- パフォーマンス劣化

**緩和策:**
1. **ヘルパー関数の活用**
   - 複雑なロジックはPython側で実装
   - テンプレートはシンプルに保つ

2. **ドキュメンテーション**
   - テンプレート内にコメント追加
   - 各セクションの目的を明記

3. **テンプレート分割**
   - 必要に応じてinclude/macroを活用
   ```jinja2
   {% include "sections/performance_summary.j2" %}
   {% include "sections/physiological_indicators.j2" %}
   ```

**対応期限**: Phase 3実装時に検討

### リスク5: サンプル再現の完全性検証困難

**重大度**: 中

**影響範囲:**
- サンプルとの差異を定量評価できない
- 主観的な判断に依存

**緩和策:**
1. **構造比較テスト**
   - セクション数、見出し、表の列数を比較
   - 自動テストで検証

2. **手動レビュー**
   - 各サンプルタイプで生成レポートを目視確認
   - チェックリスト作成

3. **差分可視化ツール**
   - Markdown diffツールで比較
   - 構造・内容の差異を可視化

**対応期限**: Phase 5で実施

## 受け入れ基準

### Phase 1完了基準
- [ ] 全レポートタイプで★評価が表示される（総合所見、全フェーズ、フォーム、環境）
- [ ] 改善ポイントが構造化される（⭐重要度、現状/推奨/期待効果）
- [ ] セクション順序がサンプルと一致
- [ ] Unit testsでstar rating extraction成功

### Phase 2完了基準
- [ ] Training type category mappingが正しく動作
- [ ] Tempo/Intervalで生理学的指標サマリー表示
- [ ] Baseで生理学的指標サマリー非表示
- [ ] 類似ワークアウト比較でpace_source注釈表示
- [ ] Intervalで4フェーズ評価、Baseで3フェーズ評価
- [ ] Integration testsで3サンプルタイプすべて成功

### Phase 3完了基準
- [ ] フォーム効率表がサンプルと視覚的に一致（基準値、補正スコア、★評価）
- [ ] Intervalスプリット表でタイプ列が正しく表示（W-up/W1/R1/C-down）
- [ ] Mermaidグラフ下に分析文が表示（Interval/Threshold）
- [ ] 折りたたみ詳細が充実

### Phase 4完了基準
- [ ] Agent出力がサンプルと同等の文章品質（具体性、有益性）
- [ ] Training type別評価基準が適切に適用
- [ ] recommendations構造化が徹底

### Phase 5完了基準
- [ ] データ欠損ケースでエラーなく表示
- [ ] 未知training typeで適切なフォールバック
- [ ] レポート生成時間が5秒以内
- [ ] 全Unit/Integration/Performance tests合格
- [ ] 手動レビューでサンプル再現度80%以上

## 最終目標

**3つのサンプルレポートを基準として、以下を達成:**

1. **構造的一貫性**
   - セクション順序・見出し・階層がサンプルと一致
   - Training type別に適切な内容の表示/非表示

2. **内容の充実度**
   - ★評価が全セクションに存在
   - 生理学的指標サマリー（Tempo/Intervalのみ）
   - 構造化された改善ポイント（⭐重要度付き）

3. **フォーマットの統一**
   - 表形式の詳細度がサンプルと一致
   - Work/Recoveryの明確な表示（Interval）
   - メイン区間重視の評価（Threshold）

4. **文章品質**
   - データドリブンで具体的
   - 建設的で実行可能な提案
   - 自然な日本語表現

**成功指標:**
- 生成レポートとサンプルの構造一致度: 95%以上
- ★評価の存在率: 100%（全セクション）
- 手動レビューでの品質評価: 4.0/5.0以上
- ユーザーフィードバック: "サンプルとほぼ同じ" 評価

---

**次のステップ:**
このplanning.mdをmain branchにコミット後、GitHub Issueを作成し、`tdd-implementer` エージェントにハンドオフしてPhase 1から実装開始。
