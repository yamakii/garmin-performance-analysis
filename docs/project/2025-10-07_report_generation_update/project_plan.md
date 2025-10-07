# Report Generation Update Project

**Project Date**: 2025-10-07
**Status**: Planning
**Priority**: High

## Project Overview

This project aims to implement an efficient report generation system based on the worker-based architecture specification. The system will generate comprehensive running analysis reports from DuckDB-stored performance data and section analyses.

## Background

- Previous implementation used placeholder-based report generation with MCP servers
- Worker-based architecture provides better performance and maintainability
- DuckDB schema has been documented with table relationships
- Section analyses specification has been completed with 5 section types

## Project Goals

1. Implement worker-based report generation system
2. Integrate section analyses from DuckDB into final reports
3. Generate Japanese markdown reports with proper formatting
4. Ensure efficient token usage through structured data retrieval
5. Support parallel section analysis execution

## Architecture

### Data Flow

```
DuckDB (section_analyses table)
    ↓
ReportGeneratorWorker.load_section_analyses()
    ↓
ReportGeneratorWorker._format_section_analysis()
    ↓
ReportTemplateRenderer.render_report()
    ↓
result/individual/{YEAR}/{MONTH}/{YYYY-MM-DD}_activity_{ACTIVITY_ID}.md
```

### Key Components

1. **ReportGeneratorWorker** (`tools/reporting/report_generator_worker.py`)
   - Load performance data from DuckDB
   - Load section analyses from DuckDB
   - Format sections for report rendering
   - Coordinate report generation pipeline

2. **ReportTemplateRenderer** (`tools/reporting/report_template_renderer.py`)
   - Jinja2 template-based rendering
   - Report structure generation
   - Report validation
   - Final report saving

3. **DuckDB Section Analyses** (`data/database/garmin_performance.duckdb`)
   - 5 section types: efficiency, environment, phase, split, summary
   - Structured JSON storage
   - Foreign key constraints with activities table

## Project Structure

```
docs/project/2025-10-07_report_generation_update/
├── project_plan.md              # This file
├── report_specification.md      # Report generation specification
├── duckdb_schema_mapping.md     # DuckDB schema documentation
└── implementation_progress.md   # Implementation progress tracking (to be created)
```

## Implementation Phases

### Phase 1: Current State Analysis ✅
- [x] Document DuckDB schema with table relationships
- [x] Document report specification with 7 sections
- [x] Remove unused report-generator MCP server
- [x] Add form metrics to split analysis specification

### Phase 2: Worker Implementation (Current)
- [ ] Review existing ReportGeneratorWorker implementation
- [ ] Implement section analysis formatting logic
- [ ] Add proper error handling and logging
- [ ] Support missing section graceful degradation
- [ ] Add report validation before saving

### Phase 3: Integration & Testing
- [ ] Create integration tests for report generation
- [ ] Test with real activity data
- [ ] Verify Japanese text formatting
- [ ] Validate report structure and content
- [ ] Performance benchmarking

### Phase 4: Documentation & Deployment
- [ ] Update CLAUDE.md with report generation workflow
- [ ] Create user guide for report generation
- [ ] Document troubleshooting procedures
- [ ] Final project completion report

## Success Criteria

1. ✅ Report generation completes successfully for activities with section analyses
2. ✅ Reports follow the 7-section structure (overview + 5 analyses + summary)
3. ✅ Japanese text is properly formatted
4. ✅ Reports are saved to correct directory structure
5. ✅ Error handling for missing data is graceful
6. ✅ Token usage is optimized through DuckDB queries

## References

- `report_specification.md`: Detailed report generation specification
- `duckdb_schema_mapping.md`: DuckDB schema documentation
- `tools/reporting/report_generator_worker.py`: Worker implementation
- `tools/reporting/report_template_renderer.py`: Template renderer
- `tools/reporting/templates/detailed_report.j2`: Jinja2 template

## Related Files

### Specifications
- `report_specification.md`: Report structure and data sources
- `duckdb_schema_mapping.md`: Database schema and relationships

### Implementation
- `tools/reporting/report_generator_worker.py`: Main worker class
- `tools/reporting/report_template_renderer.py`: Template rendering
- `tools/reporting/templates/detailed_report.j2`: Report template
- `tools/database/db_reader.py`: DuckDB read operations

### Tests
- `tests/reporting/` (to be created): Report generation tests

## Notes

- This project follows proper development process with planning phase
- All specifications have been documented before implementation
- Previous ad-hoc changes have been committed to git
- Current focus: Review and update existing worker implementation
