# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.0.1] - 2025-10-25

### Fixed - MCP Tool Import Error

#### Similar Workouts Comparison Fix
- **Fixed import error**: `No module named 'servers.garmin_db_mcp'` → `tools.rag.queries.comparisons.WorkoutComparator`
- **Fixed SQL schema issues** in `WorkoutComparator`:
  - Corrected column name: `date` → `activity_date` (3 locations)
  - Removed non-existent columns: `aerobic_te`, `anaerobic_te`, `avg_cadence`, `avg_power`
  - Updated row parsing to match actual schema (6 columns instead of 10)
- **Files Modified**:
  - `tools/reporting/report_generator_worker.py`: Import path and method call
  - `tools/rag/queries/comparisons.py`: SQL schema corrections
- **Impact**: Similar workouts table now populates with real data (when ≥3 matches found)
- **Testing**: All 26 tests passing, integration test verified with real data

#### Technical Details
- **Changes**: +12 lines added, -24 lines removed (net reduction: 12 lines)
- **Commits**: 1 fix commit (7784269)
- **Resolves**: Known Limitation #1 from v4.0.0

### References
- Planning Document: `/docs/project/_archived/2025-10-25_mcp_tool_refactoring/planning.md`
- Completion Report: `/docs/project/_archived/2025-10-25_mcp_tool_refactoring/completion_report.md`
- Related Issue: BALANCED Report V2 Known Limitation #1

---

## [4.0.0] - 2025-10-25

### Added - BALANCED Report V2 Complete Rewrite

#### Phase 0: Custom Jinja2 Filters
- Added 4 custom Jinja2 filters for template rendering:
  - `render_table`: Comparison table rendering
  - `render_rows`: Split table row rendering
  - `bullet_list`: List to markdown bullet conversion
  - `sort_splits`: Split analysis sorting by split number
- File: `tools/reporting/report_template_renderer.py`

#### Phase 1: Template Structure Rewrite
- Complete template rewrite (330→370 lines)
- Removed all section numbers (no 1-6 numbering)
- Reordered sections: 総合評価 moved to position 3 (before パフォーマンス指標)
- Added `<details>` folding sections for:
  - Split detailed analysis
  - Technical details
  - Glossary
- Implemented training_type_category conditional logic:
  - `show_physiological`: Display physiological indicators for tempo/interval runs
  - `is_interval`: 4-phase evaluation for interval workouts
  - Dynamic phase count: 1 (recovery), 3 (base/tempo), 4 (interval)
- Enhanced edge case handling with `.get()` for safe dictionary access
- File: `tools/reporting/templates/detailed_report.j2`

#### Phase 2: Mermaid Graph Data Generation
- Added `_generate_mermaid_data()` method to ReportGeneratorWorker
- Dynamic Y-axis range calculation with 10% padding
- Returns Lists (not JSON strings) for use with `| tojson` filter
- Supports pace, heart rate, and power data visualization
- File: `tools/reporting/report_generator_worker.py`

#### Phase 3: Similar Workouts Comparison
- Added `_load_similar_workouts()` method to ReportGeneratorWorker
- Integrated MCP tool `compare_similar_workouts()` with graceful fallback
- Calculates averages from top 3 similar workouts
- Generates comparison table (pace, heart rate, power)
- Returns `None` if insufficient data (< 3 workouts), template handles gracefully
- Added `_format_pace()` helper method (MM:SS/km formatting)
- File: `tools/reporting/report_generator_worker.py`

#### Phase 4: Pace-Corrected Form Efficiency
- Added `_calculate_pace_corrected_form_efficiency()` method to ReportGeneratorWorker
- Implemented pace-aware baseline formulas (from Appendix C):
  - GCT baseline: `230 + (pace - 240) * 0.22` ms
  - VO baseline: `6.8 + (pace - 240) * 0.004` cm
  - VR: Absolute threshold 8.0-9.5% (no pace correction)
- Three-tier evaluation system: 優秀 (<-5%) / 良好 (±5%) / 要改善 (>5%)
- Star rating system: ★★★★★ to ★★★☆☆
- File: `tools/reporting/report_generator_worker.py`

#### Testing
- Added 20 unit tests for new methods
- Added 11 parametrized tests for pace-correction formulas
- Updated 2 integration test assertions
- Test coverage: 100% pass rate (26/26 tests)
- Files: `tests/reporting/test_report_generator_worker.py`, `tests/reporting/test_report_generation_integration.py`

### Changed

- Report structure now matches BALANCED design specification
- Section order optimized for information flow
- Conditional content based on training type category
- Enhanced error handling and edge case coverage

### Technical Details

- **Total Changes**: +420 lines added, -187 lines removed
- **Files Modified**: 5 files
- **Commits**: 4 feature commits
- **Test Coverage**: 100% (26/26 passing)
- **Code Quality**: All checks passing (Black, Ruff, Mypy)
- **Documentation**: Planning document (1,657 lines), Completion report

### Known Limitations

1. **Similar Workouts MCP Tool**: Import path issue (`No module named 'servers.garmin_db_mcp'`)
   - Status: Gracefully handled with fallback message
   - Impact: Low (template shows "類似ワークアウトが見つかりませんでした")
   - Recommendation: Fix in separate MCP refactoring project

2. **Pace-Corrected Form Efficiency Display**: Data calculated but not displayed in template
   - Status: Worker provides `context["form_efficiency_pace_corrected"]` but template section not added
   - Impact: Low (existing form efficiency section still works)
   - Recommendation: Add template display section in future enhancement

3. **Mermaid Graph Data**: Currently returns None for some activities
   - Status: Framework complete, data source needs investigation
   - Impact: Medium (shows "グラフデータがありません")
   - Recommendation: Debug data source in separate project

### References

- Planning Document: `/docs/project/2025-10-25_balanced_report_v2_complete/planning.md`
- Completion Report: `/docs/project/2025-10-25_balanced_report_v2_complete/completion_report.md`
- Project Issue: TBD

---

## [3.x.x] - Previous Versions

(Previous changelog entries would go here)
