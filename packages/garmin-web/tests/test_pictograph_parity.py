"""The frontend and the server agree on what counts as emoji (Issue #1428).

The write gate and the display strip use
``garmin_mcp.validation.pictographs.PICTOGRAPH_RE``; the frontend's DOM and
source guards use ``frontend/src/utils/emoji.ts``. Two spellings of one rule
drift, so this pins them to the same code points.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from garmin_mcp.validation.pictographs import PICTOGRAPH_RE

import garmin_web

_EMOJI_TS = (
    Path(garmin_web.__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "utils"
    / "emoji.ts"
)
_TS_RANGE = re.compile(r"\\u\{([0-9A-Fa-f]+)\}(?:-\\u\{([0-9A-Fa-f]+)\})?")


def _ts_code_points() -> set[int]:
    text = _EMOJI_TS.read_text(encoding="utf-8")
    body = text[text.index("PICTOGRAPH_RE") :]
    points: set[int] = set()
    for start, end in _TS_RANGE.findall(body):
        first = int(start, 16)
        points.update(range(first, int(end or start, 16) + 1))
    return points


@pytest.mark.unit
def test_frontend_and_server_pictograph_sets_match() -> None:
    ts_points = _ts_code_points()
    assert ts_points, f"no ranges parsed from {_EMOJI_TS}"

    probe = set(range(0x2000, 0x2C00)) | {0xFE0F, 0x1F000, 0x1F7E1, 0x1FAFF}
    probe |= ts_points
    py_points = {cp for cp in probe if PICTOGRAPH_RE.match(chr(cp))}

    assert ts_points == py_points
