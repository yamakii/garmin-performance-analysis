"""Athlete domain tool definitions.

``profile`` / ``review`` are free-form ``object`` params, and the optional
``user_id`` / ``week_start_date`` / ``limit`` fields are modeled as
``T | None = None`` so the derived schema emits no JSON ``default`` key; the
runtime defaults are applied in the handlers below.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)

# Runtime default preserved from the previous Pydantic models: ``user_id`` is
# modeled as ``str | None = None`` (so the derived schema emits no ``default``
# key, matching the hand schema) and coalesced to this in the handlers.
_DEFAULT_USER_ID = "default"

# Controlled vocabulary for a symptom's location. Kept as a closed Literal so a
# typo ("archilles") cannot silently create a region that no query will ever
# match again; the column itself stays VARCHAR (issue #1220).
_BODY_REGIONS = Literal[
    "foot",
    "ankle",
    "achilles",
    "calf",
    "shin",
    "knee",
    "hamstring",
    "quad",
    "hip",
    "glute",
    "groin",
    "lower_back",
    "other",
]

# What an athlete-stated activity fact is about (issue #1520). Closed so a
# reader can match on kind; anything else goes under "other" with a value.
_CONTEXT_KINDS = Literal[
    "commute",
    "load",
    "strides_carried",
    "walk_reason",
    "apparel",
    "sensor_mount",
    "other",
]

# Where an athlete-specific coaching rule applies. "all" rules are returned for
# every scope filter (issue #1520).
_RULE_SCOPES = Literal[
    "all",
    "conversation",
    "run_note",
    "checkin",
    "debrief",
    "planning",
]


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
            "{season_label, period_start, period_end, narrative, key_learnings}). "
            "Every key but user_id is optional: an omitted key keeps its stored "
            "value, a present key (even null / []) replaces it."
        )
    )


class AppendFocusNotesParams(BaseModel):
    """Arguments for ``append_focus_notes``."""

    text: str = Field(description="Text to append to focus_notes (Japanese prose)")
    section: str | None = Field(
        default=None,
        description=(
            "Heading name of a 【…】 section, without the brackets (e.g. "
            "'効率ベンチマーク'). Omitted: text becomes a new line at the end. "
            "Matching heading (【name】 or 【name: …】 at a line start): text is "
            "appended to the end of that section. No match: a new 【name】text "
            "line is added at the end."
        ),
    )
    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class GetAthleteProfileParams(BaseModel):
    """Arguments for ``get_athlete_profile``."""

    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class ListAthleteProfileVersionsParams(BaseModel):
    """Arguments for ``list_athlete_profile_versions``."""

    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )
    limit: int | None = Field(
        default=None, description="Maximum number of versions to return (default: 5)"
    )


class GetAthleteProfileVersionParams(BaseModel):
    """Arguments for ``get_athlete_profile_version``."""

    version_id: int = Field(
        description="Version identifier from list_athlete_profile_versions"
    )
    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class SaveWeeklyReviewParams(BaseModel):
    """Arguments for ``save_weekly_review``."""

    review: dict[str, Any] = Field(
        description=(
            "Review JSON with user_id (default 'default'), week_start_date, "
            "week_end_date, review_date, review_data (object, e.g. {this_week, "
            "garmin_next_week, recommendations, overall}), agent_name, and "
            "agent_version. review_data must NOT carry verdict rows: the "
            "per-day plan (rating/rationale) belongs to "
            "save_weekly_prescriptions and the verdict is derived from it."
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


class SaveSymptomParams(BaseModel):
    """Arguments for ``save_symptom``."""

    date: str = Field(description="Date the symptom was felt (YYYY-MM-DD)")
    body_region: _BODY_REGIONS = Field(
        description="Where it was felt (one region per call; log two spots twice)"
    )
    severity: int = Field(
        ge=0,
        le=10,
        description=(
            "0-10, where 0 means asked and clear (worth logging: it separates "
            "'no pain' from 'not asked'), 1-3 niggle, 4-6 pain that alters the "
            "run, 7-10 pain that stops it"
        ),
    )
    phase: Literal["during_run", "after_run", "morning", "rest_day"] = Field(
        description="When it was felt: during_run, after_run, morning, rest_day"
    )
    side: Literal["left", "right", "both"] | None = Field(
        default=None, description="Side of the body (omit when not applicable)"
    )
    activity_id: int | None = Field(
        default=None, description="The run this refers to, when there is one"
    )
    note: str | None = Field(
        default=None, description="Free-form note in the athlete's own words"
    )
    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class GetSymptomsParams(BaseModel):
    """Arguments for ``get_symptoms``."""

    start_date: str = Field(description="Range start, inclusive (YYYY-MM-DD)")
    end_date: str = Field(description="Range end, inclusive (YYYY-MM-DD)")
    body_region: str | None = Field(
        default=None,
        description="Optional region filter (e.g. 'calf'); omit for every region",
    )
    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class GetSymptomStatusParams(BaseModel):
    """Arguments for ``get_symptom_status``."""

    date: str | None = Field(
        default=None,
        description=(
            "Reference day (YYYY-MM-DD). When omitted, today is used (symptoms "
            "describe how the legs are now, not on the last run's date)."
        ),
    )
    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class SaveIntakeConfirmationParams(BaseModel):
    """Arguments for ``save_intake_confirmation``."""

    date: str = Field(description="Day the food log is about (YYYY-MM-DD)")
    status: Literal["complete", "incomplete"] = Field(
        description=(
            "complete: the log holds everything eaten that day (lifts a "
            "suspect_low flag); incomplete: food is missing (the day is "
            "excluded from the energy balance)"
        )
    )
    note: str | None = Field(
        default=None, description="Free-form note in the athlete's own words"
    )


class SaveActivityContextParams(BaseModel):
    """Arguments for ``save_activity_context``."""

    activity_id: int = Field(description="The activity the fact is about")
    kind: _CONTEXT_KINDS = Field(
        description=(
            "What the fact is about: commute, load (carried weight), "
            "strides_carried (strides done the day before), walk_reason, "
            "apparel, sensor_mount, other"
        )
    )
    value: str | None = Field(
        default=None,
        description="Short free value, e.g. 'running backpack'",
    )
    load_kg: float | None = Field(
        default=None,
        ge=0,
        le=30,
        description="Carried load in kg (only for kind='load', 0-30)",
    )
    source: Literal["athlete_stated", "inferred"] = Field(
        default="athlete_stated",
        description=(
            "athlete_stated: the athlete said it; inferred: read from the "
            "conversation without being said outright"
        ),
    )
    note: str | None = Field(
        default=None, description="Free-form note in the athlete's own words"
    )
    user_id: str = Field(
        default=_DEFAULT_USER_ID, description="Profile owner identifier"
    )


class GetActivityContextParams(BaseModel):
    """Arguments for ``get_activity_context``."""

    activity_ids: list[int] | None = Field(
        default=None, description="Activities to read; omit for every activity"
    )
    start_date: str | None = Field(
        default=None,
        description="Range start on activity_date, inclusive (YYYY-MM-DD)",
    )
    end_date: str | None = Field(
        default=None,
        description="Range end on activity_date, inclusive (YYYY-MM-DD)",
    )


class SaveCoachingRuleParams(BaseModel):
    """Arguments for ``save_coaching_rule``."""

    scope: _RULE_SCOPES = Field(
        description=(
            "Where the rule applies: all, conversation, run_note, checkin, "
            "debrief, planning"
        )
    )
    rule_text: str = Field(
        min_length=1,
        max_length=400,
        description="The rule, written as an instruction (1-400 chars)",
    )
    rationale: str | None = Field(
        default=None,
        description=(
            "Why the rule exists (incident summary); background only, never "
            "shown as advice"
        ),
    )
    origin_date: str | None = Field(
        default=None, description="Date of the incident behind it (YYYY-MM-DD)"
    )


class GetCoachingRulesParams(BaseModel):
    """Arguments for ``get_coaching_rules``."""

    scopes: list[_RULE_SCOPES] | None = Field(
        default=None,
        description=(
            "Scopes to read; 'all' rules are always included. Omit for every " "scope"
        ),
    )
    include_inactive: bool = Field(
        default=False, description="Also return deactivated rules"
    )


class DeactivateCoachingRuleParams(BaseModel):
    """Arguments for ``deactivate_coaching_rule``."""

    rule_id: int = Field(description="rule_id from get_coaching_rules")


class PrefetchWeeklyReviewContextParams(BaseModel):
    """Arguments for ``prefetch_weekly_review_context``."""

    target: str | None = Field(
        default=None,
        description=(
            "Target week W selector: omit for the smart default (today == last "
            "day of the week -> next week, else this week), 'this' for the week "
            "containing today, 'next' for the following week, or a YYYY-MM-DD "
            "date within the desired week."
        ),
    )
    user_id: str | None = Field(
        default=None, description="Profile owner identifier (default: 'default')"
    )


class GetCurrentStandingParams(BaseModel):
    """Arguments for ``get_current_standing``."""

    date: str | None = Field(
        default=None,
        description="Reference day (YYYY-MM-DD). When omitted, today is used.",
    )


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _save_athlete_profile(reader: GarminDBReader, p: SaveAthleteProfileParams) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_athlete_profile
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        profile = p.profile
        user_id = profile.get("user_id") or _DEFAULT_USER_ID
        insert_athlete_profile(profile=profile, db_path=str(reader.db_path))
        # Count what is stored: omitted keys kept their previous rows.
        saved = AthleteReader(db_path=str(reader.db_path)).get_athlete_profile(
            user_id=user_id
        )
        return {
            "status": "saved",
            "user_id": user_id,
            "goal_count": len(saved["goals"]),
            "retrospective_count": len(saved["retrospectives"]),
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save athlete profile failed: {e}")
        return {"error": str(e)}


def _append_focus_notes(reader: GarminDBReader, p: AppendFocusNotesParams) -> Any:
    from garmin_mcp.database.inserters.athlete import append_focus_notes

    try:
        return append_focus_notes(
            text=p.text,
            section=p.section,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
            db_path=str(reader.db_path),
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Append focus notes failed: {e}")
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


_DEFAULT_VERSION_LIMIT = 5


def _list_athlete_profile_versions(
    reader: GarminDBReader, p: ListAthleteProfileVersionsParams
) -> Any:
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        athlete_reader = AthleteReader(db_path=str(reader.db_path))
        return athlete_reader.list_athlete_profile_versions(
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
            limit=p.limit if p.limit is not None else _DEFAULT_VERSION_LIMIT,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"List athlete profile versions failed: {e}")
        return {"error": str(e)}


def _get_athlete_profile_version(
    reader: GarminDBReader, p: GetAthleteProfileVersionParams
) -> Any:
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        athlete_reader = AthleteReader(db_path=str(reader.db_path))
        return athlete_reader.get_athlete_profile_version(
            version_id=p.version_id,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get athlete profile version failed: {e}")
        return {"error": str(e)}


def _save_weekly_review(reader: GarminDBReader, p: SaveWeeklyReviewParams) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_weekly_review

    try:
        review = p.review
        review_id = insert_weekly_review(review=review, db_path=str(reader.db_path))
        return {
            "status": "saved",
            "user_id": review.get("user_id", "default"),
            "week_start_date": review.get("week_start_date"),
            "review_id": review_id,
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


def _save_symptom(reader: GarminDBReader, p: SaveSymptomParams) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_symptom

    try:
        row = p.model_dump()
        row["user_id"] = p.user_id if p.user_id is not None else _DEFAULT_USER_ID
        symptom_id = insert_symptom(row=row, db_path=str(reader.db_path))
        return {"status": "saved", "symptom_id": symptom_id}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save symptom failed: {e}")
        return {"error": str(e)}


def _get_symptoms(reader: GarminDBReader, p: GetSymptomsParams) -> Any:
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        athlete_reader = AthleteReader(db_path=str(reader.db_path))
        return athlete_reader.get_symptoms(
            start_date=p.start_date,
            end_date=p.end_date,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
            body_region=p.body_region,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get symptoms failed: {e}")
        return {"error": str(e)}


def _get_symptom_status(reader: GarminDBReader, p: GetSymptomStatusParams) -> Any:
    try:
        return reader.get_symptom_status(
            date=p.date,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get symptom status failed: {e}")
        return {"error": str(e)}


def _save_intake_confirmation(
    reader: GarminDBReader, p: SaveIntakeConfirmationParams
) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_intake_confirmation

    try:
        saved = insert_intake_confirmation(
            date=p.date, status=p.status, note=p.note, db_path=str(reader.db_path)
        )
        return {"saved": True, **saved}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save intake confirmation failed: {e}")
        return {"error": str(e)}


def _save_activity_context(reader: GarminDBReader, p: SaveActivityContextParams) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_activity_context

    try:
        context_id = insert_activity_context(
            row=p.model_dump(), db_path=str(reader.db_path)
        )
        return {
            "status": "saved",
            "context_id": context_id,
            "activity_id": p.activity_id,
            "kind": p.kind,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save activity context failed: {e}")
        return {"error": str(e)}


def _get_activity_context(reader: GarminDBReader, p: GetActivityContextParams) -> Any:
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        return AthleteReader(db_path=str(reader.db_path)).get_activity_context(
            activity_ids=p.activity_ids,
            start_date=p.start_date,
            end_date=p.end_date,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get activity context failed: {e}")
        return {"error": str(e)}


def _save_coaching_rule(reader: GarminDBReader, p: SaveCoachingRuleParams) -> Any:
    from garmin_mcp.database.inserters.athlete import insert_coaching_rule

    try:
        rule_id = insert_coaching_rule(row=p.model_dump(), db_path=str(reader.db_path))
        return {"status": "saved", "rule_id": rule_id, "scope": p.scope}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save coaching rule failed: {e}")
        return {"error": str(e)}


def _get_coaching_rules(reader: GarminDBReader, p: GetCoachingRulesParams) -> Any:
    from garmin_mcp.database.readers.athlete import AthleteReader

    try:
        return AthleteReader(db_path=str(reader.db_path)).get_coaching_rules(
            scopes=list(p.scopes) if p.scopes is not None else None,
            include_inactive=p.include_inactive,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get coaching rules failed: {e}")
        return {"error": str(e)}


def _deactivate_coaching_rule(
    reader: GarminDBReader, p: DeactivateCoachingRuleParams
) -> Any:
    from garmin_mcp.database.inserters.athlete import deactivate_coaching_rule

    try:
        found = deactivate_coaching_rule(rule_id=p.rule_id, db_path=str(reader.db_path))
        if not found:
            return {"error": f"coaching rule {p.rule_id} not found"}
        return {"status": "deactivated", "rule_id": p.rule_id}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Deactivate coaching rule failed: {e}")
        return {"error": str(e)}


def _prefetch_weekly_review_context(
    reader: GarminDBReader, p: PrefetchWeeklyReviewContextParams
) -> Any:
    from garmin_mcp.scripts.prefetch_weekly_review_context import (
        prefetch_weekly_review_context,
    )

    return prefetch_weekly_review_context(
        target=p.target,
        user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
    )


def _get_current_standing(reader: GarminDBReader, p: GetCurrentStandingParams) -> Any:
    from garmin_mcp.database.readers.standing import StandingReader

    try:
        return StandingReader(db_path=str(reader.db_path)).get_current_standing(
            on_date=p.date
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get current standing failed: {e}")
        return {"error": str(e)}


ATHLETE_TOOLS: list[ToolDef] = [
    ToolDef(
        name="save_athlete_profile",
        description=(
            "Save the athlete profile (current focus, race goals, and season "
            "retrospectives) as a single object to DuckDB. A save is a partial "
            "update: keys omitted from the payload keep their stored value, so "
            "sending only focus_notes leaves the goals and retrospectives intact. "
            "A present key replaces the stored value (goals / retrospectives are "
            "fully replaced per user_id; null / [] clears). Each save "
            "additionally appends a JSON snapshot of the whole merged profile as "
            "a new version, keeping overwritten content (e.g. the previous "
            "focus_notes) recoverable via list_athlete_profile_versions + "
            "get_athlete_profile_version. To add to focus_notes, prefer "
            "append_focus_notes over resending the whole text."
        ),
        params=SaveAthleteProfileParams,
        handler=_save_athlete_profile,
        cli_group="athlete",
        cli_name="save-profile",
    ),
    ToolDef(
        name="append_focus_notes",
        description=(
            "Append text to athlete_profile.focus_notes without resending the "
            "whole notes. Only focus_notes changes; current_focus, goals and "
            "retrospectives are untouched. With section, the text joins the end "
            "of that 【section】 (a 。 is added first when needed; no newline, a "
            "section stays one line), or a new 【section】text line is created "
            "when no heading matches; an ambiguous section (two matching "
            "headings) is rejected without writing. Appends a profile version "
            "like save_athlete_profile. Returns status, section, "
            "section_created, chars_before, chars_after and version_id."
        ),
        params=AppendFocusNotesParams,
        handler=_append_focus_notes,
        cli_group="athlete",
        cli_name="append-focus-notes",
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
        name="list_athlete_profile_versions",
        description=(
            "List recent athlete profile snapshots as metadata only (newest "
            "first). Every save_athlete_profile appends the whole profile as a "
            "new version; this indexes that history without the bulky snapshot: "
            "each entry has version_id, user_id, created_at, current_focus, "
            "focus_notes_chars, n_goals, and n_retrospectives. Use "
            "get_athlete_profile_version to read one snapshot in full. Returns "
            "an empty list when no version exists."
        ),
        params=ListAthleteProfileVersionsParams,
        handler=_list_athlete_profile_versions,
        cli_group="athlete",
        cli_name="list-profile-versions",
    ),
    ToolDef(
        name="get_athlete_profile_version",
        description=(
            "Get one athlete profile snapshot in full: version_id, user_id, "
            "created_at, and profile_data (the snapshot decoded back into an "
            "object). Pick version_id from list_athlete_profile_versions; "
            "snapshots are large, so fetch one at a time. Returns null when no "
            "such version exists for the user."
        ),
        params=GetAthleteProfileVersionParams,
        handler=_get_athlete_profile_version,
        cli_group="athlete",
        cli_name="get-profile-version",
    ),
    ToolDef(
        name="save_weekly_review",
        description=(
            "Save a weekly training review to DuckDB. Each save appends a new "
            "version for (user_id, week_start_date) instead of overwriting, so "
            "re-running the same week keeps prior versions as history; the latest "
            "version is treated as canonical. The free-form review_data payload is "
            "stored as JSON, minus the per-day plan: a non-empty review_data."
            "verdict is rejected because those rows live in "
            "save_weekly_prescriptions (rating/rationale) and the verdict is "
            "derived from them on read. Returns {status, user_id, "
            "week_start_date, review_id}; pass review_id to "
            "save_weekly_prescriptions to link the week's prescribed sessions "
            "to this review version."
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
            "week is returned. review_data is JSON-decoded back into an object; "
            "its verdict is derived from the week's canonical weekly_prescriptions "
            "batch (verdict_source='prescriptions' with prescription_batch_id, or "
            "'stored' for reviews written before the split). Returns null when no "
            "matching review exists."
        ),
        params=GetWeeklyReviewParams,
        handler=_get_weekly_review,
        cli_group="athlete",
        cli_name="get-review",
    ),
    ToolDef(
        name="save_symptom",
        description=(
            "Log one pain / tightness report to DuckDB: what was felt, where "
            "(one body region per call), how bad (severity 0-10), and when "
            "(during_run / after_run / morning / rest_day). Rows are "
            "append-only, so two sore spots on one day are two calls and a "
            "later report never overwrites an earlier one. Log severity 0 when "
            "the athlete was asked and reported nothing: that row is what lets "
            "a later read tell 'no pain' from 'never asked'. Returns "
            "{status, symptom_id}."
        ),
        params=SaveSymptomParams,
        handler=_save_symptom,
        cli_group="athlete",
        cli_name="save-symptom",
    ),
    ToolDef(
        name="get_symptoms",
        description=(
            "Get the athlete's symptom (pain / niggle) reports in a date range, "
            "oldest first, optionally narrowed to one body_region. Each row "
            "carries date, body_region, side, severity, phase, activity_id and "
            "note; severity-0 rows are included because they record an "
            "explicit all-clear. Returns an empty list when nothing was logged."
        ),
        params=GetSymptomsParams,
        handler=_get_symptoms,
        cli_group="athlete",
        cli_name="get-symptoms",
    ),
    ToolDef(
        name="get_symptom_status",
        description=(
            "Get the deterministic symptom verdict for a day: reads the last 14 "
            "days of symptom reports and flags a body region when its two most "
            "recent reports are both severity 3+ (pain that comes and goes) or "
            "when any report within 7 days hit severity 5+. Returns {date, flag, "
            "flagged_regions (body_region, side, rule='consecutive'|'acute', "
            "latest_severity, latest_date, reports), asked_today, clear_today, "
            "recently_cleared, days_since_last_report, reason_ja}. Use this for "
            "gates ('run only if no leg tightness'): clear_today distinguishes "
            "an explicit all-clear from a question that was never asked, and "
            "days_since_last_report is null when nothing was logged at all."
        ),
        params=GetSymptomStatusParams,
        handler=_get_symptom_status,
        cli_group="athlete",
        cli_name="symptom-status",
    ),
    ToolDef(
        name="save_intake_confirmation",
        description=(
            "Record the athlete's own word on one day's food log (MyFitnessPal "
            "via Garmin): status 'complete' (everything eaten is logged -- "
            "lifts a suspect_low flag so the day counts) or 'incomplete' (food "
            "is missing -- the day is excluded from get_energy_balance). One "
            "row per date: a later call replaces the earlier one. The "
            "confirmation is ignored once the day's intake changes after it "
            "was given. Returns {saved, date, status, note, user_id, "
            "confirmed_at}."
        ),
        params=SaveIntakeConfirmationParams,
        handler=_save_intake_confirmation,
        cli_group="athlete",
        cli_name="save-intake-confirmation",
    ),
    ToolDef(
        name="save_activity_context",
        description=(
            "Record one fact the athlete stated about an activity: a commute "
            "run, the load carried (load_kg), strides carried over from the "
            "previous day, why they walked, apparel or sensor mounting. Write "
            "it silently when the athlete states the fact in conversation; "
            "never ask them to keep a log. Rows are append-only and stay in "
            "the local DB only; a later save for the same (activity_id, kind) "
            "supersedes the earlier one on read. Returns {status, context_id, "
            "activity_id, kind}."
        ),
        params=SaveActivityContextParams,
        handler=_save_activity_context,
        cli_group="athlete",
        cli_name="save-activity-context",
    ),
    ToolDef(
        name="get_activity_context",
        description=(
            "Get the athlete-stated facts about activities (commute, load, "
            "strides_carried, walk_reason, apparel, sensor_mount, other), the "
            "newest row per (activity_id, kind), filtered by activity_ids "
            "and/or an activity_date range. Each row carries activity_date, "
            "kind, value, load_kg, source (athlete_stated / inferred) and "
            "note. Returns an empty list when nothing was recorded."
        ),
        params=GetActivityContextParams,
        handler=_get_activity_context,
        cli_group="athlete",
        cli_name="get-activity-context",
    ),
    ToolDef(
        name="save_coaching_rule",
        description=(
            "Store a coaching rule that applies only to this athlete (a "
            "preference, a correction, an incident-derived read) in the local "
            "DB. coaching_rules holds athlete-specific rules that must not be "
            "written into the repository (rules, agents, skills or code). "
            "Write it silently when the athlete states or corrects something; "
            "never ask them to keep a log. scope picks where it applies (all / "
            "conversation / run_note / checkin / debrief / planning); "
            "rule_text is the instruction (1-400 chars), rationale the "
            "background (never shown as advice). Returns {status, rule_id, "
            "scope}."
        ),
        params=SaveCoachingRuleParams,
        handler=_save_coaching_rule,
        cli_group="athlete",
        cli_name="save-coaching-rule",
    ),
    ToolDef(
        name="get_coaching_rules",
        description=(
            "Get the athlete-specific coaching rules stored in the local DB "
            "(coaching_rules: rules that must not be written into the "
            "repository). With scopes, rules of those scopes plus every "
            "scope='all' rule are returned; deactivated rules are hidden "
            "unless include_inactive. Each row carries rule_id, scope, "
            "rule_text, rationale, origin_date, active, created_at and "
            "deactivated_at. Returns an empty list when none are stored."
        ),
        params=GetCoachingRulesParams,
        handler=_get_coaching_rules,
        cli_group="athlete",
        cli_name="get-coaching-rules",
    ),
    ToolDef(
        name="deactivate_coaching_rule",
        description=(
            "Retire an athlete-specific coaching rule: sets active=false and "
            "deactivated_at, keeping the row as history (readable via "
            "get_coaching_rules include_inactive). Returns {status, rule_id}, "
            "or {error} for an unknown rule_id."
        ),
        params=DeactivateCoachingRuleParams,
        handler=_deactivate_coaching_rule,
        cli_group="athlete",
        cli_name="deactivate-coaching-rule",
    ),
    ToolDef(
        name="prefetch_weekly_review_context",
        description=(
            "Pre-fetch the shared weekly-review CONTEXT bundle in a single call: "
            "resolves the target week W (and prior week W-1) and returns both "
            "weeks' activities (with performance_trends + weather), the fitness "
            "summary (Garmin native hr_zones), multi-week load_trend/acwr, "
            "recovery (trend/status/baseline_deviation), strength sessions, the "
            "training_block backbone (W's block + long-run ladder step + weeks "
            "to the block's end + quality budget), prescriptions_prev_week (W-1 "
            "rows + adherence counts), prescriptions_current_week (W's canonical "
            "batch with its batch_id / review_id), the Garmin "
            "scheduled_workouts for W with "
            "the garmin_conflicts they raise against the block, the "
            "athlete_profile, goals with weeks_to_race, and the last "
            "past_review. Every collector is null-on-error (additive). Excludes "
            "catch_up_ingest (a write); run that separately before this."
        ),
        params=PrefetchWeeklyReviewContextParams,
        handler=_prefetch_weekly_review_context,
        cli_group="athlete",
        cli_name="prefetch-weekly-review-context",
    ),
    ToolDef(
        name="get_current_standing",
        description=(
            "Get one deterministic view of where the athlete stands against "
            "the goal on a day (computed, never stored): goals (active goals "
            "with goal_pace_sec_per_km = target_time_seconds / distance_km, "
            "None without a target, and weeks_to_race), block (title, phase, "
            "purpose, week_position, current_step, next_step of the block "
            "covering the day, or null), remaining_steps (long-run ladder "
            "steps after this week up to the A goal), proven (longest_run of "
            "the last 182 days, build_baseline_km), recent_near_goal_pace "
            "(runs >= 5 km of the last 28 days within +/-15 s/km of a goal "
            "pace) and missing (absent inputs, e.g. 'no active goal'). Read "
            "this first before judging a run or a plan against the goal."
        ),
        params=GetCurrentStandingParams,
        handler=_get_current_standing,
        cli_group="athlete",
        cli_name="current-standing",
    ),
]


ATHLETE_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in ATHLETE_TOOLS}
