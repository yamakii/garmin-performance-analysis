import type { SectionResult } from "../../types";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import ReportCard from "./ReportCard";

const FIELDS: { key: string; label: string }[] = [
  { key: "efficiency", label: "フォーム効率" },
  { key: "evaluation", label: "心拍効率評価" },
  { key: "form_trend", label: "フォームトレンド" },
];

const KNOWN_KEYS = ["metadata", ...FIELDS.map((field) => field.key)];

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** "期待 <value><unit>" note from an expected metric, or null. */
function expectedNote(
  expected: number | null,
  unit: string,
  digits: number,
): string | null {
  if (expected == null) {
    return null;
  }
  return `期待${expected.toFixed(digits)}${unit}`;
}

/** "偏差 ±<value><unit>" note from a delta, or null. */
function deltaNote(
  delta: number | null,
  unit: string,
  digits: number,
): string | null {
  if (delta == null) {
    return null;
  }
  const sign = delta > 0 ? "+" : "";
  return `偏差${sign}${delta.toFixed(digits)}${unit}`;
}

function joinNotes(...parts: (string | null)[]): string | null {
  const kept = parts.filter((part): part is string => part != null);
  return kept.length > 0 ? kept.join(" / ") : null;
}

type Tile = {
  label: string;
  value: number | null;
  unit: string;
  digits: number;
  rating: string | null;
  note: string | null;
  subValue?: string | null;
};

/**
 * Efficiency analysis: structured form metrics as stat tiles alongside the
 * analyst's prose evaluation.
 *
 * Tiles read the authoritative, pace-based, expectation-relative evaluation
 * (form_evaluations table) so the values and stars match the prose. The
 * CV-based form_efficiency table is no longer used here (#292).
 */
export default function EfficiencyReport({
  section,
  formEvaluations,
}: {
  section: SectionResult | undefined;
  formEvaluations?: Record<string, unknown> | null;
}) {
  const fe = formEvaluations;

  // form_evaluations may be null for unevaluated activities; show prose only.
  const tiles: Tile[] = fe
    ? [
        {
          label: "接地時間",
          value: asNumber(fe.gct_ms_actual),
          unit: "ms",
          digits: 0,
          rating: asString(fe.gct_star_rating),
          note: joinNotes(
            expectedNote(asNumber(fe.gct_ms_expected), "ms", 0),
            deltaNote(asNumber(fe.gct_delta_pct), "%", 1),
          ),
        },
        {
          label: "上下動",
          value: asNumber(fe.vo_cm_actual),
          unit: "cm",
          digits: 1,
          rating: asString(fe.vo_star_rating),
          // VO stores an absolute cm delta (vo_delta_cm), not a percentage.
          note: joinNotes(
            expectedNote(asNumber(fe.vo_cm_expected), "cm", 1),
            deltaNote(asNumber(fe.vo_delta_cm), "cm", 1),
          ),
        },
        {
          label: "上下動比",
          value: asNumber(fe.vr_pct_actual),
          unit: "%",
          digits: 1,
          rating: asString(fe.vr_star_rating),
          note: joinNotes(
            expectedNote(asNumber(fe.vr_pct_expected), "%", 1),
            deltaNote(asNumber(fe.vr_delta_pct), "%", 1),
          ),
        },
      ]
    : [];

  // Power tile only when the activity has power data (#292).
  const powerAvg = asNumber(fe?.power_avg_w);
  const powerWkg = asNumber(fe?.power_wkg);
  if (powerAvg != null) {
    tiles.push({
      label: "パワー",
      value: powerAvg,
      unit: "W",
      digits: 0,
      rating: asString(fe?.power_efficiency_rating),
      note: null,
      subValue: powerWkg != null ? `${powerWkg.toFixed(2)} W/kg` : null,
    });
  }

  const stats = tiles.filter((tile) => tile.value != null);

  return (
    <ReportCard title="効率分析" section={section}>
      {(data) => (
        <>
          {stats.length > 0 && (
            // Columns track tile count so 4 tiles (with power) fit one row
            // and 3 tiles (no power) stay balanced without an empty cell.
            <dl
              className={`mb-4 grid grid-cols-2 gap-3 ${
                stats.length >= 4 ? "sm:grid-cols-4" : "sm:grid-cols-3"
              }`}
            >
              {stats.map(
                ({ label, value, unit, digits, rating, note, subValue }) => (
                  <div
                    key={label}
                    className="rounded-lg bg-slate-50 px-3 py-2"
                  >
                    <dt className="text-xs font-medium tracking-wide text-slate-500">
                      {label}
                    </dt>
                    {/* GCT / VO / VR / power share the violet form-metric color (#214). */}
                    <dd className="mt-0.5 font-numeric text-2xl leading-none font-semibold tabular-nums text-metric-form">
                      {value!.toFixed(digits)}
                      <span className="ml-0.5 text-xs font-normal text-slate-500">
                        {unit}
                      </span>
                    </dd>
                    {subValue && (
                      <dd className="text-xs text-slate-500">{subValue}</dd>
                    )}
                    {rating && (
                      <dd className="text-xs text-slate-500">{rating}</dd>
                    )}
                    {note && (
                      <dd className="text-[11px] leading-tight text-slate-400">
                        {note}
                      </dd>
                    )}
                  </div>
                ),
              )}
            </dl>
          )}
          {FIELDS.map(({ key, label }) => {
            const text = data[key];
            if (typeof text !== "string") {
              return null;
            }
            return (
              <div key={key} className="mt-3 first:mt-0">
                <h3 className="mb-1 text-sm font-semibold text-slate-700">
                  {label}
                </h3>
                <MarkdownText text={text} />
              </div>
            );
          })}
          <FallbackFields data={data} exclude={KNOWN_KEYS} />
        </>
      )}
    </ReportCard>
  );
}
