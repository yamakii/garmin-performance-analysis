import type { JSX } from "react";

/** One choice: the value it selects and the word written on the button. */
export interface SegmentOption<T extends string> {
  value: T;
  label: string;
}

/**
 * The segmented control the brief uses for "which slice am I looking at"
 * (#1185).
 *
 * It is a hairline box of mono words, not a pill on a `bg-well` tray: the
 * selected segment inverts to ink-on-paper, the rest stay muted until hover.
 * `aria-pressed` carries the state, so the choice is announced rather than
 * inferred from the fill — the same reasoning as the verdict words (#912).
 *
 * `/performance` (week / month) and `/activities` (the range presets) render
 * the same control from here, so the two cannot drift apart again.
 */
export default function Segment<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Accessible name of the group, e.g. "集計単位". */
  ariaLabel: string;
}): JSX.Element {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex rounded-sm border border-hairline font-mono text-[13px]"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          className={
            value === option.value
              ? "cursor-pointer bg-ink px-3 py-1.5 text-paper"
              : "cursor-pointer px-3 py-1.5 text-ink-muted hover:text-ink"
          }
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
