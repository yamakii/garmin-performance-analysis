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
        template = f"""# アクティビティ詳細分析レポート

**Activity ID**: {activity_id}
**実施日**: {date}

---

## 📊 概要

<!-- LLM_INSIGHTS_OVERVIEW -->

---

## 🎯 効率分析 (Efficiency Section)

<!-- LLM_INSIGHTS_EFFICIENCY_ANALYSIS -->

---

## 🌍 環境・コンディション分析 (Environment Section)

<!-- LLM_INSIGHTS_ENVIRONMENT_ANALYSIS -->

---

## 📈 フェーズ評価 (Phase Section)

<!-- LLM_INSIGHTS_PHASE_ANALYSIS -->

---

## 🔍 スプリット詳細分析 (Split Section)

<!-- LLM_INSIGHTS_SPLIT_ANALYSIS -->

---

## ✅ 総合評価 (Summary Section)

<!-- LLM_INSIGHTS_SUMMARY_ANALYSIS -->

---

*🤖 Generated with Garmin Performance Analysis System*
"""
        return template

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

    def get_placeholders(self) -> list[str]:
        """
        レポートテンプレートのプレースホルダー一覧を取得。

        Returns:
            List of placeholder names
        """
        return [
            "LLM_INSIGHTS_OVERVIEW",
            "LLM_INSIGHTS_EFFICIENCY_ANALYSIS",
            "LLM_INSIGHTS_ENVIRONMENT_ANALYSIS",
            "LLM_INSIGHTS_PHASE_ANALYSIS",
            "LLM_INSIGHTS_SPLIT_ANALYSIS",
            "LLM_INSIGHTS_SUMMARY_ANALYSIS",
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
