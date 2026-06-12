import type { EfficiencySectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";
import {
  SECTION_CARD_CLASS,
  SECTION_SUBTITLE_CLASS,
  SECTION_TITLE_CLASS,
} from "./SectionCard";

const FIELDS: { key: keyof EfficiencySectionData & string; label: string }[] = [
  { key: "efficiency", label: "フォーム効率" },
  { key: "evaluation", label: "心拍効率評価" },
  { key: "form_trend", label: "フォームトレンド" },
];

const KNOWN_KEYS = ["metadata", ...FIELDS.map((field) => field.key)];

export default function EfficiencySectionCard({
  data,
}: {
  data: EfficiencySectionData;
}) {
  return (
    <section className={SECTION_CARD_CLASS}>
      <h3 className={SECTION_TITLE_CLASS}>効率分析</h3>
      {FIELDS.map(({ key, label }) => {
        const text = data[key];
        if (typeof text !== "string") {
          return null;
        }
        return (
          <div key={key}>
            <h4 className={SECTION_SUBTITLE_CLASS}>{label}</h4>
            <MarkdownText text={text} />
          </div>
        );
      })}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
