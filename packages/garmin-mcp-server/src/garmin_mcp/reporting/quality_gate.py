"""Quality gate: advisory validation before report output.

Performs content quality checks on section analyses before report generation.
Failures are advisory (warning log + flag) rather than blocking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Patterns indicating zone deficit in efficiency evaluation
_ZONE_DEFICIT_PATTERNS = re.compile(r"不足|deficit|insufficient|低い比率")

# Patterns indicating ideal distribution in text
_IDEAL_DISTRIBUTION_PATTERNS = re.compile(r"理想的配分|理想的な配分|ideal distribution")

# Pattern for numbered list items (e.g., "1. xxx\n2. yyy")
_NUMBERED_LIST_PATTERN = re.compile(r"^\d+\.\s", re.MULTILINE)

# Pattern for numeric values (integers, decimals, ranges like 135-140)
_NUMERIC_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:\s*[-~]\s*\d+(?:\.\d+)?)?")


@dataclass
class QualityWarning:
    """A single quality gate warning."""

    check_name: str
    message: str
    severity: str = "warning"


@dataclass
class QualityResult:
    """Result of quality gate validation."""

    warnings: list[QualityWarning] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if no warnings were raised."""
        return len(self.warnings) == 0


class QualityGate:
    """Advisory quality gate for report content validation.

    Checks are advisory: failures produce warnings but do not block
    report generation. Warnings are logged and can be attached to the report.
    """

    def check_zone_contradiction(
        self, section_analyses: dict[str, Any]
    ) -> list[QualityWarning]:
        """Check for contradiction between zone deficit evaluation and ideal distribution text.

        If the efficiency section indicates a zone deficit but other sections
        describe the distribution as "ideal", that is a contradiction.
        """
        warnings: list[QualityWarning] = []

        efficiency = section_analyses.get("efficiency", {})
        if not efficiency:
            return warnings

        evaluation_text = efficiency.get("evaluation", "")
        if not _ZONE_DEFICIT_PATTERNS.search(evaluation_text):
            return warnings

        # Zone deficit detected -- check all text fields for contradiction
        for section_key, section_data in section_analyses.items():
            if not isinstance(section_data, dict):
                continue
            for field_key, field_value in section_data.items():
                if not isinstance(field_value, str):
                    continue
                if _IDEAL_DISTRIBUTION_PATTERNS.search(field_value):
                    warnings.append(
                        QualityWarning(
                            check_name="zone_contradiction",
                            message=(
                                f"矛盾検出: efficiency評価でZone不足を指摘しているが、"
                                f"{section_key}.{field_key}に「理想的配分」の記述あり"
                            ),
                        )
                    )

        return warnings

    def check_single_action(self, summary: dict[str, Any]) -> list[QualityWarning]:
        """Check that recommendations contain a single action, not multiple.

        Multiple numbered items (1. xxx, 2. yyy) indicate violation.
        """
        warnings: list[QualityWarning] = []

        recommendations = summary.get("recommendations", "")
        if not recommendations:
            return warnings

        numbered_items = _NUMBERED_LIST_PATTERN.findall(str(recommendations))
        if len(numbered_items) >= 2:
            warnings.append(
                QualityWarning(
                    check_name="single_action",
                    message=(
                        f"複数アクション検出: recommendationsに{len(numbered_items)}件の"
                        f"番号付きアクションが含まれています（単一であるべき）"
                    ),
                )
            )

        return warnings

    def check_numeric_action(self, summary: dict[str, Any]) -> list[QualityWarning]:
        """Check that recommendations contain specific numeric values.

        Generic advice without numbers (e.g., "practice more") is flagged.
        """
        warnings: list[QualityWarning] = []

        recommendations = summary.get("recommendations", "")
        if not recommendations:
            return warnings

        if not _NUMERIC_PATTERN.search(str(recommendations)):
            warnings.append(
                QualityWarning(
                    check_name="numeric_action",
                    message=(
                        "数値なしアクション検出: recommendationsに具体的な数値が"
                        "含まれていません（HR, ペース, ケイデンス等の数値が必要）"
                    ),
                )
            )

        return warnings

    def check_success_criterion(self, summary: dict[str, Any]) -> list[QualityWarning]:
        """Check that next_run_target has a success_criterion defined."""
        warnings: list[QualityWarning] = []

        next_run_target = summary.get("next_run_target")
        if not isinstance(next_run_target, dict):
            return warnings

        success_criterion = next_run_target.get("success_criterion")
        if not success_criterion or not str(success_criterion).strip():
            warnings.append(
                QualityWarning(
                    check_name="success_criterion",
                    message=(
                        "成功判定条件なし: next_run_targetにsuccess_criterionが"
                        "設定されていません"
                    ),
                )
            )

        return warnings

    def validate(self, section_analyses: dict[str, Any]) -> QualityResult:
        """Run all quality checks and return aggregated result.

        Args:
            section_analyses: Dict of section analyses keyed by section type.
                Must contain at minimum "efficiency" and "summary" sections.

        Returns:
            QualityResult with all collected warnings.
        """
        all_warnings: list[QualityWarning] = []

        # Check 1: Zone contradiction
        all_warnings.extend(self.check_zone_contradiction(section_analyses))

        # Checks 2-4 operate on the summary section
        summary = section_analyses.get("summary", {})
        if isinstance(summary, dict):
            all_warnings.extend(self.check_single_action(summary))
            all_warnings.extend(self.check_numeric_action(summary))
            all_warnings.extend(self.check_success_criterion(summary))

        result = QualityResult(warnings=all_warnings)

        if not result.passed:
            for w in result.warnings:
                logger.warning("QualityGate [%s]: %s", w.check_name, w.message)

        return result
