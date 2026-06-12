import type { EnvironmentSectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";

const KNOWN_KEYS = ["metadata", "environmental"];

export default function EnvironmentSectionCard({
  data,
}: {
  data: EnvironmentSectionData;
}) {
  return (
    <section className="section-card">
      <h3>環境影響</h3>
      {typeof data.environmental === "string" && (
        <MarkdownText text={data.environmental} />
      )}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
