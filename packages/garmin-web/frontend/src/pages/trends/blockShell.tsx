import type { JSX } from "react";

/**
 * The two things every `/performance` block shares (Morning Brief P3b, #1121).
 *
 * The blocks themselves no longer carry a card, a heading or a rule: they are
 * the content of a `SectionBlock`, which owns the title and the anchor. What
 * is left in common is the one mono line of numbers above the chart and the
 * sentence shown when there is nothing to plot.
 */

/** The mono summary line each block prints above its chart. */
export const BLOCK_SUMMARY_CLASS = "font-mono text-[13px] text-ink-soft";

/** Chart height on this page: tall enough to read a slope, short enough that
 *  nine of them stay scannable in one column (§Screens 5). */
export const CHART_HEIGHT = 180;

/** Why a block has no chart, in the block's own words. */
export function BlockEmpty({ message }: { message: string }): JSX.Element {
  return <p className="text-sm text-ink-muted">{message}</p>;
}
