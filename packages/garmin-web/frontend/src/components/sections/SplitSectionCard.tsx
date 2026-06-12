import type { SplitSectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";
import {
  SECTION_CARD_CLASS,
  SECTION_SUBTITLE_CLASS,
  SECTION_TITLE_CLASS,
} from "./SectionCard";

const KNOWN_KEYS = ["metadata", "highlights", "analyses"];

function splitNumber(key: string): number {
  const match = /^split_(\d+)$/.exec(key);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

export default function SplitSectionCard({ data }: { data: SplitSectionData }) {
  const analyses =
    data.analyses && typeof data.analyses === "object" ? data.analyses : null;
  const analysisEntries = analyses
    ? Object.entries(analyses).sort(
        ([a], [b]) => splitNumber(a) - splitNumber(b),
      )
    : [];

  return (
    <section className={SECTION_CARD_CLASS}>
      <h3 className={SECTION_TITLE_CLASS}>スプリット分析</h3>
      {typeof data.highlights === "string" && (
        <>
          <h4 className={SECTION_SUBTITLE_CLASS}>ハイライト</h4>
          <MarkdownText text={data.highlights} />
        </>
      )}
      {analysisEntries.length > 0 && (
        <>
          <h4 className={SECTION_SUBTITLE_CLASS}>スプリット別分析</h4>
          <div className="space-y-2">
            {analysisEntries.map(([key, text]) => (
              <div
                key={key}
                className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
              >
                <h5 className="text-xs font-semibold tabular-nums text-indigo-600">
                  {key.replace("split_", "")} km
                </h5>
                {typeof text === "string" ? (
                  <MarkdownText text={text} />
                ) : (
                  String(text)
                )}
              </div>
            ))}
          </div>
        </>
      )}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
