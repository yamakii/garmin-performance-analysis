import type { SectionResult } from "../../types";
import { extractStarSuffix } from "../../utils/starSuffix";
import Disclosure from "../Disclosure";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import ReportCard, { SUBHEADING } from "./ReportCard";
import StarBadge from "./StarBadge";
import StarRatingBreakdown from "./StarRatingBreakdown";

const PHASES: { key: string; label: string; dot: string }[] = [
  { key: "warmup_evaluation", label: "ウォームアップ", dot: "bg-sky-400" },
  { key: "run_evaluation", label: "メインラン", dot: "bg-ink" },
  // Interval training only (5.6% of rows per Spike #198).
  { key: "recovery_evaluation", label: "リカバリー", dot: "bg-violet-400" },
  { key: "cooldown_evaluation", label: "クールダウン", dot: "bg-emerald-400" },
];

const KNOWN_KEYS = [
  "metadata",
  "evaluation_criteria",
  "star_rating_breakdown",
  ...PHASES.map((phase) => phase.key),
];

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

/** One timeline node: label + score badge, verdict, then muted measurements. */
function PhaseNode({
  label,
  dot,
  text,
}: {
  label: string;
  dot: string;
  text: string;
}) {
  const { body, rating } = extractStarSuffix(text);
  const parts = splitPhaseProse(body);
  return (
    <li className="relative">
      <span
        aria-hidden="true"
        className={`absolute top-1 -left-[27px] h-3 w-3 rounded-full ring-4 ring-white ${dot}`}
      />
      <div className="flex flex-wrap items-center gap-2">
        <h3 className={SUBHEADING}>{label}</h3>
        {rating && <StarBadge score={rating.score} />}
      </div>
      <div className="mt-1">
        <MarkdownText text={parts ? parts.evaluation : body} />
      </div>
      {parts && (
        <p className="mt-1 text-xs leading-relaxed text-slate-400">
          {`実際: ${parts.actual}`}
        </p>
      )}
    </li>
  );
}

/**
 * Vertical timeline of phase evaluations (warmup / run / cooldown, plus
 * recovery when present). Each node leads with its score badge and verdict
 * (#905); the measured detail is a muted footnote and the shared
 * evaluation_criteria folds into a disclosure.
 */
export default function PhaseTimeline({
  section,
}: {
  section: SectionResult | undefined;
}) {
  return (
    <ReportCard title="フェーズ評価" section={section}>
      {(data) => {
        const phases = PHASES.filter(
          ({ key }) => typeof data[key] === "string",
        );
        return (
          <>
            {phases.length > 0 && (
              <ol className="relative ml-1.5 space-y-5 border-l-2 border-slate-200 pl-5">
                {phases.map(({ key, label, dot }) => (
                  <PhaseNode
                    key={key}
                    label={label}
                    dot={dot}
                    text={data[key] as string}
                  />
                ))}
              </ol>
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
