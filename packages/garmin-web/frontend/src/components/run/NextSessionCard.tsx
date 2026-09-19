import type { JSX, ReactNode } from "react";
import type { NextSession } from "../../types";

function asNumber(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** "2026-09-20" → "9/20"; anything unparseable is returned as-is. */
function monthDay(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (match == null) {
    return iso;
  }
  const [, , month, day] = match;
  return `${Number(month)}/${Number(day)}`;
}

/** "16" rather than "16.0" — a whole-kilometre target reads as a whole number. */
function kmValue(km: number): string {
  return Number.isInteger(km) ? String(km) : km.toFixed(1);
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs text-ink">
      <span className="text-ink-muted">{label}</span>
      <span>{value}</span>
    </span>
  );
}

/**
 * The session the athlete actually does next, under the challenge sentence.
 *
 * The card that used to sit here described the next run *of today's kind*
 * (`next_run_target`), which is a different question: on 2026-09-18 the note
 * coached the next easy run while what came next was a 16 km long run two days
 * later (#1267). This card states the scheduled session — when it is, what it
 * is, how far or how long, and the heart-rate ceiling as a guard.
 *
 * A dateless `same_type` session carries no more than `next_run_target`
 * already does, so the caller keeps showing that card instead.
 */
export default function NextSessionCard({
  session,
}: {
  session: NextSession;
}): JSX.Element {
  const date = session.date != null && session.date !== "" ? session.date : null;
  const daysAhead = asNumber(session.days_ahead);
  const when =
    date == null
      ? null
      : daysAhead != null
        ? `${monthDay(date)}（${daysAhead}日後）`
        : monthDay(date);

  const targetKm = asNumber(session.target_km);
  const targetMinutes = asNumber(session.target_minutes);
  const target =
    targetKm != null
      ? `${kmValue(targetKm)} km`
      : targetMinutes != null
        ? `${targetMinutes} 分`
        : null;

  const hrHigh = asNumber(session.hr_high);

  const chips: ReactNode[] = [];
  if (when != null) {
    chips.push(<Chip key="when" label="予定" value={when} />);
  }
  if (target != null) {
    chips.push(<Chip key="target" label="目標" value={target} />);
  }
  if (hrHigh != null) {
    chips.push(<Chip key="hr" label="心拍上限" value={`${hrHigh} bpm 以下`} />);
  }

  return (
    <div className="border-t border-hairline pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-mono text-xs text-ink-muted">次のセッション</h3>
        {session.session_label_ja !== "" && (
          <span className="rounded-sm bg-ink px-1.5 py-[3px] font-mono text-[11px] font-medium tracking-[0.04em] text-paper">
            {session.session_label_ja}
          </span>
        )}
      </div>
      {chips.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1">{chips}</div>
      )}
    </div>
  );
}
