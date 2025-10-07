# Garmin Performance Analysis Report Specification

## 概要

このドキュメントは、Garmin Performance Analysis Systemが生成する個別アクティビティレポートの仕様を定義します。

### レポートの目的

- ランニングアクティビティの詳細なパフォーマンス分析結果を提供
- データに基づいた客観的な評価と具体的な改善提案を提示
- トレーニング効果の可視化とモチベーション向上

### 対象読者

- ランナー本人（主要ユーザー）
- コーチ・トレーナー（パフォーマンス評価）
- データ分析者（トレンド分析）

### 出力形式

- **フォーマット**: Markdown (.md)
- **言語**: 日本語
- **保存先**: `result/individual/{YEAR}/{MONTH}/{YYYY-MM-DD}_activity_{ACTIVITY_ID}.md`

## レポート構造

レポートは以下の7セクションで構成されます：

```markdown
# ランニングパフォーマンス分析レポート

## 基本情報
[アクティビティメタデータ]

## 概要
[パフォーマンスサマリー]

## 1. フォーム効率
[GCT/VO/VR分析]

## 2. 環境条件の影響
[気温・湿度・風速分析]

## 3. フェーズ別評価
[ウォームアップ・メイン・フィニッシュ分析]

## 4. スプリット分析
[1km毎の詳細分析]

## 5. 総合評価と推奨事項
[全体サマリーと次回への提案]
```

## データフロー

```
DuckDB (garmin_performance.duckdb)
  ├─ activities テーブル → 基本情報
  ├─ splits テーブル → スプリット詳細
  ├─ form_efficiency テーブル → フォーム効率
  ├─ hr_efficiency テーブル → 心拍効率
  ├─ performance_trends テーブル → パフォーマンストレンド
  └─ section_analyses テーブル → 5セクション分析
       ├─ section_type='efficiency' → セクション1
       ├─ section_type='environment' → セクション2
       ├─ section_type='phase' → セクション3
       ├─ section_type='split' → セクション4
       └─ section_type='summary' → セクション5

  ↓ [report_generator_worker.py]

result/individual/YYYY/MM/YYYY-MM-DD_activity_ID.md
```
## セクション詳細仕様

### 基本情報セクション

**目的**: アクティビティの基本メタデータを表示

**データソース**: `activities` テーブル

**表示項目**:
```yaml
- アクティビティID: activity_id
- 実施日: date
- 活動名: activity_name
- 場所: location_name
- 総距離: total_distance_km
- 総時間: total_time_seconds (HH:MM:SS形式)
- 平均ペース: avg_pace_seconds_per_km (MM:SS/km形式)
- 平均心拍数: avg_heart_rate
- 平均ケイデンス: avg_cadence
- 体重: weight_kg (7日間中央値)
```

**レイアウト例**:
```markdown
## 基本情報

| 項目 | 値 |
|------|-----|
| アクティビティID | 19914912442 |
| 実施日 | 2025-09-22 |
| 総距離 | 17.0 km |
| 総時間 | 1:25:30 |
| 平均ペース | 5:02/km |
| 平均心拍数 | 152 bpm |
| 平均ケイデンス | 172 spm |
| 体重 | 76.9 kg |
```

### 概要セクション

**目的**: パフォーマンス全体の簡潔なサマリー

**データソース**:
- `activities` テーブル
- `hr_efficiency` テーブル
- `performance_trends` テーブル

**表示項目**:
```yaml
- トレーニングタイプ: hr_efficiency.training_type
  (例: aerobic_base, tempo_run, threshold_work, mixed_effort)
- パフォーマンス概要: 2-3文の簡潔な説明
- 主要メトリクス:
  - ペース一貫性: performance_trends.pace_consistency
  - 心拍ドリフト: performance_trends.hr_drift_percentage
  - 疲労パターン: performance_trends.fatigue_pattern
```

**レイアウト例**:
```markdown
## 概要

**トレーニングタイプ**: ベースラン (aerobic_base)

本日のランニングは17.0kmのベースランとして実施されました。平均ペース5:02/kmで安定したペース配分を維持し、心拍ドリフト3.2%と優秀な疲労管理を実現しました。

**主要指標**:
- ペース一貫性: 4.2% (優秀)
- 心拍ドリフト: 3.2% (理想的)
- 疲労パターン: 適切な疲労管理
```

### セクション1: フォーム効率

**目的**: ランニングフォームの効率性評価

**データソース**:
- `section_analyses` (section_type='efficiency')
- `form_efficiency` テーブル

**表示内容**:
```yaml
- 接地時間(GCT)の統計と評価:
  - 平均値: form_efficiency.gct_average
  - 標準偏差: form_efficiency.gct_std
  - ★レーティング: form_efficiency.gct_rating
- 垂直振動(VO)の統計と評価:
  - 平均値: form_efficiency.vo_average
  - 標準偏差: form_efficiency.vo_std
  - ★レーティング: form_efficiency.vo_rating
- 垂直比率(VR)の統計と評価:
  - 平均値: form_efficiency.vr_average
  - 標準偏差: form_efficiency.vr_std
  - ★レーティング: form_efficiency.vr_rating
- エージェント分析: section_analyses.analysis_data['efficiency']
```

**レイアウト例**:
```markdown
## 1. フォーム効率

### 接地時間 (GCT)
- 平均: 245ms
- 標準偏差: 12ms
- 評価: ★★★★★ (優秀)

優秀な接地時間を維持しており、効率的な地面反力の利用ができています。

### 垂直振動 (VO)
- 平均: 8.2cm
- 標準偏差: 0.8cm
- 評価: ★★★★☆ (良好)

垂直振動は良好な範囲内です。さらなる改善には体幹の安定性強化が有効です。

[エージェント分析テキスト]
```

### セクション2: 環境条件の影響

**目的**: 気象条件がパフォーマンスに与えた影響を評価

**データソース**:
- `section_analyses` (section_type='environment')
- `activities` テーブル (external_temp_c, humidity, wind_speed_ms)

**表示内容**:
```yaml
- 気温データ:
  - 外気温: activities.external_temp_c
  - 湿度: activities.humidity
  - 風速: activities.wind_speed_ms
- 環境影響評価:
  - 暑熱/寒冷の影響
  - 湿度の影響
  - 風の影響
- エージェント分析: section_analyses.analysis_data['environmental']
```

**レイアウト例**:
```markdown
## 2. 環境条件の影響

### 気象データ
- 外気温: 22.5°C
- 湿度: 65%
- 風速: 2.1 m/s

### 環境影響評価

**気温**: 22.5°Cは理想的なランニング条件です。体温調節への負担が少なく、最大パフォーマンスを発揮しやすい温度帯です。

**湿度**: 65%は適度な湿度レベルです。発汗による体温調節が効率的に機能しています。

[エージェント分析テキスト]
```

### セクション3: フェーズ別評価

**目的**: ウォームアップ・メイン・フィニッシュの3フェーズ戦略評価

**データソース**:
- `section_analyses` (section_type='phase')
- `performance_trends` テーブル

**表示内容**:
```yaml
- ウォームアップフェーズ:
  - スプリット範囲: performance_trends.warmup_phase.splits
  - 平均ペース: performance_trends.warmup_avg_pace_seconds_per_km
  - 平均心拍: performance_trends.warmup_avg_hr
  - 評価: section_analyses.analysis_data['warmup_evaluation']

- メインフェーズ:
  - スプリット範囲: performance_trends.main_phase.splits
  - 平均ペース: performance_trends.main_avg_pace_seconds_per_km
  - 平均心拍: performance_trends.main_avg_hr
  - ペース安定性: performance_trends.pace_consistency
  - 評価: section_analyses.analysis_data['main_evaluation']

- フィニッシュフェーズ:
  - スプリット範囲: performance_trends.finish_phase.splits
  - 平均ペース: performance_trends.finish_avg_pace_seconds_per_km
  - 平均心拍: performance_trends.finish_avg_hr
  - 疲労評価: performance_trends.fatigue_pattern
  - 評価: section_analyses.analysis_data['finish_evaluation']
```

**レイアウト例**:
```markdown
## 3. フェーズ別評価

### ウォームアップフェーズ (1-3km)
- 平均ペース: 5:15/km
- 平均心拍: 145 bpm

段階的なペース上昇で適切にウォームアップできています。心拍数の立ち上がりも理想的です。

### メインフェーズ (4-14km)
- 平均ペース: 4:58/km
- 平均心拍: 153 bpm
- ペース一貫性: 4.2% (優秀)

メインフェーズでのペース安定性は優秀です。エネルギー管理が適切に行われています。

### フィニッシュフェーズ (15-17km)
- 平均ペース: 4:52/km
- 平均心拍: 158 bpm
- 疲労パターン: 適切な疲労管理

ラスト3kmでペースアップに成功。疲労管理が適切で、余力を残したフィニッシュです。
```

### セクション4: スプリット分析

**目的**: 各1kmスプリットの詳細分析

**データソース**:
- `section_analyses` (section_type='split')
- `splits` テーブル

**表示内容**:
```yaml
- 各スプリット(1-N km):
  - ペース: splits.pace_seconds_per_km
  - 心拍数: splits.heart_rate
  - ケイデンス: splits.cadence
  - 歩幅: splits.stride_length
  - 接地時間(GCT): splits.ground_contact_time
  - 垂直振動(VO): splits.vertical_oscillation
  - 垂直比率(VR): splits.vertical_ratio
  - 標高変化: splits.elevation_gain / splits.elevation_loss
  - 地形タイプ: splits.terrain_type
  - エージェント分析: section_analyses.analysis_data['analyses']['split_N']
```

**レイアウト例**:
```markdown
## 4. スプリット分析

### 1km目
- ペース: 5:20/km
- 心拍数: 138 bpm
- ケイデンス: 170 spm
- 歩幅: 78.5 cm
- 接地時間: 245 ms
- 垂直振動: 8.2 cm
- 垂直比率: 10.5%
- 標高: +5m / -2m (平坦)

ウォームアップとして適切なペース設定。心拍数の上昇も緩やかで理想的です。接地時間とフォーム効率も安定しています。

### 2km目
- ペース: 5:10/km
- 心拍数: 145 bpm
- ケイデンス: 172 spm
- 歩幅: 80.1 cm
- 接地時間: 243 ms
- 垂直振動: 8.0 cm
- 垂直比率: 10.2%
- 標高: +3m / -4m (平坦)

段階的なペースアップを継続。身体が温まり、ケイデンスも安定してきました。歩幅が伸び、フォーム効率も向上しています。

[... 各スプリットの詳細分析 ...]

### 17km目
- ペース: 4:48/km
- 心拍数: 160 bpm
- ケイデンス: 176 spm
- 歩幅: 84.2 cm
- 接地時間: 248 ms
- 垂直振動: 8.5 cm
- 垂直比率: 10.8%
- 標高: +2m / -1m (平坦)

最終スプリットで最速ペース。疲労により接地時間がわずかに増加していますが、余力を残した効率的なフィニッシュです。
```

### セクション5: 総合評価と推奨事項

**目的**: 全体のパフォーマンス評価と次回トレーニングへの提案

**データソース**:
- `section_analyses` (section_type='summary')
- 全セクションの分析結果

**表示内容**:
```yaml
- トレーニングタイプ: section_analyses.analysis_data['activity_type']
- 総合評価: section_analyses.analysis_data['summary']
- 推奨事項: section_analyses.analysis_data['recommendations']
```

**レイアウト例**:
```markdown
## 5. 総合評価と推奨事項

### トレーニングタイプ
ベースラン (aerobic_base)

### 総合評価

本日のランニングは非常に優秀な内容でした。主な強みは以下の通りです：

**強み**:
- ペース一貫性4.2%と優秀な安定性
- 心拍ドリフト3.2%と理想的な疲労管理
- 接地時間245msと効率的なフォーム
- 段階的なペース配分戦略の成功

**改善ポイント**:
- 垂直振動をさらに改善する余地あり
- 体幹の安定性強化が効果的

### 次回への推奨事項

1. **トレーニング強度**: 今回と同レベルのペースで距離を1-2km延長を推奨
2. **回復時間**: 24-48時間の適切な回復を取ること
3. **強化ポイント**: 体幹トレーニングの追加で垂直振動の改善を目指す
4. **ペース設定**: 次回も5:00-5:10/kmの範囲で安定走を継続

**長期目標に向けて**: 現在のペースでの距離延長を優先し、有酸素ベースの構築を継続してください。
```

## レポート生成プロセス

### ワーカーベース実装

**実装ファイル**: `tools/reporting/report_generator_worker.py`

### 処理フロー

```
1. データ収集
   ├─ DuckDBから各テーブルデータを取得
   │  ├─ activities (基本情報)
   │  ├─ splits (スプリット詳細)
   │  ├─ form_efficiency (フォーム統計)
   │  ├─ hr_efficiency (心拍効率)
   │  ├─ performance_trends (フェーズ分析)
   │  └─ section_analyses (5セクション分析)
   ↓
2. データ変換・フォーマット
   ├─ 数値のフォーマット変換
   │  ├─ 秒 → MM:SS 形式 (ペース、時間)
   │  ├─ 距離の丸め (km)
   │  └─ パーセンテージ表示
   ├─ Markdownテキストの組み立て
   │  ├─ 基本情報テーブル
   │  ├─ 概要セクション
   │  └─ 5つの分析セクション
   ↓
3. レポート生成
   ├─ Jinja2テンプレートレンダリング
   │  (tools/reporting/templates/detailed_report.j2)
   ├─ セクションの統合
   └─ 最終Markdown出力
   ↓
4. ファイル保存
   ├─ ディレクトリ構造の作成
   │  result/individual/{YEAR}/{MONTH}/
   ├─ ファイル名生成
   │  {YYYY-MM-DD}_activity_{ACTIVITY_ID}.md
   └─ ファイル書き込み
```

### 主要メソッド

```python
class ReportGeneratorWorker:
    def __init__(self, db_path: str = None):
        """DuckDB接続とテンプレート環境の初期化"""

    def generate_report(self, activity_id: int, date: str) -> str:
        """レポート生成のメインエントリーポイント"""

    def _fetch_data(self, activity_id: int) -> dict:
        """DuckDBから全データを取得"""

    def _format_basic_info(self, data: dict) -> dict:
        """基本情報セクションのフォーマット"""

    def _format_overview(self, data: dict) -> str:
        """概要セクションのフォーマット"""

    def _format_splits(self, splits_data: list) -> list:
        """スプリット分析のフォーマット"""

    def _render_template(self, context: dict) -> str:
        """Jinja2テンプレートのレンダリング"""

    def _save_report(self, content: str, activity_id: int, date: str) -> str:
        """レポートファイルの保存"""
```

### データ取得例

```python
def _fetch_data(self, activity_id: int) -> dict:
    """DuckDBから全必要データを取得"""

    # 基本情報
    basic_info = self.conn.execute("""
        SELECT activity_id, date, activity_name,
               total_distance_km, total_time_seconds,
               avg_pace_seconds_per_km, avg_heart_rate,
               avg_cadence, weight_kg
        FROM activities
        WHERE activity_id = ?
    """, [activity_id]).fetchone()

    # スプリット詳細
    splits = self.conn.execute("""
        SELECT split_index, pace_seconds_per_km, heart_rate,
               cadence, stride_length, ground_contact_time,
               vertical_oscillation, vertical_ratio,
               elevation_gain, elevation_loss, terrain_type
        FROM splits
        WHERE activity_id = ?
        ORDER BY split_index
    """, [activity_id]).fetchall()

    # フォーム効率
    form_efficiency = self.conn.execute("""
        SELECT gct_average, gct_std, gct_rating,
               vo_average, vo_std, vo_rating,
               vr_average, vr_std, vr_rating
        FROM form_efficiency
        WHERE activity_id = ?
    """, [activity_id]).fetchone()

    # セクション分析 (5タイプ)
    section_analyses = {}
    for section_type in ['efficiency', 'environment', 'phase', 'split', 'summary']:
        result = self.conn.execute("""
            SELECT analysis_data
            FROM section_analyses
            WHERE activity_id = ? AND section_type = ?
        """, [activity_id, section_type]).fetchone()

        if result:
            section_analyses[section_type] = json.loads(result[0])

    return {
        'basic_info': basic_info,
        'splits': splits,
        'form_efficiency': form_efficiency,
        'section_analyses': section_analyses
    }
```

### テンプレートレンダリング例

```python
def _render_template(self, context: dict) -> str:
    """Jinja2テンプレートでMarkdownレポートを生成"""

    template = self.jinja_env.get_template('detailed_report.j2')

    return template.render(
        activity_id=context['activity_id'],
        date=context['date'],
        activity_name=context['activity_name'],
        total_distance_km=context['total_distance_km'],
        total_time=context['total_time_formatted'],
        avg_pace=context['avg_pace_formatted'],
        avg_heart_rate=context['avg_heart_rate'],
        weight_kg=context['weight_kg'],

        # セクションコンテンツ
        efficiency_section=context['efficiency_section'],
        environment_section=context['environment_section'],
        phase_section=context['phase_section'],
        split_section=context['split_section'],
        summary_section=context['summary_section']
    )
```

### 実行方法

```bash
# コマンドライン実行
uv run python tools/reporting/report_generator_worker.py \
    --activity-id 19914912442 \
    --date 2025-09-22

# Pythonスクリプトから
from tools.reporting.report_generator_worker import ReportGeneratorWorker

worker = ReportGeneratorWorker()
report_path = worker.generate_report(
    activity_id=19914912442,
    date="2025-09-22"
)
print(f"Report generated: {report_path}")
```

### エラーハンドリング

```python
def generate_report(self, activity_id: int, date: str) -> str:
    try:
        # データ取得
        data = self._fetch_data(activity_id)

        if not data['basic_info']:
            raise ValueError(f"Activity {activity_id} not found in database")

        # section_analysesデータの確認
        missing_sections = []
        for section_type in ['efficiency', 'environment', 'phase', 'split', 'summary']:
            if section_type not in data['section_analyses']:
                missing_sections.append(section_type)

        if missing_sections:
            logger.warning(
                f"Missing section analyses for activity {activity_id}: "
                f"{', '.join(missing_sections)}"
            )
            # 欠損セクションには警告メッセージを挿入
            for section in missing_sections:
                data['section_analyses'][section] = {
                    'warning': '⚠️ このセクションの分析データが利用できません。'
                }

        # レポート生成
        context = self._prepare_context(data)
        content = self._render_template(context)
        report_path = self._save_report(content, activity_id, date)

        return report_path

    except Exception as e:
        logger.error(f"Failed to generate report for activity {activity_id}: {e}")
        raise
```

## データソースマッピング

### DuckDBテーブル → レポートセクション

| レポートセクション | 主要データソース | 補助データソース |
|------------------|-----------------|----------------|
| 基本情報 | activities | - |
| 概要 | activities, hr_efficiency | performance_trends |
| 1. フォーム効率 | section_analyses (efficiency) | form_efficiency |
| 2. 環境条件 | section_analyses (environment) | activities (temp/humidity) |
| 3. フェーズ別評価 | section_analyses (phase) | performance_trends |
| 4. スプリット分析 | section_analyses (split) | splits |
| 5. 総合評価 | section_analyses (summary) | 全テーブル |

### performance.json → DuckDB → レポート

```
performance.json
  ├─ basic_metrics → activities → 基本情報
  ├─ form_efficiency_summary → form_efficiency → フォーム効率
  ├─ hr_efficiency_analysis → hr_efficiency → 概要
  ├─ performance_trends → performance_trends → フェーズ別評価
  └─ split_metrics[] → splits → スプリット分析

section_analyses (エージェント分析結果)
  ├─ efficiency → フォーム効率 (詳細分析テキスト)
  ├─ environment → 環境条件 (詳細分析テキスト)
  ├─ phase → フェーズ別評価 (詳細分析テキスト)
  ├─ split → スプリット分析 (詳細分析テキスト)
  └─ summary → 総合評価 (詳細分析テキスト)
```

## テンプレートシステム

### Jinja2テンプレート

**場所**: `tools/reporting/templates/detailed_report.j2`

**主要変数**:
```jinja2
{{ activity_id }}
{{ date }}
{{ activity_name }}
{{ total_distance_km }}
{{ total_time }}
{{ avg_pace }}
{{ avg_heart_rate }}
{{ weight_kg }}

{{ efficiency_section }}
{{ environment_section }}
{{ phase_section }}
{{ split_section }}
{{ summary_section }}
```

### テンプレート構造

```jinja2
# ランニングパフォーマンス分析レポート

## 基本情報

| 項目 | 値 |
|------|-----|
| アクティビティID | {{ activity_id }} |
| 実施日 | {{ date }} |
| 総距離 | {{ total_distance_km }} km |
| 総時間 | {{ total_time }} |
| 平均ペース | {{ avg_pace }}/km |
| 平均心拍数 | {{ avg_heart_rate }} bpm |
| 体重 | {{ weight_kg }} kg |

## 概要

{{ overview_text }}

## 1. フォーム効率

{{ efficiency_section }}

## 2. 環境条件の影響

{{ environment_section }}

## 3. フェーズ別評価

{{ phase_section }}

## 4. スプリット分析

{{ split_section }}

## 5. 総合評価と推奨事項

{{ summary_section }}
```

## エラーハンドリング

### データ不足時の対応

1. **section_analysesデータなし**:
   ```markdown
   ## 1. フォーム効率

   ⚠️ このセクションの分析データが利用できません。
   ```

2. **form_efficiencyデータなし**:
   - 統計値の表示を省略
   - エージェント分析テキストのみ表示

3. **環境データなし**:
   ```markdown
   ## 2. 環境条件の影響

   気象データが記録されていません。
   ```

### バージョン不一致時の警告

```markdown
⚠️ 注意: このレポートは古いバージョンの分析エージェントで生成されています。
- 分析バージョン: v1.0.0
- 推奨バージョン: v1.2.0
```

## 品質保証

### レポート検証項目

1. **データ整合性**:
   - [ ] すべてのセクションにデータが存在
   - [ ] 数値の単位が正しい（km, bpm, spm等）
   - [ ] 日付フォーマットが統一（YYYY-MM-DD）

2. **フォーマット**:
   - [ ] Markdownシンタックスが正しい
   - [ ] テーブルのアライメントが正しい
   - [ ] 見出しレベルが適切

3. **内容**:
   - [ ] 日本語テキストが文法的に正しい
   - [ ] 数値が合理的な範囲内
   - [ ] エージェント分析が適切に挿入されている

## 今後の拡張

### Phase 1: データビジュアライゼーション
- Mermaidグラフの追加（心拍・ペース推移）
- 標高プロファイルの可視化

### Phase 2: 比較分析
- 過去の同様のアクティビティとの比較
- 目標達成度の可視化

### Phase 3: インタラクティブレポート
- HTML形式での出力
- インタラクティブグラフ（Plotly等）

## 関連ドキュメント

- [DuckDB Schema Mapping](./duckdb_schema_mapping.md) - データベーススキーマ詳細
- [CLAUDE.md](../../CLAUDE.md) - システム全体のアーキテクチャ
- [WORKFLOW.md](../../WORKFLOW.md) - データ処理ワークフロー
