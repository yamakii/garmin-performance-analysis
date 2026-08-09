import type { SectionResult } from "../../types";
import { formatNumber } from "../../utils/formatNumber";
import { splitLead } from "../../utils/leadSentence";
import ClampedProse from "../ClampedProse";
import Disclosure from "../Disclosure";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import NextRunTarget from "./NextRunTarget";
import ReportCard from "./ReportCard";
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

type Tone = "emerald" | "amber";

const PALETTES: Record<Tone, { frame: string; title: string; marker: string }> =
  {
    emerald: {
      frame: "border-emerald-100 bg-emerald-50/60",
      title: "text-emerald-800",
      marker: "text-emerald-500",
    },
    amber: {
      frame: "border-amber-100 bg-amber-50/60",
      title: "text-amber-800",
      marker: "text-amber-500",
    },
  };

function Bullet({
  text,
  tone,
  marker,
}: {
  text: string;
  tone: Tone;
  marker: string;
}) {
  return (
    <li className="flex gap-2 text-sm text-slate-700">
      <span aria-hidden="true" className={`shrink-0 ${PALETTES[tone].marker}`}>
        {marker}
      </span>
      <MarkdownText text={text} />
    </li>
  );
}

function StringList({
  items,
  tone,
  title,
  marker,
}: {
  items: unknown[];
  tone: Tone;
  title: string;
  marker: string;
}) {
  const palette = PALETTES[tone];
  return (
    <div className={`rounded-lg border p-4 ${palette.frame}`}>
      <h3 className={`text-sm font-semibold ${palette.title}`}>{title}</h3>
      <ul className="mt-2 space-y-1.5">
        {items.map((item, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <Bullet key={index} text={String(item)} tone={tone} marker={marker} />
        ))}
      </ul>
    </div>
  );
}

/** Count chip: "✓ 強み 4" / "! 改善 2" — the headline before any list. */
function CountChip({
  tone,
  marker,
  label,
  count,
}: {
  tone: Tone;
  marker: string;
  label: string;
  count: number;
}) {
  const palette = PALETTES[tone];
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${palette.frame} ${palette.title}`}
    >
      {`${marker} ${label} ${count}`}
    </span>
  );
}

function asStringArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/**
 * Overall assessment report, conclusion-first (#905): the star rating and the
 * summary's opening sentence read as the verdict, with the rest of the prose
 * clamped and the full strength / improvement lists folded into a disclosure.
 * `next_action` stays outside every fold — the one thing to do next is the
 * point of the card. Unconsumed keys fall back to key-value.
 */
export default function SummaryReport({
  section,
}: {
  section: SectionResult | undefined;
}) {
  return (
    <ReportCard title="総合評価" section={section}>
      {(data) => {
        const summaryText =
          typeof data.summary === "string" ? data.summary : null;
        const summary = summaryText != null ? splitLead(summaryText) : null;
        const strengths = asStringArray(data.key_strengths);
        const improvements = asStringArray(data.improvement_areas);
        // The disclosure only earns its place once a list has more than the
        // one item already previewed above it.
        const hasMore = strengths.length > 1 || improvements.length > 1;
        return (
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
            {summary && (
              <div className="space-y-1.5">
                <p className="text-base leading-relaxed font-semibold text-ink">
                  {summary.lead}
                </p>
                {summary.body !== "" && (
                  <ClampedProse text={summary.body} lines={3} markdown />
                )}
              </div>
            )}
            {(strengths.length > 0 || improvements.length > 0) && (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  {strengths.length > 0 && (
                    <CountChip
                      tone="emerald"
                      marker="✓"
                      label="強み"
                      count={strengths.length}
                    />
                  )}
                  {improvements.length > 0 && (
                    <CountChip
                      tone="amber"
                      marker="!"
                      label="改善"
                      count={improvements.length}
                    />
                  )}
                </div>
                <ul className="space-y-1.5">
                  {strengths.length > 0 && (
                    <Bullet
                      text={String(strengths[0])}
                      tone="emerald"
                      marker="✓"
                    />
                  )}
                  {improvements.length > 0 && (
                    <Bullet
                      text={String(improvements[0])}
                      tone="amber"
                      marker="!"
                    />
                  )}
                </ul>
                {hasMore && (
                  <Disclosure title="強み・改善点をすべて見る">
                    <div className="grid gap-3 pt-1 md:grid-cols-2">
                      {strengths.length > 0 && (
                        <StringList
                          items={strengths}
                          tone="emerald"
                          title="強み"
                          marker="✓"
                        />
                      )}
                      {improvements.length > 0 && (
                        <StringList
                          items={improvements}
                          tone="amber"
                          title="改善ポイント"
                          marker="!"
                        />
                      )}
                    </div>
                  </Disclosure>
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
                  <Disclosure title="詳しい改善ポイント">
                    <MarkdownText text={data.recommendations} />
                  </Disclosure>
                )}
              </div>
            )}
            <FallbackFields data={data} exclude={KNOWN_KEYS} />
          </div>
        );
      }}
    </ReportCard>
  );
}
