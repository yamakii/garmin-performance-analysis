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

    def render_report(
        self,
        activity_id: str,
        date: str,
        basic_metrics: dict[str, Any],
        section_analyses: dict[str, dict[str, Any]],
    ) -> str:
        """
        Jinja2テンプレートでJSON dataからmarkdownを生成。

        Args:
            activity_id: Activity ID
            date: Date (YYYY-MM-DD)
            basic_metrics: Performance data (distance, time, pace, HR, cadence, power)
            section_analyses: Section analyses dict with keys:
                - "efficiency": Form & HR efficiency analysis
                - "environment_analysis": Weather, terrain, gear analysis
                - "phase_evaluation": Warmup, main, finish phase analysis
                - "split_analysis": Split-by-split detailed analysis
                - "summary": Overall rating and recommendations

        Returns:
            Rendered report content (markdown)

        Note:
            Template側でJSON dataをmarkdown形式にフォーマット。
            Worker側ではフォーマット処理を行わない（ロジックとプレゼンテーションの分離）。
        """
        template = self.load_template()
        return cast(
            str,
            template.render(
                activity_id=activity_id,
                date=date,
                basic_metrics=basic_metrics,
                efficiency=section_analyses.get("efficiency", {}),
                environment_analysis=section_analyses.get("environment_analysis", {}),
                phase_evaluation=section_analyses.get("phase_evaluation", {}),
                split_analysis=section_analyses.get("split_analysis", {}),
                summary=section_analyses.get("summary", {}),
            ),
        )

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
