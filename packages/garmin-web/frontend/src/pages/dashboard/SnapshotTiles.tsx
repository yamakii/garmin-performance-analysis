import { Link } from "react-router-dom";
import StatusBadge, { type StatusTone } from "../../components/StatusBadge";
import { INK_COLOR, METRIC_COLORS } from "../../components/chartTheme";
import { HRV_STATUS_LABELS, RHR_TREND_LABELS } from "../../labels/recovery";
import { formatNumber } from "../../utils/formatNumber";
import type {
  AcwrStatus,
  AcwrTrend,
  FormAnomalyFlagsResponse,
  HrvStatus,
  RecoveryTrend,
  RhrTrend,
} from "../../types";
import Sparkline from "./Sparkline";

/** Trailing points shown in each tile sparkline. */
const SPARK_POINTS = 8;

const ACWR_META: Record<AcwrStatus, { label: string; tone: StatusTone }> = {
  undertraining: { label: "負荷不足", tone: "info" },
  optimal: { label: "最適", tone: "good" },
  caution: { label: "注意", tone: "warn" },
  high_risk: { label: "高リスク", tone: "bad" },
  insufficient_data: { label: "データ不足", tone: "info" },
};

/** Tone per enum value; the wording comes from the shared label maps (#915). */
const HRV_TONE: Record<Exclude<HrvStatus, null>, StatusTone> = {
  balanced: "good",
  low: "warn",
  high: "info",
};

const RHR_TONE: Record<Exclude<RhrTrend, null>, StatusTone> = {
  improving: "good",
  stable: "info",
  fatigued: "warn",
};

interface SnapshotTilesProps {
  load: AcwrTrend | null;
  recovery: RecoveryTrend | null;
  flags: FormAnomalyFlagsResponse | null;
}

/**
 * Compact state row: training load (ACWR + weekly-km mini bars), HRV and RHR
 * (each its own single-series sparkline — never a dual-axis chart), and the
 * form-anomaly caution count. Every tile deep-links straight to its section on
 * `/condition` (the anchors the `/trends` split kept alive, #892) so the home
 * page never has to restate what that page already owns.
 */
export default function SnapshotTiles({
  load,
  recovery,
  flags,
}: SnapshotTilesProps) {
  return (
    <section aria-label="状態スナップショット">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <AcwrTile load={load} />
        <HrvTile recovery={recovery} />
        <RhrTile recovery={recovery} />
        <FlagsTile flags={flags} />
      </div>
    </section>
  );
}

function Tile({
  title,
  badge,
  to,
  children,
}: {
  title: string;
  badge: { label: string; tone: StatusTone } | null;
  to: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      to={to}
      className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-[box-shadow,border-color] hover:border-signal/50 hover:shadow-md focus-visible:ring-2 focus-visible:ring-signal/50 focus-visible:outline-none"
    >
      <div className="flex items-center justify-between gap-2">
        {/*
         * h2, matching every other card on the Home page (#912): as an h3 the
         * tiles claimed to be children of a section that does not exist, so the
         * outline jumped h1 → h3.
         */}
        <h2 className="text-xs font-semibold text-slate-500">{title}</h2>
        {badge != null && <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>}
      </div>
      {children}
    </Link>
  );
}

function BigValue({ value, unit }: { value: string; unit?: string }) {
  return (
    <p className="mt-1 font-numeric text-2xl font-semibold tabular-nums text-ink">
      {value}
      {unit != null && (
        <span className="ml-0.5 text-sm font-normal text-slate-500">{unit}</span>
      )}
    </p>
  );
}

function AcwrTile({ load }: { load: AcwrTrend | null }) {
  const current = load?.current ?? null;
  const insufficient =
    current == null ||
    current.status === "insufficient_data" ||
    current.acwr == null;
  const weeks = (load?.trend.weeks ?? []).slice(-SPARK_POINTS);

  return (
    <Tile
      title="訓練負荷 (ACWR)"
      badge={current != null ? ACWR_META[current.status] : null}
      to="/condition#training-load"
    >
      <BigValue value={insufficient ? "—" : formatNumber(current.acwr, 2)} />
      {weeks.length > 1 && (
        <Sparkline
          type="bar"
          data={weeks.map((w) => w.load_km)}
          labels={weeks.map((w) => w.week_start)}
          color={INK_COLOR}
          ariaLabel="週間走行距離ミニグラフ"
          decimals={1}
          unit=" km"
        />
      )}
      <p className="mt-1 text-[11px] text-slate-500">週間距離 直近{weeks.length}週</p>
    </Tile>
  );
}

function HrvTile({ recovery }: { recovery: RecoveryTrend | null }) {
  const hrv = recovery?.hrv ?? null;
  const badge =
    hrv?.under_recovery === true
      ? { label: "回復不足", tone: "bad" as StatusTone }
      : hrv?.status != null
        ? { label: HRV_STATUS_LABELS[hrv.status], tone: HRV_TONE[hrv.status] }
        : null;
  const series = (recovery?.series ?? []).slice(-SPARK_POINTS * 2);
  const values = series.map((p) => p.hrv_overnight_ms);

  return (
    <Tile title="HRV (夜間)" badge={badge} to="/condition#recovery">
      <BigValue
        value={hrv?.latest_ms != null ? formatNumber(hrv.latest_ms, 0) : "—"}
        unit="ms"
      />
      {values.some((v) => v != null) && (
        <Sparkline
          data={values}
          labels={series.map((p) => p.date)}
          color={METRIC_COLORS.hrv}
          ariaLabel="HRVミニグラフ"
          unit=" ms"
        />
      )}
      <p className="mt-1 text-[11px] text-slate-500">
        基準割れ {hrv?.hrv_below_baseline_days ?? 0}日連続
      </p>
    </Tile>
  );
}

function RhrTile({ recovery }: { recovery: RecoveryTrend | null }) {
  const rhr = recovery?.rhr ?? null;
  const series = (recovery?.series ?? []).slice(-SPARK_POINTS * 2);
  const values = series.map((p) => p.resting_hr);

  return (
    <Tile
      title="安静時心拍"
      badge={
        rhr?.rhr_trend != null
          ? {
              label: RHR_TREND_LABELS[rhr.rhr_trend],
              tone: RHR_TONE[rhr.rhr_trend],
            }
          : null
      }
      to="/condition#recovery"
    >
      <BigValue
        value={rhr?.median_7d != null ? formatNumber(rhr.median_7d, 0) : "—"}
        unit="bpm"
      />
      {values.some((v) => v != null) && (
        <Sparkline
          data={values}
          labels={series.map((p) => p.date)}
          color={METRIC_COLORS.heart_rate}
          ariaLabel="安静時心拍ミニグラフ"
          unit=" bpm"
        />
      )}
      <p className="mt-1 text-[11px] text-slate-500">7日中央値</p>
    </Tile>
  );
}

function FlagsTile({ flags }: { flags: FormAnomalyFlagsResponse | null }) {
  const count = flags?.flags.length ?? null;
  const badge =
    count == null
      ? null
      : count === 0
        ? { label: "問題なし", tone: "good" as StatusTone }
        : { label: `${count}件`, tone: "warn" as StatusTone };
  const top = flags?.flags[0]?.top_recommendation ?? null;

  return (
    <Tile title="フォーム注意点" badge={badge} to="/condition#form-anomaly">
      <BigValue value={count != null ? String(count) : "—"} unit="件" />
      <p className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-slate-500">
        {count === 0
          ? `直近${flags?.weeks ?? 2}週のランに異常なし`
          : (top ?? `直近${flags?.weeks ?? 2}週のフォーム異常検出`)}
      </p>
    </Tile>
  );
}
