import type { RecoveryRecommendation, RecoveryStatus } from "../../types";
import { CARD_CLASS } from "../../components/Card";
import { RECOMMENDATION_LABELS } from "../../labels/recovery";

interface ConditionCardProps {
  data: RecoveryStatus;
}

/**
 * Badge color family per recommendation. The wording comes from the shared
 * label map so the home hero and this card name the same verdict alike (#915).
 */
const RECOMMENDATION_CLASS: Record<RecoveryRecommendation, string> = {
  quality: " text-status-good",
  moderate: " text-ink-soft",
  easy: "bg-warn-tint text-status-warn",
  rest: "bg-bad-tint text-status-bad",
  unknown: "bg-well text-ink-muted",
};

export default function ConditionCard({ data }: ConditionCardProps) {
  const meta = {
    label:
      RECOMMENDATION_LABELS[data.recommendation] ??
      RECOMMENDATION_LABELS.unknown,
    className:
      RECOMMENDATION_CLASS[data.recommendation] ?? RECOMMENDATION_CLASS.unknown,
  };
  const isUnknown = data.recommendation === "unknown";
  // The reader always ships a reasons[]; show the leading rationale line.
  const rationale = data.reasons[0] ?? "データ無し・感覚優先";

  return (
    <section
      aria-label="当日コンディション"
      className={CARD_CLASS}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">
          当日コンディション
        </h2>
        <span
          className={`shrink-0 rounded-sm px-2.5 py-1 text-xs font-semibold ${meta.className}`}
        >
          {meta.label}
        </span>
      </div>
      {isUnknown ? (
        <p className="py-4 text-sm text-ink-muted">
          データ無し・感覚優先で判断してください
        </p>
      ) : (
        <>
          <p className="mb-2 text-sm text-ink-muted">{rationale}</p>
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
    <div className="rounded-md bg-well px-2 py-2">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="font-semibold text-ink">{value ?? "—"}</dd>
    </div>
  );
}
