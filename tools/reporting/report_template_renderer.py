"""
Report Template Renderer

Jinja2テンプレートベースでレポート構造を生成するモジュール。
"""

from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader


class ReportTemplateRenderer:
    """レポートテンプレートレンダラー。"""

    def __init__(self, template_dir: str | None = None):
        """
        Initialize renderer.

        Args:
            template_dir: Template directory path (default: tools/reporting/templates/)
        """
        self.project_root = Path(__file__).parent.parent.parent

        if template_dir is None:
            template_dir = str(Path(__file__).parent / "templates")

        self.env = Environment(loader=FileSystemLoader(template_dir))

    def load_template(self, template_name: str = "detailed_report.j2"):
        """
        Jinja2テンプレートを読み込む。

        Args:
            template_name: Template file name

        Returns:
            Jinja2 template object
        """
        return self.env.get_template(template_name)

    def create_report_structure(self, activity_id: str, date: str) -> str:
        """
        テンプレートからレポート構造を生成（プレースホルダー付き）。

        Args:
            activity_id: Activity ID
            date: Date in YYYY-MM-DD format

        Returns:
            Report structure with placeholders
        """
        template = f"""# Running Performance Analysis - Activity {activity_id}

## Basic Information
- **Activity ID**: {activity_id}
- **Date**: {date}
- **Activity Type**: <!-- LLM_INSIGHTS_ACTIVITY_TYPE -->
- **Overall Rating**: <!-- LLM_INSIGHTS_OVERALL_RATING -->

## Performance Summary

### Key Strengths
<!-- LLM_INSIGHTS_STRENGTHS -->

### Areas for Improvement
<!-- LLM_INSIGHTS_IMPROVEMENTS -->

## Phase Analysis

### Warmup Phase
<!-- LLM_INSIGHTS_WARMUP -->

### Main Phase
<!-- LLM_INSIGHTS_MAIN -->

### Finish Phase
<!-- LLM_INSIGHTS_FINISH -->

## Efficiency Analysis

### Form Efficiency
<!-- LLM_INSIGHTS_FORM_EFFICIENCY -->

### HR Efficiency
<!-- LLM_INSIGHTS_HR_EFFICIENCY -->

## Environmental Factors

### Weather Conditions
<!-- LLM_INSIGHTS_WEATHER -->

### Terrain Impact
<!-- LLM_INSIGHTS_TERRAIN -->

## Split-by-Split Analysis
<!-- LLM_INSIGHTS_SPLITS -->

## Recommendations
<!-- LLM_INSIGHTS_RECOMMENDATIONS -->

---
*Generated with Garmin Performance Analysis System*
"""
        return template

    def render_report(
        self,
        activity_id: str,
        date: str,
        activity_type: str,
        overall_rating: str,
        strengths: str,
        improvements: str,
        warmup_phase: str,
        main_phase: str,
        finish_phase: str,
        form_efficiency: str,
        hr_efficiency: str,
        weather_conditions: str,
        terrain_impact: str,
        split_analysis: str,
        recommendations: str,
    ) -> str:
        """
        Jinja2テンプレートを使用してレポートをレンダリング。

        Args:
            activity_id: Activity ID
            date: Date
            activity_type: Activity type
            overall_rating: Overall rating
            strengths: Key strengths
            improvements: Areas for improvement
            warmup_phase: Warmup phase analysis
            main_phase: Main phase analysis
            finish_phase: Finish phase analysis
            form_efficiency: Form efficiency analysis
            hr_efficiency: HR efficiency analysis
            weather_conditions: Weather conditions
            terrain_impact: Terrain impact
            split_analysis: Split-by-split analysis
            recommendations: Recommendations

        Returns:
            Rendered report content
        """
        template = self.load_template()
        return cast(
            str,
            template.render(
                activity_id=activity_id,
                date=date,
                activity_type=activity_type,
                overall_rating=overall_rating,
                strengths=strengths,
                improvements=improvements,
                warmup_phase=warmup_phase,
                main_phase=main_phase,
                finish_phase=finish_phase,
                form_efficiency=form_efficiency,
                hr_efficiency=hr_efficiency,
                weather_conditions=weather_conditions,
                terrain_impact=terrain_impact,
                split_analysis=split_analysis,
                recommendations=recommendations,
            ),
        )

    def get_placeholders(self) -> list[str]:
        """
        レポートテンプレートのプレースホルダー一覧を取得。

        Returns:
            List of placeholder names
        """
        return [
            "LLM_INSIGHTS_ACTIVITY_TYPE",
            "LLM_INSIGHTS_OVERALL_RATING",
            "LLM_INSIGHTS_STRENGTHS",
            "LLM_INSIGHTS_IMPROVEMENTS",
            "LLM_INSIGHTS_WARMUP",
            "LLM_INSIGHTS_MAIN",
            "LLM_INSIGHTS_FINISH",
            "LLM_INSIGHTS_FORM_EFFICIENCY",
            "LLM_INSIGHTS_HR_EFFICIENCY",
            "LLM_INSIGHTS_WEATHER",
            "LLM_INSIGHTS_TERRAIN",
            "LLM_INSIGHTS_SPLITS",
            "LLM_INSIGHTS_RECOMMENDATIONS",
        ]

    def validate_report(self, report_content: str) -> dict[str, Any]:
        """
        レポート内容を検証（プレースホルダーが全て置換されているか）。

        Args:
            report_content: Report content

        Returns:
            Validation result with missing placeholders
        """
        missing_placeholders = []
        for placeholder in self.get_placeholders():
            if f"<!-- {placeholder} -->" in report_content:
                missing_placeholders.append(placeholder)

        return {
            "valid": len(missing_placeholders) == 0,
            "missing_placeholders": missing_placeholders,
        }

    def get_final_report_path(self, activity_id: str, date: str) -> Path:
        """
        最終レポート保存先パスを取得。

        Args:
            activity_id: Activity ID
            date: Date in YYYY-MM-DD format

        Returns:
            Final report path
        """
        year, month, _ = date.split("-")
        final_dir = self.project_root / "result" / "individual" / year / month
        return final_dir / f"{date}_activity_{activity_id}.md"

    def save_report(
        self, activity_id: str, date: str, report_content: str
    ) -> dict[str, Any]:
        """
        レポートを保存。

        Args:
            activity_id: Activity ID
            date: Date in YYYY-MM-DD format
            report_content: Report content

        Returns:
            Save result with path
        """
        final_path = self.get_final_report_path(activity_id, date)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        with open(final_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        return {"success": True, "path": str(final_path)}
