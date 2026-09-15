import type { WellnessBaselineDeviation } from "../../types";
import { formatNumber } from "../../utils/formatNumber";
import { baselineZRows, zBarStyle, type ZRow } from "../../utils/baselineZ";

interface WellnessBaselineChartProps {
  data: WellnessBaselineDeviation;
}

/**
 * 個人基準との差: how far HRV, resting HR and readiness sit from the personal
 * baseline, as one bar per metric hanging off a centre line.
 *
 * The three boxed cards this replaces restated mean, σ and today's value for
 * each metric — nine numbers to answer one question. A bar chart of z scores
 * answers it in a glance, and the polarity is normalised so every bar to the
 * right of the line is the unfavourable direction, whichever way the metric
 * itself reads (#1120).
 */
export default function WellnessBaselineChart({
  data,
}: WellnessBaselineChartProps) {
  const rows = baselineZRows(data);

  return (
    <div className="flex flex-col gap-4">
      {data.overall_flag && (
        <p
          role="alert"
          className="rounded-md border border-warn-line bg-warn-tint px-4 py-3 text-sm text-status-warn"
        >
          個人ベースラインから不利な方向に逸脱しています。強度・回復を見直してください。
        </p>
      )}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <ZBar key={row.key} row={row} />
        ))}
      </ul>
      <p className="font-mono text-xs leading-[1.6] text-ink-muted">
        基準 = 直近 28 日の中央値 ± MAD。|z| &gt; 1.5 を「基準外」とする。
      </p>
    </div>
  );
}

function ZBar({ row }: { row: ZRow }) {
  const style = zBarStyle(row);
  return (
    <li className="grid grid-cols-[110px_1fr_90px] items-center gap-3">
      <span className="text-[13px] text-ink-soft">{row.label}</span>
      <span className="relative block h-2.5 bg-well">
        {/* The centre line is the baseline itself: left of it is favourable. */}
        <span className="absolute inset-y-0 left-1/2 w-px bg-ink" />
        <span
          className={`absolute inset-y-0 ${
            row.outside ? "bg-status-warn" : "bg-ink"
          }`}
          style={style}
        />
      </span>
      <span
        className={`text-right font-mono text-xs ${
          row.outside ? "font-bold text-status-warn" : "text-ink-muted"
        }`}
      >
        {row.z != null ? `z ${formatNumber(row.z, 2)}` : "データ不足"}
      </span>
    </li>
  );
}
