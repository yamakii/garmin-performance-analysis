"""Advisory quality gate for analysis reports.

Validates section analyses content quality before report generation.
Advisory only — never blocks report generation.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    """Result of quality gate validation."""

    passed: bool
    warnings: list[str] = field(default_factory=list)


class QualityGate:
    """Advisory quality gate that checks analysis content before report generation."""

    def validate(self, section_analyses: dict[str, dict[str, Any]]) -> QualityResult:
        """Run all quality checks and return aggregated result."""
        warnings: list[str] = []

        warnings.extend(self.check_zone_contradiction(section_analyses))
        warnings.extend(self.check_single_action(section_analyses))
        warnings.extend(self.check_numeric_action(section_analyses))
        warnings.extend(self.check_success_criterion(section_analyses))

        return QualityResult(passed=len(warnings) == 0, warnings=warnings)

    def check_zone_contradiction(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[str]:
        """Check for contradictions between zone evaluation and zone description.

        If zone distribution evaluation indicates insufficient coverage,
        the text should NOT contain "理想的配分" (ideal distribution).
        """
        warnings: list[str] = []
        efficiency = section_analyses.get("efficiency", {})
        if not efficiency:
            return warnings

        evaluation = efficiency.get("evaluation", "")
        if not isinstance(evaluation, str):
            return warnings

        insufficient_keywords = [
            "不足",
            "偏り",
            "過多",
            "改善",
            "課題",
        ]
        has_insufficient = any(kw in evaluation for kw in insufficient_keywords)

        if has_insufficient and "理想的配分" in evaluation:
            warnings.append(
                "Zone contradiction: evaluation indicates insufficient zone coverage "
                "but also mentions '理想的配分' (ideal distribution)"
            )

        return warnings

    def check_single_action(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[str]:
        """Check that recommendations have at most 1 next action item."""
        warnings: list[str] = []
        summary = section_analyses.get("summary", {})
        if not summary:
            return warnings

        recommendations = summary.get("recommendations", [])
        if not isinstance(recommendations, list):
            return warnings

        next_actions = [
            r for r in recommendations if isinstance(r, str) and "次回" in r
        ]

        if len(next_actions) > 1:
            warnings.append(
                f"Multiple next actions: found {len(next_actions)} "
                f"items containing '次回' in recommendations (max 1)"
            )

        return warnings

    def check_numeric_action(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[str]:
        """Check that next action contains specific numbers."""
        warnings: list[str] = []
        summary = section_analyses.get("summary", {})
        if not summary:
            return warnings

        recommendations = summary.get("recommendations", [])
        if not isinstance(recommendations, list):
            return warnings

        next_actions = [
            r for r in recommendations if isinstance(r, str) and "次回" in r
        ]

        if not next_actions:
            return warnings

        for action in next_actions:
            if not re.search(r"\d", action):
                warnings.append(
                    "Non-numeric next action: next action should contain "
                    "specific numbers, not vague advice"
                )
                break

        return warnings

    def check_success_criterion(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[str]:
        """Check that a success criterion is present."""
        warnings: list[str] = []
        summary = section_analyses.get("summary", {})
        if not summary:
            return warnings

        recommendations = summary.get("recommendations", [])
        if not isinstance(recommendations, list):
            return warnings

        next_actions = [
            r for r in recommendations if isinstance(r, str) and "次回" in r
        ]

        if not next_actions:
            return warnings

        success_keywords = ["成功", "達成", "目標", "判定", "基準", "クリア"]
        has_criterion = any(
            any(kw in action for kw in success_keywords) for action in next_actions
        )

        if not has_criterion:
            warnings.append(
                "Missing success criterion: next action should include "
                "an explicit success/achievement criterion"
            )

        return warnings
