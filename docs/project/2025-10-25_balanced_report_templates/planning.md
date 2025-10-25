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

#### Section Analyses構造（変更なし）

```python
section_analyses = {
    "efficiency": str,           # efficiency-section-analyst output
    "environment_analysis": str,  # environment-section-analyst output
    "phase_evaluation": dict,     # phase-section-analyst output
    "split_analysis": str,        # split-section-analyst output
    "summary": dict               # summary-section-analyst output
}
```

**重要**: エージェントのロジック・出力形式は変更しない（テンプレート側で柔軟に処理）

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

### Phase 1: テンプレート条件分岐実装
**目標**: トレーニングタイプ別のセクション表示制御

**実装内容**:
1. `detailed_report.j2` に条件分岐ロジック追加
   - `training_type` に基づく表示制御変数定義
   - 生理学的指標セクションの条件表示
   - フェーズ評価のカウント制御
2. 後方互換性の確保
   - `training_type` が `None` の場合はデフォルト構成（3フェーズ、全セクション表示）

**テスト内容**:
- [ ] `training_type=None` でレポート生成（既存動作確認）
- [ ] `training_type="recovery"` でリカバリー構成生成
- [ ] `training_type="low_moderate"` でベース走構成生成
- [ ] `training_type="lactate_threshold"` でテンポ構成生成
- [ ] `training_type="interval_sprint"` でインターバル構成生成

---

### Phase 2: セクション統合（フォーム効率）
**目標**: パワー・ストライドをフォーム効率セクションに統合

**実装内容**:
1. フォーム効率セクションの拡張
   ```jinja2
   ### フォーム効率（ペース補正評価）

   **主要指標**:
   1. 接地時間（GCT）
   2. 垂直振幅（VO）
   3. 垂直比率（VR）
   4. パワー効率  ← 新規統合
   5. ストライド長  ← 新規統合
   ```
2. 独立セクション削除
   - "## パワー効率分析" セクション削除
   - "## ストライド長分析" セクション削除
3. スプリット概要テーブルにパワー・ストライド列維持

**データソース**:
- パワー: `basic_metrics.avg_power`, `splits[].power`
- ストライド: `basic_metrics.avg_stride_length`, `splits[].stride_length`

**テスト内容**:
- [ ] フォーム効率セクションにパワー・ストライドが含まれる
- [ ] 独立セクションが削除されている
- [ ] スプリット概要テーブルにパワー・ストライド列が存在
- [ ] 行数削減効果の確認（目標: -30-50行）

---

### Phase 3: セクション再配置
**目標**: "次回トレーニングプラン" → "改善ポイント" へ変更し、下部へ移動

**実装内容**:
1. セクションタイトル変更
   - `## 次回トレーニングプラン` → `## 💡 改善ポイント`
2. セクション位置変更
   ```
   現在: 総合評価 → 次回トレーニングプラン → 技術的詳細
   変更後: 環境要因 → 💡 改善ポイント → 技術的詳細
   ```
3. コンテンツ調整
   - "具体的なトレーニングプラン" → "次回への改善アドバイス" に内容変更
   - 簡潔化（目標: 10-15行程度）

**テスト内容**:
- [ ] セクションタイトルが "💡 改善ポイント" に変更
- [ ] セクションが環境要因の後、技術的詳細の前に配置
- [ ] 内容がアドバイス形式（トレーニングプラン形式ではない）

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

### Unit Tests

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
**問題**: phase-section-analystは現在3-4フェーズを返すが、リカバリー走では1フェーズのみ必要

**解決策**:
- エージェント側は変更せず、テンプレート側で表示制御
- `phase_evaluation.warmup` が存在する場合のみWarmupセクション表示
- `phase_evaluation.cooldown` が存在する場合のみCooldownセクション表示

```jinja2
{% if phase_evaluation.warmup %}
### ウォームアップフェーズ
...
{% endif %}
```

### 課題2: パワー・ストライドデータの取得元
**問題**: 現在独立セクションで使用しているデータをフォーム効率に統合

**解決策**:
- `basic_metrics.avg_power`, `splits[].power` を使用
- `basic_metrics.avg_stride_length`, `splits[].stride_length` を使用
- 既存データ構造で対応可能（新規データ取得不要）

### 課題3: training_type値の網羅性
**問題**: DuckDBに存在する全training_type値が正しくマッピングされるか

**調査必要**:
- [ ] `SELECT DISTINCT training_type FROM hr_efficiency;` で全パターン確認
- [ ] 未対応値があれば `low_moderate` にフォールバック

### 依存関係
- **ブロッカー**: なし（既存データ・エージェントで実装可能）
- **推奨事項**: Phase 1完了後に各フェーズを段階的に実装（リスク分散）

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
| 重要情報の欠落 | 高 | v3.0との詳細比較、複数人レビュー |
| training_type未定義 | 中 | フォールバック処理（low_moderateにデフォルト） |
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

### サンプルBALANCEDレポート分析
- **ベース走** (2025-10-08_20625808856): 324行（v3.0比 496行 → 35%削減）
- **インターバル走** (2025-10-15_interval): 464行（v3.0比 615行 → 25%削減）

### 実装容易性
- ✅ テンプレート条件分岐のみで実装可能
- ✅ DuckDBスキーマ変更不要
- ✅ エージェントロジック変更不要
- ✅ 後方互換性維持可能
- ⚠️ テンプレート可読性維持が課題（関数化・コメントで対応）
