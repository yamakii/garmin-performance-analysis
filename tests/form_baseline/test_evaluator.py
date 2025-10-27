"""Tests for evaluator module.

This module tests the activity evaluation and storage functionality.
"""

from pathlib import Path

import pytest

from tools.form_baseline.evaluator import evaluate_and_store
from tools.form_baseline.scorer import compute_star_rating


class TestEvaluateAndStore:
    """Test cases for evaluate_and_store function."""

    def test_evaluate_and_store_basic(self, mocker):
        """Test basic evaluation flow with mocked dependencies."""
        # Mock _load_models_from_file
        mock_load_models = mocker.patch(
            "tools.form_baseline.evaluator._load_models_from_file"
        )
        mock_load_models.return_value = {
            "gct": mocker.Mock(),
            "vo": mocker.Mock(),
            "vr": mocker.Mock(),
        }

        # Mock _get_splits_data
        mock_get_splits = mocker.patch("tools.form_baseline.evaluator._get_splits_data")
        mock_get_splits.return_value = {
            "pace_s_per_km": 431.0,
            "gct_ms": 258.0,
            "vo_cm": 7.1,
            "vr_pct": 7.3,
            "cadence": 183.0,
        }

        # Mock score_observation
        mock_score = mocker.patch("tools.form_baseline.evaluator.score_observation")
        mock_score.return_value = {
            "pace": 431.0,
            "speed_mps": 2.32,
            "gct_ms_exp": 259.0,
            "vo_cm_exp": 7.0,
            "vr_pct_exp": 7.2,
            "gct_ms_actual": 258.0,
            "vo_cm_actual": 7.1,
            "vr_pct_actual": 7.3,
            "gct_delta_pct": -0.4,
            "gct_penalty": 2.0,
            "vo_delta_cm": 0.1,
            "vo_penalty": 2.0,
            "vr_delta_pct": 1.4,
            "vr_penalty": 2.0,
            "score": 99.3,
            "gct_needs_improvement": False,
            "vo_needs_improvement": False,
            "vr_needs_improvement": False,
        }

        # Mock compute_star_rating
        mock_star = mocker.patch("tools.form_baseline.evaluator.compute_star_rating")
        mock_star.return_value = {
            "star_rating": "★★★★★",
            "score": 5.0,
            "category": "excellent",
        }

        # Mock generate_evaluation_text
        mock_text = mocker.patch(
            "tools.form_baseline.evaluator.generate_evaluation_text"
        )
        mock_text.return_value = "評価文のテスト"

        # Mock generate_overall_text
        mock_overall = mocker.patch(
            "tools.form_baseline.evaluator.generate_overall_text"
        )
        mock_overall.return_value = "(総合評価: ★★★★★ 5.0/5.0)"

        # Call evaluate_and_store
        result = evaluate_and_store(
            activity_id=20790040925,
            activity_date="2025-10-25",
            db_path=":memory:",
            model_file=Path("/tmp/test_models.json"),
        )

        # Verify result structure
        assert result["activity_id"] == 20790040925
        assert "gct" in result
        assert "vo" in result
        assert "vr" in result
        assert "cadence" in result
        assert "overall_score" in result
        assert "overall_star_rating" in result

        # Verify GCT evaluation
        assert result["gct"]["actual"] == 258.0
        assert result["gct"]["expected"] == 259.0
        assert result["gct"]["evaluation_text"] == "評価文のテスト"

        # Verify cadence
        assert result["cadence"]["actual"] == 183.0
        assert result["cadence"]["achieved"] is True

    def test_evaluate_missing_splits(self, mocker):
        """Test error handling when splits data is missing."""
        # Mock _load_models_from_file to succeed
        mock_load_models = mocker.patch(
            "tools.form_baseline.evaluator._load_models_from_file"
        )
        mock_load_models.return_value = {
            "gct": mocker.Mock(),
            "vo": mocker.Mock(),
            "vr": mocker.Mock(),
        }

        # Mock _get_splits_data to raise ValueError
        mock_get_splits = mocker.patch("tools.form_baseline.evaluator._get_splits_data")
        mock_get_splits.side_effect = ValueError("No splits found for activity 999999")

        # This should raise ValueError
        with pytest.raises(ValueError, match="No splits found for activity"):
            evaluate_and_store(
                activity_id=999999,
                activity_date="2025-01-01",
                db_path=":memory:",
                model_file=Path("/tmp/test_models.json"),
            )

    def test_cadence_evaluation_achieved(self, mocker):
        """Test cadence evaluation when >= 180spm."""
        # Mock all dependencies
        mocker.patch(
            "tools.form_baseline.evaluator._load_models_from_file",
            return_value={
                "gct": mocker.Mock(),
                "vo": mocker.Mock(),
                "vr": mocker.Mock(),
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator._get_splits_data",
            return_value={
                "pace_s_per_km": 431.0,
                "gct_ms": 258.0,
                "vo_cm": 7.1,
                "vr_pct": 7.3,
                "cadence": 183.0,
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator.score_observation",
            return_value={
                "gct_ms_exp": 259.0,
                "vo_cm_exp": 7.0,
                "vr_pct_exp": 7.2,
                "gct_ms_actual": 258.0,
                "vo_cm_actual": 7.1,
                "vr_pct_actual": 7.3,
                "gct_delta_pct": -0.4,
                "gct_penalty": 2.0,
                "vo_delta_cm": 0.1,
                "vo_penalty": 2.0,
                "vr_delta_pct": 1.4,
                "vr_penalty": 2.0,
                "score": 99.3,
                "gct_needs_improvement": False,
                "vo_needs_improvement": False,
                "vr_needs_improvement": False,
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator.compute_star_rating",
            return_value={
                "star_rating": "★★★★★",
                "score": 5.0,
                "category": "excellent",
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator.generate_evaluation_text",
            return_value="Test text",
        )
        mocker.patch(
            "tools.form_baseline.evaluator.generate_overall_text",
            return_value="Overall text",
        )

        result = evaluate_and_store(
            activity_id=20790040925,
            activity_date="2025-10-25",
            db_path=":memory:",
            model_file=Path("/tmp/test.json"),
        )

        # Verify cadence achieved
        assert result["cadence"]["actual"] == 183.0
        assert result["cadence"]["achieved"] is True

    def test_cadence_evaluation_not_achieved(self, mocker):
        """Test cadence evaluation when < 180spm."""
        # Mock all dependencies
        mocker.patch(
            "tools.form_baseline.evaluator._load_models_from_file",
            return_value={
                "gct": mocker.Mock(),
                "vo": mocker.Mock(),
                "vr": mocker.Mock(),
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator._get_splits_data",
            return_value={
                "pace_s_per_km": 431.0,
                "gct_ms": 258.0,
                "vo_cm": 7.1,
                "vr_pct": 7.3,
                "cadence": 175.0,
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator.score_observation",
            return_value={
                "gct_ms_exp": 259.0,
                "vo_cm_exp": 7.0,
                "vr_pct_exp": 7.2,
                "gct_ms_actual": 258.0,
                "vo_cm_actual": 7.1,
                "vr_pct_actual": 7.3,
                "gct_delta_pct": -0.4,
                "gct_penalty": 2.0,
                "vo_delta_cm": 0.1,
                "vo_penalty": 2.0,
                "vr_delta_pct": 1.4,
                "vr_penalty": 2.0,
                "score": 99.3,
                "gct_needs_improvement": False,
                "vo_needs_improvement": False,
                "vr_needs_improvement": False,
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator.compute_star_rating",
            return_value={
                "star_rating": "★★★★★",
                "score": 5.0,
                "category": "excellent",
            },
        )
        mocker.patch(
            "tools.form_baseline.evaluator.generate_evaluation_text",
            return_value="Test text",
        )
        mocker.patch(
            "tools.form_baseline.evaluator.generate_overall_text",
            return_value="Overall text",
        )

        result = evaluate_and_store(
            activity_id=20790040925,
            activity_date="2025-10-25",
            db_path=":memory:",
            model_file=Path("/tmp/test.json"),
        )

        assert result["cadence"]["actual"] == 175.0
        assert result["cadence"]["achieved"] is False


class TestComputeStarRating:
    """Test cases for compute_star_rating function."""

    def test_star_rating_excellent(self):
        """Test 5-star rating for score >= 95."""
        rating = compute_star_rating(penalty=2.0, delta_pct=-1.3)
        assert rating["star_rating"] == "★★★★★"
        assert rating["score"] == 5.0
        assert rating["category"] == "excellent"

    def test_star_rating_good(self):
        """Test 4-star rating for score 85-95."""
        rating = compute_star_rating(penalty=12.0, delta_pct=-3.5)
        assert rating["star_rating"] == "★★★★☆"
        assert rating["score"] == 4.0
        assert rating["category"] == "good"

    def test_star_rating_average(self):
        """Test 3-star rating for score 75-85."""
        rating = compute_star_rating(penalty=25.0, delta_pct=15.0)
        assert rating["star_rating"] == "★★★☆☆"
        assert rating["score"] == 3.0
        assert rating["category"] == "average"

    def test_star_rating_below_average(self):
        """Test 2-star rating for score 65-75."""
        rating = compute_star_rating(penalty=45.0, delta_pct=25.0)
        assert rating["star_rating"] == "★★☆☆☆"
        assert rating["score"] == 2.0
        assert rating["category"] == "below_average"

    def test_star_rating_poor(self):
        """Test 1-star rating for score < 65."""
        rating = compute_star_rating(penalty=70.0, delta_pct=35.0)
        assert rating["star_rating"] == "★☆☆☆☆"
        assert rating["score"] == 1.0
        assert rating["category"] == "poor"
