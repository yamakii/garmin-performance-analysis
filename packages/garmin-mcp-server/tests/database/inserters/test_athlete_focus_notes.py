"""Integration tests for partial profile saves and ``append_focus_notes``.

``save_athlete_profile`` keeps every key the payload omits, and
``append_focus_notes`` adds to ``focus_notes`` without resending the whole
text (Issue #1468).
"""

import pytest

from garmin_mcp.database.inserters.athlete import (
    append_focus_notes,
    insert_athlete_profile,
)
from garmin_mcp.database.readers.athlete import AthleteReader


def _profile_with_two_goals() -> dict:
    return {
        "user_id": "default",
        "current_focus": "回復力と筋持久力",
        "focus_notes": "スピードは到達済み",
        "goals": [
            {
                "race_name": "さいたまマラソン",
                "race_date": "2027-02-01",
                "priority": "A",
                "goal_type": "marathon",
                "status": "active",
            },
            {
                "race_name": "新潟シティマラソン",
                "race_date": "2026-10-11",
                "priority": "B",
                "goal_type": "marathon",
                "status": "active",
            },
        ],
        "retrospectives": [
            {
                "season_label": "2025-2026",
                "narrative": "ハーフ2:13後に故障",
                "key_learnings": "強い実戦直後の故障に注意",
            }
        ],
    }


@pytest.mark.integration
def test_save_profile_partial_keeps_goals_and_retros(initialized_db_path) -> None:
    """A payload with only focus_notes keeps the goals, retros and focus."""
    db_path = str(initialized_db_path)
    insert_athlete_profile(_profile_with_two_goals(), db_path=db_path)

    insert_athlete_profile({"focus_notes": "新"}, db_path=db_path)

    result = AthleteReader(db_path=db_path).get_athlete_profile()
    assert result["focus_notes"] == "新"
    assert result["current_focus"] == "回復力と筋持久力"
    assert len(result["goals"]) == 2
    assert len(result["retrospectives"]) == 1


@pytest.mark.integration
def test_save_profile_explicit_empty_goals_clears(initialized_db_path) -> None:
    """A present-but-empty goals list still clears goals; retros are kept."""
    db_path = str(initialized_db_path)
    insert_athlete_profile(_profile_with_two_goals(), db_path=db_path)

    insert_athlete_profile({"goals": []}, db_path=db_path)

    result = AthleteReader(db_path=db_path).get_athlete_profile()
    assert result["goals"] == []
    assert len(result["retrospectives"]) == 1
    assert result["focus_notes"] == "スピードは到達済み"


@pytest.mark.integration
def test_save_profile_partial_snapshot_is_merged(initialized_db_path) -> None:
    """The version written by a partial save holds the whole merged profile."""
    db_path = str(initialized_db_path)
    insert_athlete_profile(_profile_with_two_goals(), db_path=db_path)

    insert_athlete_profile({"focus_notes": "新"}, db_path=db_path)

    reader = AthleteReader(db_path=db_path)
    latest = reader.list_athlete_profile_versions(limit=1)[0]
    assert latest["n_goals"] == 2
    assert latest["n_retrospectives"] == 1
    snapshot = reader.get_athlete_profile_version(latest["version_id"])
    assert snapshot is not None
    assert snapshot["profile_data"]["current_focus"] == "回復力と筋持久力"
    assert snapshot["profile_data"]["focus_notes"] == "新"


def _seed_notes(db_path: str, focus_notes: str) -> None:
    profile = _profile_with_two_goals()
    profile["focus_notes"] = focus_notes
    insert_athlete_profile(profile, db_path=db_path)


def _notes(db_path: str) -> str | None:
    notes: str | None = AthleteReader(db_path=db_path).get_athlete_profile()[
        "focus_notes"
    ]
    return notes


@pytest.mark.integration
def test_append_focus_notes_end(initialized_db_path) -> None:
    """Without a section the text becomes a new last line; goals are untouched."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A】a")

    result = append_focus_notes("【B】b", db_path=db_path)

    assert _notes(db_path) == "【A】a\n【B】b"
    assert result["section_created"] is False
    assert result["chars_before"] == 4
    assert result["chars_after"] == 9
    profile = AthleteReader(db_path=db_path).get_athlete_profile()
    assert len(profile["goals"]) == 2
    assert profile["current_focus"] == "回復力と筋持久力"


@pytest.mark.integration
def test_append_focus_notes_into_section(initialized_db_path) -> None:
    """Text joins the end of the named section, before the next heading."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A】a。\n【B】b")

    result = append_focus_notes("追記。", section="A", db_path=db_path)

    assert _notes(db_path) == "【A】a。追記。\n【B】b"
    assert result["section"] == "A"
    assert result["section_created"] is False


@pytest.mark.integration
def test_append_focus_notes_adds_period_before_join(initialized_db_path) -> None:
    """A body that does not end with 。 gets one before the joined text."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A】a\n【B】b")

    append_focus_notes("追記。", section="A", db_path=db_path)

    assert _notes(db_path) == "【A】a。追記。\n【B】b"


@pytest.mark.integration
def test_append_focus_notes_section_with_suffix(initialized_db_path) -> None:
    """A heading with a ': …' qualifier still matches its bare name."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A: 2026-09-25 再定義】a。\n【B】b")

    append_focus_notes("追記。", section="【A】", db_path=db_path)

    assert _notes(db_path) == "【A: 2026-09-25 再定義】a。追記。\n【B】b"


@pytest.mark.integration
def test_append_focus_notes_ignores_inline_reference(initialized_db_path) -> None:
    """An inline （【A】参照） is not a heading; the real 【A】 line is used."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【B】b（【A】参照）。\n【A】a。")

    append_focus_notes("追記。", section="A", db_path=db_path)

    assert _notes(db_path) == "【B】b（【A】参照）。\n【A】a。追記。"


@pytest.mark.integration
def test_append_focus_notes_creates_missing_section(initialized_db_path) -> None:
    """An unknown section is created as a new last line."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A】a。\n【B】b。")

    result = append_focus_notes("c", section="C", db_path=db_path)

    assert _notes(db_path) == "【A】a。\n【B】b。\n【C】c"
    assert result["section_created"] is True


@pytest.mark.integration
def test_append_focus_notes_ambiguous_section_raises(initialized_db_path) -> None:
    """Two line-start 【A】 headings refuse the append and leave the DB as is."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A】a。\n【A】a2。")
    versions_before = len(
        AthleteReader(db_path=db_path).list_athlete_profile_versions()
    )

    with pytest.raises(ValueError, match="ambiguous"):
        append_focus_notes("追記。", section="A", db_path=db_path)

    assert _notes(db_path) == "【A】a。\n【A】a2。"
    reader = AthleteReader(db_path=db_path)
    assert len(reader.list_athlete_profile_versions()) == versions_before


@pytest.mark.integration
def test_append_focus_notes_appends_version(initialized_db_path) -> None:
    """Each append adds one version whose snapshot carries the goals too."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A】a。")
    reader = AthleteReader(db_path=db_path)
    before = len(reader.list_athlete_profile_versions(limit=50))

    result = append_focus_notes("追記。", section="A", db_path=db_path)

    versions = reader.list_athlete_profile_versions(limit=50)
    assert len(versions) == before + 1
    assert versions[0]["version_id"] == result["version_id"]
    assert versions[0]["n_goals"] == 2
    snapshot = reader.get_athlete_profile_version(result["version_id"])
    assert snapshot is not None
    assert snapshot["profile_data"]["focus_notes"] == "【A】a。追記。"


@pytest.mark.integration
def test_append_focus_notes_rejects_emoji(initialized_db_path) -> None:
    """Emoji in the appended text are rejected before any write."""
    db_path = str(initialized_db_path)
    _seed_notes(db_path, "【A】a。")

    with pytest.raises(ValueError):
        append_focus_notes("いい感じ\U0001f3c3", section="A", db_path=db_path)

    assert _notes(db_path) == "【A】a。"


@pytest.mark.integration
def test_append_focus_notes_without_profile_creates_row(initialized_db_path) -> None:
    """With no profile yet, the append creates the row holding only the text."""
    db_path = str(initialized_db_path)

    append_focus_notes("【A】a", db_path=db_path)

    profile = AthleteReader(db_path=db_path).get_athlete_profile()
    assert profile["focus_notes"] == "【A】a"
    assert profile["goals"] == []
