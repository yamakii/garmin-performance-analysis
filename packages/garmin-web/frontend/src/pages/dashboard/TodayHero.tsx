import type { StatusTone } from "../../components/StatusBadge";
import { formatNumber } from "../../utils/formatNumber";
import type {
  MetricBaseline,
  RecoveryRecommendation,
  RecoveryStatus,
  WellnessBaselineDeviation,
} from "../../types";

/**
 * Faint topographic-contour texture (inline SVG data URI), matching the
 * HeroHeader / Goal countdown hero background.
 */
const CONTOUR_PATTERN = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='280' height='280' viewBox='0 0 280 280' fill='none' stroke='%2316213a' stroke-width='1'%3E%3Cpath d='M0 40c46-22 94 16 140-6s94-26 140-2'/%3E%3Cpath d='M0 90c46-24 94 18 140-8s94-28 140-2'/%3E%3Cpath d='M0 140c46-20 94 14 140-6s94-24 140-2'/%3E%3Cpath d='M0 190c46-26 94 20 140-8s94-30 140-2'/%3E%3Cpath d='M0 240c46-22 94 16 140-6s94-26 140-2'/%3E%3Cellipse cx='70' cy='66' rx='34' ry='13'/%3E%3Cellipse cx='70' cy='66' rx='20' ry='7'/%3E%3Cellipse cx='204' cy='214' rx='38' ry='15'/%3E%3Cellipse cx='204' cy='214' rx='22' ry='8'/%3E%3C/svg%3E")`;

export interface VerdictMeta {
  /** Big verdict word shown in the hero. */
  label: string;
  /** One-line coaching gloss under the verdict. */
  gloss: string;
  tone: StatusTone | "neutral";
}

/**
 * Map the reader's morning recommendation to the hero verdict. Exported so the
 * mapping is unit-testable without rendering.
 */
export function verdictMeta(rec: RecoveryRecommendation): VerdictMeta {
  switch (rec) {
    case "quality":
      return { label: "質練OK", gloss: "回復良好。質の高い練習が可能です", tone: "good" };
    case "moderate":
      return { label: "通常ラン OK", gloss: "中程度の練習まで問題ありません", tone: "info" };
    case "easy":
      return { label: "イージー推奨", gloss: "今日は強度を抑えて回復を優先", tone: "warn" };
    case "rest":
      return { label: "休養推奨", gloss: "走らない勇気を。回復が最優先です", tone: "bad" };
    default:
      return { label: "データなし", gloss: "感覚を優先して判断してください", tone: "neutral" };
  }
}

/** Verdict-word text color per tone (status tokens; neutral = slate). */
const TONE_TEXT: Record<VerdictMeta["tone"], string> = {
  good: "text-status-good",
  info: "text-status-info",
  warn: "text-status-warn",
  bad: "text-status-bad",
  neutral: "text-slate-400",
};

/** Left accent-bar color per tone. */
const TONE_BAR: Record<VerdictMeta["tone"], string> = {
  good: "bg-status-good",
  info: "bg-status-info",
  warn: "bg-status-warn",
  bad: "bg-status-bad",
  neutral: "bg-slate-300",
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
      className="relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100 shadow-sm"
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.04]"
        style={{ backgroundImage: CONTOUR_PATTERN }}
      />
      <span
        aria-hidden="true"
        className={`absolute inset-y-0 left-0 w-1.5 ${TONE_BAR[meta.tone]}`}
      />
      <div className="relative px-6 py-6 md:px-8">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p className="text-xs font-semibold tracking-[0.2em] text-slate-400 uppercase">
            Today&apos;s Verdict
          </p>
          {date != null && (
            <p className="font-numeric text-sm tabular-nums text-slate-500">
              {date}
            </p>
          )}
        </div>

        <p
          className={`mt-2 font-display text-4xl leading-tight font-bold tracking-tight md:text-5xl ${TONE_TEXT[meta.tone]}`}
        >
          {meta.label}
        </p>
        <p className="mt-1 text-sm font-medium text-slate-600">
          {rationale ?? meta.gloss}
        </p>

        {baseline?.overall_flag === true && (
          <p
            role="alert"
            className="mt-3 inline-block rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700"
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
      className={`rounded-lg border px-3 py-2 ${
        adverse ? "border-amber-200 bg-amber-50" : "border-slate-100 bg-white/70"
      }`}
    >
      <dt className="flex items-center gap-1 text-xs text-slate-500">
        {label}
        {adverse && (
          <span className="rounded-full bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-700">
            基準外
          </span>
        )}
      </dt>
      <dd className="mt-0.5 font-numeric text-lg font-semibold tabular-nums text-ink">
        {value}
      </dd>
    </div>
  );
}
