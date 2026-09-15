import type { TopLevelFormatterParams } from "echarts/types/dist/shared";

/**
 * Round to at most `maxDecimals` places and strip trailing zeros.
 * null / undefined / NaN render as "-".
 *
 * Examples:
 *   formatNumber(4.2000000000001, 1) -> "4.2"
 *   formatNumber(12.0, 1)            -> "12"
 *   formatNumber(1.057, 2)           -> "1.06"
 *   formatNumber(null)               -> "-"
 */
export function formatNumber(
  value: number | null | undefined,
  maxDecimals = 1,
): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  // toFixed rounds; Number() drops trailing zeros and clears IEEE754 noise.
  return String(Number(value.toFixed(maxDecimals)));
}

/**
 * Signed fixed-decimal string for a delta, e.g. "-0.0015" / "+0.0012" /
 * "±0.0000". The sign is part of the formatter so a caller never writes one
 * into its template: a hard-coded "+" turns a negative delta into "+-0.0015"
 * (Issue #1147). Decimals are kept (not stripped) because a delta is read
 * against its siblings, which need the same width.
 * null / undefined / NaN render as "-", as in {@link formatNumber}.
 */
export function formatSigned(
  value: number | null | undefined,
  decimals = 1,
): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const magnitude = Math.abs(value).toFixed(decimals);
  // Compare the rounded magnitude, so a value that rounds away (and -0) reads
  // as "no change" rather than carrying a sign the digits do not show.
  const sign = Number(magnitude) === 0 ? "±" : value > 0 ? "+" : "-";
  return `${sign}${magnitude}`;
}

/**
 * ECharts axis-tooltip formatter. Maps a series name to its decimal
 * precision; series not in the map fall back to `fallback`.
 * Preserves the default marker (param.marker) and axis label
 * (axisValueLabel) so the tooltip keeps ECharts' native look.
 */
export function axisTooltipFormatter(
  precisionBySeries: Record<string, number> = {},
  fallback = 1,
): (params: TopLevelFormatterParams) => string {
  return (params) => {
    const list = Array.isArray(params) ? params : [params];
    const header = (list[0] as { axisValueLabel?: string })?.axisValueLabel ?? "";
    const rows = list
      .map((p) => {
        const param = p as {
          seriesName?: string;
          marker?: string;
          value?: unknown;
        };
        const name = param.seriesName ?? "";
        // value may be a number or a [x, y] pair (PhysiologyBlock's LT心拍).
        const raw = Array.isArray(param.value)
          ? param.value[param.value.length - 1]
          : param.value;
        const num = typeof raw === "number" ? raw : null;
        const prec = precisionBySeries[name] ?? fallback;
        return `${param.marker ?? ""}${name}: <b>${formatNumber(num, prec)}</b>`;
      })
      .join("<br/>");
    return header ? `${header}<br/>${rows}` : rows;
  };
}
