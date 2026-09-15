import type { SectionResult } from "../../types";
import { extractStarSuffix } from "../../utils/starSuffix";
import Disclosure from "../Disclosure";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import ReportCard from "./ReportCard";
import StarRatingBreakdown from "./StarRatingBreakdown";

const PHASES: { key: string; label: string }[] = [
  { key: "warmup_evaluation", label: "ウォームアップ" },
  { key: "run_evaluation", label: "メインラン" },
  // Interval training only (5.6% of rows per Spike #198).
  { key: "recovery_evaluation", label: "リカバリー" },
  { key: "cooldown_evaluation", label: "クールダウン" },
];

const KNOWN_KEYS = [
  "metadata",
  "evaluation_criteria",
  "star_rating_breakdown",
  ...PHASES.map((phase) => phase.key),
];

const MAX_SCORE = 5;

const ACTUAL_MARKER = /\*\*実際\*\*\s*[:：]\s*/;
const EVALUATION_MARKER = /\*\*評価\*\*\s*[:：]\s*/;

/**
 * Split phase prose written as `**実際**: … **評価**: …` into its two halves.
 *
 * The verdict (評価) is what the reader needs first; the measurements (実際)
 * are supporting detail. Prose without both markers — older analyses, or a
 * free-form paragraph — returns null so the caller renders it verbatim.
 */
function splitPhaseProse(
  text: string,
): { actual: string; evaluation: string } | null {
  const actual = ACTUAL_MARKER.exec(text);
  const evaluation = EVALUATION_MARKER.exec(text);
  if (actual == null || evaluation == null || evaluation.index < actual.index) {
    return null;
  }
  const actualText = text
    .slice(actual.index + actual[0].length, evaluation.index)
    .trim();
  const evaluationText = text
    .slice(evaluation.index + evaluation[0].length)
    .trim();
  if (actualText === "" || evaluationText === "") {
    return null;
  }
  return { actual: actualText, evaluation: evaluationText };
}

/**
 * One phase as a rule-separated row: name, score, verdict (Morning Brief,
 * #1118). The old vertical timeline drew a dot and a rail for a sequence the
 * reader already knows — warmup comes before the run — so the ink now goes to
 * the three columns that differ between phases instead.
 */
function PhaseRow({ label, text }: { label: string; text: string }) {
  const { body, rating } = extractStarSuffix(text);
  const parts = splitPhaseProse(body);
  return (
    <div className="grid grid-cols-[1fr_auto] items-start gap-x-2 border-b border-hairline py-3 md:grid-cols-[120px_80px_minmax(0,1fr)]">
      <h3 className="text-[15px] font-bold text-ink">{label}</h3>
      <div>
        {rating && (
          <span
            aria-label={`評価 ${rating.score.toFixed(1)} / ${MAX_SCORE.toFixed(1)}`}
            className="font-mono text-[13px] font-medium text-star"
          >
            <span aria-hidden="true">★</span> {rating.score.toFixed(1)}
          </span>
        )}
      </div>
      {/*
        Below `md` the verdict gets the full width under the name + score row:
        at 390px a third fixed column left it about 130px wide, which turned one
        paragraph into dozens of lines (#1145).
      */}
      <div className="col-span-2 mt-1 min-w-0 md:col-span-1 md:mt-0">
        <div className="text-sm leading-[1.7] text-ink-soft">
          <MarkdownText text={parts ? parts.evaluation : body} />
        </div>
        {parts && (
          <p className="mt-1 font-mono text-xs leading-relaxed text-ink-muted">
            {`実際: ${parts.actual}`}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Phase evaluations (warmup / run / cooldown, plus recovery when present) as
 * one rule-separated table: each row leads with its score and its verdict
 * (#905), the measured detail is a mono footnote, and the shared
 * evaluation_criteria folds into a disclosure.
 */
export default function PhaseTimeline({
  section,
  id,
}: {
  section: SectionResult | undefined;
  id?: string;
}) {
  return (
    <ReportCard id={id} title="フェーズ評価" section={section}>
      {(data) => {
        const phases = PHASES.filter(
          ({ key }) => typeof data[key] === "string",
        );
        return (
          <>
            {phases.length > 0 && (
              <div className="border-t border-ink">
                {phases.map(({ key, label }) => (
                  <PhaseRow
                    key={key}
                    label={label}
                    text={data[key] as string}
                  />
                ))}
              </div>
            )}
            {data.star_rating_breakdown != null &&
              typeof data.star_rating_breakdown === "object" && (
                <div className="mt-4">
                  <StarRatingBreakdown data={data.star_rating_breakdown} />
                </div>
              )}
            {typeof data.evaluation_criteria === "string" && (
              <Disclosure title="評価基準" className="mt-4">
                <MarkdownText text={data.evaluation_criteria} />
              </Disclosure>
            )}
            <FallbackFields data={data} exclude={KNOWN_KEYS} />
          </>
        );
      }}
    </ReportCard>
  );
}
