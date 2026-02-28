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
    """Advisory quality gate for report content validation."""

    def check_zone_contradiction(
        self, section_analyses: dict[str, Any]
    ) -> list[QualityWarning]:
        """Check for contradiction between zone deficit evaluation and ideal distribution text."""
        raise NotImplementedError

    def check_single_action(
        self, summary: dict[str, Any]
    ) -> list[QualityWarning]:
        """Check that recommendations contain a single action, not multiple."""
        raise NotImplementedError

    def check_numeric_action(
        self, summary: dict[str, Any]
    ) -> list[QualityWarning]:
        """Check that recommendations contain specific numeric values."""
        raise NotImplementedError

    def check_success_criterion(
        self, summary: dict[str, Any]
    ) -> list[QualityWarning]:
        """Check that next_run_target has a success_criterion."""
        raise NotImplementedError

    def validate(
        self, section_analyses: dict[str, Any]
    ) -> QualityResult:
        """Run all quality checks and return aggregated result."""
        raise NotImplementedError
