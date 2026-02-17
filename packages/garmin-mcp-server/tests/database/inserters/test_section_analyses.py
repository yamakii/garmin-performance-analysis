"""
Tests for SectionAnalysisInserter

Test coverage:
- Unit tests for insert_section_analysis function
- Integration tests with DuckDB
"""

import json
from datetime import datetime

import duckdb
import pytest

from garmin_mcp.database.inserters.activities import insert_activities
from garmin_mcp.database.inserters.section_analyses import insert_section_analysis


class TestSectionAnalysisInserter:
    """Test suite for SectionAnalysisInserter."""

    @pytest.fixture
    def sample_analysis_data(self):
        """Sample section analysis data."""
        return {
            "metadata": {
                "activity_id": "20464005432",
                "date": "2025-09-22",
                "analyst": "efficiency-section-analyst",
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
            },
            "efficiency": {
                "form_efficiency": "GCT平均: 262ms (★★★☆☆), VO平均: 7.2cm (★★★★★)",
                "hr_efficiency": "Zone 1優位 (63.5%), aerobic_base型",
                "evaluation": "優秀な接地時間、効率的な地面反力利用",
            },
        }

    @pytest.fixture
    def sample_analysis_file(self, tmp_path, sample_analysis_data):
        """Create sample section analysis JSON file."""
        analysis_file = tmp_path / "efficiency_section_analysis.json"
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(sample_analysis_data, f, ensure_ascii=False, indent=2)
        return analysis_file

    @pytest.mark.unit
    def test_insert_section_analysis_success(
        self, sample_analysis_file, initialized_db_path
    ):
        """Test insert_section_analysis inserts data successfully."""

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(
            activity_id=20464005432,
            date="2025-09-22",
            conn=conn,
        )
        conn.close()

        result = insert_section_analysis(
            analysis_file=str(sample_analysis_file),
            activity_id=20464005432,
            activity_date="2025-09-22",
            section_type="efficiency",
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_section_analysis_missing_file(self, tmp_path):
        """Test insert_section_analysis handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_section_analysis(
            analysis_file="/nonexistent/file.json",
            activity_id=12345,
            activity_date="2025-09-22",
            section_type="efficiency",
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_section_analysis_dict_success(
        self, sample_analysis_data, initialized_db_path
    ):
        """Test insert_section_analysis_dict inserts data from dict."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(
            activity_id=20464005432,
            date="2025-09-22",
            conn=conn,
        )
        conn.close()

        result = insert_section_analysis(
            analysis_data=sample_analysis_data,
            activity_id=20464005432,
            activity_date="2025-09-22",
            section_type="efficiency",
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_section_analysis_db_integration(
        self, sample_analysis_file, initialized_db_path
    ):
        """Test insert_section_analysis actually writes to DuckDB."""
        import duckdb

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(
            activity_id=20464005432,
            date="2025-09-22",
            conn=conn,
        )
        conn.close()

        result = insert_section_analysis(
            analysis_file=str(sample_analysis_file),
            activity_id=20464005432,
            activity_date="2025-09-22",
            section_type="efficiency",
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        analyses = conn.execute("""
            SELECT * FROM section_analyses
            WHERE activity_id = 20464005432 AND section_type = 'efficiency'
            """).fetchall()

        assert len(analyses) == 1
        assert str(analyses[0][2]) == "2025-09-22"  # activity_date (column index 2)
        assert analyses[0][3] == "efficiency"  # section_type (column index 3)

        conn.close()

    @pytest.mark.integration
    def test_insert_section_analysis_dict_db_integration(
        self, sample_analysis_data, initialized_db_path
    ):
        """Test insert_section_analysis with dict actually writes to DuckDB."""
        import duckdb

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(
            activity_id=20464005432,
            date="2025-09-22",
            conn=conn,
        )
        conn.close()

        result = insert_section_analysis(
            analysis_data=sample_analysis_data,
            activity_id=20464005432,
            activity_date="2025-09-22",
            section_type="efficiency",
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        analyses = conn.execute("""
            SELECT * FROM section_analyses
            WHERE activity_id = 20464005432 AND section_type = 'efficiency'
            """).fetchall()

        assert len(analyses) == 1
        assert str(analyses[0][2]) == "2025-09-22"  # activity_date (column index 2)
        assert analyses[0][3] == "efficiency"  # section_type (column index 3)

        # Verify analysis_data is stored correctly
        analysis_json = analyses[0][4]  # analysis_data column (column index 4)
        assert analysis_json is not None

        conn.close()

    @pytest.mark.unit
    def test_insert_section_analysis_auto_metadata(self, initialized_db_path):
        """Test insert_section_analysis auto-generates metadata when not provided."""
        import duckdb

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(
            activity_id=20464005432,
            date="2025-09-22",
            conn=conn,
        )
        conn.close()

        # Analysis data WITHOUT metadata
        analysis_data_no_metadata = {
            "efficiency": "GCT平均: 262ms (★★★☆☆), VO平均: 7.2cm (★★★★★)"
        }

        result = insert_section_analysis(
            analysis_data=analysis_data_no_metadata,
            activity_id=20464005432,
            activity_date="2025-09-22",
            section_type="efficiency",
            db_path=str(db_path),
        )

        assert result is True

        # Verify metadata was auto-generated
        conn = duckdb.connect(str(db_path))

        analyses = conn.execute("""
            SELECT analysis_data, agent_name, agent_version
            FROM section_analyses
            WHERE activity_id = 20464005432 AND section_type = 'efficiency'
            """).fetchall()

        assert len(analyses) == 1

        # Parse analysis_data JSON
        analysis_json = json.loads(analyses[0][0])

        # Verify metadata exists and has correct structure
        assert "metadata" in analysis_json
        assert analysis_json["metadata"]["activity_id"] == "20464005432"
        assert analysis_json["metadata"]["date"] == "2025-09-22"
        assert analysis_json["metadata"]["analyst"] == "efficiency-section-analyst"
        assert analysis_json["metadata"]["version"] == "1.0"
        assert "timestamp" in analysis_json["metadata"]

        # Verify agent_name and agent_version columns
        assert analyses[0][1] == "efficiency-section-analyst"  # agent_name
        assert analyses[0][2] == "1.0"  # agent_version

        # Verify original analysis data is preserved
        assert "efficiency" in analysis_json
        assert "GCT平均" in analysis_json["efficiency"]

        conn.close()

    @pytest.mark.unit
    def test_insert_section_analysis_custom_agent_name(self, initialized_db_path):
        """Test insert_section_analysis with custom agent_name."""
        import duckdb

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(
            activity_id=20464005432,
            date="2025-09-22",
            conn=conn,
        )
        conn.close()

        # Analysis data WITHOUT metadata
        analysis_data = {"summary": "Overall performance evaluation"}

        result = insert_section_analysis(
            analysis_data=analysis_data,
            activity_id=20464005432,
            activity_date="2025-09-22",
            section_type="summary",
            agent_name="custom-analyst-v2",
            agent_version="2.1.0",
            db_path=str(db_path),
        )

        assert result is True

        # Verify custom agent_name was used
        conn = duckdb.connect(str(db_path))

        analyses = conn.execute("""
            SELECT analysis_data, agent_name, agent_version
            FROM section_analyses
            WHERE activity_id = 20464005432 AND section_type = 'summary'
            """).fetchall()

        assert len(analyses) == 1

        # Parse analysis_data JSON
        analysis_json = json.loads(analyses[0][0])

        # Verify custom agent name and version
        assert analysis_json["metadata"]["analyst"] == "custom-analyst-v2"
        assert analysis_json["metadata"]["version"] == "2.1.0"
        assert analyses[0][1] == "custom-analyst-v2"  # agent_name column
        assert analyses[0][2] == "2.1.0"  # agent_version column

        conn.close()
