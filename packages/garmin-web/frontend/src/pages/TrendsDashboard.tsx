import { useEffect, useState, type ReactNode } from "react";
import {
  fetchCriticalSpeed,
  fetchEfficiencyTrend,
  fetchFormTrend,
  fetchHeatAdjustedTrend,
  fetchObjectiveFitnessTrend,
  fetchPhysiologyTrend,
  fetchVolumeTrend,
} from "../api/trends";
import type {
  CriticalSpeedPoint,
  EfficiencyTrendPoint,
  FormTrendPoint,
  Granularity,
  HeatAdjustedTrend,
  ObjectiveFitnessTrend,
  PhysiologyTrend,
  VolumeTrendPoint,
} from "../api/trends";
import { fetchTrainingLoad } from "../api/training_load";
import { fetchDurabilityTrend } from "../api/durability";
import {
  fetchBodyCompositionTrend,
  fetchFormAnomalyFlags,
  fetchRecoveryStatus,
  fetchRecoveryTrend,
  fetchWeightEconomyCoupling,
  fetchWellnessBaselineDeviation,
} from "../api/recovery";
import type {
  AcwrTrend,
  BodyCompositionTrend,
  DurabilityTrend,
  FormAnomalyFlagsResponse,
  RecoveryStatus,
  RecoveryTrend,
  WeightEconomyCoupling,
  WellnessBaselineDeviation,
} from "../types";
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
  const [volume, setVolume] = useState<VolumeTrendPoint[] | null>(null);
  const [physiology, setPhysiology] = useState<PhysiologyTrend | null>(null);
  const [form, setForm] = useState<FormTrendPoint[] | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyTrendPoint[] | null>(
    null,
  );
  const [heatAdjusted, setHeatAdjusted] = useState<HeatAdjustedTrend | null>(
    null,
  );
  const [trainingLoad, setTrainingLoad] = useState<AcwrTrend | null>(null);
  const [durability, setDurability] = useState<DurabilityTrend | null>(null);
  const [recovery, setRecovery] = useState<RecoveryTrend | null>(null);
  const [recoveryStatus, setRecoveryStatus] = useState<RecoveryStatus | null>(
    null,
  );
  const [bodyComposition, setBodyComposition] =
    useState<BodyCompositionTrend | null>(null);
  const [weightEconomy, setWeightEconomy] =
    useState<WeightEconomyCoupling | null>(null);
  const [wellnessBaseline, setWellnessBaseline] =
    useState<WellnessBaselineDeviation | null>(null);
  const [criticalSpeed, setCriticalSpeed] = useState<
    CriticalSpeedPoint[] | null
  >(null);
  const [objectiveFitness, setObjectiveFitness] =
    useState<ObjectiveFitnessTrend | null>(null);
  const [formAnomalyFlags, setFormAnomalyFlags] =
    useState<FormAnomalyFlagsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchVolumeTrend(granularity)
      .then((data) => {
        if (!cancelled) setVolume(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [granularity]);

  useEffect(() => {
    let cancelled = false;
    // Wire each fetch independently (no Promise.all) so a slow endpoint never
    // holds the whole dashboard hostage: every card resolves on its own and
    // swaps its skeleton for content as soon as its data lands.
    const wire = <T,>(promise: Promise<T>, set: (value: T) => void): void => {
      promise
        .then((value) => {
          if (!cancelled) set(value);
        })
        .catch((err: unknown) => {
          if (!cancelled)
            setError(err instanceof Error ? err.message : String(err));
        });
    };
    wire(fetchPhysiologyTrend(), setPhysiology);
    wire(fetchFormTrend(), setForm);
    wire(fetchEfficiencyTrend(), setEfficiency);
    wire(fetchTrainingLoad(), setTrainingLoad);
    wire(fetchDurabilityTrend(), setDurability);
    wire(fetchRecoveryTrend(), setRecovery);
    wire(fetchRecoveryStatus(), setRecoveryStatus);
    wire(fetchBodyCompositionTrend(), setBodyComposition);
    wire(fetchHeatAdjustedTrend(HEAT_ADJUSTED_LOOKBACK_DAYS), setHeatAdjusted);
    wire(fetchCriticalSpeed(), setCriticalSpeed);
    wire(fetchObjectiveFitnessTrend(), setObjectiveFitness);
    wire(fetchWeightEconomyCoupling(), setWeightEconomy);
    wire(fetchWellnessBaselineDeviation(), setWellnessBaseline);
    wire(fetchFormAnomalyFlags(), setFormAnomalyFlags);
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <p
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        エラー: {error}
      </p>
    );
  }

  // Each card renders a per-card skeleton until its own data resolves, so the
  // slowest endpoint no longer holds the entire page behind one spinner.
  return (
    <div className="space-y-8">
      <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
        トレンドダッシュボード
      </h1>

      {/*
        Alert band: "今, 何を見るべきか" surfaced first, full width and outside
        the metric grid so the weekly caution is the top priority.
      */}
      {formAnomalyFlags == null ? (
        <CardSkeleton label="今週の注意点" />
      ) : (
        <FormAnomalyFlagsCard data={formAnomalyFlags} />
      )}

      <div className="stagger-in space-y-10">
        {/* ① 今の状態 / Condition Now */}
        <TrendSection eyebrow="Condition Now" title="今の状態">
          {recoveryStatus == null ? (
            <CardSkeleton label="当日コンディション" />
          ) : (
            <ConditionCard data={recoveryStatus} />
          )}
          {recovery == null ? (
            <CardSkeleton label="回復トレンド" />
          ) : (
            <RecoveryPanel data={recovery} />
          )}
          {wellnessBaseline == null ? (
            <CardSkeleton label="個人ベースライン逸脱" />
          ) : (
            <WellnessBaselineChart data={wellnessBaseline} />
          )}
          {trainingLoad == null ? (
            <CardSkeleton label="訓練負荷" />
          ) : (
            <TrainingLoadBlock data={trainingLoad} />
          )}
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
