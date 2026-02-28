"""
Advisory quality gate for analysis reports.

Validates analysis sections against evaluation principles
(see .claude/rules/evaluation-principles.md). All checks are advisory:
warnings are collected but never block report generation.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Patterns indicating numeric specificity in Japanese text
_NUMERIC_PATTERNS = [
    re.compile(r"\d+\s*[-~〜]\s*\d+\s*(bpm|km|m|秒|分|%|W)"),  # range: 135-140 bpm
    re.compile(r"\d+\s*(bpm|km|m|秒|分|%|W|sec|min)"),  # single: 140 bpm
    re.compile(r"\d+:\d{2}"),  # pace: 5:30
    re.compile(r"Zone\s*\d", re.IGNORECASE),  # Zone 2
]

# Patterns indicating success criterion
_SUCCESS_CRITERION_PATTERNS = [
    re.compile(r"成功"),
    re.compile(r"達成"),
    re.compile(r"判定"),
    re.compile(r"クリア"),
    re.compile(r"目標"),
    re.compile(r"超えたら|超なら|以上なら|以下なら|未満なら"),
]

# Zone insufficiency keywords
_ZONE_INSUFFICIENT_KEYWORDS = [
    "不足",
    "少ない",
    "低い割合",
    "配分が偏",
    "偏り",
    "改善が必要",
]

# Zone ideal keywords (contradicts insufficiency)
_ZONE_IDEAL_KEYWORDS = [
    "理想的配分",
    "理想的な配分",
    "理想的なゾーン",
    "バランスの良い",
    "バランスが良い",
    "適切な配分",
]


class QualityGate:
    """Advisory validation for analysis reports."""

    def validate(self, analysis_sections: dict[str, Any]) -> dict[str, Any]:
        """
        Run all quality checks on merged analysis sections.

        Args:
            analysis_sections: Dict of section_type -> analysis_data

        Returns:
            {"passed": bool, "warnings": list[str]}
        """
        warnings: list[str] = []

        warnings.extend(self.check_zone_contradiction(analysis_sections))
        warnings.extend(self.check_single_action(analysis_sections))
        warnings.extend(self.check_numeric_action(analysis_sections))
        warnings.extend(self.check_success_criterion(analysis_sections))

        passed = len(warnings) == 0

        if not passed:
            for w in warnings:
                logger.warning("Quality gate: %s", w)

        return {"passed": passed, "warnings": warnings}

    def check_zone_contradiction(self, sections: dict[str, Any]) -> list[str]:
        """
        Detect zone evaluation contradictions.

        Flags when zone insufficiency and ideal zone distribution
        co-exist across sections.
        """
        all_text = _extract_all_text(sections)

        has_insufficient = any(kw in all_text for kw in _ZONE_INSUFFICIENT_KEYWORDS)
        has_ideal = any(kw in all_text for kw in _ZONE_IDEAL_KEYWORDS)

        if has_insufficient and has_ideal:
            return ["矛盾検出: Zone不足の指摘と理想的配分の評価が共存しています"]
        return []

    def check_single_action(self, sections: dict[str, Any]) -> list[str]:
        """
        Ensure single next action.

        Checks the recommendations/next_action fields across sections.
        Multiple distinct next actions violate evaluation-principles.md.
        """
        actions = _extract_next_actions(sections)

        if len(actions) > 1:
            return [f"次回アクションが{len(actions)}件あります（1件に絞ってください）"]
        return []

    def check_numeric_action(self, sections: dict[str, Any]) -> list[str]:
        """
        Ensure next action contains specific numbers.

        Generic advice without numbers (e.g. "もっと練習しましょう")
        violates evaluation-principles.md.
        """
        actions = _extract_next_actions(sections)

        if not actions:
            return []

        for action in actions:
            if not _has_numeric_content(action):
                return ["次回アクションに具体的な数値が含まれていません"]
        return []

    def check_success_criterion(self, sections: dict[str, Any]) -> list[str]:
        """
        Ensure success criterion is defined.

        Next actions should include a clear success/failure criterion
        (e.g. "次回 Zone 2 が 60% 超なら成功").
        """
        actions = _extract_next_actions(sections)
        success_criteria = _extract_success_criteria(sections)

        if not actions:
            return []

        # Check if any action text or dedicated field contains success criterion
        has_criterion = len(success_criteria) > 0

        if not has_criterion:
            # Also check within the action text itself
            for action in actions:
                if _has_success_criterion(action):
                    has_criterion = True
                    break

        if not has_criterion:
            return ["成功判定条件が明示されていません"]
        return []


def _extract_all_text(sections: dict[str, Any]) -> str:
    """Recursively extract all string values from sections into one text blob."""
    parts: list[str] = []
    _collect_strings(sections, parts)
    return " ".join(parts)


def _collect_strings(obj: Any, parts: list[str]) -> None:
    """Recursively collect string values."""
    if isinstance(obj, str):
        parts.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, parts)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, parts)


def _extract_next_actions(sections: dict[str, Any]) -> list[str]:
    """Extract next action strings from analysis sections."""
    actions: list[str] = []

    for _section_type, data in sections.items():
        if not isinstance(data, dict):
            continue
        # Check common field names for next actions
        for key in ("next_action", "next_actions", "recommendations"):
            val = data.get(key)
            if val is None:
                continue
            if isinstance(val, str) and val.strip():
                actions.append(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        actions.append(item.strip())

    return actions


def _extract_success_criteria(sections: dict[str, Any]) -> list[str]:
    """Extract success criterion strings from analysis sections."""
    criteria: list[str] = []

    for _section_type, data in sections.items():
        if not isinstance(data, dict):
            continue
        for key in ("success_criterion", "success_criteria", "判定条件"):
            val = data.get(key)
            if val is None:
                continue
            if isinstance(val, str) and val.strip():
                criteria.append(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        criteria.append(item.strip())

    return criteria


def _has_numeric_content(text: str) -> bool:
    """Check if text contains specific numeric values."""
    return any(p.search(text) for p in _NUMERIC_PATTERNS)


def _has_success_criterion(text: str) -> bool:
    """Check if text contains success criterion language."""
    return any(p.search(text) for p in _SUCCESS_CRITERION_PATTERNS)
