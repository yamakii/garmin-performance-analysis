import type { SectionResult } from "../../types";
import { extractStarSuffix } from "../../utils/starSuffix";
import ClampedProse from "../ClampedProse";
import FallbackFields from "./FallbackFields";
import ReportCard, { isRecord } from "./ReportCard";
import StarBadge from "./StarBadge";
import StarRatingBreakdown from "./StarRatingBreakdown";

const KNOWN_KEYS = ["metadata", "environmental", "star_rating_breakdown"];

/** The `environmental` prose, split into its body and trailing star rating. */
function environmentalProse(section: SectionResult | undefined) {
  const data = isRecord(section?.data) ? section.data : null;
  const text = typeof data?.environmental === "string" ? data.environmental : "";
  return extractStarSuffix(text);
}

/**
 * Environmental impact report (weather, terrain).
 *
 * The section payload is a single prose field per Spike #198, which left this
 * card with no structure at all. It now reads conclusion-first (#905): the
 * star rating becomes a heading badge, the weighted axis bars (temperature /
 * humidity / terrain / wind) lead the card, and the prose follows clamped to
 * two lines. Structured additions fall back to key-value rendering.
 */
export default function EnvironmentReport({
  section,
}: {
  section: SectionResult | undefined;
}) {
  const { body, rating } = environmentalProse(section);
  return (
    <ReportCard
      title="環境影響"
      section={section}
      badge={rating && <StarBadge score={rating.score} />}
    >
      {(data) => (
        <div className="space-y-4">
          <StarRatingBreakdown data={data.star_rating_breakdown} />
          {body !== "" && <ClampedProse text={body} lines={2} markdown />}
          <FallbackFields data={data} exclude={KNOWN_KEYS} />
        </div>
      )}
    </ReportCard>
  );
}
