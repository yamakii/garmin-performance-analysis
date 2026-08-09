import type { ReactNode } from "react";
import { humanizeKey } from "../../utils/format";
import { formatNumber } from "../../utils/formatNumber";
import MarkdownText from "./MarkdownText";
import { META_LABEL } from "./ReportCard";

/**
 * Japanese names for payload keys that show up often enough to be worth
 * naming. Everything else is humanized (Issue #915) rather than shown raw —
 * `easy_z1_z2` reads as "easy z1 z2", not as a database column.
 */
const FIELD_LABELS: Record<string, string> = {
  activity_type: "アクティビティ種別",
  assessment: "評価",
  conclusion: "結論",
  evaluation: "評価",
  highlights: "ハイライト",
  next_run_target: "次回への処方",
  overall: "総評",
  rating: "評価",
  recommendations: "推奨アクション",
  summary: "サマリー",
  training_type: "トレーニング種別",
};

/** Display name for a payload key: known label, else humanized key. */
export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? humanizeKey(key);
}

export function renderValue(value: unknown): ReactNode {
  if (value == null) {
    return "-";
  }
  if (typeof value === "string") {
    return <MarkdownText text={value} />;
  }
  if (typeof value === "number") {
    // Strip floating-point noise / trailing zeros from un-consumed numeric
    // fields (e.g. integrated_score 4.2000000000001 -> "4.2").
    return formatNumber(value);
  }
  if (typeof value === "boolean") {
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
    return <FallbackFields data={value as Record<string, unknown>} flush />;
  }
  return String(value);
}

/**
 * Renders fields that no dedicated report component consumed as a
 * key-value list (graceful degradation for schema evolution, Spike #198).
 * String values are rendered as Markdown; arrays and nested objects
 * are rendered recursively.
 */
export default function FallbackFields({
  data,
  exclude = [],
  flush = false,
}: {
  data: Record<string, unknown>;
  exclude?: string[];
  /** Render without the top divider (for nested objects). */
  flush?: boolean;
}) {
  const entries = Object.entries(data).filter(([key]) => !exclude.includes(key));
  if (entries.length === 0) {
    return null;
  }
  const frame = flush
    ? "divide-y divide-slate-100"
    : "mt-4 divide-y divide-slate-100 border-t border-slate-100";
  return (
    <dl className={frame}>
      {entries.map(([key, value]) => (
        <div key={key} className="py-2">
          <dt className={META_LABEL}>{fieldLabel(key)}</dt>
          <dd className="mt-0.5 text-sm text-slate-700">{renderValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
