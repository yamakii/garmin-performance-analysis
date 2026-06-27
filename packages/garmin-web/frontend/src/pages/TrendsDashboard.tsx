import { useEffect, useState } from "react";
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

/** Trailing window (days) for the climate-neutral HR trend (one year). */
const HEAT_ADJUSTED_LOOKBACK_DAYS = 365;

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
    Promise.all([
      fetchPhysiologyTrend(),
      fetchFormTrend(),
      fetchEfficiencyTrend(),
      fetchTrainingLoad(),
      fetchDurabilityTrend(),
      fetchRecoveryTrend(),
      fetchRecoveryStatus(),
      fetchBodyCompositionTrend(),
      fetchHeatAdjustedTrend(HEAT_ADJUSTED_LOOKBACK_DAYS),
      fetchCriticalSpeed(),
      fetchObjectiveFitnessTrend(),
      fetchWeightEconomyCoupling(),
      fetchWellnessBaselineDeviation(),
      fetchFormAnomalyFlags(),
    ])
      .then(
        ([
          physiologyData,
          formData,
          efficiencyData,
          trainingLoadData,
          durabilityData,
          recoveryData,
          recoveryStatusData,
          bodyCompositionData,
          heatAdjustedData,
          criticalSpeedData,
          objectiveFitnessData,
          weightEconomyData,
          wellnessBaselineData,
          formAnomalyFlagsData,
        ]) => {
          if (!cancelled) {
            setPhysiology(physiologyData);
            setForm(formData);
            setEfficiency(efficiencyData);
            setTrainingLoad(trainingLoadData);
            setDurability(durabilityData);
            setRecovery(recoveryData);
            setRecoveryStatus(recoveryStatusData);
            setBodyComposition(bodyCompositionData);
            setHeatAdjusted(heatAdjustedData);
            setCriticalSpeed(criticalSpeedData);
            setObjectiveFitness(objectiveFitnessData);
            setWeightEconomy(weightEconomyData);
            setWellnessBaseline(wellnessBaselineData);
            setFormAnomalyFlags(formAnomalyFlagsData);
          }
        },
      )
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
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

  const loading =
    volume == null ||
    physiology == null ||
    form == null ||
    efficiency == null ||
    trainingLoad == null ||
    durability == null ||
    recovery == null ||
    recoveryStatus == null ||
    bodyComposition == null ||
    heatAdjusted == null ||
    criticalSpeed == null ||
    objectiveFitness == null ||
    weightEconomy == null ||
    wellnessBaseline == null ||
    formAnomalyFlags == null;
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <span
          aria-hidden="true"
          className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-ink"
        />
        読み込み中...
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-6 font-display text-2xl font-bold tracking-tight text-ink">
        トレンドダッシュボード
      </h1>
      <div className="stagger-in grid gap-4 md:grid-cols-2">
        <FormAnomalyFlagsCard data={formAnomalyFlags} />
        <VolumeBlock
          data={volume}
          granularity={granularity}
          onGranularityChange={setGranularity}
        />
        <PhysiologyBlock data={physiology} />
        <ObjectiveFitnessBlock data={objectiveFitness} />
        <FormBlock data={form} />
        <EfficiencyBlock data={efficiency} />
        <HeatAdjustedBlock data={heatAdjusted} />
        <CriticalSpeedPanel data={criticalSpeed} />
        <TrainingLoadBlock data={trainingLoad} />
        <DurabilityBlock data={durability} />
        <RecoveryPanel data={recovery} />
        <ConditionCard data={recoveryStatus} />
        <BodyCompositionChart data={bodyComposition} />
        <WeightEconomyChart data={weightEconomy} />
        <WellnessBaselineChart data={wellnessBaseline} />
      </div>
    </div>
  );
}
