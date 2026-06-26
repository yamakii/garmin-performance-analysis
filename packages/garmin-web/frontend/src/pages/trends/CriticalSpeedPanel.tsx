import type { CriticalSpeedPoint } from "../../api/trends";

interface CriticalSpeedPanelProps {
  data: CriticalSpeedPoint[];
}

function formatPace(secondsPerKm: number): string {
  const total = Math.round(secondsPerKm);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}/km`;
}

export default function CriticalSpeedPanel({ data }: CriticalSpeedPanelProps) {
  const isEmpty = data.length === 0;
  // Surface the threshold-anchored caveat from the fit (all rows share it).
  const caveat = data[0]?.label ?? "threshold-anchored (no short/long max effort)";

  return (
    <section
      aria-label="クリティカルスピード"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-1 font-display text-base font-semibold text-ink">
        クリティカルスピード (四半期)
      </h2>
      <p className="mb-3 text-xs text-amber-700">
        {caveat} — LT速度プロキシとして提示（無酸素容量は解釈不可）
      </p>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          データがありません
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="py-1 font-medium">四半期</th>
              <th className="py-1 font-medium">CSペース</th>
              <th className="py-1 font-medium">R²</th>
              <th className="py-1 font-medium">n</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.quarter} className="border-t border-slate-100">
                <td className="py-1">{row.quarter}</td>
                <td className="py-1">{formatPace(row.cs_pace_sec_per_km)}</td>
                <td className="py-1">{row.r_squared.toFixed(4)}</td>
                <td className="py-1">{row.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
