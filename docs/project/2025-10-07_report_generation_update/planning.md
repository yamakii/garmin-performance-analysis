# 計画: Report Generation Update

**Project Date**: 2025-10-07
**Status**: ✅ Completed (All TDD phases passed)
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
    ├── load_performance_data(activity_id) → basic_metrics (JSON)
    ├── load_section_analyses(activity_id) → 5 sections dict (JSON)
    └── generate_report(activity_id, date) → report_content
          ↓
[ReportTemplateRenderer]
    ├── load_template("detailed_report.j2")
    ├── render_report(activity_id, date, basic_metrics, 5 sections JSON) → markdown
    │   └── Template内でJSON dataをmarkdown形式にフォーマット
    └── save_report(activity_id, date, report_content) → file path
          ↓
[result/individual/{YEAR}/{MONTH}/{YYYY-MM-DD}_activity_{ACTIVITY_ID}.md]
```

**設計原則**: ロジックとプレゼンテーションの完全分離
- Worker層: データ取得のみ（フォーマット処理なし）
- Template層: JSON dataから柔軟にmarkdown生成

#### コンポーネント設計

**1. ReportGeneratorWorker** (`tools/reporting/report_generator_worker.py`)
- **責務**: DuckDBからJSON dataを取得し、レポート生成を調整（フォーマット処理なし）
- **主要メソッド**:
  - `load_performance_data(activity_id: int) -> dict[str, Any] | None`
    - 返り値: `{"basic_metrics": {...}}`
  - `load_section_analyses(activity_id: int) -> dict[str, dict[str, Any]] | None`
    - 返り値: `{"efficiency": {...}, "environment_analysis": {...}, ...}`
  - `generate_report(activity_id: int, date: str | None = None) -> dict[str, Any]`
    - JSON dataをRendererに渡してレポート生成

**2. ReportTemplateRenderer** (`tools/reporting/report_template_renderer.py`)
- **責務**: Jinja2テンプレートでJSON dataからmarkdownを生成、ファイル保存
- **主要メソッド**:
  - `load_template(template_name: str = "detailed_report.j2")`
  - `render_report(activity_id: str, date: str, basic_metrics: dict, section_analyses: dict) -> str`
    - **変更点**: markdown文字列ではなくJSON dictを受け取る
    - Template側でJSON dataをmarkdown形式にフォーマット
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
    "gear": {
      "shoes": "Nike Vaporfly Next% 2 (走行距離: 245km)",
      "notes": "理想的なシューズ選択"
    },
    "evaluation": "理想的な環境条件、適切な機材選択"
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

Jinja2テンプレートに渡される変数（JSON data形式）:

```python
{
  "activity_id": str,
  "date": str,  # YYYY-MM-DD
  "basic_metrics": dict,  # Performance data (distance, time, pace, HR, etc.)
  "efficiency": dict,  # Efficiency section (form_efficiency, hr_efficiency, evaluation)
  "environment_analysis": dict,  # Environment section (weather, terrain, gear, evaluation)
  "phase_evaluation": dict,  # Phase section (warmup, main, finish, overall)
  "split_analysis": dict,  # Split section (splits list, patterns)
  "summary": dict,  # Summary section (activity_type, rating, strengths, areas, recommendations)
}
```

**Template側の責務**:
- `basic_metrics`からキーメトリクス表とトレーニング概要を生成
- 各sectionのJSON dataを適切なmarkdown形式にフォーマット
- 日本語テキストの整形（箇条書き、表、見出しなど）

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
    basic_metrics: dict[str, Any],
    section_analyses: dict[str, dict[str, Any]],
) -> str:
    """
    Render report using Jinja2 template with JSON data.

    Args:
        activity_id: Activity ID
        date: Date (YYYY-MM-DD)
        basic_metrics: Performance data (distance, time, pace, HR, cadence, power)
        section_analyses: Section analyses dict with keys:
            - "efficiency": Form & HR efficiency analysis
            - "environment_analysis": Weather, terrain, gear analysis
            - "phase_evaluation": Warmup, main, finish phase analysis
            - "split_analysis": Split-by-split detailed analysis
            - "summary": Overall rating and recommendations

    Returns:
        Rendered report content (markdown)

    Note:
        Template側でJSON dataをmarkdown形式にフォーマット。
        Worker側ではフォーマット処理を行わない（ロジックとプレゼンテーションの分離）。
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

**テストケース3: load_section_analyses() - environment分析にgear情報含む**
```python
def test_load_section_analyses_includes_gear():
    """Environment分析にgear情報が含まれることを確認"""
    worker = ReportGeneratorWorker(":memory:")
    # Setup: Insert environment section with gear info
    analyses = worker.load_section_analyses(12345)

    assert analyses is not None
    assert "environment_analysis" in analyses
    env = analyses["environment_analysis"]
    assert "gear" in env
    assert "shoes" in env["gear"]
```

**テストケース4: ReportTemplateRenderer - JSON dataをテンプレートに渡す**
```python
def test_renderer_accepts_json_data():
    """RendererがJSON dataを受け取ってレンダリングできることを確認"""
    renderer = ReportTemplateRenderer()

    basic_metrics = {
        "distance_km": 5.0,
        "duration_seconds": 1800,
        "avg_pace_seconds_per_km": 360,
        "avg_heart_rate": 155,
    }

    section_analyses = {
        "efficiency": {"form_efficiency": "GCT: 262ms", "hr_efficiency": "Zone 1優位"},
        "environment_analysis": {"weather_conditions": "気温18.0°C", "gear": {"shoes": "Nike Vaporfly"}},
        "phase_evaluation": {},
        "split_analysis": {},
        "summary": {}
    }

    report = renderer.render_report("12345", "2025-09-22", basic_metrics, section_analyses)

    assert "5.0" in report or "5.00" in report  # Template側でフォーマット
    assert "GCT: 262ms" in report
    assert "Nike Vaporfly" in report
```

**テストケース5: ReportTemplateRenderer - 空セクションの扱い**
```python
def test_renderer_handles_missing_sections():
    """空のセクションに対してTemplate側で適切に処理されることを確認"""
    renderer = ReportTemplateRenderer()

    basic_metrics = {"distance_km": 5.0, "duration_seconds": 1800}
    section_analyses = {
        "efficiency": {"form_efficiency": "GCT: 262ms"},
        "environment_analysis": {},  # 空セクション
        "phase_evaluation": {},
        "split_analysis": {},
        "summary": {}
    }

    report = renderer.render_report("12345", "2025-09-22", basic_metrics, section_analyses)

    assert report is not None
    # Template側で空セクションの扱いを実装（例: 「データなし」メッセージ、またはセクション非表示）
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
2. Environment分析にgear情報（シューズなど）が含まれる
3. 一部セクション欠落時も部分的レポートが生成できる
4. 日本語テキストが正しくUTF-8でエンコードされる
5. レポートが正しいディレクトリ構造に保存される

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

## TDD実装フェーズ完了状況

### Phase 2-1: Unit Tests実装（Red） ✅
- [x] `tests/reporting/test_report_generator_worker.py` 作成
- [x] 5つのunit testケースを実装（全て失敗する状態）
  - test_load_performance_data_success
  - test_load_section_analyses_all_sections
  - test_load_section_analyses_includes_gear
  - test_renderer_accepts_json_data
  - test_renderer_handles_missing_sections
- [x] テスト実行: `uv run pytest tests/reporting/test_report_generator_worker.py -v`

### Phase 2-2: Worker & Renderer実装（Green） ✅
- [x] `load_performance_data()` 実装
- [x] `load_section_analyses()` 実装（gear情報含む）
- [x] `ReportTemplateRenderer.render_report()` 更新
  - 引数をJSON dataに変更（markdown文字列ではなく）
  - Template側でmarkdown生成ロジックを実装
- [x] テスト実行: `uv run pytest tests/reporting/test_report_generator_worker.py -v` (全てパス)

### Phase 2-3: Integration Tests実装（Green） ✅
- [x] `tests/reporting/test_report_generation_integration.py` 作成
- [x] 4つのintegration testケースを実装
- [x] テスト実行: `uv run pytest tests/reporting/test_report_generation_integration.py -m integration -v`
- [x] 全テスト合格（4 integration + 2 unit tests）

### Phase 2-4: 完全統合（Green） ✅
- [x] `generate_report()` 完全実装
- [x] エラーハンドリング追加（ValueError for missing activity）
- [x] ログ出力追加（INFO/WARNING levels）
- [x] テスト実行: `uv run pytest tests/reporting/ -v` (全てパス)

### Phase 2-5: Refactoring ✅
- [x] コードの重複削除（未使用placeholder methods削除）
- [x] 可読性向上（ロジックとプレゼンテーションの分離）
- [x] パフォーマンス最適化（不要なフォーマット処理削除）
- [x] テスト実行: `uv run pytest` (全テストパス確認)

---

## References

- `report_specification.md`: Report structure and data sources (this project)
- `docs/spec/duckdb_schema_mapping.md`: DuckDB schema documentation
- `DEVELOPMENT_PROCESS.md`: TDD development workflow
- `tools/reporting/report_generator_worker.py`: Worker implementation (to be updated)
- `tools/reporting/report_template_renderer.py`: Template renderer (existing)
- `tools/reporting/templates/detailed_report.j2`: Jinja2 template (existing)
