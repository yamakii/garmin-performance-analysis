"""Emoji guard for prose that reaches the web app (Issue #1428).

The design system states verdicts in words or the ``✓`` / ``!`` glyphs, never
emoji (#1186 / #1187 / #1188): a screen reader announces 🔴 as "large red
circle", and a page of coloured marks is the noise the brief removes. Fixing
each screen on its own let the next surface and the agents' prose regress, so
the rule lives here once and is enforced at every write that stores prose.

What counts as emoji is what renders as one: the supplementary pictograph
planes, the emoji variation selector U+FE0F, and the BMP characters whose
default presentation is emoji. Text symbols the design system uses on purpose
-- ``✓``, ``!``, the legacy ``★☆`` stars -- and a bare text ``⚠`` stay allowed.

The verdict ``rating`` key (✅ / 🟡 / 🔴) is a data identifier the web maps to
words, so it is exempt by default.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# BMP code points with Emoji_Presentation=Yes (Unicode emoji-data.txt).
_BMP_EMOJI_PRESENTATION = (
    "⌚-⌛⏩-⏬⏰⏳◽-◾☔-☕"
    "♈-♓♿⚓⚡⚪-⚫⚽-⚾⛄-⛅"
    "⛎⛔⛪⛲-⛳⛵⛺⛽✅✊-✋"
    "✨❌❎❓-❕❗➕-➗➰➿"
    "⬛-⬜⭐⭕"
)

PICTOGRAPH_RE: re.Pattern[str] = re.compile(
    f"[\U0001f000-\U0001faff️{_BMP_EMOJI_PRESENTATION}]"
)

DEFAULT_EXEMPT_KEYS: frozenset[str] = frozenset({"rating"})


def _child_path(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def find_pictographs(
    obj: Any,
    *,
    exempt_keys: Iterable[str] = DEFAULT_EXEMPT_KEYS,
    path: str = "",
) -> list[str]:
    """JSON paths (``overall``, ``recommendations[2]``) whose string holds emoji.

    Walks dicts, lists and strings; any other value is ignored. Keys named in
    ``exempt_keys`` are skipped at every depth.
    """
    exempt = frozenset(exempt_keys)
    if isinstance(obj, str):
        return [path or "<value>"] if PICTOGRAPH_RE.search(obj) else []
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in exempt:
                continue
            hits.extend(
                find_pictographs(
                    value, exempt_keys=exempt, path=_child_path(path, str(key))
                )
            )
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            hits.extend(
                find_pictographs(value, exempt_keys=exempt, path=f"{path}[{index}]")
            )
    return hits


def reject_pictographs(
    obj: Any,
    *,
    where: str,
    exempt_keys: Iterable[str] = DEFAULT_EXEMPT_KEYS,
) -> None:
    """Raise ``ValueError`` naming every path of ``obj`` that holds emoji."""
    hits = find_pictographs(obj, exempt_keys=exempt_keys)
    if hits:
        raise ValueError(
            f"{where}: emoji in prose at {', '.join(hits)}; write the word "
            "instead (e.g. 良好 / 注意 / 要改善) -- the web app shows no emoji"
        )


# What a strip removes: a whole ``<base>U+FE0F[U+20E3]`` sequence (so ``⚠️``
# does not leave a bare ``⚠`` behind), stray joiners, and every pictograph.
_STRIP_RE = re.compile(f"\\S\ufe0f\u20e3?|[\u200d\u20e3]|{PICTOGRAPH_RE.pattern}")
_SPACES = re.compile(r"[ \t\u3000]{2,}")


def strip_pictographs(text: str) -> str:
    """``text`` without emoji, for prose saved before the write gate existed."""
    if not PICTOGRAPH_RE.search(text):
        return text
    stripped = _STRIP_RE.sub("", text)
    return _SPACES.sub(" ", stripped).strip()


def strip_pictographs_deep(
    obj: Any, *, exempt_keys: Iterable[str] = DEFAULT_EXEMPT_KEYS
) -> Any:
    """A copy of ``obj`` with :func:`strip_pictographs` applied to every string."""
    exempt = frozenset(exempt_keys)
    if isinstance(obj, str):
        return strip_pictographs(obj)
    if isinstance(obj, dict):
        return {
            key: (
                value
                if key in exempt
                else strip_pictographs_deep(value, exempt_keys=exempt)
            )
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [strip_pictographs_deep(value, exempt_keys=exempt) for value in obj]
    return obj
