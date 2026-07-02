import type { SectionResult } from "../../types";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import ReportCard, { META_LABEL, SUBCARD, SUBHEADING } from "./ReportCard";
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

/**
 * Vertical timeline of phase evaluations (warmup / run / cooldown, plus
 * recovery when present). evaluation_criteria is shown as a muted footnote.
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
                  <li key={key} className="relative">
                    <span
                      aria-hidden="true"
                      className={`absolute top-1 -left-[27px] h-3 w-3 rounded-full ring-4 ring-white ${dot}`}
                    />
                    <h3 className={SUBHEADING}>{label}</h3>
                    <div className="mt-1">
                      <MarkdownText text={data[key] as string} />
                    </div>
                  </li>
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
              <div className={`mt-4 ${SUBCARD}`}>
                <h3 className={META_LABEL}>評価基準</h3>
                <MarkdownText text={data.evaluation_criteria} />
              </div>
            )}
            <FallbackFields data={data} exclude={KNOWN_KEYS} />
          </>
        );
      }}
    </ReportCard>
  );
}
