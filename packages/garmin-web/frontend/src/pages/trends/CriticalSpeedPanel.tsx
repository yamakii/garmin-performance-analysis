import type { CriticalSpeedPoint } from "../../api/trends";
import { formatPace } from "../../utils/format";
import { BLOCK_SUMMARY_CLASS, BlockEmpty } from "./blockShell";

interface CriticalSpeedPanelProps {
  data: CriticalSpeedPoint[];
}

/** The caveat every fitted row carries; shown even when there are no rows. */
function fitCaveat(data: CriticalSpeedPoint[]): string {
  return data[0]?.label ?? "threshold-anchored (no short/long max effort)";
}

/** "2026-Q2 CS 5:53/km · R² 0.9998 · n 4" — the latest quarter's fit. */
export function criticalSpeedSummaryLine(data: CriticalSpeedPoint[]): string {
  const latest = data[data.length - 1] ?? null;
  if (latest == null) {
    return "";
  }
  return [
    `${latest.quarter} CS ${formatPace(latest.cs_pace_sec_per_km)}`,
    `R² ${latest.r_squared.toFixed(4)}`,
    `n ${latest.n}`,
  ].join(" · ");
}

export default function CriticalSpeedPanel({ data }: CriticalSpeedPanelProps) {
  return (
    <div className="flex flex-col gap-3">
      <p className={BLOCK_SUMMARY_CLASS}>{criticalSpeedSummaryLine(data)}</p>
      <p className="font-mono text-xs text-status-warn">
        {fitCaveat(data)} — LT速度プロキシとして提示（無酸素容量は解釈不可）
      </p>
      {data.length === 0 ? (
        <BlockEmpty message="データがありません" />
      ) : (
        <table className="w-full font-mono text-sm">
          <thead>
            <tr className="border-b border-ink text-left text-xs text-ink-muted">
              <th scope="col" className="py-2 font-medium">
                四半期
              </th>
              <th scope="col" className="py-2 font-medium">
                CSペース
              </th>
              <th scope="col" className="py-2 font-medium">
                R²
              </th>
              <th scope="col" className="py-2 font-medium">
                n
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.quarter} className="border-b border-hairline">
                <td className="py-2">{row.quarter}</td>
                <td className="py-2">{formatPace(row.cs_pace_sec_per_km)}</td>
                <td className="py-2">{row.r_squared.toFixed(4)}</td>
                <td className="py-2">{row.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
