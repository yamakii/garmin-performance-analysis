import type { SectionResult } from "../../types";
import { formatNumber } from "../../utils/formatNumber";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import NextRunTarget from "./NextRunTarget";
import ReportCard, { SUBCARD } from "./ReportCard";
import StarRating from "./StarRating";
import StarRatingBreakdown from "./StarRatingBreakdown";

// Keys with dedicated UI (Spike #198: 100% keys + optional summary fields).
const KNOWN_KEYS = [
  "metadata",
  "star_rating",
  "star_rating_breakdown",
  "summary",
  "key_strengths",
  "improvement_areas",
  "recommendations",
  "integrated_score",
  "next_action",
  "next_run_target",
];

function StringList({
  items,
  tone,
  title,
  marker,
}: {
  items: unknown[];
  tone: "emerald" | "amber";
  title: string;
  marker: string;
}) {
  const palette =
    tone === "emerald"
      ? {
          frame: "border-emerald-100 bg-emerald-50/60",
          title: "text-emerald-800",
          marker: "text-emerald-500",
        }
      : {
          frame: "border-amber-100 bg-amber-50/60",
          title: "text-amber-800",
          marker: "text-amber-500",
        };
  return (
    <div className={`rounded-lg border p-4 ${palette.frame}`}>
      <h3 className={`text-sm font-semibold ${palette.title}`}>{title}</h3>
      <ul className="mt-2 space-y-1.5">
        {items.map((item, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <li key={index} className="flex gap-2 text-sm text-slate-700">
            <span aria-hidden="true" className={`shrink-0 ${palette.marker}`}>
              {marker}
            </span>
            <MarkdownText text={String(item)} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Overall assessment report: large star rating, summary prose,
 * strengths / improvement areas, and action callouts for the
 * recommendation-style fields. Unconsumed keys fall back to key-value.
 */
export default function SummaryReport({
  section,
}: {
  section: SectionResult | undefined;
}) {
  return (
    <ReportCard title="総合評価" section={section}>
      {(data) => (
        <div className="space-y-4">
          {(typeof data.star_rating === "string" ||
            typeof data.integrated_score === "number") && (
            <div className="flex flex-wrap items-center gap-3">
              {typeof data.star_rating === "string" && (
                <StarRating text={data.star_rating} size="lg" />
              )}
              {typeof data.integrated_score === "number" && (
                <span className="rounded-full bg-ink/5 px-3 py-1 text-xs font-semibold tabular-nums text-ink">
                  統合スコア {formatNumber(data.integrated_score, 1)}
                </span>
              )}
            </div>
          )}
          <StarRatingBreakdown
            data={data.star_rating_breakdown}
            showTotal={false}
          />
          {typeof data.summary === "string" && (
            <MarkdownText text={data.summary} />
          )}
          {((Array.isArray(data.key_strengths) &&
            data.key_strengths.length > 0) ||
            (Array.isArray(data.improvement_areas) &&
              data.improvement_areas.length > 0)) && (
            <div className="grid gap-3 md:grid-cols-2">
              {Array.isArray(data.key_strengths) &&
                data.key_strengths.length > 0 && (
                  <StringList
                    items={data.key_strengths}
                    tone="emerald"
                    title="強み"
                    marker="✓"
                  />
                )}
              {Array.isArray(data.improvement_areas) &&
                data.improvement_areas.length > 0 && (
                  <StringList
                    items={data.improvement_areas}
                    tone="amber"
                    title="改善ポイント"
                    marker="!"
                  />
                )}
            </div>
          )}
          {(typeof data.next_action === "string" ||
            data.next_run_target != null ||
            typeof data.recommendations === "string") && (
            <div className="space-y-3">
              {typeof data.next_action === "string" && (
                <p className="text-sm font-semibold text-slate-800">
                  {data.next_action}
                </p>
              )}
              {data.next_run_target != null &&
                typeof data.next_run_target === "object" &&
                !Array.isArray(data.next_run_target) && (
                  <NextRunTarget
                    data={data.next_run_target as Record<string, unknown>}
                  />
                )}
              {typeof data.recommendations === "string" && (
                <details className={SUBCARD}>
                  <summary className="cursor-pointer text-sm font-medium text-slate-600">
                    詳しい改善ポイント
                  </summary>
                  <div className="mt-2">
                    <MarkdownText text={data.recommendations} />
                  </div>
                </details>
              )}
            </div>
          )}
          <FallbackFields data={data} exclude={KNOWN_KEYS} />
        </div>
      )}
    </ReportCard>
  );
}
