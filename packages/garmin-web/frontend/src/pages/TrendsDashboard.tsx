import { useEffect, useState } from "react";
import {
  fetchEfficiencyTrend,
  fetchFormTrend,
  fetchPhysiologyTrend,
  fetchVolumeTrend,
} from "../api/trends";
import type {
  EfficiencyTrendPoint,
  FormTrendPoint,
  Granularity,
  PhysiologyTrend,
  VolumeTrendPoint,
} from "../api/trends";
import { fetchTrainingLoad } from "../api/training_load";
import type { AcwrTrend } from "../types";
import VolumeBlock from "./trends/VolumeBlock";
import PhysiologyBlock from "./trends/PhysiologyBlock";
import FormBlock from "./trends/FormBlock";
import EfficiencyBlock from "./trends/EfficiencyBlock";
import TrainingLoadBlock from "./trends/TrainingLoadBlock";

export default function TrendsDashboard() {
  const [granularity, setGranularity] = useState<Granularity>("week");
  const [volume, setVolume] = useState<VolumeTrendPoint[] | null>(null);
  const [physiology, setPhysiology] = useState<PhysiologyTrend | null>(null);
  const [form, setForm] = useState<FormTrendPoint[] | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyTrendPoint[] | null>(
    null,
  );
  const [trainingLoad, setTrainingLoad] = useState<AcwrTrend | null>(null);
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
    ])
      .then(([physiologyData, formData, efficiencyData, trainingLoadData]) => {
        if (!cancelled) {
          setPhysiology(physiologyData);
          setForm(formData);
          setEfficiency(efficiencyData);
          setTrainingLoad(trainingLoadData);
        }
      })
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
    trainingLoad == null;
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
        <VolumeBlock
          data={volume}
          granularity={granularity}
          onGranularityChange={setGranularity}
        />
        <PhysiologyBlock data={physiology} />
        <FormBlock data={form} />
        <EfficiencyBlock data={efficiency} />
        <TrainingLoadBlock data={trainingLoad} />
      </div>
    </div>
  );
}
