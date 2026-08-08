"""Shared eligibility predicate for form-baseline splits.

Both sides of the form-baseline system must agree on what counts as a *running*
split, otherwise the models are fitted on one population and applied to another.

Two kinds of lap pollute a raw ``splits`` scan:

* **Walk breaks.** Deliberate mid-run walking (heat management, recovery) is
  recorded as an ordinary lap with ``role_phase='run'``, so phase-based
  selection cannot see it. Its cadence is ~65-115 spm against ~175 spm running.
* **GPS fragments.** Manual lap presses leave 5-11 m laps whose pace is a
  measurement artifact (as fast as 4:04/km) while their cadence is that of a
  walk (#873).

``trainer`` has excluded both since #873, but ``data_fetcher`` (the evaluation
side) did not, so a run/walk activity was averaged over walk laps and scored
against a model trained without them: activity 23895612412 recorded 161.6 spm
where the running portion held 174.2 spm, and its activity pace was pulled from
497.7 to 568.5 s/km -- moving the point on the pace-dependent curve at which
every expected value is read (#878).

Keeping the predicate here means the two sides cannot drift apart again.
"""

# Minimum split distance (km). 0.4 km keeps every real lap -- including the
# deliberate sub-km ones this athlete presses for walk segments -- while
# dropping the 5-11 m GPS fragments (#873).
MIN_SPLIT_KM = 0.4

# Pace ceiling (s/km) separating running from walking. 600 s/km = 10:00/km sits
# well below any recorded running lap and above every walk lap: over the whole
# history only 1 of 2192 splits passing this filter has cadence < 140 spm.
MAX_RUNNING_PACE_S_PER_KM = 600.0


def running_split_sql(alias: str = "") -> str:
    """Return the SQL predicate selecting running (non-walk, non-fragment) splits.

    Args:
        alias: Optional table alias to prefix each column with, e.g. ``"s"``
            yields ``s.pace_seconds_per_km``. Empty string leaves columns bare.

    Returns:
        A parameterised SQL boolean expression. Bind the values returned by
        :func:`running_split_params` in the same order.
    """
    prefix = f"{alias}." if alias else ""
    return (
        f"{prefix}pace_seconds_per_km > 0 "
        f"AND {prefix}pace_seconds_per_km < ? "
        f"AND {prefix}distance >= ?"
    )


def running_split_params() -> list[float]:
    """Return bind params matching the placeholders in :func:`running_split_sql`."""
    return [MAX_RUNNING_PACE_S_PER_KM, MIN_SPLIT_KM]
