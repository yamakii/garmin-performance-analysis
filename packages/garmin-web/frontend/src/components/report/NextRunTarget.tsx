import type { JSX, ReactNode } from "react";

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

/** Builds a "low–high" / "low" / "high" range string, or null when both absent. */
function formatRange(
  low: string | number | null,
  high: string | number | null,
  unit: string,
): string | null {
  if (low != null && high != null) {
    return `${low}–${high} ${unit}`;
  }
  if (low != null) {
    return `${low} ${unit}`;
  }
  if (high != null) {
    return `${high} ${unit}`;
  }
  return null;
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
      <span className="text-indigo-500">{label}</span>
      <span className="tabular-nums">{value}</span>
    </span>
  );
}

function LabeledLine({ label, value }: { label: string; value: string }) {
  return (
    <p className="text-sm text-slate-700">
      <span className="font-semibold text-indigo-700">{label}</span>
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
    asString(data.reference_pace_low_formatted),
    asString(data.reference_pace_high_formatted),
    "/km",
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
    <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-indigo-700 uppercase">
          次回への処方
        </h3>
        {typeLabel != null && (
          <span className="rounded-full bg-indigo-600 px-2.5 py-0.5 text-xs font-semibold text-white">
            {typeLabel}
          </span>
        )}
      </div>
      {summaryJa != null && (
        <p className="mt-2 text-sm leading-relaxed text-slate-700">{summaryJa}</p>
      )}
      {chips.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">{chips}</div>
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
