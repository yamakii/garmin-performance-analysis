"""Garmin Connect calendar-service reader for scheduled workouts."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# itemType values that represent scheduled workouts (vs nap/weight/activity/etc.)
_WORKOUT_ITEM_TYPES = {"fbtAdaptiveWorkout", "workout"}


class GarminCalendarReader:
    """Reads scheduled workouts from the Garmin Connect calendar-service."""

    def _get_garmin_client(self) -> Any:
        """Get authenticated Garmin Connect client.

        Mirrors ``GarminWorkoutUploader._get_garmin_client``.
        """
        from garmin_mcp.ingest.garmin_worker import GarminIngestWorker

        worker = GarminIngestWorker()
        return worker.get_garmin_client()

    @staticmethod
    def _connectapi_get(client: Any, path: str) -> Any:
        """Perform a GET against the connectapi domain.

        garminconnect exposes ``client.client`` as the underlying auth client.
        Newer versions provide ``connectapi(path)`` directly; older ones require
        ``get("connectapi", path, api=True).json()``. Support both.
        """
        inner = client.client
        connectapi = getattr(inner, "connectapi", None)
        if callable(connectapi):
            return connectapi(path)
        return inner.get("connectapi", path, api=True).json()

    @staticmethod
    def _enumerate_months(start: date, end: date) -> list[tuple[int, int]]:
        """Enumerate (year, month) pairs spanning [start, end] inclusive.

        ``month`` is 0-based to match the calendar-service convention
        (January = 0, June = 5).
        """
        months: list[tuple[int, int]] = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            months.append((year, month - 1))  # 0-based month for the API
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        return months

    def get_scheduled_workouts(
        self, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Fetch scheduled workouts from the Garmin calendar-service.

        Enumerates every (year, month) spanning [start_date, end_date], fetches
        each month's calendar (``month`` is 0-based), merges ``calendarItems``,
        keeps only workout-type items within the date range, and returns them
        sorted by date ascending.

        Args:
            start_date: Inclusive start date "YYYY-MM-DD"
            end_date: Inclusive end date "YYYY-MM-DD"

        Returns:
            List of dicts: {date, title, item_type, training_plan_id,
            training_plan_name, workout_uuid}. Missing keys are None.
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        client = self._get_garmin_client()

        results: list[dict[str, Any]] = []
        for year, month in self._enumerate_months(start, end):
            path = f"/calendar-service/year/{year}/month/{month}"
            payload = self._connectapi_get(client, path)
            items = (payload or {}).get("calendarItems") or []

            for item in items:
                item_type = item.get("itemType")
                if item_type not in _WORKOUT_ITEM_TYPES:
                    continue

                date_str = item.get("date")
                if not date_str:
                    continue
                try:
                    item_date = date.fromisoformat(date_str)
                except ValueError:
                    logger.warning("Skipping calendar item with bad date: %r", date_str)
                    continue

                if not (start <= item_date <= end):
                    continue

                results.append(
                    {
                        "date": date_str,
                        "title": item.get("title"),
                        "item_type": item_type,
                        "training_plan_id": item.get("trainingPlanId"),
                        "training_plan_name": item.get("trainingPlanName"),
                        "workout_uuid": item.get("workoutUuid"),
                    }
                )

        results.sort(key=lambda r: r["date"])
        return results
