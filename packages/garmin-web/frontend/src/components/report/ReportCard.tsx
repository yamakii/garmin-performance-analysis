import type { ReactNode } from "react";
import type { SectionResult } from "../../types";
import SectionBlock from "../SectionBlock";

/** Sub-block nested inside a report section: a rule and the figures under it. */
export const SUBCARD = "border-t border-hairline pt-2";

/** Subsection heading inside a report card (h3). */
export const SUBHEADING = "text-sm font-semibold text-ink-soft";

/** Compact meta label for a dt / footnote heading. */
export const META_LABEL = "text-xs font-medium tracking-wide text-ink-muted";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Warning + raw payload shown when section JSON could not be parsed. */
export function ParseErrorNotice({ raw }: { raw: string | null }) {
  return (
    <>
      <p
        role="alert"
        className="rounded-md border border-bad-line bg-bad-tint px-3 py-2 text-sm text-status-bad"
      >
        分析データのJSON解析に失敗しました。
      </p>
      {raw != null && (
        <pre className="mt-2 overflow-x-auto border-t border-hairline pt-3 text-xs text-ink-soft">
          {raw}
        </pre>
      )}
    </>
  );
}

/**
 * Shell for one analysis report section (Morning Brief, #1118).
 *
 * The white card is gone: a report section is a `SectionBlock` — its title in
 * the left label column, its content in the measure — so the activity report
 * reads as one document with a spine instead of a stack of boxes. Degrades
 * gracefully:
 * - section missing -> renders nothing (the report omits the block)
 * - parse_error -> warning + raw JSON for inspection
 * - non-object data -> "no data" placeholder
 *
 * `badge` renders inside the heading — the slot for a verdict (a star rating
 * pulled out of the prose) so the conclusion is readable before any sentence.
 */
export default function ReportCard({
  id,
  title,
  section,
  badge,
  children,
}: {
  /** Anchor id, so the section nav can jump to this block. */
  id?: string;
  title: string;
  section: SectionResult | undefined;
  badge?: ReactNode;
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
    body = <p className="text-sm text-ink-muted">分析データがありません。</p>;
  }
  return (
    <SectionBlock
      id={id}
      title={title}
      headingExtra={badge != null ? <span className="ml-2">{badge}</span> : undefined}
    >
      {body}
    </SectionBlock>
  );
}
