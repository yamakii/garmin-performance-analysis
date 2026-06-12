import type { ReactNode } from "react";
import MarkdownText from "./MarkdownText";

export function renderValue(value: unknown): ReactNode {
  if (value == null) {
    return "-";
  }
  if (typeof value === "string") {
    return <MarkdownText text={value} />;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return (
      <ul className="list-disc space-y-0.5 pl-5">
        {value.map((item, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <li key={index}>{renderValue(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    return <KeyValueList data={value as Record<string, unknown>} />;
  }
  return String(value);
}

/**
 * Generic key-value renderer for unknown / fallback section fields.
 * String values are rendered as Markdown; arrays and nested objects
 * are rendered recursively.
 */
export default function KeyValueList({
  data,
  exclude = [],
}: {
  data: Record<string, unknown>;
  exclude?: string[];
}) {
  const entries = Object.entries(data).filter(([key]) => !exclude.includes(key));
  if (entries.length === 0) {
    return null;
  }
  return (
    <dl className="mt-3 divide-y divide-slate-100 border-t border-slate-100">
      {entries.map(([key, value]) => (
        <div key={key} className="py-2">
          <dt className="text-xs font-medium tracking-wide text-slate-500">
            {key}
          </dt>
          <dd className="mt-0.5 text-sm text-slate-700">{renderValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
