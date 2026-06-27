import { formatNumber } from "../../utils/formatNumber";
import type { MetricBaseline, WellnessBaselineDeviation } from "../../types";

interface WellnessBaselineChartProps {
  data: WellnessBaselineDeviation;
}

/** Display label + unit for each personal-baseline metric. */
const METRIC_META: Record<
  MetricBaseline["metric"],
  { label: string; unit: string }
> = {
  hrv: { label: "HRV (夜間)", unit: "ms" },
  readiness: { label: "Training Readiness", unit: "" },
  rhr: { label: "安静時心拍", unit: "bpm" },
};

/** Flag badge metadata: label + color family. */
const FLAG_META: Record<
  MetricBaseline["flag"],
  { label: string; className: string }
> = {
  low: { label: "低い", className: "bg-amber-100 text-amber-700" },
  high: { label: "高い", className: "bg-amber-100 text-amber-700" },
  within: { label: "範囲内", className: "bg-emerald-100 text-emerald-700" },
  insufficient: { label: "データ不足", className: "bg-slate-100 text-slate-600" },
};

const METRIC_ORDER: MetricBaseline["metric"][] = ["hrv", "readiness", "rhr"];

export default function WellnessBaselineChart({
  data,
}: WellnessBaselineChartProps) {
  return (
    <section
      aria-label="ウェルネス個人ベースライン逸脱"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm md:col-span-2"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          個人ベースライン逸脱 (HRV / Readiness / RHR)
        </h2>
        {data.date != null && (
          <span className="shrink-0 text-xs text-slate-500">{data.date}</span>
        )}
      </div>
      {data.overall_flag && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700"
        >
          個人ベースラインから不利な方向に逸脱しています。強度・回復を見直してください。
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        {METRIC_ORDER.map((metric) => (
          <MetricCard key={metric} baseline={data[metric]} />
        ))}
      </div>
    </section>
  );
}

function MetricCard({ baseline }: { baseline: MetricBaseline }) {
  const meta = METRIC_META[baseline.metric];
  const flagMeta = FLAG_META[baseline.flag] ?? FLAG_META.insufficient;
  const insufficient = baseline.flag === "insufficient";

  const bandText =
    baseline.mean != null && baseline.std != null
      ? `${formatNumber(baseline.mean, 1)} ± ${formatNumber(baseline.std, 1)}${meta.unit}`
      : "—";
  const todayText =
    baseline.today != null
      ? `${formatNumber(baseline.today, 1)}${meta.unit}`
      : "—";
  const zText = baseline.z != null ? `z ${formatNumber(baseline.z, 2)}` : "—";

  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{meta.label}</span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
            baseline.adverse ? "bg-red-100 text-red-700" : flagMeta.className
          }`}
        >
          {flagMeta.label}
        </span>
      </div>
      {insufficient ? (
        <p className="text-xs text-slate-500">
          ベースライン構築に必要なデータが不足しています
        </p>
      ) : (
        <dl className="space-y-1 text-sm">
          <div className="flex items-center justify-between">
            <dt className="text-xs text-slate-500">今日</dt>
            <dd className="font-semibold text-ink">{todayText}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-xs text-slate-500">基準帯 (平均±SD)</dt>
            <dd className="text-slate-600">{bandText}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-xs text-slate-500">逸脱</dt>
            <dd className="text-slate-600">{zText}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}
