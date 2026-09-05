import type { SectionResult } from "../../types";
import { formatNumber } from "../../utils/formatNumber";
import { splitLead } from "../../utils/leadSentence";
import { ratingMeta } from "../../utils/verdictRating";
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
  "prescription_verdict",
  "vs_previous",
];

type Tone = "emerald" | "amber" | "rose";

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
    rose: {
      frame: "border-rose-100 bg-rose-50/60",
      title: "text-rose-800",
      marker: "text-rose-500",
    },
  };

/**
 * Card palette per verdict mark (Issue #984). An unrecognized mark stays amber:
 * a verdict the schema does not know is not a green light.
 */
const VERDICT_TONES: Record<string, Tone> = {
  "✅": "emerald",
  "🟡": "amber",
  "🔴": "rose",
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

function asRecord(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * How the run answered the session prescribed for that day (Issue #984): the
 * mark is decorative and the word it stands for is what gets announced (#912),
 * with the first reason carrying the number behind the judgement. Summaries
 * written before the prescription layer simply have no key, and render as
 * they always did.
 */
function PrescriptionVerdictLine({ data }: { data: Record<string, unknown> }) {
  const verdict = typeof data.verdict === "string" ? data.verdict : null;
  if (verdict == null) {
    return null;
  }
  const palette = PALETTES[VERDICT_TONES[verdict] ?? "amber"];
  const { label } = ratingMeta(verdict);
  const title =
    typeof data.prescription_title === "string"
      ? data.prescription_title
      : null;
  const reasons = asStringArray(data.reasons);
  const reason = reasons.length > 0 ? String(reasons[0]) : null;
  return (
    <div className={`rounded-lg border p-3 ${palette.frame}`}>
      <p className={`text-sm font-semibold ${palette.title}`}>
        <span aria-hidden="true">{verdict}</span>{" "}
        {title != null ? `処方「${title}」・${label}` : `処方との比較・${label}`}
      </p>
      {reason != null && <p className="mt-1 text-sm text-slate-700">{reason}</p>}
    </div>
  );
}

/** Metrics shown as 前回比 chips, in reading order, with their units. */
const VS_PREVIOUS_METRICS: { key: string; label: string; unit: string }[] = [
  { key: "pace_s_per_km", label: "ペース", unit: "秒/km" },
  { key: "avg_hr", label: "HR", unit: "bpm" },
  { key: "gct_ms", label: "GCT", unit: "ms" },
  { key: "cadence_spm", label: "ケイデンス", unit: "spm" },
];

/** "+4 ms" / "-10 秒/km" / "±0 bpm" — the sign is the point, so it is explicit. */
function formatDelta(delta: number, unit: string): string {
  const sign = delta > 0 ? "+" : delta === 0 ? "±" : "";
  return `${sign}${formatNumber(delta)} ${unit}`;
}

function DeltaChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
      <span className="text-slate-500">{label}</span>
      <span className="tabular-nums">{value}</span>
    </span>
  );
}

/**
 * Deltas against the last run of the same training type (Issue #984). The
 * chips stay neutral in tone: whether a delta is good depends on the metric
 * and on the session's intent, and that reading belongs to the prose, not to
 * a color.
 */
function VsPreviousChips({ data }: { data: Record<string, unknown> }) {
  const chips = VS_PREVIOUS_METRICS.map(({ key, label, unit }) => {
    const delta = asRecord(data[key])?.delta;
    return typeof delta === "number" && Number.isFinite(delta)
      ? { label, value: formatDelta(delta, unit) }
      : null;
  }).filter((chip) => chip != null);
  if (chips.length === 0) {
    return null;
  }
  const daysAgo = typeof data.days_ago === "number" ? data.days_ago : null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold text-slate-500">
        {daysAgo != null ? `前回比（${daysAgo}日前）` : "前回比"}
      </span>
      {chips.map((chip) => (
        <DeltaChip key={chip.label} label={chip.label} value={chip.value} />
      ))}
    </div>
  );
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
        const verdict = asRecord(data.prescription_verdict);
        const vsPrevious = asRecord(data.vs_previous);
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
            {(verdict != null ||
              vsPrevious != null ||
              typeof data.next_action === "string" ||
              data.next_run_target != null ||
              typeof data.recommendations === "string") && (
              <div className="space-y-3">
                {/* What the plan asked for, and how the same session went last
                    time, read before the action they justify (Issue #984). */}
                {verdict != null && <PrescriptionVerdictLine data={verdict} />}
                {vsPrevious != null && <VsPreviousChips data={vsPrevious} />}
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
