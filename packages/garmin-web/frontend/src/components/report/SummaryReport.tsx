import type { SectionResult } from "../../types";
import { formatNumber } from "../../utils/formatNumber";
import { splitLead } from "../../utils/leadSentence";
import { ratingMeta } from "../../utils/verdictRating";
import CoachNote from "../CoachNote";
import Disclosure from "../Disclosure";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import NextRunTarget from "./NextRunTarget";
import ReportCard from "./ReportCard";
import StarRatingBreakdown from "./StarRatingBreakdown";

// Keys with dedicated UI (Spike #198: 100% keys + optional summary fields).
// `star_rating` and `vs_previous` are consumed by the page header (#1118).
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

/** Items of one list shown before the fold; a longer list gets a disclosure. */
const PREVIEW_LIMIT = 4;

/** Verdict mark -> the colour its line is written in; unknown stays 注意. */
const VERDICT_TONE: Record<string, "warn" | "bad" | "good"> = {
  "✅": "good",
  "🟡": "warn",
  "🔴": "bad",
};

const TONE_CLASS = {
  good: "text-ink",
  warn: "text-status-warn",
  bad: "text-status-bad",
} as const;

/**
 * One assessment point: an ink `✓` for a strength, a warn `!` for something to
 * work on. The marker is decorative — the sentence carries the meaning — so it
 * is hidden from assistive tech and the list reads as prose (#912).
 */
function Point({ text, kind }: { text: string; kind: "strength" | "issue" }) {
  return (
    <li className="flex gap-3 text-[15px] leading-[1.7] text-ink-soft">
      <span
        aria-hidden="true"
        className={`shrink-0 font-mono ${
          kind === "strength" ? "text-ink" : "font-bold text-status-warn"
        }`}
      >
        {kind === "strength" ? "✓" : "!"}
      </span>
      <MarkdownText>{text}</MarkdownText>
    </li>
  );
}

function PointList({
  strengths,
  improvements,
}: {
  strengths: unknown[];
  improvements: unknown[];
}) {
  return (
    <ul className="flex flex-col gap-2">
      {strengths.map((item, index) => (
        // eslint-disable-next-line react/no-array-index-key
        <Point key={`s${index}`} text={String(item)} kind="strength" />
      ))}
      {improvements.map((item, index) => (
        // eslint-disable-next-line react/no-array-index-key
        <Point key={`i${index}`} text={String(item)} kind="issue" />
      ))}
    </ul>
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
  const tone = TONE_CLASS[VERDICT_TONE[verdict] ?? "warn"];
  const { label } = ratingMeta(verdict);
  const title =
    typeof data.prescription_title === "string"
      ? data.prescription_title
      : null;
  const reasons = asStringArray(data.reasons);
  const reason = reasons.length > 0 ? String(reasons[0]) : null;
  return (
    <div className="border-t border-hairline pt-3">
      <p className={`text-sm font-bold ${tone}`}>
        <span aria-hidden="true">{verdict}</span>{" "}
        {title != null ? `処方「${title}」・${label}` : `処方との比較・${label}`}
      </p>
      {reason != null && (
        <p className="mt-1 text-[15px] leading-[1.7] text-ink-soft">{reason}</p>
      )}
    </div>
  );
}

/**
 * Overall assessment (Morning Brief, #1118).
 *
 * The verdict of this section — the star rating, the summary's opening
 * sentence and the deltas against the last comparable run — is the page
 * header; what is left here is the reasoning: every strength and every thing
 * to work on as a marked list, and the one action to take next as a coach's
 * note behind an ink rule. Long lists fold past four items so a good run does
 * not bury its own conclusion. Unconsumed keys fall back to key-value.
 */
export default function SummaryReport({
  section,
  id,
}: {
  section: SectionResult | undefined;
  id?: string;
}) {
  return (
    <ReportCard id={id} title="総合評価" section={section}>
      {(data) => {
        const summaryText =
          typeof data.summary === "string" ? data.summary : null;
        // The lead sentence is the page's conclusion line; this section
        // carries what follows it, so the verdict is never said twice.
        const body = summaryText != null ? splitLead(summaryText).body : "";
        const strengths = asStringArray(data.key_strengths);
        const improvements = asStringArray(data.improvement_areas);
        const verdict = asRecord(data.prescription_verdict);
        const folded =
          strengths.length > PREVIEW_LIMIT ||
          improvements.length > PREVIEW_LIMIT;
        return (
          <div className="flex flex-col gap-4">
            {body !== "" && (
              <div className="text-[15px] leading-[1.7] text-ink-soft">
                <MarkdownText>{body}</MarkdownText>
              </div>
            )}
            {(strengths.length > 0 || improvements.length > 0) && (
              <>
                <PointList
                  strengths={strengths.slice(0, PREVIEW_LIMIT)}
                  improvements={improvements.slice(0, PREVIEW_LIMIT)}
                />
                {folded && (
                  <Disclosure
                    title={`強み・改善点をすべて見る(${strengths.length} / ${improvements.length})`}
                  >
                    <PointList
                      strengths={strengths.slice(PREVIEW_LIMIT)}
                      improvements={improvements.slice(PREVIEW_LIMIT)}
                    />
                  </Disclosure>
                )}
              </>
            )}
            {verdict != null && <PrescriptionVerdictLine data={verdict} />}
            {typeof data.next_action === "string" && (
              <CoachNote strong>{data.next_action}</CoachNote>
            )}
            {typeof data.integrated_score === "number" && (
              <p className="font-mono text-xs text-ink-muted">
                統合スコア {formatNumber(data.integrated_score, 1)}
              </p>
            )}
            <StarRatingBreakdown
              data={data.star_rating_breakdown}
              showTotal={false}
            />
            {data.next_run_target != null &&
              typeof data.next_run_target === "object" &&
              !Array.isArray(data.next_run_target) && (
                <NextRunTarget
                  data={data.next_run_target as Record<string, unknown>}
                />
              )}
            {typeof data.recommendations === "string" && (
              <Disclosure title="詳しい改善ポイント">
                <MarkdownText>{data.recommendations}</MarkdownText>
              </Disclosure>
            )}
            <FallbackFields data={data} exclude={KNOWN_KEYS} />
          </div>
        );
      }}
    </ReportCard>
  );
}
