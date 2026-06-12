import type { EnvironmentSectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";
import { SECTION_CARD_CLASS, SECTION_TITLE_CLASS } from "./SectionCard";

const KNOWN_KEYS = ["metadata", "environmental"];

export default function EnvironmentSectionCard({
  data,
}: {
  data: EnvironmentSectionData;
}) {
  return (
    <section className={SECTION_CARD_CLASS}>
      <h3 className={SECTION_TITLE_CLASS}>環境影響</h3>
      {typeof data.environmental === "string" && (
        <MarkdownText text={data.environmental} />
      )}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
