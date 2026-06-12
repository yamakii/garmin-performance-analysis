import type { SummarySectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";

const KNOWN_KEYS = [
  "metadata",
  "star_rating",
  "summary",
  "key_strengths",
  "improvement_areas",
  "recommendations",
];

export default function SummarySectionCard({
  data,
}: {
  data: SummarySectionData;
}) {
  return (
    <section className="section-card">
      <h3>
        総合評価
        {typeof data.star_rating === "string" ? ` ${data.star_rating}` : ""}
      </h3>
      {typeof data.summary === "string" && <MarkdownText text={data.summary} />}
      {Array.isArray(data.key_strengths) && data.key_strengths.length > 0 && (
        <>
          <h4>強み</h4>
          <ul>
            {data.key_strengths.map((item) => (
              <li key={String(item)}>
                <MarkdownText text={String(item)} />
              </li>
            ))}
          </ul>
        </>
      )}
      {Array.isArray(data.improvement_areas) &&
        data.improvement_areas.length > 0 && (
          <>
            <h4>改善ポイント</h4>
            <ul>
              {data.improvement_areas.map((item) => (
                <li key={String(item)}>
                  <MarkdownText text={String(item)} />
                </li>
              ))}
            </ul>
          </>
        )}
      {typeof data.recommendations === "string" && (
        <>
          <h4>推奨事項</h4>
          <MarkdownText text={data.recommendations} />
        </>
      )}
      {/* Fields added without a version bump (integrated_score, next_action,
          next_run_target, plan_achievement, ...) fall back to key-value. */}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
