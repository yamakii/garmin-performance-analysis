import KeyValueList from "./KeyValueList";

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
    <section className="section-card">
      <h3>{title}</h3>
      <KeyValueList data={data} exclude={exclude} />
    </section>
  );
}
