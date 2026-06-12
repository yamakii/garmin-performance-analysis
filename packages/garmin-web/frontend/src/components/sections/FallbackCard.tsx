import KeyValueList from "./KeyValueList";
import { SECTION_CARD_CLASS, SECTION_TITLE_CLASS } from "./SectionCard";

/** Generic card rendering all fields as key-value pairs. */
export default function FallbackCard({
  title,
  data,
  exclude = [],
}: {
  title: string;
  data: Record<string, unknown>;
  exclude?: string[];
}) {
  return (
    <section className={SECTION_CARD_CLASS}>
      <h3 className={SECTION_TITLE_CLASS}>{title}</h3>
      <KeyValueList data={data} exclude={exclude} />
    </section>
  );
}
