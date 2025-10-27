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

        # Add custom filters
        self.env.filters["sort_splits"] = self._sort_splits_filter
        self.env.filters["extract_star_rating"] = self._extract_star_rating_filter
        self.env.filters["format_intensity_type"] = self._format_intensity_type_filter

    def _format_intensity_type_filter(
        self, splits: list[dict], current_index: int
    ) -> str:
        """
        Format intensity_type for interval display with counters.

        Args:
            splits: Full list of split dictionaries
            current_index: Current split index (1-based)

        Returns:
            Formatted type: "W-up" | "W1" | "R1" | "C-down"

        Examples:
            >>> _format_intensity_type_filter([{"index": 1, "intensity_type": "warmup"}], 1)
            "W-up"
            >>> _format_intensity_type_filter([
            ...     {"index": 1, "intensity_type": "warmup"},
            ...     {"index": 2, "intensity_type": "active"}
            ... ], 2)
            "W1"
        """
        # Find current split
        current_split = None
        for split in splits:
            if split.get("index") == current_index:
                current_split = split
                break

        if not current_split:
            return "N/A"

        intensity_type = current_split.get("intensity_type", "")

        if intensity_type == "warmup":
            return "W-up"
        elif intensity_type == "cooldown":
            return "C-down"
        elif intensity_type == "active":
            # Count active splits before current index
            work_count = sum(
                1
                for s in splits
                if s.get("intensity_type") == "active"
                and s.get("index", 0) <= current_index
            )
            return f"W{work_count}"
        elif intensity_type == "rest":
            # Count rest splits before current index
            recovery_count = sum(
                1
                for s in splits
                if s.get("intensity_type") == "rest"
                and s.get("index", 0) <= current_index
            )
            return f"R{recovery_count}"

        return intensity_type or "N/A"

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

    def _extract_star_rating_filter(self, text: str | dict | None) -> dict[str, Any]:
        """
        Extract star rating from text.

        Args:
            text: Text containing star rating pattern "(★★★★☆ 4.2/5.0)" or "(★★★★☆)", or dict/None

        Returns:
            Dictionary with keys:
                - stars: Star string (e.g., "★★★★☆")
                - score: Numeric score (e.g., 4.2)
                - text_without_rating: Text with rating pattern removed

        Examples:
            >>> _extract_star_rating_filter("良好です (★★★★☆ 4.2/5.0)")
            {"stars": "★★★★☆", "score": 4.2, "text_without_rating": "良好です"}

            >>> _extract_star_rating_filter("良好です (★★★★☆)")
            {"stars": "★★★★☆", "score": 4.0, "text_without_rating": "良好です"}

            >>> _extract_star_rating_filter("普通です")
            {"stars": "", "score": 0.0, "text_without_rating": "普通です"}

            >>> _extract_star_rating_filter({"key": "value"})
            {"stars": "", "score": 0.0, "text_without_rating": ""}
        """
        import re

        # Handle non-string inputs
        if not isinstance(text, str):
            return {
                "stars": "",
                "score": 0.0,
                "text_without_rating": "",
            }

        # Try pattern with score first: (★★★★☆ 4.2/5.0)
        pattern_with_score = r"\(([★☆]+) (\d+\.\d+)/5\.0\)"
        match = re.search(pattern_with_score, text)

        if match:
            stars = match.group(1)
            score = float(match.group(2))
            text_without_rating = re.sub(pattern_with_score, "", text, count=1).strip()

            return {
                "stars": stars,
                "score": score,
                "text_without_rating": text_without_rating,
            }

        # Try pattern without score: (★★★★☆)
        pattern_without_score = r"\(([★☆]+)\)"
        match = re.search(pattern_without_score, text)

        if match:
            stars = match.group(1)
            full_stars = stars.count("★")
            text_without_rating = re.sub(
                pattern_without_score, "", text, count=1
            ).strip()

            return {
                "stars": stars,
                "score": float(full_stars),
                "text_without_rating": text_without_rating,
            }

        return {
            "stars": "",
            "score": 0.0,
            "text_without_rating": text,
        }

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
        form_evaluation: (
            dict[str, Any] | None
        ) = None,  # Phase 5: Unified Form Evaluation
        performance_metrics: dict[str, Any] | None = None,
        training_type: str | None = None,
        activity_type: dict[str, str] | None = None,
        warmup_metrics: dict[str, Any] | None = None,
        run_metrics: dict[str, Any] | None = None,
        recovery_metrics: dict[str, Any] | None = None,
        cooldown_metrics: dict[str, Any] | None = None,
        main_metrics: dict[str, Any] | None = None,
        finish_metrics: dict[str, Any] | None = None,
        splits: list[dict[str, Any]] | None = None,
        mermaid_data: dict[str, Any] | None = None,
        heart_rate_zone_pie_data: str | None = None,
        highlights_list: str | None = None,
        similar_workouts: dict[str, Any] | None = None,
        reference_info: str | None = None,
        efficiency: dict[str, Any] | str | None = None,
        environment_analysis: dict[str, Any] | str | None = None,
        phase_evaluation: dict[str, Any] | None = None,
        split_analysis: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        # Phase 2: Training Type Categorization & Physiological Indicators
        training_type_category: str | None = None,
        vo2_max_data: dict[str, Any] | None = None,
        lactate_threshold_data: dict[str, Any] | None = None,
        vo2_max_utilization: float | None = None,
        vo2_max_utilization_eval: str | None = None,
        vo2_max_expected_effect: str | None = None,
        threshold_expected_effect: str | None = None,
        threshold_pace_formatted: str | None = None,
        threshold_pace_comparison: str | None = None,
        ftp_percentage: float | None = None,
        work_avg_power: float | None = None,
        power_zone_name: str | None = None,
        target_segments_description: str | None = None,
        interval_graph_analysis: str | None = None,
        zone_4_ratio: float | None = None,
        is_interval: bool | None = None,
        show_physiological: bool | None = None,
        # Phase evaluation ratings
        warmup_rating: dict | None = None,
        run_rating: dict | None = None,
        recovery_rating: dict | None = None,
        cooldown_rating: dict | None = None,
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
            activity_type: Activity type display info (ja/en/description)
            warmup_metrics: Warmup phase metrics
            run_metrics: Run/main phase metrics (new naming)
            recovery_metrics: Recovery phase metrics (4-phase interval training only)
            cooldown_metrics: Cooldown phase metrics (new naming, was finish)
            main_metrics: (Legacy) Main phase metrics - deprecated, use run_metrics
            finish_metrics: (Legacy) Finish phase metrics - deprecated, use cooldown_metrics
            splits: List of split data with metrics
            mermaid_data: Mermaid graph data for visualization
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
                form_evaluation=form_evaluation,  # Phase 5: Unified Form Evaluation
                performance_metrics=performance_metrics,
                training_type=training_type,
                activity_type=activity_type,
                warmup_metrics=warmup_metrics,
                run_metrics=run_metrics,
                recovery_metrics=recovery_metrics,
                cooldown_metrics=cooldown_metrics,
                main_metrics=main_metrics,  # Keep for backward compatibility
                finish_metrics=finish_metrics,  # Keep for backward compatibility
                splits=splits or [],
                mermaid_data=mermaid_data,
                heart_rate_zone_pie_data=heart_rate_zone_pie_data,
                highlights_list=highlights_list,
                similar_workouts=similar_workouts,
                reference_info=reference_info,
                efficiency=efficiency or {},
                environment_analysis=environment_analysis or {},
                phase_evaluation=phase_evaluation or {},
                split_analysis=split_analysis or {},
                summary=summary or {},
                # Phase 2: Training Type Categorization & Physiological Indicators
                training_type_category=training_type_category,
                vo2_max_data=vo2_max_data,
                lactate_threshold_data=lactate_threshold_data,
                vo2_max_utilization=vo2_max_utilization,
                vo2_max_utilization_eval=vo2_max_utilization_eval,
                vo2_max_expected_effect=vo2_max_expected_effect,
                threshold_expected_effect=threshold_expected_effect,
                threshold_pace_formatted=threshold_pace_formatted,
                threshold_pace_comparison=threshold_pace_comparison,
                ftp_percentage=ftp_percentage,
                work_avg_power=work_avg_power,
                power_zone_name=power_zone_name,
                target_segments_description=target_segments_description,
                interval_graph_analysis=interval_graph_analysis,
                zone_4_ratio=zone_4_ratio,
                is_interval=is_interval,
                show_physiological=show_physiological,
                # Phase evaluation ratings for headers
                warmup_rating=warmup_rating or {"score": 0, "stars": ""},
                run_rating=run_rating or {"score": 0, "stars": ""},
                recovery_rating=recovery_rating or {"score": 0, "stars": ""},
                cooldown_rating=cooldown_rating or {"score": 0, "stars": ""},
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
