"""Workout catalog: a template for every prescribable session shape (#1403).

A prescription's step structure (:mod:`garmin_mcp.analysis.workout_structure`)
is free-form, which makes it easy to author a title that says one thing and
steps that do another. The catalog closes that gap: each :class:`Template`
builds both the structure *and* the Japanese title from the same parameters,
so the two can never disagree.

The set of templates comes from the athlete's history (583 runs, 91 of them
structured) and from general training menus, and covers every session shape
``training_blocks`` plans through 2027-02.

Units:

- Heart rate is **bpm only** (the skill converts zones to bpm when authoring;
  zone boundaries drift, see :mod:`~garmin_mcp.analysis.workout_structure`).
- Pace is **s/km** (``pace_low`` = the faster bound, ``pace_high`` = the
  slower bound) and is judged only; it never reaches the watch.
- Volume is ``minutes`` or ``km`` (exactly one where both are accepted).

Parameters are strict: an unknown key, a missing required key or a value of
the wrong type raises ``ValueError``, as does a structure that fails
:func:`~garmin_mcp.analysis.workout_structure.validate_structure`.

The module is pure: no I/O, no DB access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from garmin_mcp.analysis.prescription_shape import (
    COOLDOWN_MINUTES,
    FINAL_EASY_MINUTES,
    STRIDES_DEFAULT_RECOVERY_SECONDS,
    STRIDES_DEFAULT_RUN_SECONDS,
    WARMUP_MINUTES,
)
from garmin_mcp.analysis.workout_structure import Structure, validate_structure

_MISSING: Any = object()

#: Work-step length bounds (seconds) of ``short_reps``.
SHORT_REPS_MIN_SECONDS: int = 15
SHORT_REPS_MAX_SECONDS: int = 40


@dataclass(frozen=True)
class Template:
    """One prescribable session shape.

    Attributes:
        id: Stable template identifier.
        session_types: Prescription ``session_type`` values the template may
            be used on.
        default_purpose: Purpose id (``run_purpose.PURPOSES``) a row built from
            the template gets unless it declares its own.
        build: Builds the step structure from the parameters.
        title: Builds the Japanese title from the same parameters.
        example: Documented example parameters (always expand cleanly).
    """

    id: str
    session_types: frozenset[str]
    default_purpose: str
    build: Callable[..., Structure]
    title: Callable[..., str]
    example: Mapping[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Parameter access
# ----------------------------------------------------------------------------


class _Params:
    """Read-tracking view of a parameter mapping.

    Every key a builder or title function asks for (present or not) is
    recorded, so :func:`expand` can reject keys no one read.
    """

    def __init__(self, raw: Mapping[str, Any], where: str) -> None:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{where}: params must be an object, got {raw!r}")
        self._raw = raw
        self.where = where
        self.read: set[str] = set()

    def has(self, key: str) -> bool:
        self.read.add(key)
        return self._raw.get(key) is not None

    def _get(self, key: str, default: Any) -> Any:
        self.read.add(key)
        value = self._raw.get(key)
        if value is None:
            if default is _MISSING:
                raise ValueError(f"{self.where}: missing required param {key!r}")
            return default
        return value

    def int_(self, key: str, default: Any = _MISSING, *, minimum: int = 1) -> Any:
        value = self._get(key, default)
        if value is None:
            return None
        if not (isinstance(value, int) and not isinstance(value, bool)):
            raise ValueError(f"{self.where}: {key} must be an integer, got {value!r}")
        if value < minimum:
            raise ValueError(f"{self.where}: {key} must be >= {minimum}, got {value}")
        return value

    def num(
        self, key: str, default: Any = _MISSING, *, allow_zero: bool = False
    ) -> Any:
        value = self._get(key, default)
        if value is None:
            return None
        if not (isinstance(value, int | float) and not isinstance(value, bool)):
            raise ValueError(f"{self.where}: {key} must be a number, got {value!r}")
        if value < 0 or (value == 0 and not allow_zero):
            raise ValueError(f"{self.where}: {key} must be positive, got {value}")
        return value

    def bool_(self, key: str, default: bool) -> bool:
        value = self._get(key, default)
        if not isinstance(value, bool):
            raise ValueError(f"{self.where}: {key} must be a boolean, got {value!r}")
        return value

    def str_(self, key: str, default: Any = _MISSING) -> Any:
        value = self._get(key, default)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{self.where}: {key} must be a string, got {value!r}")
        return value

    def mapping(self, key: str) -> Mapping[str, Any] | None:
        value = self._get(key, None)
        if value is not None and not isinstance(value, Mapping):
            raise ValueError(f"{self.where}: {key} must be an object, got {value!r}")
        return cast("Mapping[str, Any] | None", value)

    def list_(self, key: str) -> list[Any]:
        value = self._get(key, _MISSING)
        if not isinstance(value, list) or not value:
            raise ValueError(f"{self.where}: {key} must be a non-empty list")
        return value

    def sub(self, raw: Any, where: str) -> _Params:
        return _Params(raw, f"{self.where} {where}")

    def unknown(self) -> set[str]:
        return set(self._raw) - self.read


# ----------------------------------------------------------------------------
# Formatting and step helpers
# ----------------------------------------------------------------------------


def _fmt_num(value: float) -> str:
    """``8.0`` -> ``"8"``, ``21.1`` -> ``"21.1"``."""
    return f"{value:g}"


def _fmt_seconds(seconds: int) -> str:
    """``180`` -> ``"3分"``, ``90`` -> ``"90秒"``."""
    if seconds % 60 == 0:
        return f"{seconds // 60}分"
    return f"{seconds}秒"


def _fmt_pace(seconds_per_km: int) -> str:
    """``365`` -> ``"6:05"``."""
    return f"{seconds_per_km // 60}:{seconds_per_km % 60:02d}"


def _fmt_band(low: Any, high: Any, fmt: Callable[[Any], str]) -> str | None:
    if low is not None and high is not None:
        return f"{fmt(low)}-{fmt(high)}"
    if high is not None:
        return f"〜{fmt(high)}"
    if low is not None:
        return f"{fmt(low)}〜"
    return None


def _hr_band(low: Any, high: Any) -> str | None:
    return _fmt_band(low, high, str)


def _pace_band(low: Any, high: Any) -> str | None:
    return _fmt_band(low, high, _fmt_pace)


def _paren(*parts: str | None) -> str:
    kept = [p for p in parts if p]
    return f"（{'・'.join(kept)}）" if kept else ""


def _step(step_type: str, **fields: Any) -> dict[str, Any]:
    step: dict[str, Any] = {"step_type": step_type}
    step.update({k: v for k, v in fields.items() if v is not None})
    return step


def _km_to_m(km: float) -> int:
    return round(float(km) * 1000)


def _volume(p: _Params) -> dict[str, Any]:
    """Exactly one of ``minutes`` / ``km`` as a step duration."""
    has_minutes, has_km = p.has("minutes"), p.has("km")
    if has_minutes == has_km:
        raise ValueError(f"{p.where}: give exactly one of 'minutes' or 'km'")
    if has_minutes:
        return {"duration_minutes": p.num("minutes")}
    return {"distance_m": _km_to_m(p.num("km"))}


def _volume_label(p: _Params) -> str:
    if p.has("minutes"):
        return f"{_fmt_num(p.num('minutes'))}分"
    return f"{_fmt_num(p.num('km'))}km"


def _bookend(p: _Params, body: list[dict[str, Any]]) -> Structure:
    """Wrap ``body`` in a warmup / cooldown (a ``0`` minute bookend is omitted)."""
    warmup = p.num("warmup_minutes", WARMUP_MINUTES, allow_zero=True)
    cooldown = p.num("cooldown_minutes", COOLDOWN_MINUTES, allow_zero=True)
    steps: list[dict[str, Any]] = []
    if warmup:
        steps.append(_step("warmup", duration_minutes=warmup))
    steps.extend(body)
    if cooldown:
        steps.append(_step("cooldown", duration_minutes=cooldown))
    return cast(Structure, steps)


def _repeat(reps: int, *steps: dict[str, Any]) -> dict[str, Any]:
    return {"repeat_count": reps, "steps": list(steps)}


# ----------------------------------------------------------------------------
# Builders and titles
# ----------------------------------------------------------------------------


def _single_run(p: _Params) -> Structure:
    return cast(
        Structure,
        [_step("run", **_volume(p), hr_high=p.int_("hr_high"))],
    )


def _recovery_title(p: _Params) -> str:
    return f"リカバリー {_volume_label(p)}{_paren(_hr_band(None, p.int_('hr_high')))}"


def _easy_title(p: _Params) -> str:
    return f"イージー {_volume_label(p)}{_paren(_hr_band(None, p.int_('hr_high')))}"


def _long_easy_title(p: _Params) -> str:
    return f"ロング {_volume_label(p)}{_paren(_hr_band(None, p.int_('hr_high')))}"


def _easy_with_block(
    p: _Params, reps: int, run_seconds: int, recovery_seconds: int
) -> Structure:
    """Opening easy, ``reps`` x (run, recovery), final easy; totals ``minutes``."""
    minutes = p.num("minutes")
    hr_high = p.int_("hr_high")
    final_seconds = FINAL_EASY_MINUTES * 60
    block = reps * (run_seconds + recovery_seconds)
    opening = round(float(minutes) * 60) - block - final_seconds
    if opening <= 0:
        raise ValueError(
            f"{p.where}: the {block}s block and the final {FINAL_EASY_MINUTES}min "
            f"easy leave no opening easy running inside {minutes} minutes"
        )
    return cast(
        Structure,
        [
            _step("run", duration_seconds=opening, hr_high=hr_high),
            _repeat(
                reps,
                _step("run", duration_seconds=run_seconds),
                _step("recovery", duration_seconds=recovery_seconds),
            ),
            _step("run", duration_minutes=FINAL_EASY_MINUTES, hr_high=hr_high),
        ],
    )


def _easy_strides_build(p: _Params) -> Structure:
    return _easy_with_block(
        p,
        p.int_("reps"),
        p.int_("run_seconds", STRIDES_DEFAULT_RUN_SECONDS),
        p.int_("recovery_seconds", STRIDES_DEFAULT_RECOVERY_SECONDS),
    )


def _easy_strides_title(p: _Params) -> str:
    return (
        f"イージー {_fmt_num(p.num('minutes'))}分＋流し {p.int_('reps')}本"
        f"{_paren(_hr_band(None, p.int_('hr_high')))}"
    )


def _banded_body(p: _Params) -> Structure:
    body = _step(
        "run", **_volume(p), hr_low=p.int_("hr_low"), hr_high=p.int_("hr_high")
    )
    return _bookend(p, [body])


def _aerobic_steady_title(p: _Params) -> str:
    band = _hr_band(p.int_("hr_low"), p.int_("hr_high"))
    return f"ステディ {_volume_label(p)}{_paren(band)}"


def _tempo_continuous_build(p: _Params) -> Structure:
    body = _step(
        "run",
        duration_minutes=p.num("minutes"),
        hr_low=p.int_("hr_low"),
        hr_high=p.int_("hr_high"),
    )
    return _bookend(p, [body])


def _tempo_continuous_title(p: _Params) -> str:
    band = _hr_band(p.int_("hr_low"), p.int_("hr_high"))
    return f"テンポ {_fmt_num(p.num('minutes'))}分{_paren(band)}"


def _cruise_build(p: _Params) -> Structure:
    work = _step(
        "run",
        duration_minutes=p.num("work_minutes"),
        hr_low=p.int_("hr_low"),
        hr_high=p.int_("hr_high"),
    )
    rec = _step("recovery", duration_minutes=p.num("recovery_minutes"))
    return _bookend(p, [_repeat(p.int_("reps"), work, rec)])


def _cruise_title(p: _Params) -> str:
    band = _hr_band(p.int_("hr_low"), p.int_("hr_high"))
    return (
        f"クルーズ {p.int_('reps')}×{_fmt_num(p.num('work_minutes'))}分{_paren(band)}"
        f"／{_fmt_num(p.num('recovery_minutes'))}分ジョグ"
    )


def _vo2_build(p: _Params) -> Structure:
    work = _step(
        "run",
        duration_seconds=p.int_("work_seconds"),
        pace_low_s_per_km=p.int_("pace_low", None),
        pace_high_s_per_km=p.int_("pace_high", None),
    )
    rec = _step("recovery", duration_seconds=p.int_("recovery_seconds"))
    return _bookend(p, [_repeat(p.int_("reps"), work, rec)])


def _vo2_title(p: _Params) -> str:
    band = _pace_band(p.int_("pace_low", None), p.int_("pace_high", None))
    return (
        f"インターバル {p.int_('reps')}×{_fmt_seconds(p.int_('work_seconds'))}"
        f"{_paren(band)}／{_fmt_seconds(p.int_('recovery_seconds'))}ジョグ"
    )


def _short_reps_recovery_step(p: _Params) -> str:
    kind = p.str_("recovery_step", "recovery")
    if kind not in ("recovery", "rest"):
        raise ValueError(
            f"{p.where}: recovery_step must be 'recovery' or 'rest', got {kind!r}"
        )
    return str(kind)


def _short_reps_work_seconds(p: _Params) -> int:
    work = int(p.int_("work_seconds"))
    if not SHORT_REPS_MIN_SECONDS <= work <= SHORT_REPS_MAX_SECONDS:
        raise ValueError(
            f"{p.where}: work_seconds must be {SHORT_REPS_MIN_SECONDS}.."
            f"{SHORT_REPS_MAX_SECONDS}, got {work}"
        )
    return work


def _short_reps_build(p: _Params) -> Structure:
    work = _step("run", duration_seconds=_short_reps_work_seconds(p))
    rec = _step(
        _short_reps_recovery_step(p), duration_seconds=p.int_("recovery_seconds")
    )
    return _bookend(p, [_repeat(p.int_("reps"), work, rec)])


def _short_reps_title(p: _Params) -> str:
    rest = "休息" if _short_reps_recovery_step(p) == "rest" else "ジョグ"
    return (
        f"ショートレップ {p.int_('reps')}×{_fmt_seconds(_short_reps_work_seconds(p))}"
        f"／{_fmt_seconds(p.int_('recovery_seconds'))}{rest}"
    )


def _hill_sprints_build(p: _Params) -> Structure:
    return _easy_with_block(
        p, p.int_("reps"), p.int_("work_seconds"), p.int_("recovery_seconds")
    )


def _hill_sprints_title(p: _Params) -> str:
    return (
        f"イージー {_fmt_num(p.num('minutes'))}分＋坂ダッシュ "
        f"{p.int_('reps')}×{_fmt_seconds(p.int_('work_seconds'))}"
        f"{_paren(_hr_band(None, p.int_('hr_high')))}"
    )


def _progression_stages(p: _Params) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    raw_stages = p.list_("stages")
    if len(raw_stages) < 2:
        raise ValueError(f"{p.where}: a progression needs at least 2 stages")
    prev: tuple[int, int] | None = None
    for i, raw in enumerate(raw_stages):
        sp = p.sub(raw, f"stage {i}")
        low, high = int(sp.int_("hr_low")), int(sp.int_("hr_high"))
        if prev is not None and (
            low < prev[0] or high < prev[1] or (low, high) == prev
        ):
            raise ValueError(
                f"{p.where}: stage {i} band {low}-{high} does not ascend from "
                f"{prev[0]}-{prev[1]}"
            )
        prev = (low, high)
        stage = _step(
            "run", **_volume(sp), hr_low=low, hr_high=high, label=sp.str_("label", None)
        )
        unknown = sp.unknown()
        if unknown:
            raise ValueError(f"{sp.where}: unknown params {sorted(unknown)}")
        stages.append(stage)
    return stages


def _progression_build(p: _Params) -> Structure:
    return _bookend(p, _progression_stages(p))


def _progression_title(p: _Params) -> str:
    stages = _progression_stages(p)
    bands = "→".join(f"{s['hr_low']}-{s['hr_high']}" for s in stages)
    if all("duration_minutes" in s for s in stages):
        volume = f"{_fmt_num(sum(s['duration_minutes'] for s in stages))}分"
    elif all("distance_m" in s for s in stages):
        volume = f"{_fmt_num(sum(s['distance_m'] for s in stages) / 1000)}km"
    else:
        volume = f"{len(stages)}段"
    return f"ビルドアップ {volume}（{bands}）"


def _long_with_mp_build(p: _Params) -> Structure:
    hr_easy = p.int_("hr_high_easy")
    steps: list[dict[str, Any]] = []
    before = p.num("easy_km_before", allow_zero=True)
    if before:
        steps.append(_step("run", distance_m=_km_to_m(before), hr_high=hr_easy))
    steps.append(
        _step(
            "run",
            distance_m=_km_to_m(p.num("mp_km")),
            hr_high=p.int_("mp_hr_high"),
            pace_low_s_per_km=p.int_("mp_pace_low"),
            pace_high_s_per_km=p.int_("mp_pace_high"),
            label="MP",
        )
    )
    after = p.num("easy_km_after", 0, allow_zero=True)
    if after:
        steps.append(_step("run", distance_m=_km_to_m(after), hr_high=hr_easy))
    return cast(Structure, steps)


def _long_with_mp_title(p: _Params) -> str:
    total = (
        p.num("easy_km_before", allow_zero=True)
        + p.num("mp_km")
        + p.num("easy_km_after", 0, allow_zero=True)
    )
    band = _pace_band(p.int_("mp_pace_low"), p.int_("mp_pace_high"))
    return f"ロング {_fmt_num(total)}km（うちMP {_fmt_num(p.num('mp_km'))}km {band}）"


def _finish_band(p: _Params) -> dict[str, Any]:
    band = {
        "hr_low": p.int_("finish_hr_low", None),
        "hr_high": p.int_("finish_hr_high", None),
        "pace_low_s_per_km": p.int_("finish_pace_low", None),
        "pace_high_s_per_km": p.int_("finish_pace_high", None),
    }
    if all(v is None for v in band.values()):
        raise ValueError(f"{p.where}: the finish needs an HR and/or pace band")
    return band


def _finish_band_label(p: _Params) -> str:
    band = _finish_band(p)
    return "・".join(
        part
        for part in (
            _pace_band(band["pace_low_s_per_km"], band["pace_high_s_per_km"]),
            _hr_band(band["hr_low"], band["hr_high"]),
        )
        if part
    )


def _long_fast_finish_build(p: _Params) -> Structure:
    optional = p.bool_("optional_finish", False)
    finish = _step(
        "run",
        distance_m=_km_to_m(p.num("finish_km")),
        **_finish_band(p),
        label="ラスト上げ",
    )
    if optional:
        finish["optional"] = True
    return cast(
        Structure,
        [
            _step(
                "run",
                distance_m=_km_to_m(p.num("easy_km")),
                hr_high=p.int_("hr_high_easy"),
            ),
            finish,
        ],
    )


def _long_fast_finish_title(p: _Params) -> str:
    easy, finish = p.num("easy_km"), p.num("finish_km")
    band = _finish_band_label(p)
    if p.bool_("optional_finish", False):
        return f"ロング {_fmt_num(easy)}km＋任意ラスト{_fmt_num(finish)}km（{band}）"
    return f"ロング {_fmt_num(easy + finish)}km（ラスト{_fmt_num(finish)}km {band}）"


def _fartlek_build(p: _Params) -> Structure:
    on = _step("run", duration_seconds=p.int_("on_seconds"))
    float_ = _step(
        "recovery",
        duration_seconds=p.int_("float_seconds"),
        pace_high_s_per_km=p.int_("float_pace_high"),
    )
    return _bookend(p, [_repeat(p.int_("reps"), on, float_)])


def _fartlek_title(p: _Params) -> str:
    return (
        f"ファルトレク {p.int_('reps')}×{_fmt_seconds(p.int_('on_seconds'))}"
        f"／{_fmt_seconds(p.int_('float_seconds'))}フロート"
        f"（〜{_fmt_pace(p.int_('float_pace_high'))}）"
    )


def _race_finish(p: _Params) -> tuple[float, int, int] | None:
    raw = p.mapping("optional_finish")
    if raw is None:
        return None
    fp = p.sub(raw, "optional_finish")
    finish = (float(fp.num("km")), fp.int_("pace_low"), fp.int_("pace_high"))
    unknown = fp.unknown()
    if unknown:
        raise ValueError(f"{fp.where}: unknown params {sorted(unknown)}")
    return finish


def _race_build(p: _Params) -> Structure:
    distance = float(p.num("distance_km"))
    finish = _race_finish(p)
    main_km = distance - finish[0] if finish else distance
    if main_km <= 0:
        raise ValueError(
            f"{p.where}: the optional finish must be shorter than the race"
        )
    main = _step(
        "run",
        distance_m=_km_to_m(main_km),
        hr_high=p.int_("hr_high", None),
        pace_low_s_per_km=p.int_("pace_low", None),
        pace_high_s_per_km=p.int_("pace_high", None),
    )
    if len(main) == 2:
        raise ValueError(
            f"{p.where}: a race needs a cap (hr_high and/or pace_low / pace_high)"
        )
    steps: list[dict[str, Any]] = [main]
    if finish:
        steps.append(
            _step(
                "run",
                distance_m=_km_to_m(finish[0]),
                pace_low_s_per_km=finish[1],
                pace_high_s_per_km=finish[2],
                label="ラスト上げ",
                optional=True,
            )
        )
    return cast(Structure, steps)


def _race_title(p: _Params) -> str:
    cap = _paren(
        _pace_band(p.int_("pace_low", None), p.int_("pace_high", None)),
        _hr_band(None, p.int_("hr_high", None)),
    )
    title = f"レース {_fmt_num(p.num('distance_km'))}km{cap}"
    finish = _race_finish(p)
    if finish:
        title += (
            f"＋任意ラスト{_fmt_num(finish[0])}km"
            f"（{_pace_band(finish[1], finish[2])}）"
        )
    return title


def _time_trial_build(p: _Params) -> Structure:
    return _bookend(p, [_step("run", **_volume(p))])


def _time_trial_title(p: _Params) -> str:
    return f"タイムトライアル {_volume_label(p)}"


# ----------------------------------------------------------------------------
# Catalog
# ----------------------------------------------------------------------------


def _template(
    id_: str,
    session_types: tuple[str, ...],
    default_purpose: str,
    build: Callable[[_Params], Structure],
    title: Callable[[_Params], str],
    example: Mapping[str, Any],
) -> Template:
    return Template(
        id=id_,
        session_types=frozenset(session_types),
        default_purpose=default_purpose,
        build=build,
        title=title,
        example=example,
    )


#: Every template, keyed by id.
TEMPLATES: dict[str, Template] = {
    t.id: t
    for t in (
        _template(
            "recovery",
            ("recovery",),
            "recovery",
            _single_run,
            _recovery_title,
            {"minutes": 30, "hr_high": 135},
        ),
        _template(
            "easy",
            ("easy",),
            "easy",
            _single_run,
            _easy_title,
            {"minutes": 45, "hr_high": 150},
        ),
        _template(
            "easy_strides",
            ("easy",),
            "easy",
            _easy_strides_build,
            _easy_strides_title,
            {"minutes": 35, "hr_high": 150, "reps": 4},
        ),
        _template(
            "long_easy",
            ("long",),
            "long_easy",
            _single_run,
            _long_easy_title,
            {"km": 25, "hr_high": 150},
        ),
        _template(
            "aerobic_steady",
            ("tempo",),
            "tempo",
            _banded_body,
            _aerobic_steady_title,
            {"km": 10, "hr_low": 145, "hr_high": 155},
        ),
        _template(
            "tempo_continuous",
            ("tempo", "threshold"),
            "tempo",
            _tempo_continuous_build,
            _tempo_continuous_title,
            {"minutes": 20, "hr_low": 155, "hr_high": 165},
        ),
        _template(
            "cruise_intervals",
            ("threshold",),
            "intervals",
            _cruise_build,
            _cruise_title,
            {
                "reps": 4,
                "work_minutes": 5,
                "recovery_minutes": 3,
                "hr_low": 162,
                "hr_high": 169,
            },
        ),
        _template(
            "vo2_intervals",
            ("threshold",),
            "intervals",
            _vo2_build,
            _vo2_title,
            {
                "reps": 5,
                "work_seconds": 180,
                "recovery_seconds": 120,
                "pace_low": 270,
                "pace_high": 280,
            },
        ),
        _template(
            "short_reps",
            ("threshold",),
            "intervals",
            _short_reps_build,
            _short_reps_title,
            {
                "reps": 10,
                "work_seconds": 30,
                "recovery_seconds": 60,
                "recovery_step": "rest",
            },
        ),
        _template(
            "hill_sprints",
            ("easy",),
            "easy",
            _hill_sprints_build,
            _hill_sprints_title,
            {
                "minutes": 40,
                "hr_high": 150,
                "reps": 8,
                "work_seconds": 10,
                "recovery_seconds": 90,
            },
        ),
        _template(
            "progression",
            ("tempo", "easy", "long"),
            "progression",
            _progression_build,
            _progression_title,
            {
                "stages": [
                    {"minutes": 15, "hr_low": 136, "hr_high": 150, "label": "Z2"},
                    {"minutes": 10, "hr_low": 151, "hr_high": 161, "label": "Z3"},
                    {"minutes": 5, "hr_low": 162, "hr_high": 169, "label": "Z4"},
                ]
            },
        ),
        _template(
            "long_with_mp",
            ("long",),
            "long_goal_pace",
            _long_with_mp_build,
            _long_with_mp_title,
            {
                "easy_km_before": 10,
                "mp_km": 8,
                "easy_km_after": 2,
                "hr_high_easy": 150,
                "mp_pace_low": 365,
                "mp_pace_high": 370,
                "mp_hr_high": 162,
            },
        ),
        _template(
            "long_fast_finish",
            ("long",),
            "long_fast_finish",
            _long_fast_finish_build,
            _long_fast_finish_title,
            {
                "easy_km": 18,
                "finish_km": 4,
                "hr_high_easy": 150,
                "finish_pace_low": 350,
                "finish_pace_high": 360,
                "finish_hr_high": 165,
                "optional_finish": True,
            },
        ),
        _template(
            "fartlek",
            ("tempo",),
            "fartlek",
            _fartlek_build,
            _fartlek_title,
            {"reps": 10, "on_seconds": 60, "float_seconds": 60, "float_pace_high": 400},
        ),
        _template(
            "race",
            ("long", "tempo"),
            "race",
            _race_build,
            _race_title,
            {
                "distance_km": 21.1,
                "hr_high": 165,
                "optional_finish": {"km": 4, "pace_low": 365, "pace_high": 370},
            },
        ),
        _template(
            "time_trial",
            ("threshold",),
            "race",
            _time_trial_build,
            _time_trial_title,
            {"km": 5},
        ),
    )
}


def expand(template_id: str, params: Mapping[str, Any]) -> tuple[Structure, str]:
    """Build the structure and title of one template.

    Args:
        template_id: A key of :data:`TEMPLATES`.
        params: The template's parameters (see the module docstring for units).

    Returns:
        ``(structure, title)``: the validated step structure and the Japanese
        title built from the same parameters.

    Raises:
        ValueError: On an unknown template id, a missing / mistyped / unknown
            parameter, or a structure that fails ``validate_structure``.
    """
    template = TEMPLATES.get(template_id)
    if template is None:
        raise ValueError(
            f"unknown workout template {template_id!r}; "
            f"expected one of {sorted(TEMPLATES)}"
        )
    p = _Params(params, f"template {template_id!r}")
    structure = template.build(p)
    title = template.title(p)
    unknown = p.unknown()
    if unknown:
        raise ValueError(f"template {template_id!r}: unknown params {sorted(unknown)}")
    return validate_structure(structure, title=title), title
