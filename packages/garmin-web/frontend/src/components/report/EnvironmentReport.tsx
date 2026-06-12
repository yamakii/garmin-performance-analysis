import type { SectionResult } from "../../types";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import ReportCard from "./ReportCard";

const KNOWN_KEYS = ["metadata", "environmental"];

/**
 * Environmental impact report (weather, terrain). The section payload is
 * a single prose field per Spike #198; structured additions fall back to
 * key-value rendering.
 */
export default function EnvironmentReport({
  section,
}: {
  section: SectionResult | undefined;
}) {
  return (
    <ReportCard title="環境影響" section={section}>
      {(data) => (
        <>
          {typeof data.environmental === "string" && (
            <MarkdownText text={data.environmental} />
          )}
          <FallbackFields data={data} exclude={KNOWN_KEYS} />
        </>
      )}
    </ReportCard>
  );
}
