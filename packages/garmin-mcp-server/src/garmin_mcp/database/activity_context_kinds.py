"""Which ``activity_context`` kinds have one answer per run (issue #1596).

A run is or is not a commute and carried one load, so a newer row of these
kinds is a correction and replaces the older one on read. Every other kind
(``walk_reason``, ``apparel``, ``sensor_mount``, ``other``) can hold several
distinct facts about one run, so all of its rows are returned; an explicit
``replaces`` list is the only way to retire one.
"""

SINGLE_VALUED_KINDS: frozenset[str] = frozenset({"commute", "load", "strides_carried"})
