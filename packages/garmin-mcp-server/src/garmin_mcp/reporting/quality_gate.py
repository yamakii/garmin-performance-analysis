"""
Quality Gate - Advisory validation before report generation.

Performs 5 quality checks on section analyses before generating reports.
All checks are advisory (warnings only, never blocking).
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QualityWarning:
    """A single quality gate warning."""

    check_name: str
    message: str
    section: str | None = None


@dataclass
class QualityGateResult:
    """Result of quality gate validation."""

    warnings: list[QualityWarning] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if no warnings were raised."""
        return len(self.warnings) == 0


# Patterns indicating zone insufficiency
_ZONE_INSUFFICIENCY_PATTERNS = [
    re.compile(r"zone\s*\d?\s*不足", re.IGNORECASE),
    re.compile(r"ゾーン\s*\d?\s*不足"),
    re.compile(r"zone\s*\d?\s*が.*低", re.IGNORECASE),
    re.compile(r"ゾーン\s*\d?\s*が.*低"),
    re.compile(r"zone\s*\d?\s*の.*割合.*不十分", re.IGNORECASE),
]

# Patterns indicating ideal zone distribution
_IDEAL_DISTRIBUTION_PATTERNS = [
    re.compile(r"理想的.*配分"),
    re.compile(r"理想的.*分布"),
    re.compile(r"理想的.*バランス"),
]

# Pattern for detecting numeric values in text
_NUMERIC_PATTERN = re.compile(r"\d+\.?\d*")

# Delimiters that indicate multiple actions
_MULTI_ACTION_DELIMITERS = ["\n", "。", "；", ";"]


class QualityGate:
    """Advisory quality gate for analysis reports.

    Performs validation checks on section analyses and returns warnings.
    Warnings are advisory only -- they never block report generation.
    """

    def validate(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> QualityGateResult:
        """Run all quality checks and return aggregated result.

        Args:
            section_analyses: Dict of section_type -> analysis_data

        Returns:
            QualityGateResult with all warnings collected
        """
        result = QualityGateResult()

        result.warnings.extend(self.check_zone_contradiction(section_analyses))
        result.warnings.extend(self.check_single_action(section_analyses))
        result.warnings.extend(self.check_numeric_action(section_analyses))
        result.warnings.extend(self.check_success_criterion(section_analyses))

        if result.warnings:
            for w in result.warnings:
                logger.warning("Quality gate warning [%s]: %s", w.check_name, w.message)

        return result

    def check_zone_contradiction(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[QualityWarning]:
        """Check for contradiction between zone insufficiency and ideal distribution.

        Detects when one section says zones are insufficient while another
        says the distribution is ideal.

        Returns:
            List of warnings (empty if no contradiction found)
        """
        all_text = _extract_all_text(section_analyses)

        has_insufficiency = any(
            p.search(all_text) for p in _ZONE_INSUFFICIENCY_PATTERNS
        )
        has_ideal = any(p.search(all_text) for p in _IDEAL_DISTRIBUTION_PATTERNS)

        if has_insufficiency and has_ideal:
            return [
                QualityWarning(
                    check_name="zone_contradiction",
                    message="Zone不足の評価と「理想的配分」の記述が共存しています",
                )
            ]
        return []

    def check_single_action(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[QualityWarning]:
        """Check that next_action contains only a single action item.

        Returns:
            List of warnings (empty if single action or no next_action)
        """
        next_action = _find_field(section_analyses, "next_action")
        if next_action is None:
            return []

        action_text = str(next_action).strip()
        if not action_text:
            return []

        # Count actions by splitting on delimiters
        action_count = _count_actions(action_text)

        if action_count > 1:
            return [
                QualityWarning(
                    check_name="multiple_actions",
                    message=f"次回アクションが{action_count}つ含まれています（1つに絞ってください）",
                )
            ]
        return []

    def check_numeric_action(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[QualityWarning]:
        """Check that next_action contains specific numeric values.

        Returns:
            List of warnings (empty if numeric values present or no next_action)
        """
        next_action = _find_field(section_analyses, "next_action")
        if next_action is None:
            return []

        action_text = str(next_action).strip()
        if not action_text:
            return []

        if not _NUMERIC_PATTERN.search(action_text):
            return [
                QualityWarning(
                    check_name="no_numeric_action",
                    message="次回アクションに具体的な数値が含まれていません",
                )
            ]
        return []

    def check_success_criterion(
        self, section_analyses: dict[str, dict[str, Any]]
    ) -> list[QualityWarning]:
        """Check that success_criterion is defined.

        Returns:
            List of warnings (empty if success_criterion is present)
        """
        success_criterion = _find_field(section_analyses, "success_criterion")

        if success_criterion is None or str(success_criterion).strip() == "":
            return [
                QualityWarning(
                    check_name="missing_success_criterion",
                    message="成功判定条件（success_criterion）が設定されていません",
                )
            ]
        return []


def _extract_all_text(section_analyses: dict[str, dict[str, Any]]) -> str:
    """Recursively extract all string values from section analyses."""
    texts: list[str] = []
    _collect_strings(section_analyses, texts)
    return " ".join(texts)


def _collect_strings(obj: Any, texts: list[str]) -> None:
    """Recursively collect string values from nested structures."""
    if isinstance(obj, str):
        texts.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, texts)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings(item, texts)


def _find_field(
    section_analyses: dict[str, dict[str, Any]], field_name: str
) -> Any | None:
    """Find a field by name across all sections.

    Searches top-level keys in each section's analysis data.
    Returns the first match found, or None.
    """
    for section_data in section_analyses.values():
        if isinstance(section_data, dict) and field_name in section_data:
            return section_data[field_name]
    return None


def _count_actions(text: str) -> int:
    """Count the number of distinct action items in text.

    Splits by common delimiters (newlines, periods, semicolons)
    and counts non-empty segments.
    """
    # Split by any of the delimiters
    segments = [text]
    for delimiter in _MULTI_ACTION_DELIMITERS:
        new_segments: list[str] = []
        for seg in segments:
            new_segments.extend(seg.split(delimiter))
        segments = new_segments

    # Count non-empty, non-trivial segments
    meaningful = [s.strip() for s in segments if s.strip()]
    return len(meaningful)
