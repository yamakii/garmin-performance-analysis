# 計画: Training-Type-Specific Balanced Report Templates

## プロジェクト情報
- **プロジェクト名**: `balanced_report_templates`
- **作成日**: `2025-10-25`
- **ステータス**: 計画中
- **GitHub Issue**: TBD

---

## 要件定義

### 目的
レポートの情報量を最適化し、トレーニングタイプごとに適切な粒度の情報を提供する。

**主要目標**:
1. 情報過多を解消（現在496-615行 → 200-450行へ削減）
2. トレーニングタイプに応じた構成の最適化
3. ユーザー体験の向上（重要情報が埋もれない）

### 解決する問題

**現状の課題**:
1. **情報量の肥大化**: v3.0レポートが元レポートの3-3.7倍（496-615行）に成長
2. **一律の構造**: 全トレーニングタイプで同じ構造を使用（リカバリー走にもVO2 Max分析）
3. **セクション重複**: パワー・ストライドが独立セクションとフォーム効率の両方に登場
4. **配置の非最適性**: "次回トレーニングプラン"が下部配置（ユーザーは既にGarminでプラン作成済み）

**参考資料**: `docs/report-balance-analysis.md`

### ユースケース

#### UC-1: リカバリー走の分析
- **要求**: 最小限の情報（フォーム確認程度）
- **構成**: 1フェーズ（Recoveryのみ）、生理学的指標なし
- **目標行数**: 200-250行（50-60%削減）

#### UC-2: ベース走の分析
- **要求**: 基本的なパフォーマンス確認
- **構成**: 3フェーズ（Warmup/Run/Cooldown）、生理学的指標は参考程度
- **目標行数**: 300行（40%削減）

#### UC-3: テンポ/閾値走の分析
- **要求**: 詳細なパフォーマンス分析
- **構成**: 3フェーズ、生理学的指標あり（VO2 Max利用率、閾値超過率）
- **目標行数**: 400-450行（27-35%削減）

#### UC-4: インターバル/スプリント走の分析
- **要求**: Work/Recoveryセグメント別の詳細分析
- **構成**: 4フェーズ（Warmup/Work or Sprint/Recovery/Cooldown）、生理学的指標あり
- **目標行数**: 400-450行（27-35%削減）

---

## 設計

### アーキテクチャ

#### 現状のシステム構成

```
ReportGeneratorWorker
  ├── load_performance_data()      # DuckDBからデータ取得
  ├── load_section_analyses()      # 5エージェントの分析結果取得
  ├── load_splits_data()           # スプリットデータ取得
  └── generate_report()            # レポート生成

ReportTemplateRenderer
  ├── load_template()              # Jinja2テンプレート読み込み
  ├── render_report()              # テンプレート+データ → Markdown
  └── save_report()                # ファイル保存

detailed_report.j2 (279行)
  - Jinja2テンプレート
  - 現在は単一構造（全トレーニングタイプ共通）
```

**データフロー**:
```
DuckDB → load_performance_data() → training_type (from hr_efficiency table)
       ↓
Section Analyses (5 agents) → load_section_analyses()
       ↓
render_report(training_type, data) → Jinja2 template → Markdown
```

#### 提案システム構成

```
detailed_report.j2 (改修)
  ├── Base Structure (共通)
  ├── Conditional Sections (training_typeによる条件分岐)
  │   ├── Physiological Indicators (low_moderate: なし, tempo+: あり)
  │   ├── Phase Evaluation (recovery: 1フェーズ, base: 3フェーズ, interval: 4フェーズ)
  │   ├── Form Efficiency (統合: GCT/VO/VR + Power + Stride)
  │   └── Improvement Points (位置変更: 下部へ移動)
  └── Technical Details (折りたたみ)
```

**トレーニングタイプマッピング**:
```python
TRAINING_TYPE_CONFIGS = {
    "recovery": {
        "phase_count": 1,
        "physiological_indicators": False,
        "target_line_count": "200-250"
    },
    "low_moderate": {  # Base Run
        "phase_count": 3,
        "physiological_indicators": False,
        "target_line_count": "300"
    },
    "tempo_threshold": {  # Tempo/Threshold
        "phase_count": 3,
        "physiological_indicators": True,
        "target_line_count": "400-450"
    },
    "lactate_threshold": {  # Threshold
        "phase_count": 3,
        "physiological_indicators": True,
        "target_line_count": "400-450"
    },
    "interval_sprint": {  # Interval/Sprint
        "phase_count": 4,
        "physiological_indicators": True,
        "target_line_count": "400-450"
    }
}
```

### データモデル

#### 既存DuckDBスキーマ（変更なし）

```sql
-- Training type detection
SELECT training_type FROM hr_efficiency WHERE activity_id = ?;
-- Values: "recovery", "low_moderate", "tempo_threshold", "lactate_threshold", "interval_sprint"

-- Phase metrics (3-phase: warmup/run/cooldown, 4-phase: warmup/run/recovery/cooldown)
SELECT
    warmup_avg_pace_seconds_per_km, warmup_avg_hr,
    run_avg_pace_seconds_per_km, run_avg_hr,
    recovery_avg_pace_seconds_per_km, recovery_avg_hr,  -- NULL for 3-phase
    cooldown_avg_pace_seconds_per_km, cooldown_avg_hr
FROM performance_trends WHERE activity_id = ?;

-- Form efficiency (GCT, VO, VR)
SELECT gct_average, vo_average, vr_average FROM form_efficiency WHERE activity_id = ?;

-- Splits (power, stride_length included)
SELECT pace_seconds_per_km, heart_rate, power, stride_length, ... FROM splits WHERE activity_id = ?;
```

#### Section Analyses構造（⚠️ 出力内容変更あり）

```python
section_analyses = {
    "efficiency": str,           # efficiency-section-analyst output (内容変更: パワー・ストライド統合)
    "environment_analysis": str,  # environment-section-analyst output (変更なし)
    "phase_evaluation": dict,     # phase-section-analyst output (構造変更: 1/3/4フェーズ対応)
    "split_analysis": dict,       # split-section-analyst output (内容変更: インターバル時はWorkのみ)
    "summary": dict               # summary-section-analyst output (内容変更: recommendationsの内容)
}
```

**⚠️ 重要な変更点:**

各エージェントの**分析ロジックと出力内容を変更**します（データ構造は維持）：

**1. efficiency-section-analyst**
```python
# 現状
analysis_data = {
    "efficiency": "GCT/VO/VRの評価テキスト（フォーム効率のみ）"
}

# 変更後
analysis_data = {
    "efficiency": """
    【フォーム効率】
    GCT: 253ms (ペース基準266ms → -5% 優秀)
    VO: 7.13cm (ペース基準7.46cm → -4.4% 優秀)
    VR: 8.89% (理想範囲内)

    【パワー効率】← 新規統合
    平均パワー: 225W (類似比-5W、効率+2.2%)
    一貫性: 変動係数0.021

    【ストライド長】← 新規統合
    平均: 1.18m (類似比+1cm)
    ケイデンス×ストライド: 最適

    総合: ★★★★☆ 4.5/5.0
    """
}
```

**2. phase-section-analyst**
```python
# 現状: 3フェーズまたは4フェーズ
analysis_data = {
    "warmup_evaluation": "...",
    "run_evaluation": "...",
    "recovery_evaluation": "...",  # 4フェーズ時のみ
    "cooldown_evaluation": "..."
}

# 変更後: 1/3/4フェーズ対応
# リカバリー走（1フェーズ）← 新規パターン
analysis_data = {
    "run_evaluation": "..."  # warmup, cooldownなし
}

# ベース/テンポ/閾値（3フェーズ）← 現状維持
analysis_data = {
    "warmup_evaluation": "...",
    "run_evaluation": "...",
    "cooldown_evaluation": "..."
}

# インターバル/スプリント（4フェーズ）← 現状維持
analysis_data = {
    "warmup_evaluation": "...",
    "run_evaluation": "...",
    "recovery_evaluation": "...",
    "cooldown_evaluation": "..."
}
```

**3. split-section-analyst**
```python
# 現状: 全スプリット分析
analysis_data = {
    "analyses": {
        "split_1": "...",
        "split_2": "...",
        ...
        "split_N": "..."
    }
}

# 変更後（インターバル時）: Workセグメントのみ← 新規動作
analysis_data = {
    "analyses": {
        "split_3": "...",  # Work 1
        "split_5": "...",  # Work 2
        "split_7": "...",  # Work 3
        ...
    }
}
# ウォームアップ・リカバリー・クールダウンのスプリットは含まれない
```

**4. summary-section-analyst**
```python
# 現状
analysis_data = {
    "activity_type": "ベースラン",
    "summary": "...",
    "recommendations": "次はテンポランで6-8km走り..."  # トレーニングプラン
}

# 変更後
analysis_data = {
    "activity_type": "ベースラン",
    "summary": "...",
    "recommendations": "ウォームアップを1.5km追加すると..."  # 改善アドバイス
}
```

### API/インターフェース設計

#### ReportTemplateRenderer.render_report() (変更なし)

```python
def render_report(
    self,
    activity_id: str,
    date: str,
    basic_metrics: dict[str, Any],
    training_type: str | None = None,  # 既存パラメータ
    # ... 他のパラメータは既存のまま
) -> str:
    """
    training_typeに基づいてテンプレート内で条件分岐。
    既存のパラメータ構造を維持。
    """
```

#### Jinja2テンプレート条件分岐（新規）

```jinja2
{# Training type configuration #}
{% set is_recovery = (training_type == "recovery") %}
{% set is_base = (training_type == "low_moderate") %}
{% set is_tempo_threshold = (training_type in ["tempo_threshold", "lactate_threshold"]) %}
{% set is_interval = (training_type == "interval_sprint") %}

{% set show_physiological = (is_tempo_threshold or is_interval) %}
{% set phase_count = 1 if is_recovery else (4 if is_interval else 3) %}

{# Conditional sections #}
{% if show_physiological %}
## 📊 パフォーマンスサマリー
### 生理学的指標サマリー
...
{% else %}
## 📊 パフォーマンスサマリー
### 類似ワークアウトとの比較
> **参考**: VO2 Max データは参考程度です。
{% endif %}
```

---

## 実装フェーズ

### Phase 0: エージェント定義の変更 ⭐ **最重要・最優先**
**目標**: 各エージェントの分析ロジックをtraining_type対応に変更

**依存関係**: Phase 1-4の前提条件（Phase 0完了後にテンプレート変更可能）

#### 0-1. split-section-analyst.md の変更
**変更箇所**: `.claude/agents/split-section-analyst.md`

**MCPツールリスト変更**:
```diff
# .claude/agents/split-section-analyst.md (line 3)
-tools: mcp__garmin-db__get_splits_comprehensive, mcp__garmin-db__get_splits_pace_hr, mcp__garmin-db__get_splits_form_metrics, mcp__garmin-db__insert_section_analysis_dict
+tools: mcp__garmin-db__get_splits_comprehensive, mcp__garmin-db__get_splits_pace_hr, mcp__garmin-db__get_splits_form_metrics, mcp__garmin-db__get_hr_efficiency_analysis, mcp__garmin-db__get_interval_analysis, mcp__garmin-db__insert_section_analysis_dict
```

**追加MCPツール**:
- `mcp__garmin-db__get_hr_efficiency_analysis` - training_type取得用
- `mcp__garmin-db__get_interval_analysis` - Work/Recovery判定用

**使用方法指示の追加**:
```markdown
## 必須実行手順（更新版）

1. **training_type取得**:
   - `get_hr_efficiency_analysis(activity_id)` でtraining_typeを取得
   - training_typeをカテゴリにマッピング:
     - `vo2max`, `anaerobic_capacity`, `speed` → interval_sprint（Workセグメント評価）
     - その他 → 全スプリット評価

2. **セグメント判定**（interval_sprint の場合のみ）:
   - `get_interval_analysis(activity_id)` でWork/Recoveryセグメントを識別
   - 返り値: `{"work_segments": [{"split_number": 3, ...}, {"split_number": 5, ...}]}`
   - Work segmentのsplit_numberリストを取得

3. **スプリットデータ取得**:
   - `get_splits_comprehensive(activity_id, statistics_only=False)` で全スプリット取得
     - interval_sprint: Workセグメント詳細比較のため statistics_only=False
     - その他: statistics_only=True でも可

4. **分析実行**:
   - interval_sprint: Work segmentのsplit_numberのみ詳細評価
   - その他: 全スプリット評価
   - 評価テキストに"Work 1", "Work 2"とセグメント種別を明記

5. **DuckDB保存**: `insert_section_analysis_dict()`で結果を保存
```

**重要な制約（追加）**:
```markdown
- interval_sprint判定時は**必ず get_interval_analysis() を呼び出す**
- Work segmentのみを`analyses`辞書に含める（Warmup/Recovery/Cooldownは除外）
- split_keyは"split_3", "split_5"等の形式を維持（split番号はWork segmentの実際の番号）
```

**出力例（インターバル時）**:
```python
analysis_data = {
    "analyses": {
        "split_3": "Work 1の分析...",
        "split_5": "Work 2の分析...",
        "split_7": "Work 3の分析...",
        # Warmup, Recovery, Cooldownは含まれない
    }
}
```

**テスト内容**:
- [ ] リカバリー/ベース走: 全スプリット分析
- [ ] インターバル走: Workセグメントのみ分析
- [ ] get_hr_efficiency_analysis()が正しく呼ばれる
- [ ] get_interval_analysis()またはintensity_typeが正しく使用される

---

#### 0-2. phase-section-analyst.md の変更
**変更箇所**: `.claude/agents/phase-section-analyst.md`

**MCPツールリスト変更**:
```
# .claude/agents/phase-section-analyst.md (line 3)
# 変更なし（既に get_hr_efficiency_analysis を使用中）
tools: mcp__garmin-db__get_performance_trends, mcp__garmin-db__get_hr_efficiency_analysis, mcp__garmin-db__insert_section_analysis_dict
```

**追加MCPツール**: なし

**使用方法指示の追加**:
```markdown
## フェーズ構造判定（拡張）

### 必須実行手順（更新版）

1. **training_type取得**:
   - `get_hr_efficiency_analysis(activity_id)` でtraining_typeを取得

2. **フェーズ数判定**:
   - `training_type == "recovery"` → **1フェーズ** (Runのみ) ← 新規
   - `recovery_splits` が存在 → 4フェーズ (Warmup/Work/Recovery/Cooldown)
   - その他 → 3フェーズ (Warmup/Run/Cooldown)

3. **performance_trends取得**:
   - `get_performance_trends(activity_id)` でフェーズデータ取得

4. **出力構造調整**:
   - **1フェーズ**: `{"run_evaluation": "..."}`のみ出力（warmup/cooldownなし）
   - **3フェーズ**: `{"warmup_evaluation": "...", "run_evaluation": "...", "cooldown_evaluation": "..."}`
   - **4フェーズ**: `{"warmup_evaluation": "...", "work_evaluation": "...", "recovery_evaluation": "...", "cooldown_evaluation": "..."}`

5. **DuckDB保存**: `insert_section_analysis_dict()`で結果を保存
```

**重要な制約（追加）**:
```markdown
- recovery run（training_type='recovery'）では**必ずrun_evaluationのみ**を出力
- warmup_evaluation, cooldown_evaluationキーを含めない
- 評価テキストで「ウォームアップ・クールダウン不要」を明示しない（キー自体を出力しない）
```

**出力例（リカバリー走）**:
```python
analysis_data = {
    "run_evaluation": """
    低強度リカバリー走として理想的な実行でした。
    全体が回復ゾーン（Zone 1-2）で維持され...
    (★★★★★ 5.0/5.0)
    """
}
# warmup_evaluation, cooldown_evaluation は含まれない
```

**テスト内容**:
- [ ] `training_type="recovery"`: run_evaluationのみ出力
- [ ] `training_type="aerobic_base"`: 3フェーズ出力
- [ ] `training_type="vo2max"`: 4フェーズ出力（recovery_splitsあり）
- [ ] ReportGeneratorWorkerで1フェーズ構造が正しく処理される

---

#### 0-3. efficiency-section-analyst.md の変更 ⭐ **大幅変更**
**変更箇所**: `.claude/agents/efficiency-section-analyst.md`

**MCPツールリスト変更**:
```diff
# .claude/agents/efficiency-section-analyst.md (line 3)
-tools: mcp__garmin-db__get_form_efficiency_summary, mcp__garmin-db__get_hr_efficiency_analysis, mcp__garmin-db__get_heart_rate_zones_detail, mcp__garmin-db__get_splits_pace_hr, mcp__garmin-db__insert_section_analysis_dict
+tools: mcp__garmin-db__get_form_efficiency_summary, mcp__garmin-db__get_hr_efficiency_analysis, mcp__garmin-db__get_heart_rate_zones_detail, mcp__garmin-db__get_splits_pace_hr, mcp__garmin-db__get_splits_comprehensive, mcp__garmin-db__compare_similar_workouts, mcp__garmin-db__insert_section_analysis_dict
```

**追加MCPツール**:
- `mcp__garmin-db__get_splits_comprehensive` - パワー・ストライド取得用
- `mcp__garmin-db__compare_similar_workouts` - 類似ワークアウト比較用

**使用方法指示の追加**:
```markdown
## 使用するMCPツール（拡張）

**既存ツール**:
- `mcp__garmin-db__get_form_efficiency_summary(activity_id)` - GCT/VO/VR取得
- `mcp__garmin-db__get_hr_efficiency_analysis(activity_id)` - 心拍効率
- `mcp__garmin-db__get_splits_pace_hr(activity_id, statistics_only=True)` - ペース取得

**新規追加ツール**:
- `mcp__garmin-db__get_splits_comprehensive(activity_id, statistics_only=True)` - **パワー・ストライドデータ取得**
  - 使用目的: power, stride_length, cadence取得
  - `statistics_only=True`で統計値のみ取得（トークン削減）
- `mcp__garmin-db__compare_similar_workouts(activity_id)` - **類似ワークアウト比較**
  - 使用目的: パワー・ストライドの過去比較データ取得
  - ペース・距離が類似する過去ワークアウトとの比較
```

**分析手順（拡張）**:
```markdown
## 必須実行手順（更新版）

1. **ペース取得**: `get_splits_pace_hr(activity_id, statistics_only=True)`
   - 平均ペース、ペース区分判定に使用

2. **フォーム効率分析**（既存）:
   - `get_form_efficiency_summary(activity_id)` でGCT/VO/VR取得
   - ペース補正評価を実施（既存ロジック維持）

3. **心拍効率分析**（既存）:
   - `get_hr_efficiency_analysis(activity_id)` でゾーン分布取得

4. **パワー効率分析**（新規統合）:
   - `get_splits_comprehensive(activity_id, statistics_only=True)` でパワーデータ取得
     - 取得項目: power（平均パワー）
   - `compare_similar_workouts(activity_id)` で類似ワークアウト比較
     - 類似ワークアウトのパワー比較データ取得
   - 分析内容: パワー一貫性、FTP比率、類似比較（-5W等）

5. **ストライド長分析**（新規統合）:
   - `get_splits_comprehensive(activity_id, statistics_only=True)` でストライド・ケイデンス取得
     - 取得項目: stride_length（平均ストライド）, cadence（平均ケイデンス）
   - `compare_similar_workouts(activity_id)` で類似ワークアウト比較
     - 類似ワークアウトのストライド比較データ取得
   - 分析内容: ケイデンス×ストライド関係、理想範囲判定、類似比較（+1cm等）

6. **統合評価生成**:
   - GCT/VO/VR + パワー + ストライドを1つのテキストにまとめる
   - 総合評価（★評価）を含める

7. **DuckDB保存**: `insert_section_analysis_dict()`で統合テキストを保存
```

**重要な制約（追加）**:
```markdown
- `get_splits_comprehensive()` は**statistics_only=True**で呼び出す（トークン削減）
- `compare_similar_workouts()` で取得したデータから、パワー・ストライドの過去比較を抽出
- 統合テキストは【フォーム効率】【パワー効率】【ストライド長】【総合評価】の4セクションで構成
```

**出力例**:
```python
analysis_data = {
    "efficiency": """
    【フォーム効率（ペース補正評価）】
    - 接地時間: 253ms (ペース6:45/km基準266ms → -5% 優秀)
    - 垂直振幅: 7.13cm (ペース基準7.46cm → -4.4% 優秀)
    - 垂直比率: 8.89% (理想範囲8-9.5% → 適正)

    【パワー効率】
    - 平均パワー: 225W (FTPの79%, 類似ワークアウト比-5W)
    - パワー効率向上: 同じペースで-2.2%削減 ✅
    - パワー一貫性: 変動係数0.021 (安定)

    【ストライド長】
    - 平均ストライド: 1.18m (類似比+1cm拡大 ✅)
    - ケイデンス×ストライド: 165spm × 1.18m = 理想的バランス
    - 理想範囲: 1.15-1.25m (達成 ✅)

    【総合評価】: ★★★★☆ 4.5/5.0
    ペースに対して全指標が基準以上の効率を示しています。
    """
}
```

**テスト内容**:
- [ ] GCT/VO/VRのペース補正評価が含まれる
- [ ] パワー効率（平均、FTP比率、類似比較）が含まれる
- [ ] ストライド長（平均、ケイデンス関係、類似比較）が含まれる
- [ ] 1つの統合テキストとして出力される
- [ ] get_splits_comprehensive()とcompare_similar_workouts()が正しく呼ばれる

---

#### 0-4. summary-section-analyst.md の変更
**変更箇所**: `.claude/agents/summary-section-analyst.md`

**MCPツールリスト変更**:
```
# .claude/agents/summary-section-analyst.md (line 3)
# 変更なし（既存ツールで改善アドバイス生成可能）
tools: mcp__garmin-db__get_splits_pace_hr, mcp__garmin-db__get_splits_form_metrics, mcp__garmin-db__get_splits_elevation, mcp__garmin-db__get_form_efficiency_summary, mcp__garmin-db__get_performance_trends, mcp__garmin-db__get_vo2_max_data, mcp__garmin-db__get_lactate_threshold_data, mcp__garmin-db__get_weather_data, mcp__garmin-db__insert_section_analysis_dict
```

**追加MCPツール**: なし

**使用方法指示の変更**:
```markdown
## recommendations出力ガイドライン（変更）

### 旧形式（Phase 0実装前）
**目的**: 次回トレーニングプラン（具体的なワークアウト提案）
**例**: "次回はテンポラン（5:00-5:10/km）で6-8km走り、VO2 Max向上を目指しましょう"

### 新形式（Phase 0実装後）
**目的**: 改善ポイント（今回のパフォーマンスに基づく次回同種ワークアウトへのアドバイス）
**例**: "今回のベース走（有酸素ゾーン中心）を次回実施する際の改善点：ウォームアップを1.5km追加することで怪我リスク低減..."

### 必須実行手順

1. **既存の総合評価生成**（変更なし）:
   - activity_type判定
   - パフォーマンスデータ統合分析

2. **改善ポイント生成**（新規ロジック）:
   - 今回の課題を2-3項目抽出
   - 各項目に優先度付け（高/中/低）
   - 具体的アクション・期待効果を明記

3. **recommendations構成**:
   ```
   今回の[activity_type]を次回実施する際の改善点：

   【改善ポイント1: タイトル】⭐ 重要度: 高
   **現状**: 今回の状況説明
   **推奨アクション**: 具体的な改善策
   **期待効果**: 改善による効果

   【改善ポイント2: タイトル】⭐ 重要度: 中
   ...
   ```

4. **DuckDB保存**: `insert_section_analysis_dict()`でsummary辞書を保存

### 重要な制約（追加）

- **NG例**（トレーニングプラン形式）:
  - "次回: 5km × 3本 @ 4:30/km"
  - "次週はインターバルトレーニングを実施"
  - "VO2 Max向上のため、次は..."

- **OK例**（改善アドバイス形式）:
  - "ウォームアップを1.5km追加すると..."
  - "ペース変動を30秒/km以内に抑えると..."
  - "クールダウンで乳酸除去を促進すると..."

- 改善ポイントは**今回のワークアウトの課題**から導出
- 次回の異なるワークアウトは提案しない
```

**出力例**:
```python
analysis_data = {
    "activity_type": "有酸素ベース走",
    "summary": "...",
    "recommendations": """
    【改善ポイント1: ウォームアップの導入】⭐ 重要度: 高
    - アクション: 最初の1-1.5kmを7:30-8:00/kmで開始
    - 期待効果: 怪我リスク低減、メイン走行での効率向上

    【改善ポイント2: クールダウンの追加】⭐ 重要度: 高
    - アクション: 最後に1kmのクールダウン（8:00-8:30/km）
    - 期待効果: 乳酸除去促進、翌日の疲労感軽減

    【改善ポイント3: パワー効率の維持】⭐ 重要度: 中
    - アクション: 同じペースで低パワーを継続（225W前後）
    - 期待効果: 長期的に更に-5-10Wの効率化
    """
}
```

**テスト内容**:
- [ ] recommendationsが改善アドバイス形式になっている
- [ ] トレーニングプラン形式ではない
- [ ] 優先度付けされている
- [ ] 具体的なアクション・期待効果が含まれる

---

### Phase 1: テンプレート条件分岐実装
**目標**: トレーニングタイプ別のセクション表示制御

**前提条件**: Phase 0完了（エージェント定義変更済み）

**実装内容**:
1. `detailed_report.j2` に条件分岐ロジック追加
   - `training_type` に基づく表示制御変数定義
   - 生理学的指標セクションの条件表示
   - フェーズ評価のカウント制御（1/3/4フェーズ対応）
2. 後方互換性の確保
   - `training_type` が `None` の場合はデフォルト構成（3フェーズ、全セクション表示）
3. ReportGeneratorWorkerの1フェーズ対応
   - `load_section_analyses()` で1フェーズ構造を認識

**テスト内容**:
- [ ] `training_type=None` でレポート生成（既存動作確認）
- [ ] `training_type="recovery"` で1フェーズ構成生成
- [ ] `training_type="low_moderate"` で3フェーズ構成生成
- [ ] `training_type="lactate_threshold"` で3フェーズ + 生理学的指標
- [ ] `training_type="vo2max"` で4フェーズ + 生理学的指標

---

### Phase 2: テンプレート調整（フォーム効率表示）
**目標**: efficiency-section-analystの統合出力を表示

**前提条件**: Phase 0-3完了（efficiency-section-analystがパワー・ストライド含む）

**実装内容**:
1. フォーム効率セクションのテンプレート調整
   ```jinja2
   ## フォーム効率
   {% if efficiency %}
     {{ efficiency }}  {# パワー・ストライド統合済みのテキスト #}
   {% endif %}
   ```
2. 独立セクションが存在しないことを確認
   - "## パワー効率分析" セクションは元々存在しない（Phase 0で確認済み）
   - "## ストライド長分析" セクションも元々存在しない（Phase 0で確認済み）
3. スプリット概要テーブルにパワー・ストライド列維持（変更なし）

**データソース**:
- efficiency-section-analystが `analysis_data["efficiency"]` に統合テキストを出力
- パワー: `splits[].power` から取得（エージェント内部）
- ストライド: `splits[].stride_length` から取得（エージェント内部）

**テスト内容**:
- [ ] フォーム効率セクションにGCT/VO/VR + パワー + ストライドが含まれる
- [ ] 統合テキストが正しく表示される
- [ ] スプリット概要テーブルにパワー・ストライド列が存在
- [ ] 行数削減効果の確認（目標: 独立セクション不要のため実質±0行）

---

### Phase 3: セクション再配置
**目標**: "改善ポイント"セクションの下部配置

**前提条件**: Phase 0-4完了（summary-section-analystが改善アドバイス形式で出力）

**実装内容**:
1. セクションタイトル
   - テンプレート: `## 💡 改善ポイント`
   - データソース: `summary.recommendations` (summary-section-analystが生成)
2. セクション位置変更
   ```
   現在: 総合評価 → ... → 技術的詳細
   変更後: 環境要因 → 💡 改善ポイント → 技術的詳細
   ```
3. 表示形式
   ```jinja2
   {% if summary and summary.recommendations %}
   ## 💡 改善ポイント
   {{ summary.recommendations }}
   {% endif %}
   ```

**データソース**:
- summary-section-analyst (Phase 0-4で変更) が `analysis_data["summary"]["recommendations"]` に改善アドバイスを出力
- 内容: 現在のパフォーマンスに基づく次回への具体的改善点（トレーニングプラン形式ではない）

**テスト内容**:
- [ ] セクションタイトルが "💡 改善ポイント" に変更
- [ ] セクションが環境要因の後、技術的詳細の前に配置
- [ ] 内容がアドバイス形式（例: "ウォームアップを1.5km追加すると..."）
- [ ] トレーニングプラン形式ではない（例: "次回: 5km × 3本 @ 4:30/km" などではない）

---

### Phase 4: 生理学的指標の簡潔化（テンポ/インターバルのみ）
**目標**: サマリーとの重複を排除

**実装内容**:
1. パフォーマンスサマリーに生理学的指標を統合
   ```jinja2
   {% if show_physiological %}
   ## 📊 パフォーマンスサマリー
   ### 生理学的指標サマリー
   - VO2 Max: XX ml/kg/min
   - VO2 Max利用率: XX%
   - 閾値ペース: X:XX/km
   - 閾値超過率: XX分
   {% endif %}
   ```
2. 独立セクション簡潔化
   ```jinja2
   {% if show_physiological %}
   ## 生理学的指標との関連
   ### VO2 Max
   - 今回ペースとVO2 Maxペースの比較（1-2行）

   ### 閾値
   - 今回ペースと閾値ペースの比較（1-2行）
   {% endif %}
   ```
3. 詳細な計算式・表は削除

**テスト内容**:
- [ ] テンポ/インターバル: サマリーに生理学的指標が表示
- [ ] リカバリー/ベース: 生理学的指標は参考note程度
- [ ] 独立セクションが簡潔化（目標: 各10-15行程度）
- [ ] 行数削減効果の確認（目標: -40-60行）

---

## テスト計画

### Phase 0: エージェント定義テスト

#### test_split_section_analyst.py
```python
def test_interval_work_segment_only():
    """インターバル走でWork segmentのみ評価"""
    # モックデータ: training_type='vo2max', interval_analysis with Work segments
    result = split_section_analyst.analyze(activity_id=12345)
    assert "split_3" in result["analyses"]  # Work 1
    assert "split_5" in result["analyses"]  # Work 2
    assert "split_1" not in result["analyses"]  # Warmup (除外)
    assert "split_7" not in result["analyses"]  # Cooldown (除外)

def test_base_run_all_splits():
    """ベース走で全スプリット評価"""
    # モックデータ: training_type='low_moderate'
    result = split_section_analyst.analyze(activity_id=12345)
    assert len(result["analyses"]) == 5  # 全5スプリット
```

#### test_phase_section_analyst.py
```python
def test_recovery_one_phase():
    """Recovery runで1フェーズ評価"""
    # モックデータ: training_type='recovery'
    result = phase_section_analyst.analyze(activity_id=12345)
    assert "run_evaluation" in result
    assert "warmup_evaluation" not in result
    assert "cooldown_evaluation" not in result

def test_base_three_phases():
    """Base runで3フェーズ評価"""
    # モックデータ: training_type='low_moderate'
    result = phase_section_analyst.analyze(activity_id=12345)
    assert "warmup_evaluation" in result
    assert "run_evaluation" in result
    assert "cooldown_evaluation" in result
    assert "recovery_evaluation" not in result

def test_interval_four_phases():
    """Interval runで4フェーズ評価"""
    # モックデータ: training_type='vo2max'
    result = phase_section_analyst.analyze(activity_id=12345)
    assert "warmup_evaluation" in result
    assert "work_evaluation" in result
    assert "recovery_evaluation" in result
    assert "cooldown_evaluation" in result
```

#### test_efficiency_section_analyst.py
```python
def test_integrated_form_efficiency():
    """フォーム効率にGCT+VO+VR+パワー+ストライド統合"""
    result = efficiency_section_analyst.analyze(activity_id=12345)
    assert "GCT" in result["efficiency"]
    assert "VO" in result["efficiency"]
    assert "VR" in result["efficiency"]
    assert "パワー効率" in result["efficiency"]
    assert "ストライド長" in result["efficiency"]
    assert "総合:" in result["efficiency"]  # 統合評価

def test_power_data_from_splits():
    """パワーデータがsplitsから取得される"""
    # モックデータ: get_splits_comprehensive() returns power data
    result = efficiency_section_analyst.analyze(activity_id=12345)
    assert "平均パワー" in result["efficiency"]
    assert "類似比" in result["efficiency"]  # compare_similar_workoutsの結果

def test_stride_data_from_splits():
    """ストライドデータがsplitsから取得される"""
    # モックデータ: get_splits_comprehensive() returns stride_length
    result = efficiency_section_analyst.analyze(activity_id=12345)
    assert "平均ストライド" in result["efficiency"]
    assert "ケイデンス×ストライド" in result["efficiency"]
```

#### test_summary_section_analyst.py
```python
def test_recommendations_as_improvement_advice():
    """recommendationsが改善アドバイス形式"""
    result = summary_section_analyst.analyze(activity_id=12345)
    recommendations = result["summary"]["recommendations"]
    # トレーニングプラン形式ではないことを確認
    assert "次回: " not in recommendations  # "次回: 5km × 3本" などはNG
    assert "改善" in recommendations or "推奨" in recommendations
    # 具体的アドバイスが含まれることを確認
    assert len(recommendations) > 50  # ある程度の長さがある
```

---

### Phase 1-4: テンプレート・統合テスト

#### test_template_training_type_detection.py
```python
def test_recovery_run_structure():
    """Recovery runでは1フェーズ、生理学的指標なし"""
    assert phase_count == 1
    assert show_physiological == False

def test_base_run_structure():
    """Base runでは3フェーズ、生理学的指標なし"""
    assert phase_count == 3
    assert show_physiological == False

def test_tempo_run_structure():
    """Tempo runでは3フェーズ、生理学的指標あり"""
    assert phase_count == 3
    assert show_physiological == True

def test_interval_run_structure():
    """Interval runでは4フェーズ、生理学的指標あり"""
    assert phase_count == 4
    assert show_physiological == True
```

#### test_form_efficiency_integration.py
```python
def test_form_efficiency_includes_power():
    """フォーム効率にパワーデータが含まれる"""
    assert "パワー効率" in form_efficiency_section

def test_form_efficiency_includes_stride():
    """フォーム効率にストライドデータが含まれる"""
    assert "ストライド長" in form_efficiency_section

def test_no_independent_power_section():
    """独立パワーセクションが存在しない"""
    assert "## パワー効率分析" not in report

def test_no_independent_stride_section():
    """独立ストライドセクションが存在しない"""
    assert "## ストライド長分析" not in report
```

### Integration Tests

#### test_report_generation_integration.py
```python
def test_recovery_run_report(activity_id_recovery: int):
    """Recovery runの完全なレポート生成テスト"""
    report = generate_report(activity_id_recovery)
    assert 200 <= count_lines(report) <= 250
    assert "生理学的指標サマリー" not in report
    assert count_phases(report) == 1

def test_base_run_report(activity_id_base: int):
    """Base runの完全なレポート生成テスト"""
    report = generate_report(activity_id_base)
    assert 280 <= count_lines(report) <= 320
    assert "生理学的指標サマリー" not in report
    assert count_phases(report) == 3

def test_threshold_run_report(activity_id_threshold: int):
    """Threshold runの完全なレポート生成テスト"""
    report = generate_report(activity_id_threshold)
    assert 400 <= count_lines(report) <= 450
    assert "生理学的指標サマリー" in report
    assert count_phases(report) == 3

def test_interval_run_report(activity_id_interval: int):
    """Interval runの完全なレポート生成テスト"""
    report = generate_report(activity_id_interval)
    assert 400 <= count_lines(report) <= 464
    assert "生理学的指標サマリー" in report
    assert count_phases(report) == 4
```

### Performance Tests

#### test_line_count_targets.py
```python
@pytest.mark.parametrize("training_type,min_lines,max_lines", [
    ("recovery", 200, 250),
    ("low_moderate", 280, 320),
    ("lactate_threshold", 400, 450),
    ("interval_sprint", 400, 464),
])
def test_line_count_within_target(training_type, min_lines, max_lines):
    """各トレーニングタイプの行数が目標範囲内"""
    report = generate_report_by_type(training_type)
    line_count = count_lines(report)
    assert min_lines <= line_count <= max_lines
```

### Manual Testing

#### テストデータ
- **Recovery**: 2025-10-XX (activity_id: TBD)
- **Base Run**: 2025-10-08 (activity_id: 20625808856) ← サンプルあり
- **Threshold**: 2025-10-20 (activity_id: 20744768051)
- **Interval**: 2025-10-15 (架空データ) ← サンプルあり

#### 検証項目
- [ ] 各トレーニングタイプでレポート生成成功
- [ ] 行数が目標範囲内
- [ ] Markdown構文が正しい（GitHub Previewで確認）
- [ ] 既存のv3.0レポートと情報量比較（重要情報の欠落なし）
- [ ] サンプルBALANCEDレポートとの一致度確認

---

## 受け入れ基準

### 機能要件
- [ ] 4種類のトレーニングタイプで異なる構成のレポート生成
- [ ] リカバリー走: 1フェーズ、生理学的指標なし、200-250行
- [ ] ベース走: 3フェーズ、生理学的指標なし、280-320行
- [ ] テンポ/閾値走: 3フェーズ、生理学的指標あり、400-450行
- [ ] インターバル/スプリント: 4フェーズ、生理学的指標あり、400-464行
- [ ] フォーム効率にパワー・ストライド統合
- [ ] "改善ポイント"セクションが下部に配置

### 品質要件
- [ ] 全Unit Tests合格
- [ ] 全Integration Tests合格
- [ ] Performance Tests合格（行数目標達成）
- [ ] Pre-commit hooks合格（Black, Ruff, Mypy）
- [ ] コードカバレッジ80%以上

### ドキュメント要件
- [ ] `docs/report-balance-analysis.md` に実装結果を追記
- [ ] `CHANGELOG.md` に変更内容を記載
- [ ] サンプルレポート更新（4種類すべて）

### 後方互換性
- [ ] `training_type=None` で既存動作維持
- [ ] 既存のエージェント出力形式で動作
- [ ] DuckDBスキーマ変更なし

---

## 技術的課題と依存関係

### 課題1: Phase評価のダイナミック制御
**問題**: phase-section-analystが1/3/4フェーズを動的に返す必要がある

**解決策（Phase 0-2で実装）**:
- **エージェント側で変更**: phase-section-analystがtraining_typeに応じて出力構造を変更
  - Recovery: `{"run_evaluation": "..."}` のみ（warmup/cooldown なし）
  - Base/Tempo/Threshold: `{"warmup_evaluation": "...", "run_evaluation": "...", "cooldown_evaluation": "..."}`
  - Interval/Sprint: `{"warmup_evaluation": "...", "work_evaluation": "...", "recovery_evaluation": "...", "cooldown_evaluation": "..."}`
- **テンプレート側で表示制御**: 存在するキーのみ表示

```jinja2
{% if phase_evaluation.warmup %}
### ウォームアップフェーズ
{{ phase_evaluation.warmup }}
{% endif %}

### メイン走行フェーズ
{{ phase_evaluation.run_evaluation or phase_evaluation.work_evaluation }}

{% if phase_evaluation.recovery_evaluation %}
### リカバリーフェーズ
{{ phase_evaluation.recovery_evaluation }}
{% endif %}

{% if phase_evaluation.cooldown %}
### クールダウンフェーズ
{{ phase_evaluation.cooldown }}
{% endif %}
```

### 課題2: パワー・ストライドデータの取得元
**問題**: efficiency-section-analystがパワー・ストライドデータを統合する必要がある

**解決策（Phase 0-3で実装）**:
- **MCPツール使用**: efficiency-section-analystが以下のツールを呼び出し
  - `get_splits_comprehensive(activity_id, statistics_only=True)` - パワー・ストライド平均値取得
  - `compare_similar_workouts(activity_id)` - 類似ワークアウトとの比較データ取得
- **データ統合**: GCT/VO/VR + パワー + ストライドを1つのテキストに整形
- **テンプレート**: `{{ efficiency }}` で統合テキストを表示するだけ（データ処理なし）

### 課題3: training_type値の網羅性
**問題**: DuckDBに存在する全training_type値が正しくマッピングされるか

**調査必要**:
- [ ] `SELECT DISTINCT training_type FROM hr_efficiency;` で全パターン確認
- [ ] 未対応値があれば `low_moderate` にフォールバック

### 依存関係
- **ブロッカー**: なし（既存データで実装可能）
- **Phase間依存**:
  - Phase 1-4は**Phase 0完了が前提**（エージェント出力形式変更後にテンプレート対応）
  - Phase 2-4は**Phase 1完了が前提**（training_type判定後にセクション制御）
- **推奨事項**: Phase 0を最優先で実装・テスト完了後、Phase 1-4を段階的実装

### 工数見積もり

| Phase | 作業内容 | 見積工数 | 備考 |
|-------|---------|---------|------|
| **Phase 0-1** | split-section-analyst変更 | **2-3時間** | Work segment判定ロジック追加、テスト作成 |
| **Phase 0-2** | phase-section-analyst変更 | **1-2時間** | 1-phase対応追加（既存ロジック流用可） |
| **Phase 0-3** | efficiency-section-analyst変更 | **4-6時間** | パワー・ストライド統合、最も複雑な変更 |
| **Phase 0-4** | summary-section-analyst変更 | **1-2時間** | recommendations形式変更 |
| **Phase 1** | training_type判定・分岐 | **2-3時間** | テンプレート条件分岐、テスト作成 |
| **Phase 2** | フォーム効率表示調整 | **1時間** | テンプレート表示調整のみ |
| **Phase 3** | セクション再配置 | **1時間** | セクション順序変更、簡単 |
| **Phase 4** | 生理学的指標簡潔化 | **2-3時間** | 条件分岐、サマリー統合 |
| **統合テスト** | 4種類×複数活動テスト | **3-4時間** | 実データ検証、v3.0比較 |
| **ドキュメント** | README、CHANGELOG更新 | **1-2時間** | - |
| **合計** | - | **18-27時間** | 実装2-3日、テスト1日 |

**クリティカルパス**: Phase 0-3 (efficiency-section-analyst) が最も時間を要する

---

## マイグレーション計画

### ロールアウト戦略

#### Stage 1: 開発環境テスト（Phase 1-4完了後）
1. Worktreeで実装・テスト
2. 新旧レポート比較（行数、情報量、可読性）
3. 4種類すべてのトレーニングタイプで検証

#### Stage 2: バージョンフラグ導入（オプション）
```python
# report_generator_worker.py
USE_BALANCED_TEMPLATE = os.getenv("USE_BALANCED_TEMPLATE", "false").lower() == "true"

if USE_BALANCED_TEMPLATE:
    template = "detailed_report_balanced.j2"
else:
    template = "detailed_report.j2"
```

**メリット**: 段階的移行、問題時の即時ロールバック

#### Stage 3: 本番環境適用
1. 1週間の並行運用（v3.0とBALANCED両方生成）
2. ユーザーフィードバック収集
3. 問題なければBALANCEDをデフォルトに

#### Stage 4: 旧テンプレート削除
- v3.0テンプレートをアーカイブ
- バージョンフラグ削除
- ドキュメント更新

### リスク管理

| リスク | 影響度 | 対策 |
|--------|--------|------|
| **エージェント定義変更の複雑性** | **高** | Phase 0を最優先で実装・テスト、1エージェントずつ段階的に変更 |
| **efficiency-section-analystの大幅変更** | **高** | 詳細なユニットテスト作成、既存出力との比較検証 |
| 重要情報の欠落 | 高 | v3.0との詳細比較、複数人レビュー、サンプルBALANCEDとの一致確認 |
| training_type未定義 | 中 | フォールバック処理（low_moderateにデフォルト）、DISTINCT値調査 |
| エージェント間データ連携エラー | 中 | Integration testsで全エージェント連携テスト、データ構造検証 |
| テンプレート肥大化 | 低 | 条件分岐を関数化、可読性維持 |
| パフォーマンス低下 | 低 | レンダリング時間計測、ベンチマーク |

---

## 参考資料

- `docs/report-balance-analysis.md` - 詳細な問題分析・改善提案
- `result/individual/2025/10/2025-10-08_20625808856_SAMPLE_BALANCED.md` - ベース走サンプル（324行）
- `result/individual/2025/10/2025-10-15_interval_SAMPLE_BALANCED.md` - インターバルサンプル（464行）
- `tools/reporting/templates/detailed_report.j2` - 現行テンプレート（279行）
- `tools/reporting/report_template_renderer.py` - テンプレートレンダラー
- `tools/reporting/report_generator_worker.py` - レポート生成ワーカー

---

## 補足: 調査結果サマリー

### 現状アーキテクチャ
- **テンプレートエンジン**: Jinja2 (`detailed_report.j2`, 279行)
- **レンダラー**: `ReportTemplateRenderer.render_report()`
- **データソース**: DuckDB (`activities`, `hr_efficiency`, `performance_trends`, `form_efficiency`, `splits`)
- **training_type取得**: `hr_efficiency.training_type`
- **エージェント**: 5つの独立エージェント（split/phase/summary/efficiency/environment）

### training_type値（hr_efficiency.training_typeから取得）
- `"recovery"` - リカバリー走
- `"low_moderate"` - ベース走
- `"tempo_threshold"` - テンポ走
- `"lactate_threshold"` - 閾値走
- `"interval_sprint"` - インターバル/スプリント走

### エージェント間データ受け渡し（受け渡し項目の調査結果）

#### 現在の受け渡し構造（DuckDB section_analyses → ReportGeneratorWorker → Template）

**DuckDB `section_analyses` テーブル構造:**
```sql
CREATE TABLE section_analyses (
    analysis_id INTEGER PRIMARY KEY,
    activity_id INTEGER,
    activity_date DATE,
    section_type VARCHAR,  -- 'split', 'phase', 'summary', 'efficiency', 'environment'
    analysis_data JSON     -- エージェント出力内容
);
```

**ReportGeneratorWorker読み込み処理（`report_generator_worker.py:151-324`）:**
```python
# training_type取得（line 151-159）
training_type = hr_efficiency.get("training_type")

# 各エージェント結果を読み込み
split_analysis = get_section_analysis(activity_id, "split")
phase_evaluation = get_section_analysis(activity_id, "phase")
summary = get_section_analysis(activity_id, "summary")
efficiency = get_section_analysis(activity_id, "efficiency")
environment_analysis = get_section_analysis(activity_id, "environment")

# Templateに渡すデータ構造
template_data = {
    "training_type": training_type,
    "split_analysis": split_analysis["analyses"],  # dict of split evaluations
    "phase_evaluation": phase_evaluation,          # dict of phase evaluations
    "summary": summary,                            # dict with activity_type, summary, recommendations
    "efficiency": efficiency,                      # str (text output)
    "environment_analysis": environment_analysis,  # str (text output)
    ...
}
```

#### Phase 0実装後の変更点

**1. split-section-analyst出力変更:**
```python
# 現在（全スプリット評価）
analysis_data = {
    "analyses": {
        "split_1": "ウォームアップ評価...",
        "split_2": "メイン走行1...",
        "split_3": "メイン走行2...",
        ...
    }
}

# Phase 0実装後（インターバル走の場合、Work segmentのみ）
analysis_data = {
    "analyses": {
        "split_3": "Work 1評価（4:28/km、心拍168bpm）...",
        "split_5": "Work 2評価（4:30/km、心拍170bpm）...",
        # Warmup/Recovery/Cooldownは含まれない
    }
}
```

**2. phase-section-analyst出力変更:**
```python
# 現在（常に3または4フェーズ）
analysis_data = {
    "warmup_evaluation": "...",
    "run_evaluation": "...",
    "cooldown_evaluation": "..."
}

# Phase 0実装後（Recovery run: 1フェーズ）
analysis_data = {
    "run_evaluation": "..."
    # warmup_evaluation, cooldown_evaluation なし
}

# Phase 0実装後（Interval run: 4フェーズ）
analysis_data = {
    "warmup_evaluation": "...",
    "work_evaluation": "...",     # 新規（runではなくwork）
    "recovery_evaluation": "...",  # 新規
    "cooldown_evaluation": "..."
}
```

**3. efficiency-section-analyst出力変更（最大の変更）:**
```python
# 現在（GCT/VO/VRのみ）
analysis_data = {
    "efficiency": """
    【フォーム効率】
    GCT: 253ms (ペース基準266ms → -5% 優秀)
    VO: 7.13cm (ペース基準7.46cm → -4.4% 優秀)
    VR: 8.89% (理想範囲内)

    総合: ★★★★☆ 4.5/5.0
    """
}

# Phase 0実装後（GCT/VO/VR + パワー + ストライド統合）
analysis_data = {
    "efficiency": """
    【フォーム効率（ペース補正評価）】

    **1. 接地時間（GCT）**
    - 実測値: 253ms
    - ペース基準値: 266ms
    - ペース補正スコア: -5% 優秀 ✅
    - 評価: ★★★★★ 5.0/5.0

    **2. 垂直振幅（VO）**
    - 実測値: 7.13cm
    - ペース基準値: 7.46cm
    - ペース補正スコア: -4.4% 優秀 ✅
    - 評価: ★★★★☆ 4.5/5.0

    **3. 垂直比率（VR）**
    - 実測値: 8.89%
    - 理想範囲: 8.0-9.5% ✅
    - 評価: ★★★★★ 5.0/5.0

    **4. パワー効率**  ← 新規統合
    - 平均パワー: 225W (FTPの79%)
    - 類似ワークアウト比: -5W（効率向上）✅
    - パワー一貫性: 変動係数0.021 ✅

    **5. ストライド長**  ← 新規統合
    - 平均ストライド: 1.18m
    - 理想範囲: 1.15-1.25m ✅
    - 類似ワークアウト比: +1cm ✅
    - ケイデンス×ストライドバランス: 最適 ✅

    **総合評価: ★★★★☆ 4.5/5.0**
    6:45/kmという中強度ペースに対して、全指標が基準以上の効率を示しています。
    """
}
```

**4. summary-section-analyst出力変更:**
```python
# 現在（トレーニングプラン形式）
analysis_data = {
    "summary": {
        "activity_type": "ベース走（有酸素ゾーン中心）",
        "summary": "総合所見...",
        "recommendations": """
        次回トレーニングプラン:
        - 距離: 8-10km
        - ペース: 6:30-7:00/km
        - 心拍: 140-155bpm
        ...
        """
    }
}

# Phase 0実装後（改善アドバイス形式）
analysis_data = {
    "summary": {
        "activity_type": "ベース走（有酸素ゾーン中心）",
        "summary": "総合所見...",
        "recommendations": """
        今回のベース走（有酸素ゾーン中心）を次回実施する際の改善点：

        ### 1. ウォームアップの導入 ⭐ 重要度: 高
        **現状**: なし（最初から心拍145bpmでスタート）
        **推奨アクション:**
        - 最初の1-1.5kmをゆっくり開始（7:30-8:00/km）
        **期待効果**: 怪我リスク低減、メイン走行での効率向上

        ### 2. ペース一貫性の維持
        **現状**: 6:21-7:08/kmの変動（47秒/kmの差）
        **推奨アクション:**
        - ペース変動を30秒/km以内に抑える
        ...
        """
    }
}
```

#### テンプレートでの受け渡し処理変更

**現在:**
```jinja2
## フォーム効率
{{ efficiency }}

## 次回トレーニングプラン
{{ summary.recommendations }}
```

**Phase 0実装後:**
```jinja2
## フォーム効率（パワー・ストライド統合済み）
{{ efficiency }}  {# エージェントが統合テキスト生成済み #}

## 💡 改善ポイント
{{ summary.recommendations }}  {# エージェントが改善アドバイス生成済み #}
```

**データフロー全体像:**
```
MCPツール → Agent分析 → DuckDB section_analyses → Worker読み込み → Template表示
            ^^^^^^^^                                   ^^^^^^^^
            Phase 0変更                                変更不要
```

### サンプルBALANCEDレポート分析
- **ベース走** (2025-10-08_20625808856): 324行（v3.0比 496行 → 35%削減）
- **インターバル走** (2025-10-15_interval): 464行（v3.0比 615行 → 25%削減）

### 実装容易性（修正版）
- ⚠️ **エージェント定義の変更が必要**（Phase 0が最重要）
  - split-section-analyst: Work segment評価追加
  - phase-section-analyst: 1-phase対応追加
  - efficiency-section-analyst: パワー・ストライド統合（大幅変更）
  - summary-section-analyst: 改善アドバイス形式へ変更
- ✅ DuckDBスキーマ変更不要（既存データで対応可能）
- ✅ テンプレート変更は比較的単純（条件分岐追加）
- ✅ 後方互換性維持可能（training_type=Noneで既存動作）
- ⚠️ Phase 0完了後にPhase 1-4実装可能（依存関係あり）

---

## 付録A: エージェント別MCPツール変更サマリー

### split-section-analyst（Phase 0-1）

**変更前（現状）**:
```
tools: get_splits_comprehensive, get_splits_pace_hr, get_splits_form_metrics, insert_section_analysis_dict
```

**変更後（Phase 0実装後）**:
```
tools: get_splits_comprehensive, get_splits_pace_hr, get_splits_form_metrics,
       get_hr_efficiency_analysis,    # NEW: training_type取得
       get_interval_analysis,         # NEW: Work/Recovery判定
       insert_section_analysis_dict
```

**追加MCPツール**: 2個（`get_hr_efficiency_analysis`, `get_interval_analysis`）

---

### phase-section-analyst（Phase 0-2）

**変更前（現状）**:
```
tools: get_performance_trends, get_hr_efficiency_analysis, insert_section_analysis_dict
```

**変更後（Phase 0実装後）**:
```
tools: get_performance_trends, get_hr_efficiency_analysis, insert_section_analysis_dict
# 変更なし（既に get_hr_efficiency_analysis を使用中）
```

**追加MCPツール**: 0個（変更なし）

---

### efficiency-section-analyst（Phase 0-3） ⭐ 最大の変更

**変更前（現状）**:
```
tools: get_form_efficiency_summary, get_hr_efficiency_analysis, get_heart_rate_zones_detail,
       get_splits_pace_hr, insert_section_analysis_dict
```

**変更後（Phase 0実装後）**:
```
tools: get_form_efficiency_summary, get_hr_efficiency_analysis, get_heart_rate_zones_detail,
       get_splits_pace_hr,
       get_splits_comprehensive,      # NEW: パワー・ストライド取得
       compare_similar_workouts,      # NEW: 類似ワークアウト比較
       insert_section_analysis_dict
```

**追加MCPツール**: 2個（`get_splits_comprehensive`, `compare_similar_workouts`）

---

### summary-section-analyst（Phase 0-4）

**変更前（現状）**:
```
tools: get_splits_pace_hr, get_splits_form_metrics, get_splits_elevation,
       get_form_efficiency_summary, get_performance_trends, get_vo2_max_data,
       get_lactate_threshold_data, get_weather_data, insert_section_analysis_dict
```

**変更後（Phase 0実装後）**:
```
tools: get_splits_pace_hr, get_splits_form_metrics, get_splits_elevation,
       get_form_efficiency_summary, get_performance_trends, get_vo2_max_data,
       get_lactate_threshold_data, get_weather_data, insert_section_analysis_dict
# 変更なし（既存ツールで改善アドバイス生成可能）
```

**追加MCPツール**: 0個（変更なし）

---

### environment-section-analyst（変更なし）

**変更前・変更後（同一）**:
```
tools: get_weather_data, get_splits_elevation, get_hr_efficiency_analysis,
       insert_section_analysis_dict
# Phase 0での変更なし
```

**追加MCPツール**: 0個（変更なし）

---

### 全エージェントMCPツール変更サマリー

| エージェント | 追加ツール数 | 追加ツール名 | 変更規模 |
|------------|------------|------------|---------|
| split-section-analyst | **2個** | get_hr_efficiency_analysis, get_interval_analysis | 中 |
| phase-section-analyst | 0個 | なし | 小 |
| efficiency-section-analyst | **2個** | get_splits_comprehensive, compare_similar_workouts | **大** |
| summary-section-analyst | 0個 | なし | 小 |
| environment-section-analyst | 0個 | なし | なし |
| **合計** | **4個** | - | - |

**新規使用MCPツール**:
1. `get_hr_efficiency_analysis` - training_type取得（split-section-analystで新規使用）
2. `get_interval_analysis` - Work/Recovery判定（新規使用）
3. `get_splits_comprehensive` - パワー・ストライド取得（efficiency-section-analystで新規使用）
4. `compare_similar_workouts` - 類似ワークアウト比較（新規使用）

**注**: `get_hr_efficiency_analysis`はphase-section-analyst, efficiency-section-analyst, environment-section-analystで既に使用中
