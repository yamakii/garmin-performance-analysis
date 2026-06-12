import type { SectionResult } from "../../types";
import EfficiencySectionCard from "./EfficiencySectionCard";
import EnvironmentSectionCard from "./EnvironmentSectionCard";
import FallbackCard from "./FallbackCard";
import PhaseSectionCard from "./PhaseSectionCard";
import SplitSectionCard from "./SplitSectionCard";
import SummarySectionCard from "./SummarySectionCard";

export const SECTION_TITLES: Record<string, string> = {
  summary: "総合評価",
  split: "スプリット分析",
  phase: "フェーズ評価",
  efficiency: "効率分析",
  environment: "環境影響",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Dispatches a section analysis to its dedicated card.
 * - Known section types get dedicated rendering; unknown fields inside
 *   them fall back to key-value rendering automatically.
 * - Unknown section types or non-object data fall back to FallbackCard.
 * - Parse errors render the raw string for inspection.
 */
export default function SectionCard({
  sectionType,
  section,
}: {
  sectionType: string;
  section: SectionResult;
}) {
  const title = SECTION_TITLES[sectionType] ?? sectionType;

  if (section.parse_error) {
    return (
      <section className="section-card">
        <h3>{title}</h3>
        <p role="alert">分析データのJSON解析に失敗しました。</p>
        {section.raw != null && <pre>{section.raw}</pre>}
      </section>
    );
  }

  if (!isRecord(section.data)) {
    return (
      <section className="section-card">
        <h3>{title}</h3>
        <p>分析データがありません。</p>
      </section>
    );
  }

  switch (sectionType) {
    case "summary":
      return <SummarySectionCard data={section.data} />;
    case "split":
      return <SplitSectionCard data={section.data} />;
    case "phase":
      return <PhaseSectionCard data={section.data} />;
    case "efficiency":
      return <EfficiencySectionCard data={section.data} />;
    case "environment":
      return <EnvironmentSectionCard data={section.data} />;
    default:
      return <FallbackCard title={title} data={section.data} />;
  }
}
