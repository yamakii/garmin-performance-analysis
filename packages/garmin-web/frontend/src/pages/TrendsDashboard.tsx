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
import VolumeBlock from "./trends/VolumeBlock";
import PhysiologyBlock from "./trends/PhysiologyBlock";
import FormBlock from "./trends/FormBlock";
import EfficiencyBlock from "./trends/EfficiencyBlock";

export default function TrendsDashboard() {
  const [granularity, setGranularity] = useState<Granularity>("week");
  const [volume, setVolume] = useState<VolumeTrendPoint[] | null>(null);
  const [physiology, setPhysiology] = useState<PhysiologyTrend | null>(null);
  const [form, setForm] = useState<FormTrendPoint[] | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyTrendPoint[] | null>(
    null,
  );
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
    Promise.all([fetchPhysiologyTrend(), fetchFormTrend(), fetchEfficiencyTrend()])
      .then(([physiologyData, formData, efficiencyData]) => {
        if (!cancelled) {
          setPhysiology(physiologyData);
          setForm(formData);
          setEfficiency(efficiencyData);
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
    return <p role="alert">エラー: {error}</p>;
  }

  const loading =
    volume == null || physiology == null || form == null || efficiency == null;
  if (loading) {
    return <p>読み込み中...</p>;
  }

  return (
    <div>
      <h1>トレンドダッシュボード</h1>
      <VolumeBlock
        data={volume}
        granularity={granularity}
        onGranularityChange={setGranularity}
      />
      <PhysiologyBlock data={physiology} />
      <FormBlock data={form} />
      <EfficiencyBlock data={efficiency} />
    </div>
  );
}
