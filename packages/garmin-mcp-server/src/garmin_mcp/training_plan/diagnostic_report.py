"""Diagnostic report generation for training plan fitness assessment.

Generates a Markdown report summarizing the fitness assessment, gap detection,
and training plan rationale. Saved to result/diagnostics/.
"""

from __future__ import annotations

import logging
from datetime import datetime

from garmin_mcp.training_plan.models import FitnessSummary

logger = logging.getLogger(__name__)


class DiagnosticReportGenerator:
    """Generates and saves fitness diagnostic reports as Markdown files."""

    def generate(
        self,
        fitness: FitnessSummary,
        goal_type: str,
        plan_params: dict[str, float | str | None],
    ) -> str:
        """Generate a Markdown diagnostic report.

        Args:
            fitness: Current fitness assessment.
            goal_type: Training goal type (e.g., "return_to_run").
            plan_params: Plan parameters including start_km, peak_km, etc.

        Returns:
            Markdown string of the diagnostic report.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        lines: list[str] = []

        lines.append(f"# フィットネス診断レポート（{today}）")
        lines.append("")
        lines.append("## 現状診断")

        if fitness.gap_detected:
            lines.append(f"⚠️ 休養期間を検知しました（約{fitness.gap_weeks}週間）")
            lines.append("")
            lines.append("### 休養前ベースライン")
            lines.append(f"- 週間走行距離: {fitness.pre_gap_weekly_volume_km}km")
            if fitness.pre_gap_vdot is not None:
                lines.append(f"- VDOT: {fitness.pre_gap_vdot}")
            lines.append("")
            lines.append("### 復帰後の状況")
            if fitness.recent_runs:
                distances = [
                    f"{r.get('distance_km', 0)}km" for r in fitness.recent_runs
                ]
                lines.append(
                    f"- 復帰ラン: {len(fitness.recent_runs)}回"
                    f"（{', '.join(distances)}）"
                )
            else:
                lines.append("- 復帰ランの記録なし")
        else:
            lines.append(
                f"- VDOT: {fitness.vdot} | "
                f"週間走行距離: {fitness.weekly_volume_km}km | "
                f"走行頻度: {fitness.runs_per_week}回/週"
            )
            if fitness.training_type_distribution:
                dist_parts = [
                    f"{k} {int(v * 100)}%"
                    for k, v in fitness.training_type_distribution.items()
                ]
                lines.append(f"- トレーニング構成: {', '.join(dist_parts)}")

        lines.append("")
        lines.append("## プラン根拠")
        lines.append(f"- 目標: {goal_type}")

        start_km = plan_params.get("start_km")
        peak_km = plan_params.get("peak_km")
        if start_km is not None:
            lines.append(f"- 開始ボリューム: {start_km}km")
        if peak_km is not None:
            lines.append(f"- ピーク: {peak_km}km")

        if fitness.gap_detected and fitness.pre_gap_weekly_volume_km > 0:
            target_75 = round(fitness.pre_gap_weekly_volume_km * 0.75, 1)
            lines.append(
                f"- 理由: 段階的に休養前（{fitness.pre_gap_weekly_volume_km}km/週）の"
                f"75%（{target_75}km/週）まで回復を目指す"
            )

        lines.append("")
        return "\n".join(lines)

    def save(self, content: str, report_date: str | None = None) -> dict[str, str]:
        """Save diagnostic report to file.

        Args:
            content: Markdown content to save.
            report_date: Date string (YYYY-MM-DD). Defaults to today.

        Returns:
            Dict with 'path' key containing the saved file path.
        """
        from garmin_mcp.utils.paths import get_result_dir

        if report_date is None:
            report_date = datetime.now().strftime("%Y-%m-%d")

        diagnostics_dir = get_result_dir() / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{report_date}_fitness_diagnostic.md"
        filepath = diagnostics_dir / filename
        filepath.write_text(content, encoding="utf-8")

        logger.info(f"Diagnostic report saved: {filepath}")
        return {"path": str(filepath)}
