# 計画: Report Generation Update

**Project Date**: 2025-10-07
**Status**: Planning Phase (TDD準備中)
**Priority**: High

---

## 要件定義

### 目的

DuckDBに保存されたセクション分析データから、効率的かつ高品質な日本語レポートを生成する。Worker-basedアーキテクチャにより、MCP server依存を排除し、保守性と拡張性を向上させる。

### 背景

- **以前の実装**: プレースホルダーベースのレポート生成、MCP server依存
- **問題点**:
  - MCPサーバー経由のデータ取得は非効率
  - プレースホルダー方式は柔軟性に欠ける
  - エラーハンドリングが不十分
- **改善策**:
  - Worker-basedアーキテクチャ
  - DuckDBから直接データ取得
  - Jinja2テンプレートによる柔軟なレンダリング

### ユースケース

#### UC1: 完全なレポート生成
**前提条件**: DuckDBにactivity_idに対応する5つのセクション分析が保存されている

**フロー**:
1. ユーザーが `uv run python -m tools.reporting.report_generator_worker <activity_id>` を実行
2. ReportGeneratorWorkerがDuckDBからperformance dataを取得
3. ReportGeneratorWorkerがDuckDBから5つのsection analysesを取得
4. 各セクションをマークダウン形式にフォーマット
5. Jinja2テンプレートでレポートをレンダリング
6. `result/individual/{YEAR}/{MONTH}/{YYYY-MM-DD}_activity_{ACTIVITY_ID}.md` に保存

**成功条件**: レポートが7セクション構造（概要 + 5分析 + 総合評価）で生成される

#### UC2: セクション分析が一部欠落している場合のレポート生成
**前提条件**: DuckDBに一部のセクション分析のみ保存されている（例: efficiency, environmentのみ）

**フロー**:
1. ReportGeneratorWorkerがDuckDBから利用可能なsection analysesを取得
2. 欠落しているセクションに対して「データがありません」メッセージを挿入
3. 利用可能なセクションのみでレポートを生成

**成功条件**: エラーで停止せず、利用可能なデータで部分的なレポートが生成される

#### UC3: activity_idが存在しない場合のエラーハンドリング
**前提条件**: DuckDBに存在しないactivity_idを指定

**フロー**:
1. ReportGeneratorWorkerがDuckDBからperformance dataを取得
2. データが見つからない場合、ValueErrorをraiseして終了

**成功条件**: 明確なエラーメッセージが表示され、プログラムが正常終了する

### 解決する問題

1. **非効率なデータ取得**: MCP server経由 → DuckDB直接アクセス
2. **柔軟性の欠如**: プレースホルダー方式 → Jinja2テンプレート
3. **エラーハンドリング不足**: 部分的データ対応、明確なエラーメッセージ
4. **保守性の低さ**: MCP server依存 → Python Worker単独動作

---

## 設計

### アーキテクチャ設計

#### データフロー

```
[DuckDB: garmin_performance.duckdb]
    ├── activities table (basic metadata)
    ├── performance_data table (basic_metrics, hr_zones, etc.)
    └── section_analyses table (5 section types)
          ↓
[ReportGeneratorWorker]
    ├── load_performance_data(activity_id) → basic_metrics
    ├── load_section_analyses(activity_id) → 5 sections dict
    ├── _format_overview(performance_data) → markdown
    ├── _format_section_analysis(section_data, section_name) → markdown
    └── generate_report(activity_id, date) → report_content
          ↓
[ReportTemplateRenderer]
    ├── load_template("detailed_report.j2")
    ├── render_report(activity_id, date, overview, 5 sections) → markdown
    └── save_report(activity_id, date, report_content) → file path
          ↓
[result/individual/{YEAR}/{MONTH}/{YYYY-MM-DD}_activity_{ACTIVITY_ID}.md]
```

#### コンポーネント設計

**1. ReportGeneratorWorker** (`tools/reporting/report_generator_worker.py`)
- **責務**: DuckDBからデータを取得し、レポート生成を調整
- **主要メソッド**:
  - `load_performance_data(activity_id: int) -> dict[str, Any] | None`
  - `load_section_analyses(activity_id: int) -> dict[str, dict[str, Any]] | None`
  - `_format_overview(performance_data: dict[str, Any]) -> str`
  - `_format_section_analysis(section_data: dict[str, Any], section_name: str) -> str`
  - `generate_report(activity_id: int, date: str | None = None) -> dict[str, Any]`

**2. ReportTemplateRenderer** (`tools/reporting/report_template_renderer.py`)
- **責務**: Jinja2テンプレートベースのレンダリングとファイル保存
- **主要メソッド**:
  - `load_template(template_name: str = "detailed_report.j2")`
  - `render_report(activity_id: str, date: str, overview: str, efficiency_analysis: str, ...) -> str`
  - `save_report(activity_id: str, date: str, report_content: str) -> dict[str, Any]`
  - `validate_report(report_content: str) -> dict[str, Any]`
  - `get_final_report_path(activity_id: str, date: str) -> Path`

**3. GarminDBReader** (`tools/database/db_reader.py`)
- **責務**: DuckDBからデータを読み取る（既存実装）
- **主要メソッド**:
  - `get_performance_section(activity_id: int, section: str) -> dict[str, Any] | None`
  - `get_section_analysis(activity_id: int, section_type: str) -> dict[str, Any] | None`
  - `get_activity_date(activity_id: int) -> str | None`

### データモデル設計

#### Section Analyses Structure

DuckDBから取得されるセクション分析のJSON構造:

```python
# Efficiency Section
{
  "metadata": {
    "activity_id": "20464005432",
    "date": "2025-09-22",
    "analyst": "efficiency-section-analyst",
    "version": "1.0"
  },
  "efficiency": {
    "form_efficiency": "GCT平均: 262ms (★★★☆☆), VO平均: 7.2cm (★★★★★)",
    "hr_efficiency": "Zone 1優位 (63.5%), aerobic_base型",
    "evaluation": "優秀な接地時間、効率的な地面反力利用"
  }
}

# Environment Section
{
  "metadata": {...},
  "environment_analysis": {
    "weather_conditions": "気温18.0°C、快適な条件",
    "terrain_impact": "平坦コース (標高変化+2m/-2m)",
    "evaluation": "理想的な環境条件"
  }
}

# Phase Section
{
  "metadata": {...},
  "phase_evaluation": {
    "warmup": {"splits": [1], "avg_pace": "6'15\"", "evaluation": "適切なウォームアップ"},
    "main": {"splits": [2, 3, 4], "pace_stability": "高い安定性", "evaluation": "一貫したペース維持"},
    "finish": {"splits": [5], "fatigue_level": "軽度", "evaluation": "適切なペース配分"},
    "overall": "優れたペース配分"
  }
}

# Split Section
{
  "metadata": {...},
  "split_analysis": {
    "splits": [
      {"km": 1, "pace": "6'15\"", "hr": 152, "cadence": 168, "stride": 102, "gct": 262, "vo": 7.2, "vr": 7.1},
      ...
    ],
    "patterns": {
      "pace_trend": "安定",
      "hr_trend": "漸増",
      "form_consistency": "高い"
    }
  }
}

# Summary Section
{
  "metadata": {...},
  "summary": {
    "activity_type": {"classification": "Easy Run", "confidence": "high"},
    "overall_rating": {"score": 4.5, "stars": "★★★★☆"},
    "key_strengths": ["フォーム効率", "ペース安定性"],
    "improvement_areas": ["心拍ドリフト管理"],
    "recommendations": "理想的なEasy Runテンポを維持"
  }
}
```

#### Report Template Variables

Jinja2テンプレートに渡される変数:

```python
{
  "activity_id": str,
  "date": str,  # YYYY-MM-DD
  "overview": str,  # キーメトリクス表 + トレーニング概要
  "efficiency_analysis": str,  # Efficiency section formatted
  "environment_analysis": str,  # Environment section formatted
  "phase_analysis": str,  # Phase section formatted
  "split_analysis": str,  # Split section formatted
  "summary_analysis": str,  # Summary section formatted
}
```

### API/インターフェース設計

#### ReportGeneratorWorker.generate_report()

```python
def generate_report(
    self, activity_id: int, date: str | None = None
) -> dict[str, Any]:
    """
    Generate final report from performance.json and section analyses.

    Args:
        activity_id: Activity ID
        date: Activity date (YYYY-MM-DD format), auto-resolved if None

    Returns:
        {
            "success": True,
            "activity_id": int,
            "date": str,
            "report_path": str,
            "timestamp": str (ISO format)
        }

    Raises:
        ValueError: If activity_id not found or no section analyses exist
    """
```

#### ReportTemplateRenderer.render_report()

```python
def render_report(
    self,
    activity_id: str,
    date: str,
    overview: str,
    efficiency_analysis: str,
    environment_analysis: str,
    phase_analysis: str,
    split_analysis: str,
    summary_analysis: str,
) -> str:
    """
    Render report using Jinja2 template.

    Args:
        activity_id: Activity ID
        date: Date
        overview: Overview section (key metrics + training summary)
        efficiency_analysis: Efficiency section analysis (from DuckDB)
        environment_analysis: Environment section analysis (from DuckDB)
        phase_analysis: Phase section analysis (from DuckDB)
        split_analysis: Split section analysis (from DuckDB)
        summary_analysis: Summary section analysis (from DuckDB)

    Returns:
        Rendered report content (markdown)
    """
```

---

## テスト計画

### Unit Tests

#### `tests/reporting/test_report_generator_worker.py`

**テストケース1: load_performance_data() - 正常系**
```python
def test_load_performance_data_success():
    """DuckDBからperformance dataを正しく読み取れることを確認"""
    worker = ReportGeneratorWorker(":memory:")
    # Setup: Insert test activity
    data = worker.load_performance_data(12345)

    assert data is not None
    assert "basic_metrics" in data
    assert data["basic_metrics"]["distance_km"] > 0
```

**テストケース2: load_section_analyses() - 5セクション取得**
```python
def test_load_section_analyses_all_sections():
    """5つのセクション分析を正しく取得できることを確認"""
    worker = ReportGeneratorWorker(":memory:")
    # Setup: Insert 5 section analyses
    analyses = worker.load_section_analyses(12345)

    assert analyses is not None
    assert "efficiency" in analyses
    assert "environment_analysis" in analyses
    assert "phase_evaluation" in analyses
    assert "split_analysis" in analyses
    assert "summary" in analyses
```

**テストケース3: _format_overview() - マークダウン生成**
```python
def test_format_overview():
    """Performance dataから概要セクションを生成できることを確認"""
    worker = ReportGeneratorWorker(":memory:")
    performance_data = {
        "basic_metrics": {
            "distance_km": 5.0,
            "duration_seconds": 1800,
            "avg_pace_seconds_per_km": 360,
            "avg_heart_rate": 155,
        }
    }

    overview = worker._format_overview(performance_data)

    assert "5.00 km" in overview
    assert "30分0秒" in overview
    assert "6'00\"" in overview
    assert "155 bpm" in overview
```

**テストケース4: _format_section_analysis() - セクションフォーマット**
```python
def test_format_section_analysis_with_data():
    """セクション分析をマークダウンにフォーマットできることを確認"""
    worker = ReportGeneratorWorker(":memory:")
    section_data = {
        "form_efficiency": "GCT: 262ms",
        "hr_efficiency": "Zone 1優位"
    }

    result = worker._format_section_analysis(section_data, "efficiency")

    assert "GCT: 262ms" in result
    assert "Zone 1優位" in result
```

**テストケース5: _format_section_analysis() - 空データ**
```python
def test_format_section_analysis_empty():
    """空のセクションデータに対してメッセージを返すことを確認"""
    worker = ReportGeneratorWorker(":memory:")

    result = worker._format_section_analysis({}, "efficiency")

    assert "データがありません" in result
```

### Integration Tests

#### `tests/reporting/test_report_generation_integration.py`

**テストケース1: generate_report() - 完全なレポート生成**
```python
@pytest.mark.integration
def test_generate_report_full_workflow(tmp_path):
    """DuckDBからレポート生成までの完全なフローを確認"""
    # Setup: Create test database with activity + 5 section analyses
    db_path = tmp_path / "test.duckdb"
    worker = ReportGeneratorWorker(str(db_path))

    # Insert test data...

    result = worker.generate_report(12345, "2025-09-22")

    assert result["success"] is True
    assert result["activity_id"] == 12345
    assert Path(result["report_path"]).exists()

    # Verify report content
    report_content = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "# アクティビティ詳細分析レポート" in report_content
    assert "## 🎯 効率分析" in report_content
    assert "## ✅ 総合評価" in report_content
```

**テストケース2: generate_report() - 部分的なセクション分析**
```python
@pytest.mark.integration
def test_generate_report_partial_sections(tmp_path):
    """一部のセクション分析のみでもレポート生成できることを確認"""
    db_path = tmp_path / "test.duckdb"
    worker = ReportGeneratorWorker(str(db_path))

    # Insert only efficiency and summary sections

    result = worker.generate_report(12345, "2025-09-22")

    assert result["success"] is True
    report_content = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "efficiency section データがありません" not in report_content
    assert "environment section データがありません" in report_content
```

**テストケース3: generate_report() - activity_id不存在エラー**
```python
@pytest.mark.integration
def test_generate_report_activity_not_found(tmp_path):
    """存在しないactivity_idでValueErrorがraiseされることを確認"""
    db_path = tmp_path / "test.duckdb"
    worker = ReportGeneratorWorker(str(db_path))

    with pytest.raises(ValueError, match="No performance data found"):
        worker.generate_report(99999, "2025-09-22")
```

**テストケース4: Japanese text encoding**
```python
@pytest.mark.integration
def test_report_japanese_encoding(tmp_path):
    """日本語テキストが正しくUTF-8でエンコードされることを確認"""
    db_path = tmp_path / "test.duckdb"
    worker = ReportGeneratorWorker(str(db_path))

    # Insert Japanese analysis text

    result = worker.generate_report(12345, "2025-09-22")
    report_content = Path(result["report_path"]).read_text(encoding="utf-8")

    assert "優秀な接地時間" in report_content
    assert "適切な疲労管理" in report_content
```

### Performance Tests（オプション）

**テストケース1: レポート生成速度**
```python
@pytest.mark.performance
def test_report_generation_speed(tmp_path):
    """レポート生成が3秒以内に完了することを確認"""
    import time

    db_path = tmp_path / "test.duckdb"
    worker = ReportGeneratorWorker(str(db_path))

    # Insert test data

    start = time.time()
    result = worker.generate_report(12345, "2025-09-22")
    elapsed = time.time() - start

    assert elapsed < 3.0  # 3秒以内
    assert result["success"] is True
```

### 受け入れ基準

✅ **機能要件**:
1. 全5セクション分析を含むレポートが生成できる
2. 一部セクション欠落時も部分的レポートが生成できる
3. 日本語テキストが正しくUTF-8でエンコードされる
4. レポートが正しいディレクトリ構造に保存される

✅ **非機能要件**:
1. レポート生成が3秒以内に完了する
2. テストカバレッジが80%以上
3. エラーメッセージが明確で理解しやすい
4. ログ出力が適切（INFO/WARNING/ERRORレベル）

✅ **コード品質**:
1. Black, Ruff, Mypy全てパス
2. Pre-commit hooks全てパス
3. 全関数にdocstringが記述されている
4. 型ヒントが適切に使用されている

---

## TDD実装フェーズ準備

### Phase 2-1: Unit Tests実装（Red）
- [ ] `tests/reporting/test_report_generator_worker.py` 作成
- [ ] 5つのunit testケースを実装（全て失敗する状態）
- [ ] テスト実行: `uv run pytest tests/reporting/test_report_generator_worker.py -v`

### Phase 2-2: Worker実装（Green）
- [ ] `load_performance_data()` 実装
- [ ] `load_section_analyses()` 実装
- [ ] `_format_overview()` 実装
- [ ] `_format_section_analysis()` 実装
- [ ] テスト実行: `uv run pytest tests/reporting/test_report_generator_worker.py -v` (全てパス)

### Phase 2-3: Integration Tests実装（Red）
- [ ] `tests/reporting/test_report_generation_integration.py` 作成
- [ ] 4つのintegration testケースを実装
- [ ] テスト実行: `uv run pytest tests/reporting/test_report_generation_integration.py -m integration -v`

### Phase 2-4: 完全統合（Green）
- [ ] `generate_report()` 完全実装
- [ ] エラーハンドリング追加
- [ ] ログ出力追加
- [ ] テスト実行: `uv run pytest tests/reporting/ -v` (全てパス)

### Phase 2-5: Refactoring
- [ ] コードの重複削除
- [ ] 可読性向上
- [ ] パフォーマンス最適化
- [ ] テスト実行: `uv run pytest` (全テストパス確認)

---

## References

- `report_specification.md`: Report structure and data sources (this project)
- `docs/spec/duckdb_schema_mapping.md`: DuckDB schema documentation
- `DEVELOPMENT_PROCESS.md`: TDD development workflow
- `tools/reporting/report_generator_worker.py`: Worker implementation (to be updated)
- `tools/reporting/report_template_renderer.py`: Template renderer (existing)
- `tools/reporting/templates/detailed_report.j2`: Jinja2 template (existing)
