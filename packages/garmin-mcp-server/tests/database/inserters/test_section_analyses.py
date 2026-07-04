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

    @pytest.mark.unit
    def test_insert_section_analysis_appends(self, initialized_db_path):
        """Re-inserting the same (activity_id, section_type) appends a new row.

        Append-only storage (issue #720): a second analysis run for the same
        section keeps the prior version instead of overwriting it.
        """
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(activity_id=999901, date="2025-09-22", conn=conn)
        conn.close()

        for note in ("first version", "second version"):
            result = insert_section_analysis(
                analysis_data={"summary": note},
                activity_id=999901,
                activity_date="2025-09-22",
                section_type="summary",
                db_path=str(db_path),
            )
            assert result is True

        conn = duckdb.connect(str(db_path))
        rows = conn.execute(
            "SELECT analysis_data FROM section_analyses"
            " WHERE activity_id = 999901 AND section_type = 'summary'"
            " ORDER BY created_at, analysis_id"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        summaries = [json.loads(row[0])["summary"] for row in rows]
        assert summaries == ["first version", "second version"]

    @pytest.mark.integration
    def test_migration_drops_unique_index(self, tmp_path):
        """Applying the migration on a legacy DB allows double inserts.

        Rebuilds the pre-#720 shape (unique index on (activity_id, section_type))
        and confirms the migration drops it so a second row for the same key can
        be inserted.
        """
        from garmin_mcp.database.migrations.drop_section_analysis_index import (
            drop_section_analysis_index,
        )

        db_path = tmp_path / "legacy.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE section_analyses (
                analysis_id INTEGER PRIMARY KEY,
                activity_id BIGINT NOT NULL,
                activity_date DATE NOT NULL,
                section_type VARCHAR NOT NULL,
                analysis_data VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
        conn.execute(
            "CREATE UNIQUE INDEX idx_activity_section"
            " ON section_analyses(activity_id, section_type)"
        )
        conn.execute(
            "INSERT INTO section_analyses"
            " (analysis_id, activity_id, activity_date, section_type, analysis_data)"
            " VALUES (1, 999902, '2025-09-22', 'summary', '{\"v\": 1}')"
        )

        # Before the migration the unique index blocks a second version.
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                "INSERT INTO section_analyses"
                " (analysis_id, activity_id, activity_date, section_type,"
                "  analysis_data)"
                " VALUES (2, 999902, '2025-09-22', 'summary', '{\"v\": 2}')"
            )

        drop_section_analysis_index(conn)

        # After the migration the second version inserts successfully.
        conn.execute(
            "INSERT INTO section_analyses"
            " (analysis_id, activity_id, activity_date, section_type, analysis_data)"
            " VALUES (2, 999902, '2025-09-22', 'summary', '{\"v\": 2}')"
        )
        count_row = conn.execute(
            "SELECT COUNT(*) FROM section_analyses"
            " WHERE activity_id = 999902 AND section_type = 'summary'"
        ).fetchone()
        conn.close()

        assert count_row is not None
        assert count_row[0] == 2

    @pytest.mark.unit
    def test_run_id_shared_across_run(self, initialized_db_path):
        """A shared run_id groups several sections into one version (#776)."""
        from garmin_mcp.database.db_writer import GarminDBWriter

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(activity_id=999903, date="2025-09-22", conn=conn)
        conn.close()

        writer = GarminDBWriter(db_path=str(db_path))
        run_id = writer.next_run_id()
        for section in ("efficiency", "phase", "summary"):
            assert writer.insert_section_analysis(
                activity_id=999903,
                activity_date="2025-09-22",
                section_type=section,
                analysis_data={"note": section},
                run_id=run_id,
            )

        conn = duckdb.connect(str(db_path))
        run_ids = conn.execute(
            "SELECT DISTINCT run_id FROM section_analyses WHERE activity_id = 999903"
        ).fetchall()
        conn.close()
        # All three sections share the one run_id → a single version.
        assert run_ids == [(run_id,)]

    @pytest.mark.unit
    def test_reanalysis_increments_run_id(self, initialized_db_path):
        """A standalone re-analysis gets a new run_id, so it is its own version."""
        from garmin_mcp.database.db_writer import GarminDBWriter

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        insert_activities(activity_id=999904, date="2025-09-22", conn=conn)
        conn.close()

        writer = GarminDBWriter(db_path=str(db_path))
        # Two separate writes with no explicit run_id → two distinct run_ids.
        writer.insert_section_analysis(
            activity_id=999904,
            activity_date="2025-09-22",
            section_type="summary",
            analysis_data={"v": 1},
        )
        writer.insert_section_analysis(
            activity_id=999904,
            activity_date="2025-09-22",
            section_type="summary",
            analysis_data={"v": 2},
        )

        conn = duckdb.connect(str(db_path))
        run_ids = conn.execute(
            "SELECT run_id FROM section_analyses"
            " WHERE activity_id = 999904 ORDER BY analysis_id"
        ).fetchall()
        conn.close()
        assert run_ids[0][0] != run_ids[1][0]

    @pytest.mark.integration
    def test_migration_backfills_one_run_per_activity(self, tmp_path):
        """Migration 14 assigns each existing activity a single unique run_id."""
        from garmin_mcp.database.migrations.add_section_analysis_run_id import (
            add_section_analysis_run_id,
        )

        db_path = tmp_path / "legacy_run_id.duckdb"
        conn = duckdb.connect(str(db_path))
        # Legacy shape: no run_id column. Two activities, 3 sections each, with
        # per-section distinct timestamps (the exact pre-#776 situation).
        conn.execute("""
            CREATE TABLE section_analyses (
                analysis_id INTEGER PRIMARY KEY,
                activity_id BIGINT NOT NULL,
                activity_date DATE NOT NULL,
                section_type VARCHAR NOT NULL,
                analysis_data VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
        rows = [
            (1, 111, "2025-09-22 10:00:00.1", "efficiency"),
            (2, 111, "2025-09-22 10:00:00.2", "phase"),
            (3, 111, "2025-09-22 10:00:00.3", "summary"),
            (4, 222, "2025-09-23 10:00:00.1", "efficiency"),
            (5, 222, "2025-09-23 10:00:00.2", "phase"),
            (6, 222, "2025-09-23 10:00:00.3", "summary"),
        ]
        for analysis_id, activity_id, stamp, section in rows:
            conn.execute(
                "INSERT INTO section_analyses"
                " (analysis_id, activity_id, activity_date, section_type,"
                "  analysis_data, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [analysis_id, activity_id, "2025-09-22", section, "{}", stamp],
            )

        add_section_analysis_run_id(conn)

        # Each activity collapses to exactly one run_id, and the two differ.
        per_activity = conn.execute(
            "SELECT activity_id, COUNT(DISTINCT run_id)"
            " FROM section_analyses GROUP BY activity_id ORDER BY activity_id"
        ).fetchall()
        assert per_activity == [(111, 1), (222, 1)]
        distinct_runs = conn.execute(
            "SELECT COUNT(DISTINCT run_id) FROM section_analyses"
        ).fetchone()
        # A fresh run_id must allocate above the backfilled ones (no collision).
        next_run = conn.execute("SELECT nextval('seq_analysis_run_id')").fetchone()
        max_backfill = conn.execute(
            "SELECT MAX(run_id) FROM section_analyses"
        ).fetchone()
        conn.close()

        assert distinct_runs is not None and distinct_runs[0] == 2
        assert next_run is not None and max_backfill is not None
        assert next_run[0] > max_backfill[0]

    @pytest.mark.unit
    def test_next_run_id_persists_across_writer_instances(self, initialized_db_path):
        """A lone nextval used to evaporate on close; now it persists (#819).

        Writer A allocates N; a brand-new Writer B (fresh connection) must get
        N+1 — not N again, which was the pre-fix bug (all runs shared run_id 113).
        """
        from garmin_mcp.database.db_writer import GarminDBWriter

        db_path = initialized_db_path
        writer_a = GarminDBWriter(db_path=str(db_path))
        first = writer_a.next_run_id()

        writer_b = GarminDBWriter(db_path=str(db_path))
        second = writer_b.next_run_id()

        assert second == first + 1

    @pytest.mark.unit
    def test_next_run_id_records_analysis_run(self, initialized_db_path):
        """next_run_id() writes an auditable analysis_runs row (#819)."""
        from garmin_mcp.database.db_writer import GarminDBWriter

        db_path = initialized_db_path
        writer = GarminDBWriter(db_path=str(db_path))
        run_id = writer.next_run_id()

        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            "SELECT run_id, started_at FROM analysis_runs WHERE run_id = ?",
            [run_id],
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == run_id
        assert row[1] is not None

    @pytest.mark.integration
    def test_migration_splits_conflated_run_113(self, tmp_path):
        """Migration 18 splits the conflated run 113 into per-run clusters (#819).

        15 rows sharing run_id=113 in 3 created_at clusters (>1 min apart, 5
        sections each) → the oldest cluster keeps 113 and the next two become
        114 / 115. The sequence is re-advanced so the next allocation is 116.
        """
        from garmin_mcp.database.migrations.add_analysis_runs_table import (
            add_analysis_runs_table,
        )

        db_path = tmp_path / "conflated_run_113.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE section_analyses (
                analysis_id INTEGER PRIMARY KEY,
                activity_id BIGINT NOT NULL,
                activity_date DATE NOT NULL,
                section_type VARCHAR NOT NULL,
                analysis_data VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                run_id BIGINT
            )
            """)
        # Three clusters, >1 min apart; five sections per cluster (one run each),
        # all originally conflated onto run_id 113.
        sections = ("efficiency", "phase", "environment", "summary", "split")
        clusters = [
            ("2025-07-03 01:18:00", 700),  # oldest → keeps 113
            ("2025-07-04 13:58:00", 701),  # → 114
            ("2025-07-04 17:48:00", 702),  # → 115
        ]
        analysis_id = 1
        for base_ts, activity_id in clusters:
            base_minute = base_ts[:-2]  # strip seconds, keep "... HH:MM:"
            for i, section in enumerate(sections):
                stamp = f"{base_minute}{i:02d}.{i}"  # sub-second apart within run
                conn.execute(
                    "INSERT INTO section_analyses"
                    " (analysis_id, activity_id, activity_date, section_type,"
                    "  analysis_data, created_at, run_id)"
                    " VALUES (?, ?, ?, ?, ?, ?, 113)",
                    [analysis_id, activity_id, base_ts[:10], section, "{}", stamp],
                )
                analysis_id += 1

        add_analysis_runs_table(conn)

        # Each activity's five sections now carry a single distinct run_id, and
        # the oldest cluster keeps 113 while the others take 114 and 115.
        per_run = conn.execute(
            "SELECT run_id, COUNT(*) FROM section_analyses GROUP BY run_id"
            " ORDER BY run_id"
        ).fetchall()
        assert per_run == [(113, 5), (114, 5), (115, 5)]

        # The oldest cluster (activity 700) keeps 113.
        oldest = conn.execute(
            "SELECT DISTINCT run_id FROM section_analyses WHERE activity_id = 700"
        ).fetchall()
        assert oldest == [(113,)]

        # analysis_runs is backfilled with one row per distinct run_id.
        run_rows = conn.execute(
            "SELECT run_id FROM analysis_runs ORDER BY run_id"
        ).fetchall()
        assert run_rows == [(113,), (114,), (115,)]

        # The sequence is re-advanced above the highest run_id → next id is 116.
        next_run = conn.execute("SELECT nextval('seq_analysis_run_id')").fetchone()
        conn.close()
        assert next_run is not None and next_run[0] == 116
