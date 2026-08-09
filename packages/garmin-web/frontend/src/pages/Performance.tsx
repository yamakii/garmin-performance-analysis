import { useState, type ReactNode } from "react";
import {
  useCriticalSpeed,
  useDurabilityTrend,
  useEfficiencyTrend,
  useFormTrend,
  useHeatAdjustedTrend,
  useObjectiveFitnessTrend,
  usePhysiologyTrend,
  useVolumeTrend,
  useWeightEconomyCoupling,
} from "../api/hooks";
import type { Granularity } from "../api/trends";
import QueryBoundary from "../components/QueryBoundary";
import SectionHeading from "../components/SectionHeading";
import SectionNav from "../components/SectionNav";
import TrendNarrationCard from "../components/TrendNarrationCard";
import { usePageTitle } from "../hooks/usePageTitle";
import CriticalSpeedPanel from "./trends/CriticalSpeedPanel";
import DurabilityBlock from "./trends/DurabilityBlock";
import EfficiencyBlock from "./trends/EfficiencyBlock";
import FormBlock from "./trends/FormBlock";
import HeatAdjustedBlock from "./trends/HeatAdjustedBlock";
import ObjectiveFitnessBlock from "./trends/ObjectiveFitnessBlock";
import PhysiologyBlock from "./trends/PhysiologyBlock";
import VolumeBlock from "./trends/VolumeBlock";
import WeightEconomyChart from "./trends/WeightEconomyChart";

/**
 * "速くなっているか?" — the longitudinal performance read: coach narration on
 * top, then volume, physiology, efficiency, critical speed, objective fitness,
 * climate-neutral HR, form, durability and weight × economy.
 *
 * Split out of the 16-card `/trends` mega-page (#892); the readiness cards
 * moved to `/condition`.
 *
 * The week/month choice is a page-level control rather than a switch buried in
 * the volume card, because it also drives the narration at the top of the page:
 * the old hidden toggle rewrote content far above itself. Each card owns its
 * own query and failure via `QueryBoundary`.
 */

/** Trailing window (days) for the climate-neutral HR trend (one year). */
const HEAT_ADJUSTED_LOOKBACK_DAYS = 365;

function toggleClass(active: boolean): string {
  const base =
    "rounded-md px-3 py-1 text-sm font-medium transition-colors cursor-pointer";
  return active
    ? `${base} bg-white text-ink shadow-sm`
    : `${base} text-slate-600 hover:text-ink`;
}

/** Page-level week/month switch driving both the narration and the volume card. */
function GranularityToggle({
  granularity,
  onChange,
}: {
  granularity: Granularity;
  onChange: (granularity: Granularity) => void;
}) {
  return (
    <div
      role="group"
      aria-label="集計単位"
      className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5"
    >
      <button
        type="button"
        aria-pressed={granularity === "week"}
        className={toggleClass(granularity === "week")}
        onClick={() => onChange("week")}
      >
        週
      </button>
      <button
        type="button"
        aria-pressed={granularity === "month"}
        className={toggleClass(granularity === "month")}
        onClick={() => onChange("month")}
      >
        月
      </button>
    </div>
  );
}

export default function Performance() {
  usePageTitle("パフォーマンス");
  const [granularity, setGranularity] = useState<Granularity>("week");

  const volumeQuery = useVolumeTrend(granularity);
  const physiologyQuery = usePhysiologyTrend();
  const efficiencyQuery = useEfficiencyTrend();
  const criticalSpeedQuery = useCriticalSpeed();
  const objectiveFitnessQuery = useObjectiveFitnessTrend();
  const heatAdjustedQuery = useHeatAdjustedTrend(HEAT_ADJUSTED_LOOKBACK_DAYS);
  const formQuery = useFormTrend();
  const durabilityQuery = useDurabilityTrend();
  const weightEconomyQuery = useWeightEconomyCoupling();

  // One list drives both the in-page table of contents and the cards, so the
  // nav can never point at an anchor that is not rendered.
  const cards: { id: string; label: string; card: ReactNode }[] = [
    {
      id: "volume",
      label: "走行量",
      card: (
        <QueryBoundary label="走行量" query={volumeQuery}>
          {(data) => <VolumeBlock data={data} granularity={granularity} />}
        </QueryBoundary>
      ),
    },
    {
      id: "physiology",
      label: "生理指標",
      card: (
        <QueryBoundary label="生理指標" query={physiologyQuery}>
          {(data) => <PhysiologyBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "efficiency",
      label: "効率推移",
      card: (
        <QueryBoundary label="効率推移" query={efficiencyQuery}>
          {(data) => <EfficiencyBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "critical-speed",
      label: "クリティカルスピード",
      card: (
        <QueryBoundary label="クリティカルスピード" query={criticalSpeedQuery}>
          {(data) => <CriticalSpeedPanel data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "objective-fitness",
      label: "客観フィットネス",
      card: (
        <QueryBoundary
          label="客観フィットネス曲線"
          query={objectiveFitnessQuery}
        >
          {(data) => <ObjectiveFitnessBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "heat-adjusted",
      label: "気候中立HR",
      card: (
        <QueryBoundary label="気候中立HRトレンド" query={heatAdjustedQuery}>
          {(data) => <HeatAdjustedBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "form",
      label: "フォームスコア",
      card: (
        <QueryBoundary label="フォームスコア推移" query={formQuery}>
          {(data) => <FormBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "durability",
      label: "耐久性",
      card: (
        <QueryBoundary label="耐久性" query={durabilityQuery}>
          {(data) => <DurabilityBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "weight-economy",
      label: "体重 × エコノミー",
      card: (
        <QueryBoundary
          label="体重 × ランニングエコノミー"
          query={weightEconomyQuery}
        >
          {(data) => <WeightEconomyChart data={data} />}
        </QueryBoundary>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SectionHeading eyebrow="Performance" title="速くなっているか" />
        <GranularityToggle
          granularity={granularity}
          onChange={setGranularity}
        />
      </div>

      <SectionNav items={cards.map(({ id, label }) => ({ id, label }))} />

      {/*
        Coach narration: the qualitative story leads the page, full width and
        outside the metric grid. Hides itself when no narration has been
        generated yet (404 / empty table).
      */}
      <TrendNarrationCard granularity={granularity} />

      <div className="stagger-in grid gap-4 md:grid-cols-2">
        {cards.map(({ id, card }) => (
          <div key={id} id={id} className="scroll-mt-20">
            {card}
          </div>
        ))}
      </div>
    </div>
  );
}
