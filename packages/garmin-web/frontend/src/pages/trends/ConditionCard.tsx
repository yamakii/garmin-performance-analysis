import type { RecoveryRecommendation, RecoveryStatus } from "../../types";

interface ConditionCardProps {
  data: RecoveryStatus;
}

/** Recommended-intensity badge metadata (label + color family). */
const RECOMMENDATION_META: Record<
  RecoveryRecommendation,
  { label: string; className: string }
> = {
  quality: { label: "質練OK", className: "bg-emerald-100 text-emerald-700" },
  moderate: { label: "中程度", className: "bg-sky-100 text-sky-700" },
  easy: { label: "イージー", className: "bg-amber-100 text-amber-700" },
  rest: { label: "休養", className: "bg-red-100 text-red-700" },
  unknown: { label: "データ無し", className: "bg-slate-100 text-slate-600" },
};

export default function ConditionCard({ data }: ConditionCardProps) {
  const meta = RECOMMENDATION_META[data.recommendation] ?? RECOMMENDATION_META.unknown;
  const isUnknown = data.recommendation === "unknown";
  // The reader always ships a reasons[]; show the leading rationale line.
  const rationale = data.reasons[0] ?? "データ無し・感覚優先";

  return (
    <section
      aria-label="当日コンディション"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          当日コンディション
        </h2>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${meta.className}`}
        >
          {meta.label}
        </span>
      </div>
      {isUnknown ? (
        <p className="py-4 text-sm text-slate-500">
          データ無し・感覚優先で判断してください
        </p>
      ) : (
        <>
          <p className="mb-2 text-sm text-slate-600">{rationale}</p>
          <dl className="grid grid-cols-3 gap-2 text-center">
            <Stat label="準備度" value={data.training_readiness} />
            <Stat label="睡眠スコア" value={data.sleep_score} />
            <Stat label="Body Battery" value={data.body_battery_high} />
          </dl>
        </>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-lg bg-slate-50 px-2 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-semibold text-ink">{value ?? "—"}</dd>
    </div>
  );
}
