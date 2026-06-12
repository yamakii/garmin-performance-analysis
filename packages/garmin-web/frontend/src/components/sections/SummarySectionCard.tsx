import type { SummarySectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";
import {
  SECTION_CARD_CLASS,
  SECTION_SUBTITLE_CLASS,
  SECTION_TITLE_CLASS,
} from "./SectionCard";

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
    <section className={SECTION_CARD_CLASS}>
      <h3 className={SECTION_TITLE_CLASS}>
        総合評価
        {typeof data.star_rating === "string" ? (
          <span className="ml-2 font-normal text-amber-500">
            {data.star_rating}
          </span>
        ) : (
          ""
        )}
      </h3>
      {typeof data.summary === "string" && <MarkdownText text={data.summary} />}
      {Array.isArray(data.key_strengths) && data.key_strengths.length > 0 && (
        <>
          <h4 className={SECTION_SUBTITLE_CLASS}>強み</h4>
          <ul className="list-disc space-y-1 pl-5">
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
            <h4 className={SECTION_SUBTITLE_CLASS}>改善ポイント</h4>
            <ul className="list-disc space-y-1 pl-5">
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
          <h4 className={SECTION_SUBTITLE_CLASS}>推奨事項</h4>
          <MarkdownText text={data.recommendations} />
        </>
      )}
      {/* Fields added without a version bump (integrated_score, next_action,
          next_run_target, plan_achievement, ...) fall back to key-value. */}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
