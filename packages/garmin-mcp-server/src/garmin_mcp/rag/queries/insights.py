"""Insight extraction from section analyses using keyword-based search.

This module provides the InsightExtractor class for searching and extracting
insights from section analyses stored in DuckDB. Supports keyword-based search,
pagination, and token limiting.
"""

import json
from typing import Any

from garmin_mcp.database.db_reader import GarminDBReader


class InsightExtractor:
    """Extract insights from section analyses using keyword-based search.

    This class provides functionality to search section analyses by keywords
    (improvements, concerns, patterns) and extract relevant insights with
    pagination and token limiting support.

    Attributes:
        db_reader: GarminDBReader instance for database access.
    """

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize InsightExtractor.

        Args:
            db_path: Path to DuckDB database file. If None, uses default path.
        """
        self.db_reader = GarminDBReader(db_path)

    def search_by_keywords(
        self,
        keywords: list[str],
        section_types: list[str] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search section analyses by keywords.

        Searches for section analyses where the specified keywords (improvements,
        concerns, patterns) have non-empty values in the analysis_data JSON.

        Args:
            keywords: List of keywords to search for (e.g., ["improvements", "concerns"]).
            section_types: Optional list of section types to filter by.
            limit: Maximum number of results to return.
            offset: Number of results to skip (for pagination).

        Returns:
            List of section analysis records matching the search criteria.
            Each record contains:
                - activity_id: Activity ID
                - activity_date: Activity date
                - section_type: Section type
                - analysis_data: Parsed JSON analysis data

        Examples:
            >>> extractor = InsightExtractor()
            >>> # Search for improvements and concerns
            >>> results = extractor.search_by_keywords(
            ...     keywords=["improvements", "concerns"],
            ...     section_types=["efficiency"],
            ...     limit=5,
            ...     offset=0
            ... )
        """
        if not keywords:
            return []

        # Build WHERE clause for keyword filtering
        keyword_conditions = []
        for keyword in keywords:
            # Check if the keyword field exists and has a non-empty value.
            # Supports both array fields (key_strengths) and dict fields (efficiency).
            keyword_conditions.append(
                f"(json_extract(analysis_data, '$.{keyword}') IS NOT NULL AND "
                f"CAST(json_extract(analysis_data, '$.{keyword}') AS VARCHAR) NOT IN ('null', '[]', '{{}}', '\"\"'))"
            )

        where_clause = f"({' OR '.join(keyword_conditions)})"

        # Add section type filter if specified
        if section_types:
            section_filter = ", ".join([f"'{st}'" for st in section_types])
            where_clause += f" AND section_type IN ({section_filter})"

        # Execute query
        query = f"""
            SELECT
                activity_id,
                activity_date,
                section_type,
                analysis_data
            FROM section_analyses
            WHERE {where_clause}
            ORDER BY activity_date DESC, activity_id DESC, section_type
            LIMIT {limit}
            OFFSET {offset}
        """

        try:
            from garmin_mcp.database.connection import get_connection

            with get_connection(self.db_reader.db_path) as conn:
                results = conn.execute(query).fetchall()
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Error searching by keywords: {e}")
            return []

        # Parse JSON analysis_data
        parsed_results = []
        for row in results:
            parsed_row = {
                "activity_id": row[0],
                "activity_date": str(row[1]),
                "section_type": row[2],
                "analysis_data": (
                    json.loads(row[3]) if isinstance(row[3], str) else row[3]
                ),
            }
            parsed_results.append(parsed_row)

        return parsed_results

    def extract_insights(
        self,
        activity_id: int,
        keywords: list[str],
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Extract insights for a specific activity with optional token limiting.

        Args:
            activity_id: Activity ID to extract insights for.
            keywords: List of keywords to search for.
            max_tokens: Maximum number of tokens to return. If None, no limit.

        Returns:
            Dictionary containing:
                - insights: List of extracted insights
                - total_tokens: Total token count
                - truncated: Boolean indicating if results were truncated

        Examples:
            >>> extractor = InsightExtractor()
            >>> results = extractor.extract_insights(
            ...     activity_id=20594901208,
            ...     keywords=["improvements", "concerns"],
            ...     max_tokens=500
            ... )
            >>> print(results["total_tokens"])
            342
            >>> print(results["truncated"])
            False
        """
        # Build WHERE clause with activity_id filter
        if not keywords:
            return {"insights": [], "total_tokens": 0, "truncated": False}

        keyword_conditions = []
        for keyword in keywords:
            keyword_conditions.append(
                f"(json_extract(analysis_data, '$.{keyword}') IS NOT NULL AND "
                f"CAST(json_extract(analysis_data, '$.{keyword}') AS VARCHAR) NOT IN ('null', '[]', '{{}}', '\"\"'))"
            )

        where_clause = (
            f"activity_id = {activity_id} AND ({' OR '.join(keyword_conditions)})"
        )

        # Execute query
        query = f"""
            SELECT
                activity_id,
                activity_date,
                section_type,
                analysis_data
            FROM section_analyses
            WHERE {where_clause}
            ORDER BY section_type
        """

        try:
            from garmin_mcp.database.connection import get_connection

            with get_connection(self.db_reader.db_path) as conn:
                results = conn.execute(query).fetchall()
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Error extracting insights: {e}")
            return {"insights": [], "total_tokens": 0, "truncated": False}

        # Parse JSON analysis_data
        insights = []
        total_tokens = 0
        truncated = False

        for row in results:
            parsed_row = {
                "activity_id": row[0],
                "activity_date": str(row[1]),
                "section_type": row[2],
                "analysis_data": (
                    json.loads(row[3]) if isinstance(row[3], str) else row[3]
                ),
            }

            # Extract requested keyword data
            insight_data = {
                "section_type": parsed_row["section_type"],
            }

            for keyword in keywords:
                if keyword in parsed_row["analysis_data"]:
                    insight_data[keyword] = parsed_row["analysis_data"][keyword]

            # Calculate tokens for this insight
            insight_text = json.dumps(insight_data)
            insight_tokens = self._count_tokens(insight_text)

            # Check token limit
            if max_tokens is not None and total_tokens + insight_tokens > max_tokens:
                truncated = True
                break

            insights.append(insight_data)
            total_tokens += insight_tokens

        return {
            "insights": insights,
            "total_tokens": total_tokens,
            "truncated": truncated,
        }

    def _count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses a simple heuristic: ~1 token per 4 characters.

        Args:
            text: Text to count tokens for.

        Returns:
            Estimated token count.
        """
        return len(text) // 4
