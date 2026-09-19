import type { JSX, ReactNode } from "react";
import { PACE_UNIT } from "../../utils/format";

/** Japanese labels for known training types; unknown types fall through to raw. */
const TYPE_LABELS: Record<string, string> = {
  aerobic_base: "ベース走",
  recovery: "リカバリー",
  tempo: "テンポ走",
  interval: "インターバル",
  long_run: "ロング走",
  threshold: "閾値走",
};

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Builds a "low–high" / "low" / "high" range string, or null when both absent.
 * `/km` is written tight against the number, matching `formatPace` everywhere
 * else; worded units keep their space (#915).
 */
function formatRange(
  low: string | number | null,
  high: string | number | null,
  unit: string,
): string | null {
  const span =
    low != null && high != null ? `${low}–${high}` : (low ?? high ?? null);
  if (span == null) {
    return null;
  }
  return unit === PACE_UNIT ? `${span}${unit}` : `${span} ${unit}`;
}

/**
 * A pace bound without its unit, so the range carries `/km` exactly once.
 *
 * `reference_pace_*_formatted` is written by the agent and sometimes already
 * carries the unit ("5:40/km"), which the range then appended a second one to:
 * the same-type fallback card read "5:40/km–5:43/km/km" (#1277). Both shapes
 * are accepted and the unit is added once, by `formatRange`.
 */
function stripPaceUnit(value: string | null): string | null {
  if (value == null) {
    return null;
  }
  const bare = value.endsWith(PACE_UNIT)
    ? value.slice(0, -PACE_UNIT.length).trimEnd()
    : value;
  return bare !== "" ? bare : null;
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs text-ink">
      <span className="text-ink-muted">{label}</span>
      <span>{value}</span>
    </span>
  );
}

function LabeledLine({ label, value }: { label: string; value: string }) {
  return (
    <p className="text-[15px] leading-[1.7] text-ink-soft">
      <span className="font-bold text-ink">{label}</span>
      <span className="ml-1.5">{value}</span>
    </p>
  );
}

/**
 * Prescription card for the structured `next_run_target` object: lead summary,
 * a Japanese training-type badge, target HR / reference pace chips, and
 * labeled success criterion / adjustment tip. Renders only present fields and
 * never exposes raw English keys. Returns null for non-object input.
 */
export default function NextRunTarget({
  data,
}: {
  data: Record<string, unknown>;
}): JSX.Element | null {
  if (data == null || typeof data !== "object" || Array.isArray(data)) {
    return null;
  }

  const summaryJa = asString(data.summary_ja);
  const recommendedType = asString(data.recommended_type);
  const typeLabel =
    recommendedType != null
      ? (TYPE_LABELS[recommendedType] ?? recommendedType)
      : null;

  const hrRange = formatRange(
    asNumber(data.target_hr_low),
    asNumber(data.target_hr_high),
    "bpm",
  );
  const paceRange = formatRange(
    stripPaceUnit(asString(data.reference_pace_low_formatted)),
    stripPaceUnit(asString(data.reference_pace_high_formatted)),
    PACE_UNIT,
  );

  const successCriterion = asString(data.success_criterion);
  const adjustmentTip = asString(data.adjustment_tip);

  const chips: ReactNode[] = [];
  if (hrRange != null) {
    chips.push(<Chip key="hr" label="目標HR" value={hrRange} />);
  }
  if (paceRange != null) {
    chips.push(<Chip key="pace" label="参考ペース" value={paceRange} />);
  }

  return (
    <div className="border-t border-hairline pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-mono text-xs text-ink-muted">次回への処方</h3>
        {typeLabel != null && (
          <span className="rounded-sm bg-ink px-1.5 py-[3px] font-mono text-[11px] font-medium tracking-[0.04em] text-paper">
            {typeLabel}
          </span>
        )}
      </div>
      {summaryJa != null && (
        <p className="mt-2 text-[15px] leading-[1.7] text-ink-soft">
          {summaryJa}
        </p>
      )}
      {chips.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1">{chips}</div>
      )}
      {(successCriterion != null || adjustmentTip != null) && (
        <div className="mt-3 space-y-1.5">
          {successCriterion != null && (
            <LabeledLine label="成功条件" value={successCriterion} />
          )}
          {adjustmentTip != null && (
            <LabeledLine label="調整ヒント" value={adjustmentTip} />
          )}
        </div>
      )}
    </div>
  );
}
