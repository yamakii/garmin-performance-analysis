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

/**
 * Efficiency analysis: structured form metrics (from the form_efficiency
 * table) as stat tiles alongside the analyst's prose evaluation.
 */
export default function EfficiencyReport({
  section,
  formEfficiency,
}: {
  section: SectionResult | undefined;
  formEfficiency?: Record<string, unknown> | null;
}) {
  const stats = [
    {
      label: "接地時間",
      value: asNumber(formEfficiency?.gct_average),
      unit: "ms",
      rating: asString(formEfficiency?.gct_rating),
    },
    {
      label: "上下動",
      value: asNumber(formEfficiency?.vo_average),
      unit: "cm",
      rating: asString(formEfficiency?.vo_rating),
    },
    {
      label: "上下動比",
      value: asNumber(formEfficiency?.vr_average),
      unit: "%",
      rating: asString(formEfficiency?.vr_rating),
    },
  ].filter((stat) => stat.value != null);

  return (
    <ReportCard title="効率分析" section={section}>
      {(data) => (
        <>
          {stats.length > 0 && (
            <dl className="mb-4 grid grid-cols-3 gap-3">
              {stats.map(({ label, value, unit, rating }) => (
                <div
                  key={label}
                  className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                >
                  <dt className="text-xs font-medium tracking-wide text-slate-500">
                    {label}
                  </dt>
                  {/* GCT / VO / VR share the violet form-metric color (#214). */}
                  <dd className="mt-0.5 font-numeric text-2xl leading-none font-semibold tabular-nums text-metric-form">
                    {value}
                    <span className="ml-0.5 text-xs font-normal text-slate-500">
                      {unit}
                    </span>
                  </dd>
                  {rating && (
                    <dd className="text-xs text-slate-500">{rating}</dd>
                  )}
                </div>
              ))}
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
