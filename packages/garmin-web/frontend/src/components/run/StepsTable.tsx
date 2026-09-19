import type { RunFlowStep } from "../../types";
import {
  formatBpmValue,
  formatDistanceKmValue,
  formatPace,
  MISSING,
} from "../../utils/format";

const STEP_COLUMNS = [
  "区間",
  "KM",
  "時間",
  "ペース",
  "平均心拍",
  "最大心拍",
];

/**
 * "6:00", "1:04:30" — a step's elapsed time, minutes unpadded.
 *
 * `formatDuration` pads the minutes ("06:00"), which is right for a whole run
 * read against other runs but wrong in a column of two-minute rests.
 */
export function formatStepDuration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) {
    return MISSING;
  }
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const mmss = `${minutes}:${String(rest).padStart(2, "0")}`;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
    : mmss;
}

/**
 * The steps of a structured session, in the order it executed them (#1269).
 *
 * On a rep session the split table is the wrong unit to open with: one rep is
 * routinely recorded as two laps (a lap press a beat late), a rest covers
 * 0.18 km, and the reader asks "how did the reps go", not "what did lap 6
 * do". The steps are therefore the record, and the raw laps sit behind a
 * disclosure underneath.
 */
export default function StepsTable({ steps }: { steps: RunFlowStep[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] font-mono text-sm">
        <caption className="sr-only">区間ごとの距離・時間・ペース・心拍</caption>
        <thead>
          <tr className="border-b border-ink text-[11px] tracking-[0.04em] text-ink-muted">
            {STEP_COLUMNS.map((column, index) => (
              <th
                key={column}
                scope="col"
                className={`px-2 py-2 font-medium ${
                  index === 0 ? "text-left" : "text-right"
                }`}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {steps.map((step) => (
            <tr key={step.id} className="border-b border-hairline">
              <td className="px-2 py-2 text-left text-ink-muted">
                {step.label_ja}
              </td>
              <td className="px-2 py-2 text-right">
                {formatDistanceKmValue(step.distance_km)}
              </td>
              <td className="px-2 py-2 text-right">
                {formatStepDuration(step.duration_s)}
              </td>
              <td className="px-2 py-2 text-right">
                {formatPace(step.pace_s_per_km)}
              </td>
              <td className="px-2 py-2 text-right">
                {formatBpmValue(step.avg_hr)}
              </td>
              <td className="px-2 py-2 text-right">
                {formatBpmValue(step.max_hr)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
