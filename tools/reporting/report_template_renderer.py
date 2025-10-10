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

        # Add custom filter for split sorting
        self.env.filters["sort_splits"] = self._sort_splits_filter

    def _sort_splits_filter(self, items):
        """Sort split analysis items by numeric split number."""

        def extract_split_num(item):
            key = item[0]  # Get key from (key, value) tuple
            # Extract number from "split_1", "split_2", etc.
            if isinstance(key, str) and key.startswith("split_"):
                try:
                    return int(key.split("_")[1])
                except (IndexError, ValueError):
                    return 0
            return 0

        return sorted(items, key=extract_split_num)

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
        section_analyses: dict[str, dict[str, Any]] | None = None,
        activity_name: str | None = None,
        location_name: str | None = None,
        weight_kg: float | None = None,
        weather_data: dict[str, Any] | None = None,
        gear_name: str | None = None,
        form_efficiency: dict[str, Any] | None = None,
        performance_metrics: dict[str, Any] | None = None,
        training_type: str | None = None,
        warmup_metrics: dict[str, Any] | None = None,
        run_metrics: dict[str, Any] | None = None,
        recovery_metrics: dict[str, Any] | None = None,
        cooldown_metrics: dict[str, Any] | None = None,
        main_metrics: dict[str, Any] | None = None,
        finish_metrics: dict[str, Any] | None = None,
        splits: list[dict[str, Any]] | None = None,
        efficiency: dict[str, Any] | str | None = None,
        environment_analysis: dict[str, Any] | str | None = None,
        phase_evaluation: dict[str, Any] | None = None,
        split_analysis: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
    ) -> str:
        """
        Jinja2テンプレートでJSON dataからmarkdownを生成。

        Args:
            activity_id: Activity ID
            date: Date (YYYY-MM-DD)
            basic_metrics: Performance data (distance, time, pace, HR, cadence, power)
            section_analyses: (Legacy) Section analyses dict - deprecated, use individual params
            activity_name: Activity name
            location_name: Location name
            weight_kg: Body weight in kg
            weather_data: Weather conditions (temp, humidity, wind)
            gear_name: Gear/shoe name
            form_efficiency: Form efficiency statistics (GCT, VO, VR)
            performance_metrics: Performance metrics (pace consistency, HR drift, etc.)
            training_type: Training type classification
            warmup_metrics: Warmup phase metrics
            run_metrics: Run/main phase metrics (new naming)
            recovery_metrics: Recovery phase metrics (4-phase interval training only)
            cooldown_metrics: Cooldown phase metrics (new naming, was finish)
            main_metrics: (Legacy) Main phase metrics - deprecated, use run_metrics
            finish_metrics: (Legacy) Finish phase metrics - deprecated, use cooldown_metrics
            splits: List of split data with metrics
            efficiency: Form & HR efficiency analysis
            environment_analysis: Weather, terrain, gear analysis
            phase_evaluation: Phase analysis (supports 3-phase and 4-phase)
            split_analysis: Split-by-split detailed analysis
            summary: Overall rating and recommendations

        Returns:
            Rendered report content (markdown)

        Note:
            Template側でJSON dataをmarkdown形式にフォーマット。
            Worker側ではフォーマット処理を行わない（ロジックとプレゼンテーションの分離）。
        """
        # Support legacy section_analyses parameter
        if section_analyses:
            efficiency = efficiency or section_analyses.get("efficiency", {})
            environment_analysis = environment_analysis or section_analyses.get(
                "environment_analysis", {}
            )
            phase_evaluation = phase_evaluation or section_analyses.get(
                "phase_evaluation", {}
            )
            split_analysis = split_analysis or section_analyses.get(
                "split_analysis", {}
            )
            summary = summary or section_analyses.get("summary", {})

        # Support legacy main_metrics/finish_metrics naming
        if main_metrics and not run_metrics:
            run_metrics = main_metrics
        if finish_metrics and not cooldown_metrics:
            cooldown_metrics = finish_metrics

        template = self.load_template()
        return cast(
            str,
            template.render(
                activity_id=activity_id,
                date=date,
                activity_name=activity_name,
                location_name=location_name,
                basic_metrics=basic_metrics,
                weight_kg=weight_kg,
                weather_data=weather_data or {},
                gear_name=gear_name,
                form_efficiency=form_efficiency,
                performance_metrics=performance_metrics,
                training_type=training_type,
                warmup_metrics=warmup_metrics,
                run_metrics=run_metrics,
                recovery_metrics=recovery_metrics,
                cooldown_metrics=cooldown_metrics,
                main_metrics=main_metrics,  # Keep for backward compatibility
                finish_metrics=finish_metrics,  # Keep for backward compatibility
                splits=splits or [],
                efficiency=efficiency or {},
                environment_analysis=environment_analysis or {},
                phase_evaluation=phase_evaluation or {},
                split_analysis=split_analysis or {},
                summary=summary or {},
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
        from tools.utils.paths import get_result_dir

        year, month, _ = date.split("-")
        final_dir = get_result_dir() / "individual" / year / month
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
