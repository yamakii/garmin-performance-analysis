import type { EfficiencySectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";

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
    <section className="section-card">
      <h3>効率分析</h3>
      {FIELDS.map(({ key, label }) => {
        const text = data[key];
        if (typeof text !== "string") {
          return null;
        }
        return (
          <div key={key}>
            <h4>{label}</h4>
            <MarkdownText text={text} />
          </div>
        );
      })}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
