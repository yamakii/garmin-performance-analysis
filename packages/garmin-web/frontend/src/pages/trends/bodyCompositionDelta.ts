import type { BodyCompositionSeriesPoint } from "../../types";

export interface BodyCompositionDeltas {
  weight: (number | null)[];
  fat: (number | null)[];
  lean: (number | null)[];
}

/**
 * Each metric expressed as the change (kg, 1 decimal) from its first
 * non-null reading in the window (Issue #1167).
 *
 * A 12-week ~2kg weight drop reads as a near-flat line on an absolute
 * 50-90kg axis (the body's own mass dwarfs the movement the chart exists to
 * show). Plotting the change from the window's own baseline instead puts
 * every series on the same 0-anchored scale, so the slope carries the story.
 * null stays null: a metric with no reading yet has no delta either.
 */
export function toDeltaSeries(
  series: BodyCompositionSeriesPoint[],
): BodyCompositionDeltas {
  return {
    weight: deltaFrom(series.map((point) => point.weight_kg)),
    fat: deltaFrom(series.map((point) => point.fat_mass)),
    lean: deltaFrom(series.map((point) => point.lean_mass)),
  };
}

/** `values` minus the first non-null entry, rounded to 1 decimal. */
function deltaFrom(values: (number | null)[]): (number | null)[] {
  const baseline = values.find(
    (value): value is number => value != null,
  );
  if (baseline == null) {
    return values.map(() => null);
  }
  return values.map((value) =>
    value == null ? null : round1(value - baseline),
  );
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}
