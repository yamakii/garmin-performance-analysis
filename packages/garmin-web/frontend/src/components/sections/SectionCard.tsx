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

/** Shared Tailwind classes for analysis section cards (Issue #210). */
export const SECTION_CARD_CLASS =
  "rounded-xl border border-slate-200 bg-white p-5 shadow-sm";

export const SECTION_TITLE_CLASS = "mb-2 text-base font-semibold text-slate-800";

export const SECTION_SUBTITLE_CLASS =
  "mt-4 mb-1 text-sm font-semibold text-slate-600";

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
      <section className={SECTION_CARD_CLASS}>
        <h3 className={SECTION_TITLE_CLASS}>{title}</h3>
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          分析データのJSON解析に失敗しました。
        </p>
        {section.raw != null && (
          <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-100 p-3 text-xs text-slate-700">
            {section.raw}
          </pre>
        )}
      </section>
    );
  }

  if (!isRecord(section.data)) {
    return (
      <section className={SECTION_CARD_CLASS}>
        <h3 className={SECTION_TITLE_CLASS}>{title}</h3>
        <p className="text-sm text-slate-500">分析データがありません。</p>
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
