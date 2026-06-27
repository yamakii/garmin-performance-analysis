"""Athlete domain tool definitions.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.

All four tools use ``input_schema_override``: ``profile`` / ``review`` are
free-form ``object`` params, and the optional ``user_id`` / ``week_start_date``
fields were declared without JSON ``default`` keys in the hand schemas.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)

# Runtime default preserved from the previous Pydantic models: ``user_id`` is
# modeled as ``str | None = None`` (so the derived schema emits no ``default``
# key, matching the hand schema) and coalesced to this in the handlers.
_DEFAULT_USER_ID = "default"


# ----------------------------------------------------------------------------
# Params models
# ----------------------------------------------------------------------------


class SaveAthleteProfileParams(BaseModel):
    """Arguments for ``save_athlete_profile``."""

    profile: dict[str, Any] = Field(
        description=(
            "Profile JSON with user_id (default 'default'), current_focus, "
            "focus_notes, week_start_day (0=Mon..6=Sun, default 0), goals (list "
            "of {race_name, race_date, priority, goal_type, distance_km, "
            "target_time_seconds, status, notes}), and retrospectives (list of "
            "{season_label, period_start, period_end, narrative, key_learnings})."
        )
    )


class GetAthleteProfileParams(BaseModel):
    """Arguments for ``get_athlete_profile``."""

    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class SaveWeeklyReviewParams(BaseModel):
    """Arguments for ``save_weekly_review``."""

    review: dict[str, Any] = Field(
        description=(
            "Review JSON with user_id (default 'default'), week_start_date, "
            "week_end_date, review_date, review_data (object, e.g. {this_week, "
            "garmin_next_week, verdict, recommendations, overall}), agent_name, "
            "and agent_version."
        )
    )


class GetWeeklyReviewParams(BaseModel):
    """Arguments for ``get_weekly_review``."""

    week_start_date: str | None = Field(
        default=None,
        description=(
            "Week start date (YYYY-MM-DD). When omitted, returns the most recent "
            "review."
        ),
    )
    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _save_athlete_profile(reader: GarminDBReader, p: SaveAthleteProfileParams) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_athlete_profile

    try:
        profile = p.profile
        insert_athlete_profile(profile=profile, db_path=str(reader.db_path))
        return {
            "status": "saved",
            "user_id": profile.get("user_id", "default"),
            "goal_count": len(profile.get("goals") or []),
            "retrospective_count": len(profile.get("retrospectives") or []),
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save athlete profile failed: {e}")
        return {"error": str(e)}


def _get_athlete_profile(reader: GarminDBReader, p: GetAthleteProfileParams) -> Any:
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        athlete_reader = AthleteReader(db_path=str(reader.db_path))
        return athlete_reader.get_athlete_profile(
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get athlete profile failed: {e}")
        return {"error": str(e)}


def _save_weekly_review(reader: GarminDBReader, p: SaveWeeklyReviewParams) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_weekly_review

    try:
        review = p.review
        insert_weekly_review(review=review, db_path=str(reader.db_path))
        return {
            "status": "saved",
            "user_id": review.get("user_id", "default"),
            "week_start_date": review.get("week_start_date"),
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save weekly review failed: {e}")
        return {"error": str(e)}


def _get_weekly_review(reader: GarminDBReader, p: GetWeeklyReviewParams) -> Any:
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        athlete_reader = AthleteReader(db_path=str(reader.db_path))
        return athlete_reader.get_weekly_review(
            week_start_date=p.week_start_date,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get weekly review failed: {e}")
        return {"error": str(e)}


ATHLETE_TOOLS: list[ToolDef] = [
    ToolDef(
        name="save_athlete_profile",
        description=(
            "Save the athlete profile (current focus, race goals, and season "
            "retrospectives) as a single object to DuckDB. The profile row is "
            "upserted on user_id; goals and retrospectives are fully replaced per "
            "user_id."
        ),
        params=SaveAthleteProfileParams,
        handler=_save_athlete_profile,
        cli_group="athlete",
        cli_name="save-profile",
    ),
    ToolDef(
        name="get_athlete_profile",
        description=(
            "Get the athlete profile (current focus, goals, and retrospectives) "
            "merged into a single object. Returns an empty structure "
            "(current_focus=None, goals=[], retrospectives=[]) when no profile is "
            "registered."
        ),
        params=GetAthleteProfileParams,
        handler=_get_athlete_profile,
        cli_group="athlete",
        cli_name="get-profile",
    ),
    ToolDef(
        name="save_weekly_review",
        description=(
            "Save a weekly training review to DuckDB. Each save appends a new "
            "version for (user_id, week_start_date) instead of overwriting, so "
            "re-running the same week keeps prior versions as history; the latest "
            "version is treated as canonical. The free-form review_data payload is "
            "stored as JSON."
        ),
        params=SaveWeeklyReviewParams,
        handler=_save_weekly_review,
        cli_group="athlete",
        cli_name="save-review",
    ),
    ToolDef(
        name="get_weekly_review",
        description=(
            "Get a single weekly review (the latest version of its week). When "
            "week_start_date is omitted, the latest version of the most recent "
            "week is returned. review_data is JSON-decoded back into an object. "
            "Returns null when no matching review exists."
        ),
        params=GetWeeklyReviewParams,
        handler=_get_weekly_review,
        cli_group="athlete",
        cli_name="get-review",
    ),
]


ATHLETE_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in ATHLETE_TOOLS}
