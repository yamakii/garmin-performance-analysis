"""
Report Generator Worker

Reads performance data from DuckDB and generates final Markdown report.
Python Worker for report generation from section analyses.
"""

import json
import logging
from datetime import datetime
from typing import Any

from tools.database.db_reader import GarminDBReader
from tools.reporting.report_template_renderer import ReportTemplateRenderer

logger = logging.getLogger(__name__)


class ReportGeneratorWorker:
    """Python Worker for report generation from section analyses."""

    def __init__(self, db_path: str | None = None):
        """
        Initialize report generator worker.

        Args:
            db_path: DuckDB database path (default: uses environment variable)
        """
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        self.db_reader = GarminDBReader(db_path)
        self.renderer = ReportTemplateRenderer()

    def load_performance_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Load all performance data from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Complete performance data dict or None
        """
        logger.info("[1/4] Loading performance data from DuckDB...")

        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Load basic info and metrics from activities table
            result = conn.execute(
                """
                SELECT
                    activity_name,
                    location_name,
                    start_time_local,
                    total_distance_km,
                    total_time_seconds,
                    avg_pace_seconds_per_km,
                    avg_heart_rate,
                    temp_celsius,
                    relative_humidity_percent,
                    wind_speed_kmh,
                    gear_type,
                    gear_model
                FROM activities
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            if not result:
                conn.close()
                logger.warning(
                    f"Warning: No performance data found in DuckDB for activity {activity_id}"
                )
                return None

            # Load form efficiency statistics
            form_eff = conn.execute(
                """
                SELECT
                    gct_average, gct_std, gct_rating,
                    vo_average, vo_std, vo_rating,
                    vr_average, vr_std, vr_rating
                FROM form_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            # Load performance trends (support both 3-phase and 4-phase)
            # Check which columns exist in the schema
            schema_check = conn.execute(
                "PRAGMA table_info('performance_trends')"
            ).fetchall()
            column_names = [row[1] for row in schema_check]
            has_new_schema = "run_avg_pace_seconds_per_km" in column_names
            has_old_schema = "main_avg_pace_seconds_per_km" in column_names

            if has_new_schema:
                # Use new schema (run/cooldown)
                perf_trends = conn.execute(
                    """
                    SELECT
                        pace_consistency,
                        hr_drift_percentage,
                        cadence_consistency,
                        fatigue_pattern,
                        warmup_avg_pace_seconds_per_km,
                        warmup_avg_hr,
                        run_avg_pace_seconds_per_km,
                        run_avg_hr,
                        recovery_avg_pace_seconds_per_km,
                        recovery_avg_hr,
                        cooldown_avg_pace_seconds_per_km,
                        cooldown_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()
            elif has_old_schema:
                # Use old schema (main/finish) - map to new naming
                perf_trends = conn.execute(
                    """
                    SELECT
                        pace_consistency,
                        hr_drift_percentage,
                        cadence_consistency,
                        fatigue_pattern,
                        warmup_avg_pace_seconds_per_km,
                        warmup_avg_hr,
                        main_avg_pace_seconds_per_km,
                        main_avg_hr,
                        NULL,
                        NULL,
                        finish_avg_pace_seconds_per_km,
                        finish_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()
            else:
                perf_trends = None

            # Load HR efficiency (for training type)
            hr_eff = conn.execute(
                """
                SELECT training_type
                FROM hr_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            # Load VO2 Max data (optional table)
            try:
                vo2_max = conn.execute(
                    """
                    SELECT value, precise_value, category, fitness_age
                    FROM vo2_max
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()
            except Exception:
                vo2_max = None

            # Load lactate threshold data (optional table)
            try:
                lactate_threshold = conn.execute(
                    """
                    SELECT
                        heart_rate,
                        speed_mps,
                        functional_threshold_power
                    FROM lactate_threshold
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()
            except Exception:
                lactate_threshold = None

            conn.close()

            # Construct data structure
            data = {
                "activity_name": result[0],
                "location_name": result[1],
                "basic_metrics": {
                    "start_time": str(result[2]) if result[2] else None,
                    "distance_km": result[3],
                    "duration_seconds": result[4],
                    "avg_pace_seconds_per_km": result[5],
                    "avg_heart_rate": result[6],
                },
                "weather_data": {
                    "temp_celsius": result[7],
                    "relative_humidity_percent": result[8],
                    "wind_speed_kmh": result[9],
                },
                "gear_type": result[10],
                "gear_model": result[11],
            }

            # Add form efficiency if available
            if form_eff:
                data["form_efficiency"] = {
                    "gct_average": form_eff[0],
                    "gct_std": form_eff[1],
                    "gct_rating": form_eff[2],
                    "vo_average": form_eff[3],
                    "vo_std": form_eff[4],
                    "vo_rating": form_eff[5],
                    "vr_average": form_eff[6],
                    "vr_std": form_eff[7],
                    "vr_rating": form_eff[8],
                }

            # Add performance metrics if available
            if perf_trends:
                data["performance_metrics"] = {
                    "pace_consistency": perf_trends[0],
                    "hr_drift_percentage": perf_trends[1],
                    "cadence_consistency": perf_trends[2],
                    "fatigue_pattern": perf_trends[3],
                }
                data["warmup_metrics"] = {
                    "avg_pace_seconds_per_km": perf_trends[4],
                    "avg_hr": perf_trends[5],
                }
                # Check if recovery data exists (4-phase) or not (3-phase)
                if perf_trends[8] is not None:
                    # 4-phase structure (interval training)
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "pace_consistency": perf_trends[0],
                    }
                    data["recovery_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[8],
                        "avg_hr": perf_trends[9],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[10],
                        "avg_hr": perf_trends[11],
                        "fatigue_pattern": perf_trends[3],
                    }
                else:
                    # 3-phase structure (regular run)
                    # Map to new naming: run (was main), cooldown (was finish)
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "pace_consistency": perf_trends[0],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[10],
                        "avg_hr": perf_trends[11],
                        "fatigue_pattern": perf_trends[3],
                    }
                    # Legacy naming for backward compatibility
                    data["main_metrics"] = data["run_metrics"]
                    data["finish_metrics"] = data["cooldown_metrics"]

            # Add training type if available
            if hr_eff:
                data["training_type"] = hr_eff[0]

            # Add VO2 Max data if available
            if vo2_max:
                data["vo2_max_data"] = {
                    "value": vo2_max[0],
                    "precise_value": vo2_max[1],
                    "category": vo2_max[2],
                    "fitness_age": vo2_max[3],
                }

            # Add lactate threshold data if available
            if lactate_threshold:
                data["lactate_threshold_data"] = {
                    "heart_rate": lactate_threshold[0],
                    "speed_mps": lactate_threshold[1],
                    "functional_threshold_power": lactate_threshold[2],
                }

            # Add similar workouts comparison (Phase 3)
            # Determine comparison pace based on training type
            comparison_pace, pace_source = self._get_comparison_pace(data)

            current_metrics = {
                "avg_pace": comparison_pace,
                "avg_hr": data["basic_metrics"]["avg_heart_rate"],
                "pace_source": pace_source,
            }
            data["similar_workouts"] = self._load_similar_workouts(
                activity_id, current_metrics
            )

            # Generate workout insight based on comparison data
            if data["similar_workouts"]:
                data["similar_workouts"]["insight"] = self._generate_workout_insight(
                    data["similar_workouts"], data.get("training_type", "aerobic_base")
                )

            # Generate reference info (VO2 Max + Threshold pace)
            data["reference_info"] = self._generate_reference_info(
                data.get("vo2_max_data"), data.get("lactate_threshold_data")
            )

            # Add pace-corrected form efficiency (Phase 4)
            if form_eff:
                data["form_efficiency_pace_corrected"] = (
                    self._calculate_pace_corrected_form_efficiency(
                        data["basic_metrics"]["avg_pace_seconds_per_km"],
                        data["form_efficiency"],
                    )
                )

            # Load splits and generate Mermaid graph data
            data["splits"] = self._load_splits(activity_id)
            data["mermaid_data"] = self._generate_mermaid_data(data.get("splits"))

            return data

        except Exception as e:
            logger.error(f"Error loading performance data: {e}")
            return None

    def _generate_mermaid_data(
        self, splits: list[dict[str, Any]] | None
    ) -> dict[str, Any] | None:
        """
        Generate Mermaid graph data from splits.

        Args:
            splits: List of split dictionaries

        Returns:
            Dictionary with Mermaid graph data or None if no splits
        """
        if not splits:
            return None

        # Extract data from splits
        x_axis_labels = [f"{s['index']}" for s in splits]
        pace_data = [s["pace_seconds_per_km"] for s in splits]
        heart_rate_data = [s["heart_rate"] for s in splits]
        power_data = [s.get("power", 0) or 0 for s in splits]  # Handle None values

        # Calculate dynamic Y-axis ranges with 10% padding
        if pace_data:
            pace_min = min(pace_data) * 0.9
            pace_max = max(pace_data) * 1.1
        else:
            pace_min = pace_max = 0

        if heart_rate_data:
            hr_min = min(heart_rate_data) * 0.9
            hr_max = max(heart_rate_data) * 1.1
        else:
            hr_min = hr_max = 0

        return {
            "x_axis_labels": x_axis_labels,
            "pace_data": pace_data,
            "heart_rate_data": heart_rate_data,
            "power_data": power_data,
            "pace_min": round(pace_min, 1),
            "pace_max": round(pace_max, 1),
            "hr_min": round(hr_min, 1),
            "hr_max": round(hr_max, 1),
        }

    def _generate_hr_zone_pie_data(self, activity_id: int) -> str | None:
        """
        Generate Mermaid pie chart data for heart rate zones.

        Args:
            activity_id: Activity ID

        Returns:
            Mermaid pie chart data string or None if no data available
        """
        try:
            # Query heart rate zone data from DuckDB
            import duckdb

            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    zone_number,
                    zone_percentage
                FROM heart_rate_zones
                WHERE activity_id = ?
                AND zone_percentage > 0
                ORDER BY zone_number
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                return None

            # Format as Mermaid pie chart data
            pie_lines = []
            for zone_number, percentage in result:
                pie_lines.append(f'    "Zone {zone_number}" : {percentage:.2f}')

            if not pie_lines:
                return None

            return "\n".join(pie_lines)

        except Exception as e:
            logger.warning(f"Failed to generate HR zone pie data: {e}")
            return None

    def _load_splits(self, activity_id: int) -> list[dict[str, Any]]:
        """
        Load splits from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            List of split dictionaries with index, pace, HR, etc.
        """
        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    split_index AS index,
                    pace_seconds_per_km,
                    heart_rate,
                    cadence,
                    power,
                    stride_length,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    intensity_type
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                logger.warning(f"No splits found for activity {activity_id}")
                return []

            # Convert to dict format expected by template
            splits = []
            for row in result:
                splits.append(
                    {
                        "index": row[0],
                        "pace_seconds_per_km": row[1],
                        "heart_rate": row[2],
                        "cadence": row[3],
                        "power": row[4],
                        "stride_length": row[5],
                        "ground_contact_time": row[6],
                        "vertical_oscillation": row[7],
                        "vertical_ratio": row[8],
                        "elevation_gain": row[9],
                        "elevation_loss": row[10],
                        "intensity_type": row[11],
                    }
                )

            logger.info(f"Loaded {len(splits)} splits for activity {activity_id}")
            return splits

        except Exception as e:
            logger.error(f"Error loading splits: {e}", exc_info=True)
            return []

    def _format_pace(self, pace_seconds_per_km: float) -> str:
        """Format pace as MM:SS/km.

        Args:
            pace_seconds_per_km: Pace in seconds per kilometer

        Returns:
            Formatted pace string (e.g., "4:30/km")
        """
        minutes = int(pace_seconds_per_km / 60)
        seconds = int(pace_seconds_per_km % 60)
        return f"{minutes}:{seconds:02d}/km"

    def _get_activity_type_display(self, training_type: str) -> dict[str, str]:
        """Map training_type to Japanese display name and English subtitle.

        Args:
            training_type: DuckDB training_type value

        Returns:
            dict with keys: "ja" (Japanese name), "en" (English name), "description"
        """
        mapping = {
            "recovery": {
                "ja": "リカバリーラン",
                "en": "Recovery Run",
                "description": "軽い有酸素運動で疲労回復を促進",
            },
            "aerobic_base": {
                "ja": "有酸素ベース走",
                "en": "Aerobic Base",
                "description": "心拍ゾーン2-3中心の中強度トレーニング。有酸素能力の基盤構築に最適な強度です。",
            },
            "tempo": {
                "ja": "テンポラン",
                "en": "Tempo Run",
                "description": "心拍ゾーン3-4の中高強度。閾値走より少し楽なペースで持久力を強化",
            },
            "lactate_threshold": {
                "ja": "乳酸閾値トレーニング",
                "en": "Lactate Threshold",
                "description": "3フェーズ構成（ウォームアップ-メイン-クールダウン）で、閾値ペースを維持する持久力強化トレーニング。Zone 4中心で乳酸処理能力を向上させることが目的です。",
            },
            "vo2max": {
                "ja": "VO2 Maxトレーニング",
                "en": "VO2 Max Training",
                "description": "最大酸素摂取量向上を目的とした高強度インターバル",
            },
            "anaerobic_capacity": {
                "ja": "無酸素容量トレーニング",
                "en": "Anaerobic Capacity",
                "description": "短時間高強度で無酸素能力を強化",
            },
            "speed": {
                "ja": "スピードトレーニング",
                "en": "Speed Training",
                "description": "短距離スプリントでスピードとパワーを強化",
            },
            "interval_training": {
                "ja": "インターバルトレーニング",
                "en": "Interval Training",
                "description": "1km×5本のWorkセグメントをZone 4-5（閾値〜最大心拍）で実施し、400mのRecoveryで回復する高強度トレーニング。VO2 max向上とスピード持久力の強化が目的です。",
            },
        }
        return mapping.get(
            training_type,
            {
                "ja": "その他のトレーニング",
                "en": "Other Training",
                "description": "分類不明のトレーニング",
            },
        )

    def _get_training_type_category(self, training_type: str) -> str:
        """Map training_type to template category for conditional logic.

        Args:
            training_type: DuckDB training_type value

        Returns:
            Category string:
            - "low_moderate": recovery, aerobic_base, aerobic_endurance, unknown
            - "tempo_threshold": tempo, lactate_threshold
            - "interval_sprint": vo2max, anaerobic_capacity, speed, interval_training

        This categorization is used for:
        - Showing/hiding physiological indicators summary
        - Selecting appropriate comparison pace (main_set vs overall)
        - Determining evaluation focus (overall vs specific phases)
        """
        interval_sprint = {
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
        }
        tempo_threshold = {"tempo", "lactate_threshold"}

        if training_type in interval_sprint:
            return "interval_sprint"
        elif training_type in tempo_threshold:
            return "tempo_threshold"
        else:
            # Default to low_moderate for recovery, aerobic_base, and unknown types
            return "low_moderate"

    def _calculate_physiological_indicators(
        self,
        training_type_category: str,
        vo2_max_data: dict | None,
        lactate_threshold_data: dict | None,
        run_metrics: dict,
    ) -> dict | None:
        """Calculate physiological indicators for tempo/threshold/interval workouts.

        Args:
            training_type_category: Training type category from _get_training_type_category
            vo2_max_data: VO2 Max data from database
            lactate_threshold_data: Lactate threshold data from database
            run_metrics: Run/main phase metrics

        Returns:
            Dictionary with physiological indicators or None if:
            - training_type_category is "low_moderate"
            - Required data is missing

        Indicators:
            - vo2_max_utilization: Percentage of VO2 Max being utilized (0-100%)
            - threshold_pace_formatted: Threshold pace in MM:SS/km format
            - ftp_percentage: Percentage of FTP (Functional Threshold Power)
        """
        # Only calculate for tempo_threshold and interval_sprint
        if training_type_category == "low_moderate":
            return None

        # Check required data
        if not vo2_max_data or not lactate_threshold_data or not run_metrics:
            return None

        # Extract values with None checks
        vo2_max_value = vo2_max_data.get("precise_value")
        threshold_speed = lactate_threshold_data.get("speed_mps")
        ftp = lactate_threshold_data.get("functional_threshold_power")
        target_pace = run_metrics.get("avg_pace_seconds_per_km")
        work_avg_power = run_metrics.get("avg_power", 0)

        if not all([vo2_max_value, threshold_speed, target_pace]):
            return None

        # Type guards - now mypy knows these are not None
        assert isinstance(vo2_max_value, int | float)
        assert isinstance(threshold_speed, int | float)
        assert isinstance(target_pace, int | float)

        # Calculate VO2 Max utilization
        # Empirical formula: vVO2max (km/h) ≈ VO2max / 3.5
        # This gives running speed at VO2 Max intensity
        # For VO2max 52.3 → vVO2max ≈ 14.9 km/h ≈ 4:01/km
        vo2_max_speed_kmh = vo2_max_value / 3.5
        vo2_max_pace_seconds_per_km = 3600 / vo2_max_speed_kmh

        # Utilization = VO2max pace / current pace * 100
        # Example: VO2max pace 241s/km, current 304s/km → 241/304 = 79%
        vo2_max_utilization = (vo2_max_pace_seconds_per_km / target_pace) * 100

        # Format threshold pace
        threshold_pace_seconds_per_km = 1000 / threshold_speed
        threshold_pace_formatted = self._format_pace(threshold_pace_seconds_per_km)

        # Calculate FTP percentage
        ftp_percentage = 0.0
        if ftp and isinstance(ftp, int | float) and ftp > 0 and work_avg_power:
            ftp_percentage = (work_avg_power / ftp) * 100

        return {
            "vo2_max_utilization": round(vo2_max_utilization, 1),
            "threshold_pace_formatted": threshold_pace_formatted,
            "ftp_percentage": round(ftp_percentage, 1),
        }

    def _get_comparison_pace(self, performance_data: dict) -> tuple[float, str]:
        """
        Determine which pace to use for similarity comparison.

        Args:
            performance_data: Performance data dict with training_type, run_metrics, basic_metrics

        Returns:
            tuple: (pace_seconds_per_km, pace_source)
            - pace_source: "main_set" | "overall"

        Logic:
            - Structured workouts (tempo, lactate_threshold, vo2max, anaerobic_capacity, speed):
              → Use run_metrics.avg_pace_seconds_per_km (if available)
            - Recovery/base/unknown:
              → Use basic_metrics.avg_pace_seconds_per_km
        """
        training_type = performance_data.get("training_type", "unknown")
        structured_types = {
            "tempo",
            "lactate_threshold",
            "vo2max",
            "anaerobic_capacity",
            "speed",
        }

        # Use main set pace for structured workouts (if available)
        if training_type in structured_types:
            run_metrics = performance_data.get("run_metrics")
            if run_metrics and run_metrics.get("avg_pace_seconds_per_km"):
                return (run_metrics["avg_pace_seconds_per_km"], "main_set")

        # Fallback: use overall average pace
        return (performance_data["basic_metrics"]["avg_pace_seconds_per_km"], "overall")

    def _load_similar_workouts(
        self, activity_id: int, current_metrics: dict
    ) -> dict | None:
        """Load similar workouts comparison using MCP tool.

        Returns None if insufficient data or error occurs.
        Template will gracefully handle None with "類似ワークアウトが見つかりませんでした。"

        Args:
            activity_id: Activity ID to find similar workouts for
            current_metrics: Dictionary with 'avg_pace' and 'avg_hr' keys

        Returns:
            Dictionary with comparison data or None
        """
        try:
            # Import WorkoutComparator from correct location
            from tools.rag.queries.comparisons import WorkoutComparator

            comparator = WorkoutComparator()
            result = comparator.find_similar_workouts(
                activity_id=activity_id,
                distance_tolerance=0.10,
                pace_tolerance=0.10,
                terrain_match=True,
                limit=10,
            )

            # Extract workouts list from result (correct key name)
            similar = result.get("similar_activities", [])

            if not similar or len(similar) < 3:
                logger.warning(
                    f"Insufficient similar workouts for activity {activity_id}"
                )
                return None

            # Calculate average differences from top 3
            # Note: WorkoutComparator already calculates pace_diff and hr_diff
            top_3 = similar[:3]
            avg_pace_diff = sum([w["pace_diff"] for w in top_3]) / 3
            avg_hr_diff = sum([w["hr_diff"] for w in top_3]) / 3

            # Use the average differences (negative means current is faster)
            pace_diff = avg_pace_diff
            hr_diff = avg_hr_diff

            # Calculate average values from differences
            # Note: pace_diff = candidate_pace - target_pace
            # So: avg_similar_pace = current_pace - avg_pace_diff (negative diff means current is faster)
            avg_similar_pace = current_metrics["avg_pace"] - avg_pace_diff
            avg_similar_hr = current_metrics["avg_hr"] - avg_hr_diff

            # Format comparison table
            comparisons = [
                {
                    "metric": "平均ペース",
                    "current": self._format_pace(current_metrics["avg_pace"]),
                    "average": self._format_pace(avg_similar_pace),
                    "change": (
                        f"+{abs(int(pace_diff))}秒速い"
                        if pace_diff < 0
                        else f"-{int(pace_diff)}秒遅い"
                    ),
                    "trend": (
                        "↗️ 改善"
                        if pace_diff < 0
                        else ("↘️ 悪化" if pace_diff > 5 else "➡️ 同等")
                    ),
                },
                {
                    "metric": "平均心拍",
                    "current": f"{int(current_metrics['avg_hr'])} bpm",
                    "average": f"{int(avg_similar_hr)} bpm",
                    "change": (
                        f"+{int(hr_diff)} bpm" if hr_diff > 0 else f"{int(hr_diff)} bpm"
                    ),
                    "trend": (
                        "➡️ 同等"
                        if abs(hr_diff) < 5
                        else ("⚠️ 高い" if hr_diff > 0 else "✅ 低い")
                    ),
                },
            ]

            # Generate insight
            insight = f"過去の類似ワークアウト{len(top_3)}回と比較して分析しました。"

            # Get distance range from similar activities (using target as reference)
            target_distance = result.get("target_activity", {}).get("distance_km", 0)

            return {
                "conditions": f"距離約{target_distance:.1f}km、ペース類似",
                "count": len(top_3),
                "comparisons": comparisons,
                "insight": insight,
                "pace_source": current_metrics.get("pace_source", "overall"),
            }

        except Exception as e:
            logger.warning(f"Could not load similar workouts: {e}")
            return None

    def _generate_workout_insight(
        self, similar_workouts: dict, training_type: str
    ) -> str:
        """
        Generate workout insight based on comparison data and training type.

        Args:
            similar_workouts: Similar workouts comparison data
            training_type: Training type (aerobic_base, lactate_threshold, etc.)

        Returns:
            Insight text with efficiency improvement percentage
        """
        if not similar_workouts or "comparisons" not in similar_workouts:
            return "データ不足のため算出不可"

        comparisons = {comp["metric"]: comp for comp in similar_workouts["comparisons"]}

        # Base run pattern: Pace faster + Power lower = Efficiency improvement
        if training_type in ["aerobic_base", "recovery"]:
            pace_comp = comparisons.get("平均ペース")
            power_comp = comparisons.get("平均パワー")

            if pace_comp and power_comp:
                # Extract numeric changes
                pace_change = self._extract_numeric_change(pace_comp["change"])
                power_change = self._extract_numeric_change(power_comp["change"])

                if pace_change < 0 and power_change < 0:  # Faster pace, lower power
                    # Calculate efficiency improvement percentage
                    avg_power = self._extract_numeric_value(power_comp["average"])
                    if avg_power and avg_power > 0:
                        efficiency_pct = abs(power_change / avg_power * 100)
                        return f"ペース{abs(pace_change):.0f}秒速いのにパワー{abs(power_change):.0f}W低下＝**効率が{efficiency_pct:.1f}%向上** ✅"

        # Interval pattern: Multiple metrics improvement
        elif training_type in [
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
        ]:
            improvements = []
            pace_comp = comparisons.get("Work平均ペース")
            power_comp = comparisons.get("Work平均パワー")
            stride_comp = comparisons.get("Work平均ストライド")

            if pace_comp and self._extract_numeric_change(pace_comp["change"]) < 0:
                pace_change = abs(self._extract_numeric_change(pace_comp["change"]))
                improvements.append(f"Workペース+{pace_change:.0f}秒速")

            if power_comp and self._extract_numeric_change(power_comp["change"]) > 0:
                power_change = self._extract_numeric_change(power_comp["change"])
                improvements.append(f"パワー+{power_change:.0f}W")

            if stride_comp and self._extract_numeric_change(stride_comp["change"]) > 0:
                stride_change = self._extract_numeric_change(stride_comp["change"])
                improvements.append(f"ストライド+{stride_change * 100:.0f}cm向上")

            if improvements:
                improvements_text = "、".join(improvements)
                return f"{improvements_text} = **高強度下でもフォーム効率とパワー出力を改善** ✅"

        # Threshold pattern: Same pace + Lower HR = Efficiency improvement
        elif training_type in ["lactate_threshold", "tempo"]:
            pace_comp = comparisons.get("メイン平均ペース")
            hr_comp = comparisons.get("メイン平均心拍")

            if pace_comp and hr_comp:
                pace_change = self._extract_numeric_change(pace_comp["change"])
                hr_change = self._extract_numeric_change(hr_comp["change"])

                if abs(pace_change) <= 1 and hr_change < 0:  # Same pace, lower HR
                    avg_hr = self._extract_numeric_value(hr_comp["average"])
                    if avg_hr and avg_hr > 0:
                        efficiency_pct = abs(hr_change / avg_hr * 100)
                        return f"同じペースで心拍{abs(hr_change):.0f}bpm低下 = **閾値での効率が{efficiency_pct:.1f}%向上** ✅"

        # Fallback: Generic improvement message
        return "複数指標で改善が見られます"

    def _extract_numeric_change(self, change_text: str) -> float:
        """
        Extract numeric change from comparison text.

        Examples:
            "+3秒速い" -> -3 (faster is negative)
            "-4 bpm" -> -4
            "+7 W" -> +7
            "+0.03 m" -> +0.03

        Args:
            change_text: Change text from comparison

        Returns:
            Numeric change value (negative for improvements in pace/HR)
        """
        import re

        # Extract number with optional sign
        match = re.search(r"([+-]?\d+\.?\d*)", change_text)
        if not match:
            return 0.0

        value = float(match.group(1))

        # Invert sign for "速い" (faster is better, so negative)
        if "速い" in change_text:
            value = -abs(value)

        return value

    def _extract_numeric_value(self, value_text: str) -> float | None:
        """
        Extract numeric value from text.

        Examples:
            "230 W" -> 230.0
            "171 bpm" -> 171.0
            "6:48/km" -> None (not a simple number)

        Args:
            value_text: Value text

        Returns:
            Numeric value or None
        """
        import re

        match = re.search(r"(\d+\.?\d*)", value_text)
        if match:
            return float(match.group(1))
        return None

    def _generate_reference_info(
        self, vo2_max_data: dict | None, lactate_threshold_data: dict | None
    ) -> str:
        """
        Generate reference information text for VO2 Max and lactate threshold.

        Example output:
            "> **参考**: VO2 Max 52.3 ml/kg/min（優秀）、閾値ペース 4:35/km"

        Args:
            vo2_max_data: VO2 Max data from database
            lactate_threshold_data: Lactate threshold data from database

        Returns:
            Formatted reference info text
        """
        parts = []

        # VO2 Max
        if vo2_max_data:
            vo2_value = vo2_max_data.get("precise_value") or vo2_max_data.get("value")
            vo2_category = vo2_max_data.get("category", "N/A")
            if vo2_value:
                parts.append(f"VO2 Max {vo2_value} ml/kg/min（{vo2_category}）")

        # Lactate threshold pace
        if lactate_threshold_data:
            threshold_speed = lactate_threshold_data.get("speed_mps")
            if threshold_speed and threshold_speed > 0:
                # Convert m/s to min/km
                pace_seconds_per_km = 1000 / threshold_speed
                pace_min = int(pace_seconds_per_km // 60)
                pace_sec = int(pace_seconds_per_km % 60)
                parts.append(f"閾値ペース {pace_min}:{pace_sec:02d}/km")

        if parts:
            return "> **参考**: " + "、".join(parts)
        return ""

    def _calculate_pace_corrected_form_efficiency(
        self, avg_pace_seconds_per_km: float, form_eff: dict
    ) -> dict:
        """Calculate pace-corrected form efficiency scores.

        Formulas from planning.md Appendix C:
        - GCT baseline: 230 + (pace - 240) * 0.22 ms
        - VO baseline: 6.8 + (pace - 240) * 0.004 cm
        - VR: No correction, absolute threshold 8.0-9.5%

        Args:
            avg_pace_seconds_per_km: Average pace in seconds per km
            form_eff: Form efficiency dictionary with gct_average, vo_average, vr_average

        Returns:
            Dictionary with pace-corrected form efficiency data
        """
        # Baseline calculations
        baseline_gct = 230 + (avg_pace_seconds_per_km - 240) * 0.22
        baseline_vo = 6.8 + (avg_pace_seconds_per_km - 240) * 0.004

        # GCT efficiency
        gct_actual = form_eff.get("gct_average", 0)
        gct_score = (
            ((gct_actual - baseline_gct) / baseline_gct) * 100
            if baseline_gct > 0
            else 0
        )
        gct_label = (
            "優秀" if gct_score < -5 else ("良好" if abs(gct_score) <= 5 else "要改善")
        )
        gct_rating = (
            5.0
            if gct_score < -5
            else (4.5 if gct_score < -2 else (4.0 if abs(gct_score) <= 5 else 3.0))
        )

        # VO efficiency
        vo_actual = form_eff.get("vo_average", 0)
        vo_score = (
            ((vo_actual - baseline_vo) / baseline_vo) * 100 if baseline_vo > 0 else 0
        )
        vo_label = (
            "優秀" if vo_score < -5 else ("良好" if abs(vo_score) <= 5 else "要改善")
        )
        vo_rating = (
            5.0
            if vo_score < -5
            else (4.5 if vo_score < -2 else (4.0 if abs(vo_score) <= 5 else 3.0))
        )

        # VR (no pace correction)
        vr_actual = form_eff.get("vr_average", 0)
        vr_label = "理想範囲内" if 8.0 <= vr_actual <= 9.5 else "要改善"
        vr_rating = 5.0 if 8.0 <= vr_actual <= 9.5 else 3.5

        return {
            "avg_pace_seconds": int(avg_pace_seconds_per_km),
            "gct": {
                "actual": round(gct_actual, 1),
                "baseline": round(baseline_gct, 1),
                "score": round(gct_score, 1),
                "label": gct_label,
                "rating_stars": "★" * int(gct_rating) + "☆" * (5 - int(gct_rating)),
                "rating_score": gct_rating,
            },
            "vo": {
                "actual": round(vo_actual, 2),
                "baseline": round(baseline_vo, 2),
                "score": round(vo_score, 1),
                "label": vo_label,
                "rating_stars": "★" * int(vo_rating) + "☆" * (5 - int(vo_rating)),
                "rating_score": vo_rating,
            },
            "vr": {
                "actual": round(vr_actual, 2),
                "label": vr_label,
                "rating_stars": "★" * int(vr_rating) + "☆" * (5 - int(vr_rating)),
                "rating_score": vr_rating,
            },
        }

    def load_section_analyses(
        self, activity_id: int
    ) -> dict[str, dict[str, Any]] | None:
        """
        Load section analyses from DuckDB matching actual data structures.

        Actual structure in DuckDB:
        - efficiency: {"efficiency": "..."}
        - environment: {"environmental": "..."}
        - phase: {"warmup_evaluation": "...", "main_evaluation": "...", "finish_evaluation": "..."}
        - split: {"analyses": {...}}
        - summary: {"activity_type": "...", "summary": "...", "recommendations": "..."}

        Args:
            activity_id: Activity ID

        Returns:
            Section analyses dict or None
        """
        logger.info("[2/4] Loading section analyses from DuckDB...")

        analyses = {}

        # Load efficiency analysis
        efficiency_data = self.db_reader.get_section_analysis(activity_id, "efficiency")
        if efficiency_data:
            analyses["efficiency"] = efficiency_data.get("efficiency", {})
        else:
            logger.warning("Warning: efficiency section analysis missing")

        # Load environment analysis (key is "environmental" not "environment_analysis")
        environment_data = self.db_reader.get_section_analysis(
            activity_id, "environment"
        )
        if environment_data:
            analyses["environment_analysis"] = environment_data.get("environmental", {})
        else:
            logger.warning("Warning: environment section analysis missing")

        # Load phase analysis (support both 3-phase and 4-phase structures)
        phase_data = self.db_reader.get_section_analysis(activity_id, "phase")
        if phase_data:
            # Detect structure: 4-phase (interval) or 3-phase (regular)
            if "recovery_evaluation" in phase_data:
                # 4-phase structure (warmup/run/recovery/cooldown)
                analyses["phase_evaluation"] = {
                    "warmup": {"evaluation": phase_data.get("warmup_evaluation", "")},
                    "run": {"evaluation": phase_data.get("run_evaluation", "")},
                    "recovery": {
                        "evaluation": phase_data.get("recovery_evaluation", "")
                    },
                    "cooldown": {
                        "evaluation": phase_data.get("cooldown_evaluation", "")
                    },
                }
            elif "run_evaluation" in phase_data:
                # 3-phase structure with new naming (warmup/run/cooldown)
                analyses["phase_evaluation"] = {
                    "warmup": {"evaluation": phase_data.get("warmup_evaluation", "")},
                    "run": {"evaluation": phase_data.get("run_evaluation", "")},
                    "cooldown": {
                        "evaluation": phase_data.get("cooldown_evaluation", "")
                    },
                }
            else:
                # Legacy 3-phase structure (warmup/main/finish)
                analyses["phase_evaluation"] = {
                    "warmup": {"evaluation": phase_data.get("warmup_evaluation", "")},
                    "main": {"evaluation": phase_data.get("main_evaluation", "")},
                    "finish": {"evaluation": phase_data.get("finish_evaluation", "")},
                }
        else:
            logger.warning("Warning: phase section analysis missing")

        # Load split analysis (includes both "analyses" and "highlights")
        split_data = self.db_reader.get_section_analysis(activity_id, "split")
        if split_data:
            analyses["split_analysis"] = split_data
        else:
            logger.warning("Warning: split section analysis missing or empty")

        # Load summary analysis
        summary_data = self.db_reader.get_section_analysis(activity_id, "summary")
        if summary_data:
            analyses["summary"] = summary_data
        else:
            logger.warning("Warning: summary section analysis missing")

        if not analyses:
            logger.warning("Warning: No section analyses found in DuckDB")
            return None

        return analyses

    def load_splits_data(self, activity_id: int) -> list[dict[str, Any]] | None:
        """
        Load splits data from splits table.

        Args:
            activity_id: Activity ID

        Returns:
            List of split dictionaries or None
        """
        logger.info("[2.5/4] Loading splits data from DuckDB...")

        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Load splits data from splits table
            result = conn.execute(
                """
                SELECT
                    split_index,
                    distance,
                    pace_seconds_per_km,
                    heart_rate,
                    cadence,
                    power,
                    stride_length,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    pace_str
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                logger.warning(
                    f"Warning: No splits data found in DuckDB for activity {activity_id}"
                )
                return None

            splits = []
            for row in result:
                splits.append(
                    {
                        "index": row[0],
                        "distance": row[1],
                        "pace_seconds_per_km": row[2],
                        "pace_formatted": (
                            row[12] if row[12] else "N/A"
                        ),  # Use pace_str from DB
                        "heart_rate": row[3],
                        "cadence": row[4],
                        "power": row[5],
                        "stride_length": (
                            row[6] / 100 if row[6] else None
                        ),  # Convert cm to m
                        "ground_contact_time": row[7],
                        "vertical_oscillation": row[8],
                        "vertical_ratio": row[9],
                        "elevation_gain": row[10],
                        "elevation_loss": row[11],
                    }
                )

            return splits

        except Exception as e:
            logger.error(f"Error loading splits data: {e}")
            return None

    def generate_report(
        self, activity_id: int, date: str | None = None
    ) -> dict[str, Any]:
        """
        Generate final report from performance.json and section analyses.

        Args:
            activity_id: Activity ID
            date: Activity date (YYYY-MM-DD format)

        Returns:
            Report generation result with path
        """
        # Resolve date if not provided
        if not date:
            date = self.db_reader.get_activity_date(activity_id)
            if not date:
                raise ValueError(f"Could not resolve date for activity {activity_id}")

        # Load data
        performance_data = self.load_performance_data(activity_id)
        if not performance_data:
            raise ValueError(f"No performance data found for activity {activity_id}")

        section_analyses = self.load_section_analyses(activity_id)

        if not section_analyses:
            raise ValueError(
                f"No section analyses found for activity {activity_id}. Cannot generate report."
            )

        # Load splits data for split analysis基本データ表示
        splits_data = self.load_splits_data(activity_id)

        logger.info("[3/4] Generating report from section analyses...")

        # Format pace values for display
        def format_pace(pace_seconds_per_km):
            if pace_seconds_per_km is None or pace_seconds_per_km == 0:
                return "N/A"
            minutes = int(pace_seconds_per_km // 60)
            seconds = int(pace_seconds_per_km % 60)
            return f"{minutes}:{seconds:02d}"

        # Add formatted pace values
        if "warmup_metrics" in performance_data:
            performance_data["warmup_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["warmup_metrics"].get("avg_pace_seconds_per_km")
            )
        if "run_metrics" in performance_data:
            performance_data["run_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["run_metrics"].get("avg_pace_seconds_per_km")
            )
        if "recovery_metrics" in performance_data:
            performance_data["recovery_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["recovery_metrics"].get("avg_pace_seconds_per_km")
            )
        if "cooldown_metrics" in performance_data:
            performance_data["cooldown_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["cooldown_metrics"].get("avg_pace_seconds_per_km")
            )
        # Legacy support
        if "main_metrics" in performance_data:
            performance_data["main_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["main_metrics"].get("avg_pace_seconds_per_km")
            )
        if "finish_metrics" in performance_data:
            performance_data["finish_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["finish_metrics"].get("avg_pace_seconds_per_km")
            )

        # Generate heart rate zone pie chart data
        hr_zone_pie_data = self._generate_hr_zone_pie_data(activity_id)

        # Extract split highlights
        split_analysis_data = section_analyses.get("split_analysis", {})
        highlights_list = split_analysis_data.get("highlights", "N/A")

        # Prepare template context
        training_type = performance_data.get("training_type", "")
        activity_type_display = self._get_activity_type_display(training_type)

        context = {
            "activity_id": str(activity_id),
            "date": date,
            "activity_name": performance_data.get("activity_name"),
            "location_name": performance_data.get("location_name"),
            "basic_metrics": performance_data.get("basic_metrics", {}),
            "weight_kg": performance_data.get("weight_kg"),
            "weather_data": performance_data.get("weather_data", {}),
            "gear_name": performance_data.get("gear_name"),
            "form_efficiency": performance_data.get("form_efficiency"),
            "performance_metrics": performance_data.get("performance_metrics"),
            "training_type": training_type,
            "activity_type": activity_type_display,
            "warmup_metrics": performance_data.get("warmup_metrics"),
            "run_metrics": performance_data.get("run_metrics"),
            "recovery_metrics": performance_data.get("recovery_metrics"),
            "cooldown_metrics": performance_data.get("cooldown_metrics"),
            "main_metrics": performance_data.get("main_metrics"),  # Legacy
            "finish_metrics": performance_data.get("finish_metrics"),  # Legacy
            "splits": splits_data,
            "efficiency": section_analyses.get("efficiency"),
            "environment_analysis": section_analyses.get("environment_analysis"),
            "phase_evaluation": section_analyses.get("phase_evaluation"),
            "split_analysis": section_analyses.get("split_analysis"),
            "summary": section_analyses.get("summary"),
            # Phase 3: Similar workouts comparison (from performance_data)
            "similar_workouts": performance_data.get("similar_workouts"),
            # Mermaid graph data
            "mermaid_data": performance_data.get("mermaid_data"),
            # Heart rate zone pie chart data
            "heart_rate_zone_pie_data": hr_zone_pie_data,
            # Split highlights
            "highlights_list": highlights_list,
        }

        # Render report using Jinja2 template with all data
        report_content = self.renderer.render_report(**context)

        logger.info("[4/4] Saving report to result/individual/...")

        # Save report
        save_result = self.renderer.save_report(str(activity_id), date, report_content)

        return {
            "success": True,
            "activity_id": activity_id,
            "date": date,
            "report_path": save_result["path"],
            "timestamp": datetime.now().isoformat(),
        }


def main():
    """Main entry point for report generator worker."""
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python -m tools.reporting.report_generator_worker <activity_id> [date]"
        )
        sys.exit(1)

    activity_id = int(sys.argv[1])
    date = sys.argv[2] if len(sys.argv) > 2 else None

    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id, date)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
