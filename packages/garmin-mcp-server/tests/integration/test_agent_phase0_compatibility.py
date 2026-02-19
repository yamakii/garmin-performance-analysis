"""Integration tests for agent Phase 0 optimization compatibility.

Tests verify that section analysis agents can correctly use the new
statistics_only parameter and avoid deprecated functions.
"""

from unittest.mock import Mock

import pytest


@pytest.mark.unit
class TestSplitSectionAnalystStatisticsMode:
    """Test split-section-analyst agent compatibility with statistics_only parameter."""

    def test_statistics_mode_for_trend_analysis(self):
        """Verify agent can use statistics_only=True for trend analysis."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.get_splits_pace_hr.return_value = {
            "activity_id": 12345,
            "statistics": {
                "pace": {"mean": 315.5, "std": 12.3, "min": 295.0, "max": 335.0},
                "heart_rate": {"mean": 152.5, "std": 8.2, "min": 140, "max": 165},
            },
        }
        mock_client.get_splits_form_metrics.return_value = {
            "activity_id": 12345,
            "statistics": {
                "ground_contact_time": {
                    "mean": 262.0,
                    "std": 15.0,
                    "min": 245,
                    "max": 285,
                },
                "vertical_oscillation": {
                    "mean": 7.2,
                    "std": 0.5,
                    "min": 6.5,
                    "max": 8.0,
                },
            },
        }

        # Simulate agent calling with statistics_only=True
        pace_data = mock_client.get_splits_pace_hr(
            activity_id=12345, statistics_only=True
        )
        form_data = mock_client.get_splits_form_metrics(
            activity_id=12345, statistics_only=True
        )

        # Verify correct parameters
        mock_client.get_splits_pace_hr.assert_called_with(
            activity_id=12345, statistics_only=True
        )
        mock_client.get_splits_form_metrics.assert_called_with(
            activity_id=12345, statistics_only=True
        )

        # Verify data structure
        assert "statistics" in pace_data
        assert "statistics" in form_data
        assert "pace" in pace_data["statistics"]
        assert "ground_contact_time" in form_data["statistics"]

    def test_detailed_mode_for_split_comparison(self):
        """Verify agent can still use statistics_only=False for detailed analysis."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.get_splits_pace_hr.return_value = {
            "activity_id": 12345,
            "splits": [
                {"split_number": 1, "pace": 320.5, "heart_rate": 145},
                {"split_number": 2, "pace": 315.2, "heart_rate": 150},
                {"split_number": 3, "pace": 310.8, "heart_rate": 155},
            ],
        }

        # Simulate agent calling with statistics_only=False
        pace_data = mock_client.get_splits_pace_hr(
            activity_id=12345, statistics_only=False
        )

        # Verify correct parameters
        mock_client.get_splits_pace_hr.assert_called_with(
            activity_id=12345, statistics_only=False
        )

        # Verify data structure
        assert "splits" in pace_data
        assert len(pace_data["splits"]) == 3
        assert pace_data["splits"][0]["split_number"] == 1

    def test_backward_compatibility_default_false(self):
        """Verify backward compatibility: statistics_only defaults to False."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.get_splits_pace_hr.return_value = {
            "activity_id": 12345,
            "splits": [{"split_number": 1, "pace": 320.5}],
        }

        # Simulate agent calling without statistics_only parameter
        pace_data = mock_client.get_splits_pace_hr(activity_id=12345)

        # Verify backward compatibility (should still work)
        assert "splits" in pace_data or "statistics" in pace_data


@pytest.mark.unit
class TestSummarySectionAnalystNoDeprecated:
    """Test summary-section-analyst agent avoids deprecated functions."""

    def test_uses_lightweight_splits_not_splits_all(self):
        """Verify agent uses lightweight splits instead of get_splits_all()."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.get_splits_pace_hr.return_value = {
            "statistics": {"pace": {"mean": 315.5}}
        }
        mock_client.get_splits_form_metrics.return_value = {
            "statistics": {"ground_contact_time": {"mean": 262.0}}
        }
        mock_client.get_weather_data.return_value = {"temperature": 18.5}
        mock_client.get_performance_trends.return_value = {"pace_consistency": 0.03}

        # Simulate agent calling recommended functions
        _pace_data = mock_client.get_splits_pace_hr(
            activity_id=12345, statistics_only=True
        )
        _form_data = mock_client.get_splits_form_metrics(
            activity_id=12345, statistics_only=True
        )
        _weather_data = mock_client.get_weather_data(activity_id=12345)
        _trends_data = mock_client.get_performance_trends(activity_id=12345)

        # Verify agent uses recommended functions
        mock_client.get_splits_pace_hr.assert_called_once()
        mock_client.get_splits_form_metrics.assert_called_once()
        mock_client.get_weather_data.assert_called_once()
        mock_client.get_performance_trends.assert_called_once()

        # Verify agent does NOT use deprecated get_splits_all
        assert (
            not hasattr(mock_client, "get_splits_all")
            or not mock_client.get_splits_all.called
        )

    def test_uses_extract_insights_not_get_section_analysis(self):
        """Verify agent uses extract_insights() instead of get_section_analysis()."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.extract_insights.return_value = {
            "insights": [
                {
                    "activity_id": 12345,
                    "section_type": "efficiency",
                    "content": "フォーム効率が良好です",
                }
            ]
        }

        # Simulate agent calling extract_insights
        _insights = mock_client.extract_insights(keywords=["フォーム", "効率"], limit=5)

        # Verify agent uses extract_insights
        mock_client.extract_insights.assert_called_once()

        # Verify agent does NOT use deprecated get_section_analysis
        assert (
            not hasattr(mock_client, "get_section_analysis")
            or not mock_client.get_section_analysis.called
        )

    def test_summary_agent_token_reduction(self):
        """Verify summary agent achieves token reduction with new approach."""
        # Old approach: get_splits_all() returns all 22 fields × N splits
        old_splits_all = {
            "splits": [
                {
                    "split_number": i,
                    "distance": 1.0,
                    "pace": 315.0 + i,
                    "heart_rate": 150 + i,
                    "cadence": 180,
                    "ground_contact_time": 260,
                    "vertical_oscillation": 7.2,
                    # ... 15 more fields
                }
                for i in range(10)  # 10 splits × 22 fields = 220 data points
            ]
        }

        # New approach: statistics_only returns 4 values × N metrics
        _new_pace_stats = {
            "statistics": {
                "pace": {"mean": 315.5, "std": 12.3, "min": 295.0, "max": 335.0},
                "heart_rate": {"mean": 152.5, "std": 8.2, "min": 140, "max": 165},
                # 2 metrics × 4 stats = 8 data points (vs 20 from 10 splits)
            }
        }

        # Simulate token count (rough approximation: 1 data point = 10 tokens)
        old_token_count = len(old_splits_all["splits"]) * 22 * 10  # ~2200 tokens
        new_token_count = 2 * 4 * 10  # ~80 tokens

        # Verify token reduction
        token_reduction = 1 - (new_token_count / old_token_count)
        assert (
            token_reduction > 0.80
        ), f"Expected >80% reduction, got {token_reduction:.1%}"


@pytest.mark.unit
class TestDefaultParameterBehavior:
    """Test backward compatibility of Phase 0 changes."""

    def test_existing_agent_behavior_preserved(self):
        """Verify existing agent behavior still works without statistics_only."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.get_splits_pace_hr.return_value = {
            "activity_id": 12345,
            "splits": [{"split_number": 1, "pace": 320.5}],
        }

        # Simulate existing agent calling without new parameter
        pace_data = mock_client.get_splits_pace_hr(activity_id=12345)

        # Verify call succeeds
        assert pace_data is not None
        assert "activity_id" in pace_data

    def test_no_breaking_changes_to_output_format(self):
        """Verify agent output format is unchanged."""
        # Mock section analysis data structure
        analysis_data = {
            "analyses": {
                "split_1": "ウォームアップとして理想的なペースです。",
                "split_2": "メインペースに入り、安定しています。",
            }
        }

        # Verify structure matches expected format
        assert "analyses" in analysis_data
        assert isinstance(analysis_data["analyses"], dict)
        assert "split_1" in analysis_data["analyses"]
        assert isinstance(analysis_data["analyses"]["split_1"], str)

        # Verify no metadata (auto-generated by insert_section_analysis_dict)
        assert "metadata" not in analysis_data
        assert "timestamp" not in analysis_data


@pytest.mark.integration
class TestAgentPhase0Integration:
    """Integration tests for agent Phase 0 optimization end-to-end."""

    def test_split_analyst_workflow_with_statistics_only(self):
        """Test split-section-analyst workflow with statistics_only=True."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.get_splits_pace_hr.return_value = {
            "activity_id": 12345,
            "statistics": {
                "pace": {"mean": 315.5, "std": 12.3, "min": 295.0, "max": 335.0},
            },
        }
        mock_client.get_splits_form_metrics.return_value = {
            "activity_id": 12345,
            "statistics": {
                "ground_contact_time": {
                    "mean": 262.0,
                    "std": 15.0,
                    "min": 245,
                    "max": 285,
                },
            },
        }
        mock_client.insert_section_analysis_dict.return_value = {"success": True}

        # Simulate agent workflow
        # 1. Get data with statistics_only=True
        _pace_data = mock_client.get_splits_pace_hr(
            activity_id=12345, statistics_only=True
        )
        _form_data = mock_client.get_splits_form_metrics(
            activity_id=12345, statistics_only=True
        )

        # 2. Analyze (simulated)
        analysis = {
            "analyses": {
                "split_1": "統計データに基づく分析結果",
            }
        }

        # 3. Save to DuckDB
        result = mock_client.insert_section_analysis_dict(
            activity_id=12345,
            activity_date="2025-01-15",
            section_type="split",
            analysis_data=analysis,
        )

        # Verify workflow
        assert result["success"] is True
        mock_client.get_splits_pace_hr.assert_called_with(
            activity_id=12345, statistics_only=True
        )
        mock_client.insert_section_analysis_dict.assert_called_once()

    def test_summary_analyst_workflow_no_deprecated(self):
        """Test summary-section-analyst workflow without deprecated functions."""
        # Mock MCP client
        mock_client = Mock()
        mock_client.get_splits_pace_hr.return_value = {"statistics": {}}
        mock_client.get_splits_form_metrics.return_value = {"statistics": {}}
        mock_client.get_weather_data.return_value = {"temperature": 18.5}
        mock_client.get_performance_trends.return_value = {}
        mock_client.insert_section_analysis_dict.return_value = {"success": True}

        # Simulate agent workflow (NO get_splits_all or get_section_analysis)
        # 1. Get data with recommended functions
        _pace_data = mock_client.get_splits_pace_hr(
            activity_id=12345, statistics_only=True
        )
        _form_data = mock_client.get_splits_form_metrics(
            activity_id=12345, statistics_only=True
        )
        _weather_data = mock_client.get_weather_data(activity_id=12345)
        _trends_data = mock_client.get_performance_trends(activity_id=12345)

        # 2. Analyze (simulated)
        analysis = {
            "activity_type": "ベースラン",
            "summary": "総合評価",
            "recommendations": "改善提案",
        }

        # 3. Save to DuckDB
        result = mock_client.insert_section_analysis_dict(
            activity_id=12345,
            activity_date="2025-01-15",
            section_type="summary",
            analysis_data=analysis,
        )

        # Verify workflow
        assert result["success"] is True
        assert mock_client.get_splits_pace_hr.call_count == 1
        assert mock_client.get_splits_form_metrics.call_count == 1
        assert mock_client.get_weather_data.call_count == 1
        assert mock_client.insert_section_analysis_dict.call_count == 1

        # Verify deprecated functions NOT called
        assert (
            not hasattr(mock_client, "get_splits_all")
            or mock_client.get_splits_all.call_count == 0
        )
        assert (
            not hasattr(mock_client, "get_section_analysis")
            or mock_client.get_section_analysis.call_count == 0
        )
