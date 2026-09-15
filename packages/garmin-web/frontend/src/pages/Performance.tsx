import { useState, type ReactNode } from "react";
import {
  useCriticalSpeed,
  useDurabilityTrend,
  useEfficiencyTrend,
  useFormTrend,
  useHeatAdjustedTrend,
  useObjectiveFitnessTrend,
  usePhysiologyTrend,
  useTrendNarration,
  useTrendNarrationVersions,
  useVolumeTrend,
  useWeightEconomyCoupling,
} from "../api/hooks";
import type {
  CriticalSpeedPoint,
  Granularity,
  ObjectiveFitnessTrend,
  TrendNarration,
} from "../api/trends";
import QueryBoundary from "../components/QueryBoundary";
import SectionBlock from "../components/SectionBlock";
import Segment, { type SegmentOption } from "../components/Segment";
import SectionNav from "../components/SectionNav";
import TrendNarrationCard, {
  narrationLead,
} from "../components/TrendNarrationCard";
import VerdictLine from "../components/VerdictLine";
import VitalsRow, { type VitalItem } from "../components/VitalsRow";
import { usePageTitle } from "../hooks/usePageTitle";
import type { DurabilityTrend, WeightEconomyCoupling } from "../types";
import { formatDateLabel, formatPaceValue } from "../utils/format";
import { formatNumber } from "../utils/formatNumber";
import { performanceVerdict, type PerformanceKpis } from "../utils/verdict";
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
 * "速くなっているか?" — the longitudinal performance read (Morning Brief P3b,
 * #1121).
 *
 * The page opens with the verdict and the coach's first paragraph, then the
 * four objective numbers behind it, then the nine metric blocks in one column:
 * volume, physiology, efficiency, critical speed, objective fitness,
 * climate-neutral HR, form, durability and weight × economy. The blocks are a
 * single column rather than a two-up grid because they are read top-down as one
 * argument, not compared side by side.
 *
 * The week/month choice is a page-level control rather than a switch buried in
 * the volume block, because it also drives the narration at the top of the
 * page: the old hidden toggle rewrote content far above itself. Each block
 * owns its own query and failure via `QueryBoundary`.
 */

/** Trailing window (days) for the climate-neutral HR trend (one year). */
const HEAT_ADJUSTED_LOOKBACK_DAYS = 365;

/** The comparison window every "4週" delta on this page uses. */
const FOUR_WEEKS_DAYS = 28;

/**
 * Decoupling target for a long run in the strong band. The chart keeps its 5%
 * 目安 line — that is where a run has clearly faded; this tighter mark is what
 * a durability-focused block is aiming at, so the vitals note flags it first.
 */
const DECOUPLING_TARGET_PCT = 3.5;

/** "09/07" — the day part of the short label, for a period range. */
function shortDay(iso: string): string {
  return formatDateLabel(iso).slice(0, 5);
}

/** UTC epoch of a YYYY-MM-DD day; null when it is not a calendar day. */
function utcDay(iso: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return match == null
    ? null
    : Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

/**
 * The latest value of a dated series and the value it had `days` ago — the
 * latest reading at least that old, so a sparse series compares against a real
 * measurement rather than an interpolation. `previous` is null when the series
 * does not reach back that far: a four-week delta needs four weeks.
 */
function seriesWindow(
  points: { date: string; value: number | null }[],
  days: number,
): { latest: number | null; previous: number | null } {
  const usable = points
    .filter((p) => p.value != null && utcDay(p.date) != null)
    .sort((a, b) => a.date.localeCompare(b.date));
  const last = usable[usable.length - 1] ?? null;
  if (last == null) {
    return { latest: null, previous: null };
  }
  const cutoff = utcDay(last.date)! - days * 86_400_000;
  const prior =
    [...usable].reverse().find((p) => utcDay(p.date)! <= cutoff) ?? null;
  return { latest: last.value, previous: prior?.value ?? null };
}

/** The objective numbers behind the verdict and the vitals row. */
function performanceKpis(
  objective: ObjectiveFitnessTrend | null,
  weightEconomy: WeightEconomyCoupling | null,
  durability: DurabilityTrend | null,
): PerformanceKpis {
  const vdot = seriesWindow(
    (objective?.objective_curve ?? []).map((p) => ({
      date: p.date,
      value: p.vdot,
    })),
    FOUR_WEEKS_DAYS,
  );
  const ef = seriesWindow(
    (weightEconomy?.series ?? []).map((p) => ({
      date: p.run_date,
      value: p.ef,
    })),
    FOUR_WEEKS_DAYS,
  );
  const latestLongRun = durability?.activities.at(-1) ?? null;
  return {
    objectiveVdot: vdot.latest,
    vdotDelta4w:
      vdot.latest != null && vdot.previous != null
        ? vdot.latest - vdot.previous
        : null,
    ef: ef.latest,
    efDeltaPct4w:
      ef.latest != null && ef.previous != null && ef.previous !== 0
        ? ((ef.latest - ef.previous) / ef.previous) * 100
        : null,
    decouplingPct: latestLongRun?.decoupling_pct ?? null,
  };
}

/** "+0.8" / "-0.5" / "±0.0". */
function signed(value: number, digits: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "±";
  return `${sign}${Math.abs(value).toFixed(digits)}`;
}

/** The four numbers the verdict rests on, each linked to the block that owns it. */
function vitalsItems(
  kpis: PerformanceKpis,
  criticalSpeed: CriticalSpeedPoint[] | null,
): VitalItem[] {
  const cs = criticalSpeed?.at(-1) ?? null;
  const decoupling = kpis.decouplingPct;
  const decouplingAdverse =
    decoupling != null && decoupling >= DECOUPLING_TARGET_PCT;
  return [
    {
      label: "客観 VDOT",
      value:
        kpis.objectiveVdot != null ? formatNumber(kpis.objectiveVdot, 1) : "—",
      note:
        kpis.vdotDelta4w != null
          ? `4週 ${signed(kpis.vdotDelta4w, 1)}`
          : "実走ベース",
      to: "#objective-fitness",
    },
    {
      label: "効率 EF",
      value: kpis.ef != null ? formatNumber(kpis.ef, 4) : "—",
      note:
        kpis.efDeltaPct4w != null
          ? `4週 ${signed(kpis.efDeltaPct4w, 1)}%`
          : "易ラン",
      to: "#weight-economy",
    },
    {
      label: "クリティカルスピード",
      value: cs != null ? formatPaceValue(cs.cs_pace_sec_per_km) : "—",
      unit: cs != null ? "/km" : undefined,
      note: cs != null ? `${cs.quarter} · R² ${cs.r_squared.toFixed(2)}` : "四半期推定",
      to: "#critical-speed",
    },
    {
      label: "耐久性 デカップリング",
      value: decoupling != null ? formatNumber(decoupling, 1) : "—",
      unit: decoupling != null ? "%" : undefined,
      note: decouplingAdverse
        ? `目標 ${DECOUPLING_TARGET_PCT}% 未満を超過`
        : `目標 ${DECOUPLING_TARGET_PCT}% 未満`,
      noteTone: decouplingAdverse ? "warn" : "muted",
      to: "#durability",
    },
  ];
}

/** "週次トレンド · 10/06 – 10/12 · 解説 v2" — what this page is showing. */
function metaLine(
  granularity: Granularity,
  narration: TrendNarration | null,
  versionCount: number,
): string {
  const parts = [granularity === "month" ? "月次トレンド" : "週次トレンド"];
  if (narration != null) {
    parts.push(
      `${shortDay(narration.period_start)} – ${shortDay(narration.period_end)}`,
    );
  }
  if (versionCount > 0) {
    parts.push(`解説 v${versionCount}`);
  }
  return parts.join(" · ");
}

/** Page-level week/month switch driving both the narration and the volume block. */
const GRANULARITY_OPTIONS: SegmentOption<Granularity>[] = [
  { value: "week", label: "週" },
  { value: "month", label: "月" },
];

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
  const narrationQuery = useTrendNarration(granularity);
  const versionsQuery = useTrendNarrationVersions(
    granularity,
    narrationQuery.data?.period_start,
  );

  // The verdict and the vitals row read whatever has landed: a missing block is
  // an em dash in one cell, not an error banner over the page. The blocks
  // themselves still surface their own failures through `QueryBoundary`.
  const narration = narrationQuery.data ?? null;
  const kpis = performanceKpis(
    objectiveFitnessQuery.data ?? null,
    weightEconomyQuery.data ?? null,
    durabilityQuery.data ?? null,
  );
  const verdict = performanceVerdict(narration, kpis);
  const lead = narration != null ? narrationLead(narration) : "";

  // One list drives both the in-page table of contents and the blocks, so the
  // nav can never point at an anchor that is not rendered.
  const sections: {
    id: string;
    label: string;
    note: string;
    content: ReactNode;
  }[] = [
    {
      id: "volume",
      label: "走行量",
      note: granularity === "week" ? "週次 · km" : "月次 · km",
      content: (
        <QueryBoundary label="走行量" query={volumeQuery}>
          {(data) => <VolumeBlock data={data} granularity={granularity} />}
        </QueryBoundary>
      ),
    },
    {
      id: "physiology",
      label: "生理指標",
      note: "VO2max / 乳酸閾値",
      content: (
        <QueryBoundary label="生理指標" query={physiologyQuery}>
          {(data) => <PhysiologyBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "efficiency",
      label: "効率推移",
      note: "HRゾーン分布 · 月次 · 直近12ヶ月",
      content: (
        <QueryBoundary label="効率推移" query={efficiencyQuery}>
          {(data) => <EfficiencyBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "critical-speed",
      label: "クリティカルスピード",
      note: "四半期 · LT速度プロキシ",
      content: (
        <QueryBoundary label="クリティカルスピード" query={criticalSpeedQuery}>
          {(data) => <CriticalSpeedPanel data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "objective-fitness",
      label: "客観フィットネス",
      note: "実走VDOT vs Garmin VO2max",
      content: (
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
      note: "暑熱補正 · 直近365日",
      content: (
        <QueryBoundary label="気候中立HRトレンド" query={heatAdjustedQuery}>
          {(data) => <HeatAdjustedBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "form",
      label: "フォームスコア",
      note: "スコア + 偏差",
      content: (
        <QueryBoundary label="フォームスコア推移" query={formQuery}>
          {(data) => <FormBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "durability",
      label: "耐久性",
      note: "ロングラン · デカップリング",
      content: (
        <QueryBoundary label="耐久性" query={durabilityQuery}>
          {(data) => <DurabilityBlock data={data} />}
        </QueryBoundary>
      ),
    },
    {
      id: "weight-economy",
      label: "体重 × エコノミー",
      note: "易ラン EF",
      content: (
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
    <div className="flex flex-col gap-12">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <p className="font-mono text-[13px] text-ink-muted">
            {metaLine(granularity, narration, versionsQuery.data?.length ?? 0)}
          </p>
          <Segment
            options={GRANULARITY_OPTIONS}
            value={granularity}
            onChange={setGranularity}
            ariaLabel="集計単位"
          />
        </div>

        {/*
          The coach's own words carry the verdict: its opening paragraph is the
          rationale, the rest of the write-up is folded away below it.
        */}
        <VerdictLine
          verdict={verdict.verdict}
          verdictTone={verdict.tone}
          rest={verdict.rest}
          lead={lead !== "" ? lead : undefined}
        />
        <TrendNarrationCard granularity={granularity} />
      </div>

      <VitalsRow
        ariaLabel="客観指標"
        items={vitalsItems(kpis, criticalSpeedQuery.data ?? null)}
      />

      <SectionNav items={sections.map(({ id, label }) => ({ id, label }))} />

      {sections.map(({ id, label, note, content }) => (
        <SectionBlock key={id} id={id} title={label} note={note} noteMono>
          {content}
        </SectionBlock>
      ))}
    </div>
  );
}
