"""Tests for InsightExtractor."""

from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.rag.queries.insights import InsightExtractor


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary DuckDB database with sample section analyses."""
    import duckdb

    from garmin_mcp.database.db_writer import GarminDBWriter
    from garmin_mcp.database.inserters.activities import insert_activities

    db_file = tmp_path / "test_garmin.db"
    db_writer = GarminDBWriter(str(db_file))  # Initialize schema

    # First, insert activities to satisfy foreign key constraint
    sample_activities: list[dict[str, Any]] = [
        {
            "activity_id": 20594901208,
            "date": "2025-10-05",
            "distance": 10.0,
            "duration": 3600,
        },
        {
            "activity_id": 20615445009,
            "date": "2025-10-07",
            "distance": 12.0,
            "duration": 4200,
        },
    ]

    conn = duckdb.connect(str(db_file))
    for activity in sample_activities:
        insert_activities(
            activity_id=int(activity["activity_id"]),
            date=str(activity["date"]),
            conn=conn,
        )
    conn.close()

    # Insert sample section analyses with actual agent output field names
    sample_analyses: list[dict[str, Any]] = [
        {
            "activity_id": 20594901208,
            "activity_date": "2025-10-05",
            "section_type": "efficiency",
            "analysis_data": {
                "evaluation": {
                    "gct": "Good ground contact time",
                    "vo": "Normal vertical oscillation",
                },
                "key_strengths": ["Improved ground contact time by 5ms"],
                "improvement_areas": [],
                "efficiency": {"hr_zone_distribution": "Zone 2 dominant"},
            },
        },
        {
            "activity_id": 20594901208,
            "activity_date": "2025-10-05",
            "section_type": "phase",
            "analysis_data": {
                "evaluation": {"warmup": "Good", "main": "Strong"},
                "key_strengths": ["Better negative split execution"],
                "improvement_areas": ["Slight HR drift in final phase"],
            },
        },
        {
            "activity_id": 20615445009,
            "activity_date": "2025-10-07",
            "section_type": "efficiency",
            "analysis_data": {
                "evaluation": {
                    "gct": "Degraded",
                    "vo": "High vertical oscillation",
                },
                "key_strengths": [],
                "improvement_areas": [
                    "Vertical oscillation increased by 2cm",
                    "Cadence drop in final km",
                ],
                "efficiency": {"hr_zone_distribution": "Zone 3 heavy"},
            },
        },
        {
            "activity_id": 20615445009,
            "activity_date": "2025-10-07",
            "section_type": "environment",
            "analysis_data": {
                "environmental_impact": "Hot weather reduced performance",
                "key_strengths": [],
                "improvement_areas": ["Temperature 32°C affected performance"],
            },
        },
    ]

    for analysis in sample_analyses:
        db_writer.insert_section_analysis(
            activity_id=int(analysis["activity_id"]),
            activity_date=str(analysis["activity_date"]),
            section_type=str(analysis["section_type"]),
            analysis_data=dict(analysis["analysis_data"]),  # Pass dict, not JSON string
        )

    return db_file


@pytest.fixture
def extractor(db_path: Path) -> InsightExtractor:
    """Create an InsightExtractor instance."""
    return InsightExtractor(str(db_path))


@pytest.mark.integration
class TestInsightExtractorBasics:
    """Test basic functionality of InsightExtractor."""

    def test_initialization(self, db_path: Path) -> None:
        """Test InsightExtractor initialization."""
        extractor = InsightExtractor(str(db_path))
        assert extractor is not None

    def test_search_by_keywords_key_strengths(
        self, extractor: InsightExtractor
    ) -> None:
        """Test searching for key_strengths keyword."""
        results = extractor.search_by_keywords(
            keywords=["key_strengths"],
            section_types=None,
            limit=10,
            offset=0,
        )

        assert len(results) > 0
        # Should find entries with non-empty key_strengths
        assert any("key_strengths" in r["analysis_data"] for r in results)

    def test_search_by_keywords_improvement_areas(
        self, extractor: InsightExtractor
    ) -> None:
        """Test searching for improvement_areas keyword."""
        results = extractor.search_by_keywords(
            keywords=["improvement_areas"],
            section_types=None,
            limit=10,
            offset=0,
        )

        assert len(results) > 0
        # Should find entries with non-empty improvement_areas
        assert any("improvement_areas" in r["analysis_data"] for r in results)

    def test_search_by_keywords_evaluation(self, extractor: InsightExtractor) -> None:
        """Test searching for evaluation keyword (dict field)."""
        results = extractor.search_by_keywords(
            keywords=["evaluation"],
            section_types=None,
            limit=10,
            offset=0,
        )

        assert len(results) > 0
        # Should find entries with non-empty evaluation dict
        assert any("evaluation" in r["analysis_data"] for r in results)


@pytest.mark.integration
class TestInsightExtractorFiltering:
    """Test filtering capabilities of InsightExtractor."""

    def test_filter_by_section_type(self, extractor: InsightExtractor) -> None:
        """Test filtering by section type."""
        results = extractor.search_by_keywords(
            keywords=["key_strengths", "improvement_areas", "evaluation"],
            section_types=["efficiency"],
            limit=10,
            offset=0,
        )

        assert len(results) > 0
        # All results should be efficiency sections
        assert all(r["section_type"] == "efficiency" for r in results)

    def test_filter_by_multiple_section_types(
        self, extractor: InsightExtractor
    ) -> None:
        """Test filtering by multiple section types."""
        results = extractor.search_by_keywords(
            keywords=["key_strengths", "improvement_areas", "evaluation"],
            section_types=["efficiency", "phase"],
            limit=10,
            offset=0,
        )

        assert len(results) > 0
        # All results should be either efficiency or phase sections
        assert all(r["section_type"] in ["efficiency", "phase"] for r in results)


@pytest.mark.integration
class TestInsightExtractorPagination:
    """Test pagination functionality of InsightExtractor."""

    def test_pagination_limit(self, extractor: InsightExtractor) -> None:
        """Test limit parameter."""
        results = extractor.search_by_keywords(
            keywords=["key_strengths", "improvement_areas", "evaluation"],
            section_types=None,
            limit=2,
            offset=0,
        )

        assert len(results) <= 2

    def test_pagination_offset(self, extractor: InsightExtractor) -> None:
        """Test offset parameter."""
        # Get first 2 results
        first_batch = extractor.search_by_keywords(
            keywords=["key_strengths", "improvement_areas", "evaluation"],
            section_types=None,
            limit=2,
            offset=0,
        )

        # Get next 2 results
        second_batch = extractor.search_by_keywords(
            keywords=["key_strengths", "improvement_areas", "evaluation"],
            section_types=None,
            limit=2,
            offset=2,
        )

        # Should be different results
        if len(first_batch) > 0 and len(second_batch) > 0:
            assert (
                first_batch[0]["activity_id"] != second_batch[0]["activity_id"]
                or first_batch[0]["section_type"] != second_batch[0]["section_type"]
            )


@pytest.mark.integration
class TestInsightExtractorTokenLimit:
    """Test token limiting functionality of InsightExtractor."""

    def test_extract_insights_with_token_limit(
        self, extractor: InsightExtractor
    ) -> None:
        """Test extract_insights with max_tokens limit."""
        results = extractor.extract_insights(
            activity_id=20594901208,
            keywords=["key_strengths", "improvement_areas", "evaluation"],
            max_tokens=100,
        )

        # Should return results
        assert "insights" in results
        assert "total_tokens" in results
        assert "truncated" in results

        # Token count should be under limit
        assert results["total_tokens"] <= 100

    def test_extract_insights_no_token_limit(self, extractor: InsightExtractor) -> None:
        """Test extract_insights without token limit."""
        results = extractor.extract_insights(
            activity_id=20594901208,
            keywords=["key_strengths", "improvement_areas", "evaluation"],
            max_tokens=None,
        )

        # Should return all insights
        assert "insights" in results
        assert "total_tokens" in results
        assert results["truncated"] is False

    def test_count_tokens(self, extractor: InsightExtractor) -> None:
        """Test token counting method."""
        text = "This is a test string with multiple words."
        token_count = extractor._count_tokens(text)

        # Rough estimate: ~1 token per 4 characters
        assert token_count > 0
        assert token_count <= len(text)


@pytest.mark.integration
class TestInsightExtractorEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_keywords(self, extractor: InsightExtractor) -> None:
        """Test with empty keywords list."""
        results = extractor.search_by_keywords(
            keywords=[],
            section_types=None,
            limit=10,
            offset=0,
        )

        # Should return empty results
        assert len(results) == 0

    def test_nonexistent_activity(self, extractor: InsightExtractor) -> None:
        """Test extract_insights for non-existent activity."""
        results = extractor.extract_insights(
            activity_id=99999999999,
            keywords=["key_strengths"],
            max_tokens=None,
        )

        # Should return empty insights
        assert results["insights"] == []
        assert results["total_tokens"] == 0
        assert results["truncated"] is False

    def test_nonexistent_section_type(self, extractor: InsightExtractor) -> None:
        """Test filtering by non-existent section type."""
        results = extractor.search_by_keywords(
            keywords=["key_strengths"],
            section_types=["nonexistent"],
            limit=10,
            offset=0,
        )

        # Should return empty results
        assert len(results) == 0
