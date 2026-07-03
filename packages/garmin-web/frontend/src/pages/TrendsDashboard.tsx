import { useState, type ReactNode } from "react";
import {
  useBodyCompositionTrend,
  useCriticalSpeed,
  useDurabilityTrend,
  useEfficiencyTrend,
  useFormAnomalyFlags,
  useFormTrend,
  useHeatAdjustedTrend,
  useObjectiveFitnessTrend,
  usePhysiologyTrend,
  useRecoveryStatus,
  useRecoveryTrend,
  useTrainingLoad,
  useVolumeTrend,
  useWeightEconomyCoupling,
  useWellnessBaselineDeviation,
} from "../api/hooks";
import type { Granularity } from "../api/trends";
import VolumeBlock from "./trends/VolumeBlock";
import PhysiologyBlock from "./trends/PhysiologyBlock";
import FormBlock from "./trends/FormBlock";
import EfficiencyBlock from "./trends/EfficiencyBlock";
import HeatAdjustedBlock from "./trends/HeatAdjustedBlock";
import CriticalSpeedPanel from "./trends/CriticalSpeedPanel";
import ObjectiveFitnessBlock from "./trends/ObjectiveFitnessBlock";
import TrainingLoadBlock from "./trends/TrainingLoadBlock";
import DurabilityBlock from "./trends/DurabilityBlock";
import RecoveryPanel from "./trends/RecoveryPanel";
import ConditionCard from "./trends/ConditionCard";
import FormAnomalyFlagsCard from "./trends/FormAnomalyFlagsCard";
import BodyCompositionChart from "./trends/BodyCompositionChart";
import WeightEconomyChart from "./trends/WeightEconomyChart";
import WellnessBaselineChart from "./trends/WellnessBaselineChart";
import CardSkeleton from "../components/CardSkeleton";
import SectionHeading from "../components/SectionHeading";

/** Trailing window (days) for the climate-neutral HR trend (one year). */
const HEAT_ADJUSTED_LOOKBACK_DAYS = 365;

/** Eyebrow style shared with the Goal page section headers. */
const SECTION_HEADING =
  "text-xs font-semibold tracking-[0.2em] text-slate-400 uppercase";

/**
 * One titled metric group: an English eyebrow + Japanese heading (matching the
 * Goal page section pattern) above a two-column grid of trend cards. The
 * `aria-label` mirrors the Japanese title so the region (and its membership) is
 * addressable in tests and assistive tech.
 */
function TrendSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}): ReactNode {
  return (
    <section aria-label={title}>
      <p className={SECTION_HEADING}>{eyebrow}</p>
      <p className="mt-1 mb-4 font-display text-xl font-bold tracking-tight text-ink">
        {title}
      </p>
      <div className="grid gap-4 md:grid-cols-2">{children}</div>
    </section>
  );
}

export default function TrendsDashboard() {
  const [granularity, setGranularity] = useState<Granularity>("week");

  // Each card is fed by an independent query (no Promise.all) so a slow
  // endpoint never holds the whole dashboard hostage: every card resolves on
  // its own and swaps its skeleton for content as soon as its data lands.
  const volumeQuery = useVolumeTrend(granularity);
  const physiologyQuery = usePhysiologyTrend();
  const formQuery = useFormTrend();
  const efficiencyQuery = useEfficiencyTrend();
  const heatAdjustedQuery = useHeatAdjustedTrend(HEAT_ADJUSTED_LOOKBACK_DAYS);
  const criticalSpeedQuery = useCriticalSpeed();
  const objectiveFitnessQuery = useObjectiveFitnessTrend();
  const trainingLoadQuery = useTrainingLoad();
  const durabilityQuery = useDurabilityTrend();
  const recoveryQuery = useRecoveryTrend();
  const recoveryStatusQuery = useRecoveryStatus();
  const bodyCompositionQuery = useBodyCompositionTrend();
  const weightEconomyQuery = useWeightEconomyCoupling();
  const wellnessBaselineQuery = useWellnessBaselineDeviation();
  const formAnomalyFlagsQuery = useFormAnomalyFlags();

  const volume = volumeQuery.data ?? null;
  const physiology = physiologyQuery.data ?? null;
  const form = formQuery.data ?? null;
  const efficiency = efficiencyQuery.data ?? null;
  const heatAdjusted = heatAdjustedQuery.data ?? null;
  const criticalSpeed = criticalSpeedQuery.data ?? null;
  const objectiveFitness = objectiveFitnessQuery.data ?? null;
  const trainingLoad = trainingLoadQuery.data ?? null;
  const durability = durabilityQuery.data ?? null;
  const recovery = recoveryQuery.data ?? null;
  const recoveryStatus = recoveryStatusQuery.data ?? null;
  const bodyComposition = bodyCompositionQuery.data ?? null;
  const weightEconomy = weightEconomyQuery.data ?? null;
  const wellnessBaseline = wellnessBaselineQuery.data ?? null;
  const formAnomalyFlags = formAnomalyFlagsQuery.data ?? null;

  // A failure in any card's endpoint takes the page down with a banner; the
  // first error encountered wins.
  const error =
    volumeQuery.error ??
    physiologyQuery.error ??
    formQuery.error ??
    efficiencyQuery.error ??
    heatAdjustedQuery.error ??
    criticalSpeedQuery.error ??
    objectiveFitnessQuery.error ??
    trainingLoadQuery.error ??
    durabilityQuery.error ??
    recoveryQuery.error ??
    recoveryStatusQuery.error ??
    bodyCompositionQuery.error ??
    weightEconomyQuery.error ??
    wellnessBaselineQuery.error ??
    formAnomalyFlagsQuery.error ??
    null;

  if (error) {
    return (
      <p
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        エラー: {error.message}
      </p>
    );
  }

  // Each card renders a per-card skeleton until its own data resolves, so the
  // slowest endpoint no longer holds the entire page behind one spinner.
  return (
    <div className="space-y-8">
      <SectionHeading eyebrow="Trends" title="トレンドダッシュボード" />

      {/*
        Alert band: "今, 何を見るべきか" surfaced first, full width and outside
        the metric grid so the weekly caution is the top priority.
      */}
      {/* id anchors let the Home snapshot tiles deep-link to the matching card
          (e.g. フォーム注意点 → /trends#form-anomaly). scroll-mt keeps the
          target clear of the sticky header. */}
      <div id="form-anomaly" className="scroll-mt-20">
        {formAnomalyFlags == null ? (
          <CardSkeleton label="今週の注意点" />
        ) : (
          <FormAnomalyFlagsCard data={formAnomalyFlags} />
        )}
      </div>

      <div className="stagger-in space-y-10">
        {/* ① 今の状態 / Condition Now */}
        <TrendSection eyebrow="Condition Now" title="今の状態">
          {recoveryStatus == null ? (
            <CardSkeleton label="当日コンディション" />
          ) : (
            <ConditionCard data={recoveryStatus} />
          )}
          <div id="recovery" className="scroll-mt-20">
            {recovery == null ? (
              <CardSkeleton label="回復トレンド" />
            ) : (
              <RecoveryPanel data={recovery} />
            )}
          </div>
          {wellnessBaseline == null ? (
            <CardSkeleton label="個人ベースライン逸脱" />
          ) : (
            <WellnessBaselineChart data={wellnessBaseline} />
          )}
          <div id="training-load" className="scroll-mt-20">
            {trainingLoad == null ? (
              <CardSkeleton label="訓練負荷" />
            ) : (
              <TrainingLoadBlock data={trainingLoad} />
            )}
          </div>
        </TrendSection>

        {/* ② パフォーマンス / Performance */}
        <TrendSection eyebrow="Performance" title="パフォーマンス">
          {volume == null ? (
            <CardSkeleton label="走行量" />
          ) : (
            <VolumeBlock
              data={volume}
              granularity={granularity}
              onGranularityChange={setGranularity}
            />
          )}
          {physiology == null ? (
            <CardSkeleton label="生理指標" />
          ) : (
            <PhysiologyBlock data={physiology} />
          )}
          {efficiency == null ? (
            <CardSkeleton label="効率推移" />
          ) : (
            <EfficiencyBlock data={efficiency} />
          )}
          {criticalSpeed == null ? (
            <CardSkeleton label="クリティカルスピード" />
          ) : (
            <CriticalSpeedPanel data={criticalSpeed} />
          )}
          {objectiveFitness == null ? (
            <CardSkeleton label="客観フィットネス曲線" />
          ) : (
            <ObjectiveFitnessBlock data={objectiveFitness} />
          )}
          {heatAdjusted == null ? (
            <CardSkeleton label="気候中立HRトレンド" />
          ) : (
            <HeatAdjustedBlock data={heatAdjusted} />
          )}
        </TrendSection>

        {/* ③ フォーム & 身体 / Body & Form */}
        <TrendSection eyebrow="Body & Form" title="フォーム & 身体">
          {form == null ? (
            <CardSkeleton label="フォームスコア推移" />
          ) : (
            <FormBlock data={form} />
          )}
          {durability == null ? (
            <CardSkeleton label="耐久性" />
          ) : (
            <DurabilityBlock data={durability} />
          )}
          {bodyComposition == null ? (
            <CardSkeleton label="体組成" />
          ) : (
            <BodyCompositionChart data={bodyComposition} />
          )}
          {weightEconomy == null ? (
            <CardSkeleton label="体重 × ランニングエコノミー" />
          ) : (
            <WeightEconomyChart data={weightEconomy} />
          )}
        </TrendSection>
      </div>
    </div>
  );
}
