import type { SplitSectionData } from "../../types";
import KeyValueList from "./KeyValueList";
import MarkdownText from "./MarkdownText";

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
    <section className="section-card">
      <h3>スプリット分析</h3>
      {typeof data.highlights === "string" && (
        <>
          <h4>ハイライト</h4>
          <MarkdownText text={data.highlights} />
        </>
      )}
      {analysisEntries.length > 0 && (
        <>
          <h4>スプリット別分析</h4>
          {analysisEntries.map(([key, text]) => (
            <div key={key} className="split-analysis">
              <h5>{key.replace("split_", "")} km</h5>
              {typeof text === "string" ? (
                <MarkdownText text={text} />
              ) : (
                String(text)
              )}
            </div>
          ))}
        </>
      )}
      <KeyValueList data={data} exclude={KNOWN_KEYS} />
    </section>
  );
}
