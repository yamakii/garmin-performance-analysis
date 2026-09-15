import type { StatusTone } from "../../components/StatusBadge";
import { RECOMMENDATION_LABELS } from "../../labels/recovery";
import { formatDate } from "../../utils/format";
import { formatNumber } from "../../utils/formatNumber";
import type {
  MetricBaseline,
  RecoveryRecommendation,
  RecoveryStatus,
  WellnessBaselineDeviation,
} from "../../types";

export interface VerdictMeta {
  /** Big verdict word shown in the hero. */
  label: string;
  /** One-line coaching gloss under the verdict. */
  gloss: string;
  tone: StatusTone | "neutral";
}

/** Coaching gloss + tone per recommendation; the word itself is shared. */
const VERDICT_DETAIL: Record<
  RecoveryRecommendation,
  { gloss: string; tone: VerdictMeta["tone"] }
> = {
  quality: { gloss: "回復良好。質の高い練習が可能です", tone: "good" },
  moderate: { gloss: "中程度の練習まで問題ありません", tone: "info" },
  easy: { gloss: "今日は強度を抑えて回復を優先", tone: "warn" },
  rest: { gloss: "走らない勇気を。回復が最優先です", tone: "bad" },
  unknown: { gloss: "感覚を優先して判断してください", tone: "neutral" },
};

/**
 * Map the reader's morning recommendation to the hero verdict. Exported so the
 * mapping is unit-testable without rendering. The verdict word comes from the
 * shared label map so the condition page says the same thing (#915).
 */
export function verdictMeta(rec: RecoveryRecommendation): VerdictMeta {
  const detail = VERDICT_DETAIL[rec] ?? VERDICT_DETAIL.unknown;
  return {
    label: RECOMMENDATION_LABELS[rec] ?? RECOMMENDATION_LABELS.unknown,
    ...detail,
  };
}

/** Verdict-word text color per tone (status tokens; neutral = slate). */
const TONE_TEXT: Record<VerdictMeta["tone"], string> = {
  today: "text-accent",
  good: "text-status-good",
  info: "text-accent",
  warn: "text-status-warn",
  bad: "text-status-bad",
  neutral: "text-ink-muted",
};

/** Left accent-bar color per tone. */
const TONE_BAR: Record<VerdictMeta["tone"], string> = {
  today: "bg-accent",
  good: "bg-status-good",
  info: "bg-accent",
  warn: "bg-status-warn",
  bad: "bg-status-bad",
  neutral: "bg-well",
};

interface TodayHeroProps {
  status: RecoveryStatus;
  baseline: WellnessBaselineDeviation | null;
}

/**
 * Dashboard hero: today's go/no-go verdict from the morning recovery status,
 * with the leading rationale and wellness chips (readiness / sleep / HRV /
 * RHR). Baseline-adverse metrics are flagged on their chip so "why" is visible
 * without leaving the home page.
 */
export default function TodayHero({ status, baseline }: TodayHeroProps) {
  const meta = verdictMeta(status.recommendation);
  const rationale = status.reasons[0] ?? null;
  const date = status.date ?? baseline?.date ?? null;

  return (
    <header
      aria-label="今日の判定"
      className="relative overflow-hidden rounded-md border border-hairline"
    >
      <span
        aria-hidden="true"
        className={`absolute inset-y-0 left-0 w-1.5 ${TONE_BAR[meta.tone]}`}
      />
      <div className="relative px-6 py-6 md:px-8">
        {/*
         * Muted copy on this band is slate-600, not the slate-500 used on the
         * white cards: the hero runs the old hero gradient,
         * where slate-500 drops to 4.35:1 (Issue #911).
         */}
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          {/* Decorative eyebrow: the verdict heading below says the same (#912). */}
          <p
            aria-hidden="true"
            className="text-xs font-semibold font-mono text-ink-muted"
          >
            Today&apos;s Verdict
          </p>
          {date != null && (
            <p className="font-mono text-sm text-ink-muted">
              {formatDate(date)}
            </p>
          )}
        </div>

        {/*
         * The verdict word is the hero's heading, not a stray paragraph (#912):
         * it is the one thing this card exists to say, so it belongs in the
         * page outline under the Home h1. Styling is unchanged.
         */}
        <h2
          className={`mt-2 text-4xl leading-tight font-bold tracking-tight md:text-5xl ${TONE_TEXT[meta.tone]}`}
        >
          {meta.label}
        </h2>
        <p className="mt-1 text-sm font-medium text-ink-muted">
          {rationale ?? meta.gloss}
        </p>

        {baseline?.overall_flag === true && (
          <p
            role="alert"
            className="mt-3 inline-block rounded-md border border-warn-line bg-warn-tint px-3 py-1.5 text-xs font-medium text-status-warn"
          >
            個人ベースラインから不利な方向に逸脱中 — 強度より回復を優先
          </p>
        )}

        <dl className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <ChipStat label="準備度" value={fmtInt(status.training_readiness)} />
          <ChipStat label="睡眠スコア" value={fmtInt(status.sleep_score)} />
          <ChipStat
            label="HRV (夜間)"
            value={fmtMetric(baseline?.hrv ?? null, "ms")}
            adverse={baseline?.hrv.adverse === true}
          />
          <ChipStat
            label="安静時心拍"
            value={fmtMetric(baseline?.rhr ?? null, "bpm")}
            adverse={baseline?.rhr.adverse === true}
          />
        </dl>
      </div>
    </header>
  );
}

function fmtInt(value: number | null): string {
  return value != null ? String(Math.round(value)) : "—";
}

function fmtMetric(baseline: MetricBaseline | null, unit: string): string {
  if (baseline?.today == null) {
    return "—";
  }
  return `${formatNumber(baseline.today, 0)}${unit}`;
}

function ChipStat({
  label,
  value,
  adverse = false,
}: {
  label: string;
  value: string;
  adverse?: boolean;
}) {
  return (
    <div
      className={`rounded-md border px-3 py-2 ${
 adverse ? "border-warn-line bg-warn-tint" : "border-hairline"
 }`}
    >
      <dt className="flex items-center gap-1 text-xs text-ink-muted">
        {label}
        {adverse && (
          <span className="rounded-sm bg-warn-tint px-1.5 text-[10px] font-semibold text-status-warn">
            基準外
          </span>
        )}
      </dt>
      <dd className="mt-0.5 font-mono text-lg font-semibold text-ink">
        {value}
      </dd>
    </div>
  );
}
