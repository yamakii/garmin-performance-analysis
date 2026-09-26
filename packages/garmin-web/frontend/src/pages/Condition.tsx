import {
  useBodyCompositionTrend,
  useEnergyBalance,
  useFormAnomalyFlags,
  useRecoveryStatus,
  useRecoveryTrend,
  useTrainingLoad,
  useWellnessBaselineDeviation,
} from "../api/hooks";
import QueryBoundary, { type QueryLike } from "../components/QueryBoundary";
import SectionBlock from "../components/SectionBlock";
import VerdictLine from "../components/VerdictLine";
import VitalsRow, { type VitalItem } from "../components/VitalsRow";
import { usePageTitle } from "../hooks/usePageTitle";
import type {
  AcwrStatus,
  AcwrTrend,
  EnergyBalance,
  MetricBaseline,
  RecoveryStatus,
  RecoveryTrend,
  WellnessBaselineDeviation,
} from "../types";
import { baselineBand } from "../utils/baselineZ";
import { formatDate } from "../utils/format";
import { formatNumber } from "../utils/formatNumber";
import { conditionVerdict } from "../utils/verdict";
import BodyCompositionChart from "./trends/BodyCompositionChart";
import EnergyBalancePanel from "./trends/EnergyBalancePanel";
import { monthDay } from "./trends/energyBalanceLabels";
import FormAnomalyFlagsCard from "./trends/FormAnomalyFlagsCard";
import RecoveryPanel from "./trends/RecoveryPanel";
import TrainingLoadBlock from "./trends/TrainingLoadBlock";
import WellnessBaselineChart from "./trends/WellnessBaselineChart";

/** The three endpoints behind the vitals row, as one block's worth of data. */
interface VitalsData {
  load: AcwrTrend | null;
  recovery: RecoveryTrend | null;
  status: RecoveryStatus | null;
}

const ACWR_LABELS: Record<AcwrStatus, string> = {
  undertraining: "負荷不足",
  optimal: "最適",
  caution: "注意",
  high_risk: "高リスク",
  insufficient_data: "データ不足",
};

/** ACWR status → note tone; only 注意 and 高リスク get a colour. */
const ACWR_TONE: Partial<Record<AcwrStatus, "warn" | "bad">> = {
  caution: "warn",
  high_risk: "bad",
};

/** A number, or the em dash that stands in for a missing reading. */
function reading(value: number | null | undefined, digits = 0): string {
  return value != null ? formatNumber(value, digits) : "—";
}

/** "基準 44–48" / "基準外 44–48" — where the reading sits in its own band. */
function bandNote(
  metric: MetricBaseline | null,
  label: string,
  underRecovery: boolean,
): string {
  const band = baselineBand(metric);
  if (band == null) {
    return "基準データなし";
  }
  const outside = metric?.adverse === true || underRecovery;
  return `${outside ? "基準外" : label} ${band}`;
}

/** "MM/DD – MM/DD" of the energy-balance window, once the data has landed. */
function energyWindowNote(data: EnergyBalance | undefined): string | undefined {
  const days = data?.days.filter((day) => day.in_window) ?? [];
  if (days.length === 0) {
    return undefined;
  }
  return `${monthDay(days[0].date)} – ${monthDay(days[days.length - 1].date)}`;
}

/** The four readings the morning turns on, in the order the verdict used them. */
function vitalsItems(
  { load, recovery, status }: VitalsData,
  baseline: WellnessBaselineDeviation | null,
): VitalItem[] {
  const hrv = recovery?.hrv ?? null;
  const rhr = recovery?.rhr ?? null;
  const acwr = load?.current ?? null;
  const weeks = load?.trend.weeks ?? [];
  const lastWeek = weeks[weeks.length - 1] ?? null;
  const hrvBaseline = baseline?.hrv ?? null;
  const rhrBaseline = baseline?.rhr ?? null;

  return [
    {
      // The band, not the z score: the deviation has its own section below,
      // and restating it here would answer the same question twice (#894).
      label: "HRV 夜間",
      value: reading(hrv?.latest_ms),
      unit: "ms",
      note: bandNote(hrvBaseline, "基準", hrv?.under_recovery === true),
      noteTone:
        hrvBaseline?.adverse === true || hrv?.under_recovery === true
          ? "warn"
          : "muted",
    },
    {
      label: "安静時心拍",
      value: reading(rhr?.median_7d),
      unit: "bpm",
      note: bandNote(rhrBaseline, "基準", false),
      noteTone: rhrBaseline?.adverse === true ? "warn" : "muted",
    },
    {
      label: "睡眠 / 準備度 / BB",
      value: (
        <>
          {reading(status?.sleep_score)}
          <span className="mx-1.5 text-[13px] text-ink-muted">/</span>
          {reading(status?.training_readiness)}
          <span className="mx-1.5 text-[13px] text-ink-muted">/</span>
          {reading(status?.body_battery_high)}
        </>
      ),
      note: "睡眠スコア / 準備度 / Body Battery",
    },
    {
      label: "負荷 ACWR",
      value:
        acwr?.acwr != null && acwr.status !== "insufficient_data"
          ? formatNumber(acwr.acwr, 2)
          : "—",
      note:
        acwr != null
          ? `${ACWR_LABELS[acwr.status]}${
              lastWeek != null
                ? ` · 週 ${formatNumber(lastWeek.load_km, 1)}km`
                : ""
            }`
          : "週間負荷 —",
      noteTone: acwr != null ? (ACWR_TONE[acwr.status] ?? "muted") : "muted",
    },
  ];
}

/**
 * "今の体の状態は?" — the morning's recovery read, as a brief.
 *
 * The page opens with the verdict (how recovered the body is, what is out of
 * band, how many cautions the recent runs raised), states the four numbers
 * behind it once, and then spends one section on each supporting reading:
 * this week's cautions, the recovery trend, the distance from the personal
 * baseline, the training load, the logged energy balance (#1439) and body
 * composition (#1120).
 *
 * The `form-anomaly` / `recovery` / `training-load` anchors are the home vitals
 * row's deep-link targets and the `/trends` redirect's, so they sit on the
 * sections themselves and exist from first paint — a jump must land even while
 * the data is still loading.
 *
 * Every section owns its query behind a `QueryBoundary`: a pending query is a
 * skeleton and a failed one a retryable in-card alert, so a single broken
 * endpoint no longer blanks the page behind an all-or-nothing banner.
 */
export default function Condition() {
  usePageTitle("コンディション");
  const formAnomalyFlagsQuery = useFormAnomalyFlags();
  const recoveryStatusQuery = useRecoveryStatus();
  const recoveryQuery = useRecoveryTrend();
  const wellnessBaselineQuery = useWellnessBaselineDeviation();
  const trainingLoadQuery = useTrainingLoad();
  const bodyCompositionQuery = useBodyCompositionTrend();
  const energyBalanceQuery = useEnergyBalance();

  // Supplementary readings: they qualify the verdict and the recovery band but
  // must not fail either, so they are read off the query rather than awaited.
  const baseline = wellnessBaselineQuery.data ?? null;
  const flags = formAnomalyFlagsQuery.data ?? null;

  // The vitals row reads as one block, so it gets one boundary. Each of its
  // three endpoints also owns a section below, which reports its own failure —
  // so the row only fails when *every* reading is gone, and otherwise renders
  // what landed with an em dash in place of what did not. Restating one dead
  // endpoint as two alerts would make a single outage look like two.
  const vitalsErrors = [
    trainingLoadQuery.error,
    recoveryQuery.error,
    recoveryStatusQuery.error,
  ];
  const vitalsQuery: QueryLike<VitalsData> = {
    data:
      trainingLoadQuery.data === undefined &&
      recoveryQuery.data === undefined &&
      recoveryStatusQuery.data === undefined
        ? undefined
        : {
            load: trainingLoadQuery.data ?? null,
            recovery: recoveryQuery.data ?? null,
            status: recoveryStatusQuery.data ?? null,
          },
    error: vitalsErrors.every((error) => error != null)
      ? vitalsErrors[0]
      : null,
    refetch: () => {
      trainingLoadQuery.refetch();
      recoveryQuery.refetch();
      recoveryStatusQuery.refetch();
    },
  };

  const flagsNote =
    flags != null
      ? `直近${flags.weeks}週 · ${flags.scanned}本を走査${
          flags.limited ? "（上限により一部）" : ""
        }`
      : undefined;

  return (
    <div className="flex flex-col gap-12">
      {/* ① 判定: 体はどこまで回復しているか */}
      <QueryBoundary label="回復判定" query={recoveryStatusQuery}>
        {(status) => {
          const verdict = conditionVerdict(status, baseline, flags);
          return (
            <VerdictLine
              verdict={verdict.verdict}
              verdictTone={verdict.tone}
              rest={verdict.rest}
              lead={status.reasons[0] ?? null}
            />
          );
        }}
      </QueryBoundary>

      {/* ② 今朝の数値: 判定を支える4つの読み */}
      <QueryBoundary label="今朝の数値" query={vitalsQuery}>
        {(vitals) => (
          <VitalsRow
            id="today"
            ariaLabel="今朝の数値"
            items={vitalsItems(vitals, baseline)}
          />
        )}
      </QueryBoundary>

      {/* ③ 今週の注意点: 直近のランが上げたフォーム異常 */}
      <SectionBlock id="form-anomaly" title="今週の注意点" note={flagsNote} noteMono>
        <QueryBoundary label="今週の注意点" query={formAnomalyFlagsQuery}>
          {(data) => <FormAnomalyFlagsCard data={data} />}
        </QueryBoundary>
      </SectionBlock>

      {/* ④ 回復トレンド: RHR と HRV を基準帯に重ねて */}
      <SectionBlock
        id="recovery"
        title="回復トレンド"
        note="低いRHRと高いHRVが回復の向き"
      >
        <QueryBoundary label="回復トレンド" query={recoveryQuery}>
          {(data) => <RecoveryPanel data={data} baseline={baseline} />}
        </QueryBoundary>
      </SectionBlock>

      {/* ⑤ 個人基準との差: z スコアで正規化した逸脱 */}
      <SectionBlock
        title="個人基準との差"
        note={baseline?.date != null ? formatDate(baseline.date) : undefined}
        noteMono
      >
        <QueryBoundary label="個人ベースライン逸脱" query={wellnessBaselineQuery}>
          {(data) => <WellnessBaselineChart data={data} />}
        </QueryBoundary>
      </SectionBlock>

      {/* ⑥ 訓練負荷: 急性 / 慢性の比 */}
      <SectionBlock id="training-load" title="訓練負荷" note="急性7日 / 慢性28日">
        <QueryBoundary label="訓練負荷" query={trainingLoadQuery}>
          {(data) => <TrainingLoadBlock data={data} />}
        </QueryBoundary>
      </SectionBlock>

      {/* ⑦ エネルギー収支: 記録された摂取と消費の差を減量方針の目標帯と比べて */}
      <SectionBlock
        id="energy-balance"
        title="エネルギー収支"
        note={energyWindowNote(energyBalanceQuery.data)}
        noteMono
      >
        <QueryBoundary label="エネルギー収支" query={energyBalanceQuery}>
          {(data) => <EnergyBalancePanel data={data} />}
        </QueryBoundary>
      </SectionBlock>

      {/* ⑧ 体組成: 体重の内訳 */}
      <SectionBlock
        title="体組成"
        note={
          bodyCompositionQuery.data != null
            ? `直近${bodyCompositionQuery.data.weeks}週`
            : undefined
        }
        noteMono
      >
        <QueryBoundary label="体組成" query={bodyCompositionQuery}>
          {(data) => <BodyCompositionChart data={data} />}
        </QueryBoundary>
      </SectionBlock>
    </div>
  );
}
