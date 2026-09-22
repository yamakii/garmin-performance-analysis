"""Purpose-aware deviation policy for the scenes of one run (Issue #1314).

``analysis.run_moments`` finds *what happened* -- a walk break at km 14, a
fade over the last three kilometres. Whether that is a problem depends on
what the run was *for* (``analysis.run_purpose``): a walk break is part of the
deal on an aerobic long run and a real miss on a goal-pace rehearsal. This
module answers that second question with one table, so detection stays
purpose-blind and the verdict lives in exactly one place.

Every moment gets ``policy = {"verdict", "reason"}``:

* ``concern`` -- a deviation from what this purpose asks for. Only these (plus
  outside-and-adverse signals and off-plan axes) may carry a coach growth point.
* ``acceptable`` -- expected or explicitly allowed for this purpose.
* ``neutral`` -- descriptive; neither praise nor a problem.

Step scenes (``warmup``, ``rep`` ...) describe the session's structure and are
always ``neutral``. ``unknown`` keeps the behaviour from before purposes
existed: only a ceiling touch is a concern.

The module is pure: no I/O, no DB access.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

Verdict = Literal["acceptable", "concern", "neutral"]

#: Scene kinds that describe the session's shape rather than a deviation.
ALWAYS_NEUTRAL_KINDS: frozenset[str] = frozenset(
    {
        "warmup",
        "cooldown",
        "rest",
        "main",
        "rep",
        "work_set",
        "strides",
        "start",
        "steady",
    }
)

# The judged kinds, in the column order of the table below.
_KINDS: tuple[str, ...] = (
    "ceiling_touch",
    "fade",
    "walk_break",
    "fast_start",
    "surge",
    "strong_finish",
    "progression",
    "climb",
)

_LETTER: dict[str, Verdict] = {"C": "concern", "A": "acceptable", "N": "neutral"}

# purpose -> one letter per ``_KINDS`` column (C = concern, A = acceptable,
# N = neutral). Kept as a compact grid so it can be read against Issue #1314.
_GRID: dict[str, str] = {
    "easy": "CNACNNNN",
    "recovery": "CNACCCCN",
    "long_easy": "CNACNNNN",
    "long_goal_pace": "NCCCNANN",
    "long_fast_finish": "CCCCNAAN",
    "progression": "NCCCNAAN",
    "tempo": "NCCCNNNN",
    "intervals": "NNNNNNNN",
    "fartlek": "NNNNANNN",
    "race": "NCCCNANN",
    "unknown": "CNNNNNNN",
}

#: purpose id -> moment kind -> verdict.
POLICY: dict[str, dict[str, Verdict]] = {
    purpose: {kind: _LETTER[letter] for kind, letter in zip(_KINDS, row, strict=True)}
    for purpose, row in _GRID.items()
}

_FALLBACK_PURPOSE = "unknown"


def policy_for(
    kind: str, purpose: str, allowances: Mapping[str, Any] | None
) -> tuple[Verdict, str]:
    """Judge one scene kind against the run's purpose.

    Args:
        kind: The moment's ``kind`` (``walk_break``, ``fade`` ...).
        purpose: The resolved purpose id. An id the table does not know is
            judged as ``unknown``.
        allowances: The prescription's ``allowances`` (``{"walk": bool}``), or
            ``None``. ``walk`` overrides the table for ``walk_break``.

    Returns:
        ``(verdict, reason)`` where ``reason`` is a short English explanation.
    """
    if kind in ALWAYS_NEUTRAL_KINDS:
        return "neutral", f"{kind} is part of the session structure"

    walk = (allowances or {}).get("walk")
    if kind == "walk_break" and isinstance(walk, bool):
        if walk:
            return "acceptable", "walk breaks are allowed by the prescription"
        return "concern", "walk breaks are ruled out by the prescription"

    table = POLICY.get(purpose)
    judged_as = purpose
    if table is None:
        table = POLICY[_FALLBACK_PURPOSE]
        judged_as = _FALLBACK_PURPOSE
    verdict = table.get(kind, "neutral")
    return verdict, f"{kind} is {verdict} on a {judged_as} run"


def apply_policy(
    moments: Sequence[Mapping[str, Any]],
    purpose: str,
    allowances: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return copies of moments with policy={"verdict", "reason"} added."""
    judged: list[dict[str, Any]] = []
    for moment in moments:
        verdict, reason = policy_for(str(moment.get("kind") or ""), purpose, allowances)
        judged.append({**moment, "policy": {"verdict": verdict, "reason": reason}})
    return judged
