import type { JSX } from "react";
import StatusBadge, { type StatusTone } from "../StatusBadge";
import type { Adherence } from "../../types";

/**
 * How much of what was prescribed actually happened, as one chip.
 *
 * The label counts against everything prescribed ("3/4 実施"), but the tone is
 * judged against the *resolved* sessions only: a week whose Sunday long run has
 * not happened yet is not failing, it is unfinished. Once nothing is pending,
 * the two denominators coincide.
 */
export function adherenceTone(adherence: Adherence): StatusTone {
  const resolved = adherence.prescribed - adherence.pending;
  if (adherence.prescribed === 0 || resolved <= 0) {
    return "info";
  }
  const ratio = adherence.done / resolved;
  if (ratio >= 0.8) {
    return "good";
  }
  return ratio >= 0.5 ? "warn" : "bad";
}

export default function AdherenceChip({
  adherence,
}: {
  adherence: Adherence;
}): JSX.Element {
  if (adherence.prescribed === 0) {
    return <StatusBadge tone="info">未処方</StatusBadge>;
  }
  return (
    <StatusBadge tone={adherenceTone(adherence)}>
      {adherence.done}/{adherence.prescribed} 実施
    </StatusBadge>
  );
}
