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
        """Get authenticated Garmin Connect client via the ingest worker."""
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

        The calendar service repeats the same item within a single month payload
        (every entry of a real 2026-08/09 query came back exactly twice, #880), so
        rows are de-duplicated in first-seen order by ``schedule_id`` when present,
        falling back to (date, item_type, workout_uuid, title) otherwise. Two
        genuinely distinct assignments carry different ids and are both kept.

        Args:
            start_date: Inclusive start date "YYYY-MM-DD"
            end_date: Inclusive end date "YYYY-MM-DD"

        Returns:
            List of dicts: {date, title, item_type, schedule_id,
            training_plan_id, training_plan_name, workout_uuid}. Missing keys
            are None.
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        client = self._get_garmin_client()

        results: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
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

                schedule_id = item.get("id")
                title = item.get("title")
                workout_uuid = item.get("workoutUuid")
                key: tuple[Any, ...] = (
                    ("id", schedule_id)
                    if schedule_id is not None
                    else ("row", date_str, item_type, workout_uuid, title)
                )
                if key in seen:
                    continue
                seen.add(key)

                results.append(
                    {
                        "date": date_str,
                        "title": title,
                        "item_type": item_type,
                        "schedule_id": schedule_id,
                        "training_plan_id": item.get("trainingPlanId"),
                        "training_plan_name": item.get("trainingPlanName"),
                        "workout_uuid": workout_uuid,
                    }
                )

        results.sort(key=lambda r: r["date"])
        return results
