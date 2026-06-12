import type { PhaseSectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";

const PHASE_FIELDS: { key: keyof PhaseSectionData & string; label: string }[] = [
  { key: "warmup_evaluation", label: "ウォームアップ" },
  { key: "run_evaluation", label: "メインラン" },
  { key: "recovery_evaluation", label: "リカバリー" }, // interval training only
  { key: "cooldown_evaluation", label: "クールダウン" },
  { key: "evaluation_criteria", label: "評価基準" },
];

const KNOWN_KEYS = ["metadata", ...PHASE_FIELDS.map((field) => field.key)];

export default function PhaseSectionCard({ data }: { data: PhaseSectionData }) {
  return (
    <section className="section-card">
      <h3>フェーズ評価</h3>
      {PHASE_FIELDS.map(({ key, label }) => {
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
