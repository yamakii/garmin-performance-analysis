import type { SectionResult } from "../../types";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import { isRecord, ParseErrorNotice, SUBCARD, SUBHEADING } from "./ReportCard";

const KNOWN_KEYS = ["metadata", "highlights", "analyses"];

function splitNumber(key: string): number {
  const match = /^split_(\d+)$/.exec(key);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

function splitLabel(key: string): string {
  const match = /^split_(\d+)$/.exec(key);
  return match ? match[1] : key;
}

/**
 * Per-split narrative from `analyses.split_N` (dynamic, distance-dependent
 * keys per Spike #198), rendered in ascending split order with a number
 * badge. Designed to be embedded directly under the splits table.
 */
export default function SplitNarrative({
  section,
}: {
  section: SectionResult | undefined;
}) {
  if (!section) {
    return null;
  }
  if (section.parse_error) {
    return (
      <div className="mt-4 border-t border-slate-100 pt-4">
        <ParseErrorNotice raw={section.raw} />
      </div>
    );
  }
  if (!isRecord(section.data)) {
    return null;
  }
  const data = section.data;
  const analyses = isRecord(data.analyses) ? data.analyses : null;
  const entries = analyses
    ? Object.entries(analyses).sort(
        ([a], [b]) => splitNumber(a) - splitNumber(b),
      )
    : [];

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <h3 className={SUBHEADING}>スプリット解説</h3>
      {typeof data.highlights === "string" && (
        <div className={`mt-2 ${SUBCARD}`}>
          <MarkdownText text={data.highlights} />
        </div>
      )}
      {entries.length > 0 && (
        <ol className="mt-3 space-y-2.5">
          {entries.map(([key, text]) => (
            <li key={key} className="flex items-start gap-3">
              <span
                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink/10 font-numeric text-xs font-semibold tabular-nums text-ink"
                aria-label={`スプリット ${splitLabel(key)}`}
              >
                {splitLabel(key)}
              </span>
              <div className="min-w-0">
                {typeof text === "string" ? (
                  <MarkdownText text={text} />
                ) : (
                  String(text)
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      <FallbackFields data={data} exclude={KNOWN_KEYS} />
    </div>
  );
}
