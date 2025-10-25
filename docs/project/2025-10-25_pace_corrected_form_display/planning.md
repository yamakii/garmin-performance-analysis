# 計画: Pace-Corrected Form Efficiency Template Display

## プロジェクト情報
- **プロジェクト名**: `pace_corrected_form_display`
- **作成日**: `2025-10-25`
- **ステータス**: 計画中
- **優先度**: Medium (enhancement, not blocker)
- **推定時間**: 2-3 hours
- **GitHub Issue**: TBD (計画承認後に作成)
- **親プロジェクト**: `2025-10-25_balanced_report_v2_complete`

---

## 要件定義

### 目的
Display pace-corrected form efficiency evaluation (already calculated in Worker) in BALANCED report template to provide runners with relative performance assessment.

### 解決する問題

**Current Issue**:
- **Worker**: Phase 4 implementation complete (201 lines added in completion report)
- **Data**: `context["form_efficiency_pace_corrected"]` is generated successfully
- **Template**: No display section exists in `detailed_report.j2`
- **Impact**: Valuable pace-corrected data calculated but invisible to users

**Data Structure (Already Available)**:
```python
context["form_efficiency_pace_corrected"] = {
    "avg_pace_seconds": 405,  # 6:45/km
    "gct": {
        "actual": 253.0,      # ms
        "baseline": 266.3,    # ms (pace-adjusted)
        "score": -5.0,        # % deviation
        "label": "優秀",
        "rating_stars": "★★★★☆",
        "rating_score": 4.5,
    },
    "vo": {
        "actual": 7.1,        # cm
        "baseline": 7.46,     # cm (pace-adjusted)
        "score": -4.8,        # % deviation
        "label": "優秀",
        "rating_stars": "★★★★☆",
        "rating_score": 4.5,
    },
    "vr": {
        "actual": 9.2,        # %
        "label": "理想範囲内",
        "rating_stars": "★★★★★",
        "rating_score": 5.0,
    },
}
```

**Formula Sources** (from Appendix C in planning.md):
- GCT baseline: `230 + (pace - 240) * 0.22` ms
- VO baseline: `6.8 + (pace - 240) * 0.004` cm
- VR: Absolute threshold (8.0-9.5%)

### ユースケース
1. **Runner Reviews Form Efficiency**:
   - Opens BALANCED report
   - Sees absolute form metrics (GCT 253ms, VO 7.1cm)
   - Sees pace-corrected evaluation table
   - Understands: "For my pace (6:45/km), my GCT is 5% better than expected"
   - Actionable insight: Form efficiency is good relative to pace

2. **Compare Slow vs Fast Runs**:
   - Slow run (7:30/km): GCT 270ms → baseline 280ms → "優秀" (better than expected)
   - Fast run (5:00/km): GCT 240ms → baseline 240ms → "良好" (as expected)
   - Insight: Form efficiency maintained across paces

---

## 現状分析

### 既存実装 (Worker - Completed)

**File**: `tools/reporting/report_generator_worker.py`
**Method**: `_calculate_pace_corrected_form_efficiency()` (lines ~1069-1128 in planning.md)

**Status**: ✅ Fully implemented and tested
- 11 parametrized unit tests passing
- Data correctly calculated for all test activities
- Integration with Worker complete

### テンプレート現状 (Missing Display)

**File**: `tools/reporting/templates/detailed_report.j2`
**Section**: "## パフォーマンス指標" > "### フォーム効率"

**Current Content** (line ~350 in planning.md):
```jinja2
### フォーム効率（{% if is_interval %}Workセグメント {% endif %}ペース補正評価）{% if form_efficiency_rating_stars %} ({{ form_efficiency_rating_stars }} {{ form_efficiency_rating_score }}/5.0){% endif %}

{% if efficiency %}
```mermaid
pie title "心拍ゾーン分布"
{{ heart_rate_zone_pie_data|default("") }}
```

{{ efficiency.evaluation if efficiency.evaluation else efficiency if efficiency is string else "フォーム効率データがありません。" }}
{% else %}
フォーム効率データがありません。
{% endif %}
```

**What's Missing**:
- No table displaying `form_efficiency_pace_corrected` data
- No explanation of pace correction concept
- No comparison between actual and baseline values

---

## 設計

### テンプレート追加内容

**Location**: Insert after existing フォーム効率 evaluation text, before closing the section

**Option A: Subsection with Table** (Recommended)
```jinja2
### フォーム効率（{% if is_interval %}Workセグメント {% endif %}ペース補正評価）

{# Existing content: Heart rate zone pie chart + efficiency.evaluation text #}
{% if efficiency %}
```mermaid
pie title "心拍ゾーン分布"
{{ heart_rate_zone_pie_data|default("") }}
```

{{ efficiency.evaluation }}
{% endif %}

{# NEW: Pace-corrected form efficiency table #}
{% if form_efficiency_pace_corrected %}

#### ペース補正フォーム効率評価

あなたの平均ペース（**{{ (form_efficiency_pace_corrected.avg_pace_seconds // 60)|int }}:{{ "%02d"|format(form_efficiency_pace_corrected.avg_pace_seconds % 60) }}/km**）に対する相対評価：

| 指標 | 実測値 | ペース基準値 | 補正スコア | 評価 | レーティング |
|------|--------|--------------|------------|------|--------------|
| **GCT**（接地時間） | {{ form_efficiency_pace_corrected.gct.actual }} ms | {{ form_efficiency_pace_corrected.gct.baseline }} ms | {{ "%+.1f"|format(form_efficiency_pace_corrected.gct.score) }}% | {{ form_efficiency_pace_corrected.gct.label }} | {{ form_efficiency_pace_corrected.gct.rating_stars }} ({{ form_efficiency_pace_corrected.gct.rating_score }}/5.0) |
| **VO**（垂直振幅） | {{ form_efficiency_pace_corrected.vo.actual }} cm | {{ form_efficiency_pace_corrected.vo.baseline }} cm | {{ "%+.1f"|format(form_efficiency_pace_corrected.vo.score) }}% | {{ form_efficiency_pace_corrected.vo.label }} | {{ form_efficiency_pace_corrected.vo.rating_stars }} ({{ form_efficiency_pace_corrected.vo.rating_score }}/5.0) |
| **VR**（垂直比率） | {{ form_efficiency_pace_corrected.vr.actual }}% | - | - | {{ form_efficiency_pace_corrected.vr.label }} | {{ form_efficiency_pace_corrected.vr.rating_stars }} ({{ form_efficiency_pace_corrected.vr.rating_score }}/5.0) |

**📊 評価基準**:
- **優秀**: 基準値より5%以上良好（ペースに対して効率的）
- **良好**: 基準値±5%以内（ペース相応）
- **要改善**: 基準値より5%以上悪化（改善余地あり）

**💡 ペース補正の意味**: 速いペースほどGCTは短く、VOは小さくなるのが自然です。この評価は「同じペースのランナー」との比較を示しています。

{% endif %}

---
```

**Option B: Compact Display (Inside Existing Section)**
```jinja2
### フォーム効率

{{ efficiency.evaluation }}

{% if form_efficiency_pace_corrected %}
**ペース補正評価**（{{ (form_efficiency_pace_corrected.avg_pace_seconds // 60)|int }}:{{ "%02d"|format(form_efficiency_pace_corrected.avg_pace_seconds % 60) }}/km 基準）:
- GCT: {{ form_efficiency_pace_corrected.gct.actual }}ms (基準{{ form_efficiency_pace_corrected.gct.baseline }}ms, {{ "%+.1f"|format(form_efficiency_pace_corrected.gct.score) }}%) → {{ form_efficiency_pace_corrected.gct.label }} {{ form_efficiency_pace_corrected.gct.rating_stars }}
- VO: {{ form_efficiency_pace_corrected.vo.actual }}cm (基準{{ form_efficiency_pace_corrected.vo.baseline }}cm, {{ "%+.1f"|format(form_efficiency_pace_corrected.vo.score) }}%) → {{ form_efficiency_pace_corrected.vo.label }} {{ form_efficiency_pace_corrected.vo.rating_stars }}
- VR: {{ form_efficiency_pace_corrected.vr.actual }}% → {{ form_efficiency_pace_corrected.vr.label }} {{ form_efficiency_pace_corrected.vr.rating_stars }}
{% endif %}
```

**Recommendation**: Option A (subsection with table)
- Clearer visual hierarchy
- Easier to understand comparison
- Consistent with BALANCED principle (structured information)

---

## 実装フェーズ

### Phase 1: Template Modification (1-2 hours)

**Step 1.1: Locate Insertion Point**
```bash
# Find フォーム効率 section in template
cd /home/yamakii/workspace/claude_workspace/garmin-performance-analysis
grep -n "### フォーム効率" tools/reporting/templates/detailed_report.j2
```

**Step 1.2: Insert New Subsection**
1. Open `tools/reporting/templates/detailed_report.j2`
2. Find line ~350 (after `{{ efficiency.evaluation }}`)
3. Insert Option A code block (subsection with table)
4. Ensure proper indentation (Jinja2 template format)

**Step 1.3: Edge Case Handling**
```jinja2
{# Only show if data exists #}
{% if form_efficiency_pace_corrected %}
  {# Check if GCT/VO data exists #}
  {% if form_efficiency_pace_corrected.gct and form_efficiency_pace_corrected.vo %}
    {# Render table #}
  {% else %}
    ペース補正データが不足しています。
  {% endif %}
{% endif %}
```

---

### Phase 2: Testing (1 hour)

**Step 2.1: Unit Test (Template Rendering)**
```python
# tests/reporting/test_pace_corrected_display.py
def test_pace_corrected_section_present():
    """Pace-corrected form efficiency section appears in template."""
    context = {
        "form_efficiency_pace_corrected": {
            "avg_pace_seconds": 405,
            "gct": {
                "actual": 253.0,
                "baseline": 266.3,
                "score": -5.0,
                "label": "優秀",
                "rating_stars": "★★★★☆",
                "rating_score": 4.5,
            },
            "vo": {
                "actual": 7.1,
                "baseline": 7.46,
                "score": -4.8,
                "label": "優秀",
                "rating_stars": "★★★★☆",
                "rating_score": 4.5,
            },
            "vr": {
                "actual": 9.2,
                "label": "理想範囲内",
                "rating_stars": "★★★★★",
                "rating_score": 5.0,
            },
        },
        "efficiency": {"evaluation": "フォーム効率は良好です。"},
        # ... (other required fields)
    }

    report = render_template(context)

    # Check for subsection header
    assert "#### ペース補正フォーム効率評価" in report

    # Check for table headers
    assert "| 指標 | 実測値 | ペース基準値 | 補正スコア | 評価 | レーティング |" in report

    # Check for data rows
    assert "| **GCT**（接地時間） |" in report
    assert "253.0 ms" in report
    assert "266.3 ms" in report
    assert "-5.0%" in report
    assert "優秀" in report

def test_pace_corrected_section_missing_data():
    """Pace-corrected section gracefully handles missing data."""
    context = {
        "form_efficiency_pace_corrected": None,
        "efficiency": {"evaluation": "フォーム効率は良好です。"},
    }

    report = render_template(context)

    # Should NOT render subsection if data is None
    assert "#### ペース補正フォーム効率評価" not in report
```

**Step 2.2: Integration Test (Full Report)**
```python
@pytest.mark.integration
def test_pace_corrected_in_full_report():
    """Pace-corrected form efficiency appears in generated report."""
    from tools.reporting.report_generator_worker import ReportGeneratorWorker

    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id=20625808856)

    with open(result["report_path"]) as f:
        report = f.read()

    # Check for subsection
    assert "#### ペース補正フォーム効率評価" in report

    # Check for table structure
    assert "| **GCT**（接地時間） |" in report
    assert "| **VO**（垂直振幅） |" in report
    assert "| **VR**（垂直比率） |" in report

    # Check for explanation
    assert "ペース補正の意味" in report
```

**Step 2.3: Visual Inspection**
```bash
# Generate report and preview
uv run python -c "
from tools.reporting.report_generator_worker import ReportGeneratorWorker
worker = ReportGeneratorWorker()
result = worker.generate_report(activity_id=20625808856)
print(f'Report: {result[\"report_path\"]}')
"

# Open in GitHub-compatible markdown viewer
# Check:
# 1. Table renders correctly (no broken pipes)
# 2. Rating stars display correctly
# 3. Percentage format is correct (+/- sign)
# 4. Explanation text is readable
```

---

## テスト計画

### Unit Tests
- [x] `test_pace_corrected_section_present()` - Section renders with valid data
- [x] `test_pace_corrected_table_structure()` - Table has correct columns/rows
- [x] `test_pace_corrected_section_missing_data()` - Graceful handling when data is None
- [x] `test_pace_corrected_formatting()` - Percentage, pace, stars format correctly

### Integration Tests
- [x] `test_pace_corrected_in_full_report()` - Appears in generated report
- [x] `test_pace_corrected_location()` - Correct position in "パフォーマンス指標" section

### Manual Tests
- [ ] Generate report for base run (20625808856)
- [ ] Verify table displays correctly in GitHub markdown preview
- [ ] Verify rating stars (★★★★☆) render correctly
- [ ] Check explanation text is clear and helpful
- [ ] Test with different paces (slow run vs fast run)

---

## 受け入れ基準

### Functional Requirements
- [ ] Pace-corrected form efficiency table visible in reports
- [ ] Table shows: GCT, VO, VR with actual/baseline/score/label/rating
- [ ] Explanation text clarifies pace correction concept
- [ ] Section integrates naturally with existing フォーム効率 section
- [ ] Graceful handling when `form_efficiency_pace_corrected` is None

### Quality Requirements
- [ ] All unit tests pass (4 tests)
- [ ] All integration tests pass (2 tests)
- [ ] Table markdown syntax valid (no broken pipes)
- [ ] Pre-commit hooks pass (template is .j2, not checked by Black)

### Documentation Requirements
- [ ] Inline comments explain pace correction formulas (reference Appendix C)
- [ ] Completion report includes before/after screenshots (if possible)

### Backward Compatibility
- [ ] No changes to Worker (only template modified)
- [ ] Reports without `form_efficiency_pace_corrected` still generate (graceful fallback)
- [ ] Existing フォーム効率 section unchanged

---

## リスクと対策

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Table too wide for mobile** | Low (readability) | Medium | Keep columns minimal (5-6 columns max) |
| **Confusing to users** | Medium (misinterpretation) | Low | Add clear explanation text + 評価基準 |
| **Missing data** | Low (empty section) | Low | Wrap in `{% if %}` check |
| **Markdown syntax error** | Medium (broken table) | Low | Test with GitHub markdown preview |

---

## 依存関係

**Depends On**:
- BALANCED Report V2 Complete - Phase 4 (Worker implementation) ✅ Complete
- `context["form_efficiency_pace_corrected"]` data structure defined ✅ Complete

**Blocks**:
- None (independent enhancement)

**Related Projects**:
- `2025-10-25_balanced_report_v2_complete` (parent project - Phase 4)

---

## 参考資料

### Related Files
- `tools/reporting/templates/detailed_report.j2` - Template to modify (line ~350)
- `tools/reporting/report_generator_worker.py` - Worker (already complete, no changes)
- `docs/project/_archived/2025-10-25_balanced_report_v2_complete/planning.md` - Appendix C (formula sources)
- `docs/project/_archived/2025-10-25_balanced_report_v2_complete/completion_report.md` - Known limitation #2

### Data Structure Reference
See planning.md lines 1069-1128 for Worker implementation and data structure.

### Sample Output (Expected)
```markdown
#### ペース補正フォーム効率評価

あなたの平均ペース（**6:45/km**）に対する相対評価：

| 指標 | 実測値 | ペース基準値 | 補正スコア | 評価 | レーティング |
|------|--------|--------------|------------|------|--------------|
| **GCT**（接地時間） | 253.0 ms | 266.3 ms | -5.0% | 優秀 | ★★★★☆ (4.5/5.0) |
| **VO**（垂直振幅） | 7.1 cm | 7.46 cm | -4.8% | 優秀 | ★★★★☆ (4.5/5.0) |
| **VR**（垂直比率） | 9.2% | - | - | 理想範囲内 | ★★★★★ (5.0/5.0) |

**📊 評価基準**:
- **優秀**: 基準値より5%以上良好（ペースに対して効率的）
- **良好**: 基準値±5%以内（ペース相応）
- **要改善**: 基準値より5%以上悪化（改善余地あり）

**💡 ペース補正の意味**: 速いペースほどGCTは短く、VOは小さくなるのが自然です。この評価は「同じペースのランナー」との比較を示しています。
```

---

## Next Steps (After Planning Approval)

1. Create GitHub Issue
2. Create worktree: `git worktree add -b feat/pace-corrected-display ../garmin-pace-display main`
3. Activate Serena MCP in worktree (if modifying code; template-only may not need it)
4. Execute Phase 1 (Template modification)
5. Execute Phase 2 (Testing)
6. Generate completion report
7. Merge to main

---

*このプランは、BALANCED Report V2 Complete Rewrite の Known Limitation #2 を解決します。*

**作成日**: 2025-10-25
**ステータス**: 計画中（承認待ち）
**推定行数増加**: +15-20 lines in template
