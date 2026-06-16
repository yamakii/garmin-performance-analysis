import type { ReactNode } from "react";
import type { SectionResult } from "../../types";

export const REPORT_CARD_CLASS =
  "rounded-xl border border-slate-200 bg-white p-5 shadow-sm";

/** Neutral gray sub-box nested on a white report card. */
export const SUBCARD = "rounded-lg bg-slate-50 px-3 py-2";

/** Subsection heading inside a report card (h3). */
export const SUBHEADING = "text-sm font-semibold text-slate-700";

/** Compact meta label for a dt / footnote heading. */
export const META_LABEL = "text-xs font-medium tracking-wide text-slate-500";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Warning + raw payload shown when section JSON could not be parsed. */
export function ParseErrorNotice({ raw }: { raw: string | null }) {
  return (
    <>
      <p
        role="alert"
        className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
      >
        分析データのJSON解析に失敗しました。
      </p>
      {raw != null && (
        <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-100 p-3 text-xs text-slate-700">
          {raw}
        </pre>
      )}
    </>
  );
}

/**
 * Card shell for one analysis report section. Degrades gracefully:
 * - section missing -> renders nothing (the report omits the block)
 * - parse_error -> warning + raw JSON for inspection
 * - non-object data -> "no data" placeholder
 */
export default function ReportCard({
  title,
  section,
  children,
}: {
  title: string;
  section: SectionResult | undefined;
  children: (data: Record<string, unknown>) => ReactNode;
}) {
  if (!section) {
    return null;
  }
  let body: ReactNode;
  if (section.parse_error) {
    body = <ParseErrorNotice raw={section.raw} />;
  } else if (isRecord(section.data)) {
    body = children(section.data);
  } else {
    body = <p className="text-sm text-slate-500">分析データがありません。</p>;
  }
  return (
    <section className={REPORT_CARD_CLASS}>
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        {title}
      </h2>
      {body}
    </section>
  );
}
